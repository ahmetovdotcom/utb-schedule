"""Persist a complete manual-scheduler snapshot before delivering it to UTB2."""
from datetime import datetime, timezone
import json
from online import online_label
import os
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from publication_schema import PublicationPayload

router = APIRouter(prefix='/api/publication')
# Bound by main after the database helpers have been defined.
database = read_refs = read_lessons = validate_lesson = None
SCHEMA = '''
CREATE TABLE IF NOT EXISTS publication_source(id INTEGER PRIMARY KEY CHECK(id=1), source_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS publication_groups(ref_id INTEGER PRIMARY KEY REFERENCES refs(id) ON DELETE CASCADE, source_id TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS publications(id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, draft_revision INTEGER NOT NULL, status TEXT NOT NULL);
'''


def destination():
    url = os.getenv('STUDENT_PUBLISH_URL', '').strip()
    key = os.getenv('PUBLISH_SECRET_KEY', '')
    try:
        parsed = urlsplit(url)
        local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
        internal = (os.getenv('STUDENT_PUBLISH_ALLOW_INTERNAL_HTTP') == 'true'
                    and parsed.hostname == 'student-api' and parsed.port == 8000)
        valid = (len(key) >= 32 and parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment and parsed.path == '/api/v1/manual-publication'
                 and (parsed.scheme == 'https' or (parsed.scheme == 'http' and (local or internal))))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(503, 'Публикация не настроена. Укажите STUDENT_PUBLISH_URL и PUBLISH_SECRET_KEY на сервере manual-scheduler.')
    return url, key


def status_in(con):
    try:
        destination()
        configured = True
    except HTTPException:
        configured = False
    last = con.execute("SELECT * FROM publications WHERE status='confirmed' ORDER BY id DESC LIMIT 1").fetchone()
    latest = con.execute('SELECT id,status FROM publications ORDER BY id DESC LIMIT 1').fetchone()
    payload = json.loads(last['payload']) if last else None
    revision = con.execute('SELECT value FROM change_revision WHERE id=1').fetchone()[0]
    return {'configured': configured, 'published_at': payload['published_at'] if payload else None,
            'revision': last['id'] if last else None,
            'dirty': not last or last['draft_revision'] != revision,
            'last_status': latest['status'] if latest else None}


@router.get('')
def status():
    with database() as con:
        return status_in(con)


def snapshot(con):
    references, rows = read_refs(con), read_lessons(con)
    con.execute('INSERT OR IGNORE INTO publication_source VALUES(1,?)', (str(uuid4()),))
    source = con.execute('SELECT source_id FROM publication_source WHERE id=1').fetchone()[0]
    groups, teachers = {}, {}
    for ref in references.values():
        if ref['kind'] == 'groups':
            con.execute('INSERT OR IGNORE INTO publication_groups VALUES(?,?)', (ref['id'], str(uuid4())))
            key = con.execute('SELECT source_id FROM publication_groups WHERE ref_id=?', (ref['id'],)).fetchone()[0]
            groups[ref['id']] = {'source_id': key, 'title': ref['name'], 'lessons': []}
        elif ref['kind'] == 'teachers':
            teachers[ref['id']] = {'id': ref['id'], 'title': ref['name'], 'lessons': []}
    for row in rows:
        validate_lesson(row, references, rows)
        if row.get('delivery') == 'online':
            room_title = online_label(row, include_url=False)
        else:
            room = references[row['room_id']]
            building = room.get('building', '').strip()
            room_title = room['name']
            if building and not room_title.startswith((building+' / ', building+' · ')):
                room_title = f'{building} · {room_title}'
        lesson = {'day_of_week': row['day'], 'time': f"{row['slot']:02d}:00-{row['slot']:02d}:50",
                  'subject': references[row['subject_id']]['name'], 'room': room_title}
        lesson.update({key: row.get(key, 'in_person' if key == 'delivery' else '') for key in ('delivery','online_url','meeting_id','passcode')})
        for group_id in row['group_ids']:
            groups[group_id]['lessons'].append(lesson.copy())
        teachers[row['teacher_id']]['lessons'].append({**lesson, 'id': row['id'],
            'groups': [groups[g]['title'] for g in row['group_ids']]})
    return source, list(groups.values()), list(teachers.values())


def prepare():
    with database(True) as con:
        source, groups, teachers = snapshot(con)
        draft_revision = con.execute('SELECT value FROM change_revision WHERE id=1').fetchone()[0]
        revision = con.execute("INSERT INTO publications(payload,draft_revision,status) VALUES('{}',?,'pending')", (draft_revision,)).lastrowid
        try:
            payload = PublicationPayload(source_id=source, revision=revision,
                published_at=datetime.now(timezone.utc), groups=groups, teachers=teachers).model_dump(mode='json')
        except ValidationError as error:
            first = error.errors()[0]
            raise HTTPException(409, f"Проверьте данные публикации ({'.'.join(map(str, first['loc']))}): {first['msg']}") from error
        con.execute('UPDATE publications SET payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), revision))
    return payload


async def send_publication(url, key, payload):
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.post(url, json=payload, headers={'Authorization': f'Bearer {key}'})
        response.raise_for_status()
        receipt = response.json()
        if (not isinstance(receipt, dict) or receipt.get('published') is not True
                or receipt.get('source_id') != payload['source_id'] or receipt.get('revision') != payload['revision']):
            raise ValueError('Invalid publication receipt')
        return receipt


@router.post('')
async def publish():
    from starlette.concurrency import run_in_threadpool
    url, key = destination()
    payload = await run_in_threadpool(prepare)
    def mark(value):
        with database(True) as con:
            con.execute('UPDATE publications SET status=? WHERE id=?', (value, payload['revision']))
    try:
        receipt = await send_publication(url, key, payload)
    except (httpx.HTTPError, ValueError) as error:
        await run_in_threadpool(mark, 'unconfirmed')
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403):
            raise HTTPException(502, 'UTB2 отклонил ключ публикации. Проверьте настройки обоих серверов.') from error
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 409:
            raise HTTPException(409, 'UTB2 уже получил более новую версию или подключён к другой базе manual-scheduler. Обновите страницу и проверьте настройки.') from error
        raise HTTPException(502, 'UTB2 не подтвердил получение расписания. Проверьте соединение и повторите публикацию.') from error
    await run_in_threadpool(mark, 'confirmed')
    return receipt
