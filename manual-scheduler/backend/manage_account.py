"""Create/change the shared account; changing it revokes every existing session."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import main
import auth

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('login',nargs='?',default='admin')
    parser.add_argument('--generate',action='store_true',help='Write a generated password to an owner-only local credentials file')
    args=parser.parse_args()
    if args.generate:
        output=Path(__file__).with_name('admin.credentials')
        password=secrets.token_urlsafe(18)
        # Never overwrite an existing credentials file silently.
        fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            auth.configure_account(args.login,password)
            with os.fdopen(fd,'w') as file:
                file.write(f'Логин: {args.login}\nПароль: {password}\n')
        except Exception:
            output.unlink(missing_ok=True)
            raise
        print('Учётная запись создана. Данные для входа:',output)
    else:
        password=getpass.getpass('Новый общий пароль (минимум 12 символов): ')
        if password!=getpass.getpass('Повторите пароль: '):
            raise SystemExit('Пароли не совпадают')
        auth.configure_account(args.login,password)
        print('Общий аккаунт сохранён. Все старые сеансы завершены.')
