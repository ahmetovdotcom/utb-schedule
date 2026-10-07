"""Shared account, independent revocable browser sessions, and login throttling."""
import hashlib
import hmac
import secrets
import time
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

COOKIE = 'scheduler_session'
SESSION_SECONDS = 12 * 60 * 60
router = APIRouter()
# Supplied by main, so tests and CLI use the same configured database.
database = None

SCHEMA = '''
CREATE TABLE IF NOT EXISTS shared_account(id INTEGER PRIMARY KEY CHECK(id=1), login TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT PRIMARY KEY, attempts INTEGER NOT NULL, started REAL NOT NULL);
'''


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def configure_account(login, password):
    if not login.strip() or len(password) < 12 or len(password) > 256:
        raise ValueError('Укажите логин и пароль длиной от 12 до 256 символов')
    salt = secrets.token_hex(16)
    hashed = password_hash(password, salt)
    with database(True) as con:
        con.execute('INSERT OR REPLACE INTO shared_account VALUES(1,?,?,?)', (login.strip(),salt,hashed))
        con.execute('DELETE FROM sessions')
        con.execute('DELETE FROM login_attempts')


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def valid_session(token):
    if not token or len(token)>200:return False
    with database() as con:
        return bool(con.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires>?',(token_hash(token),time.time())).fetchone())


def require_session(request: Request):
    if not valid_session(request.cookies.get(COOKIE)):
        raise HTTPException(401, 'Войдите в общий аккаунт')


class Login(BaseModel):
    login: str = Field(min_length=1,max_length=120)
    password: str = Field(min_length=1,max_length=256)


@router.get('/me')
def me(request: Request):
    require_session(request)
    with database() as con:
        row=con.execute('SELECT login FROM shared_account WHERE id=1').fetchone()
        return {'login':row['login']}


@router.post('/login')
def login(value: Login, request: Request, response: Response):
    ip=request.client.host if request.client else 'unknown'
    now=time.time()
    # Persist failed attempts by committing before returning a failure.
    with database(True) as con:
        row=con.execute('SELECT * FROM login_attempts WHERE ip=?',(ip,)).fetchone()
        if row and now-row['started']<300 and row['attempts']>=10:
            raise HTTPException(429,'Слишком много попыток. Повторите через 5 минут.')
        account=con.execute('SELECT * FROM shared_account WHERE id=1').fetchone()
        salt=account['salt'] if account else '00'*16
        hashed=password_hash(value.password,salt)
        correct=bool(account and hmac.compare_digest(value.login.encode(),account['login'].encode()) and hmac.compare_digest(hashed,account['password_hash']))
        if correct:
            token=secrets.token_urlsafe(32)
            con.execute('DELETE FROM sessions WHERE expires<=?',(now,))
            con.execute('INSERT INTO sessions VALUES(?,?)',(token_hash(token),now+SESSION_SECONDS))
            con.execute('DELETE FROM login_attempts WHERE ip=?',(ip,))
        else:
            if not row or now-row['started']>=300:
                con.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,1,?)',(ip,now))
            else:
                con.execute('UPDATE login_attempts SET attempts=attempts+1 WHERE ip=?',(ip,))
    if not correct:raise HTTPException(401,'Неверный логин или пароль')
    response.set_cookie(COOKIE,token,max_age=SESSION_SECONDS,httponly=True,samesite='strict',secure=os.environ.get('COOKIE_SECURE','false').lower()=='true',path='/')
    return {'login':value.login}


@router.post('/logout')
def logout(request: Request, response: Response):
    token=request.cookies.get(COOKIE,'')
    with database(True) as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash(token),))
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}
