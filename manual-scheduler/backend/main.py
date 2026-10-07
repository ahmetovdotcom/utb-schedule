from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import asyncio
import time
import auth
import publication
from analytics import router as analytics_router
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal

DB = Path(os.environ.get('SCHEDULER_DB', Path(__file__).with_name('schedule.db')))
app = FastAPI(title='Расписание · ручной редактор', dependencies=[Depends(auth.require_session)])
# Authentication endpoints live in a separate public sub-application.
auth_app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
auth_app.include_router(auth.router)
app.mount('/api/auth', auth_app)
TYPES = {'classroom': 'Учебная аудитория', 'lecture_hall': 'Лекционная', 'laboratory': 'Лаборатория', 'computer_class': 'Компьютерный класс', 'special': 'Спецкабинет', 'other': 'Не для занятий'}
DAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

@contextmanager
def database(write=False):
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS refs (
      id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
      data TEXT NOT NULL, UNIQUE(kind, name));
    CREATE TABLE IF NOT EXISTS lessons (
      id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES refs(id),
      subject_id INTEGER NOT NULL REFERENCES refs(id), room_id INTEGER NOT NULL REFERENCES refs(id),
      day INTEGER NOT NULL, slot INTEGER NOT NULL, lesson_type TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS lesson_groups (
      lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
      group_id INTEGER NOT NULL REFERENCES refs(id), PRIMARY KEY(lesson_id, group_id));
    ''')
    con.executescript(auth.SCHEMA)
    con.executescript(publication.SCHEMA)
    try:
        con.execute('BEGIN IMMEDIATE')
        for table in ('refs','lessons'):
            if 'version' not in {r[1] for r in con.execute('PRAGMA table_info('+table+')')}:
                con.execute('ALTER TABLE '+table+" ADD COLUMN version TEXT NOT NULL DEFAULT ''")
                con.execute('UPDATE '+table+' SET version=lower(hex(randomblob(16)))')
        con.execute('CREATE TABLE IF NOT EXISTS change_revision(id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)')
        con.execute('INSERT OR IGNORE INTO change_revision VALUES(1,0)')
        for table in ('refs','lessons','lesson_groups'):
            for action in ('INSERT','UPDATE','DELETE'):
                con.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_{action}_revision AFTER {action} ON {table} BEGIN UPDATE change_revision SET value=value+1 WHERE id=1; END')
        for table in ('refs','lessons'):
            con.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_insert_version AFTER INSERT ON {table} BEGIN UPDATE {table} SET version=lower(hex(randomblob(16))) WHERE id=new.id; END')
            con.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_update_version AFTER UPDATE ON {table} WHEN new.version=old.version BEGIN UPDATE {table} SET version=lower(hex(randomblob(16))) WHERE id=new.id; END')
        con.commit()
        con.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

auth.database = database

class Reference(BaseModel):
    expected_version: str | None = None
    name: str = Field(min_length=1, max_length=512)
    department: str = Field(default='', max_length=512)
    capacity: int = Field(default=30, ge=1, le=5000)
    students: int = Field(default=20, ge=1, le=5000)
    course: int = Field(default=1, ge=0, le=8)
    building: str = Field(default='Главный корпус', max_length=100)
    room_type: Literal['classroom', 'lecture_hall', 'laboratory', 'computer_class', 'special', 'other'] = 'classroom'

class Lesson(BaseModel):
    teacher_id: int
    subject_id: int
    room_id: int
    group_ids: list[int] = Field(min_length=1)
    day: int = Field(ge=1, le=6)
    slot: int = Field(ge=8, le=20)
    lesson_type: Literal['lecture', 'practice', 'lab'] = 'practice'

class SaveLesson(Lesson):
    accept_warnings: bool = False
    expected_version: str | None = None


def refs(con):
    return {r['id']: {'id': r['id'], 'kind': r['kind'], 'name': r['name'], **json.loads(r['data']), 'version': r['version']} for r in con.execute('SELECT * FROM refs ORDER BY name')}


def lessons(con):
    groups = {}
    for row in con.execute('SELECT * FROM lesson_groups'):
        groups.setdefault(row['lesson_id'], []).append(row['group_id'])
    return [{**dict(r), 'group_ids': groups.get(r['id'], [])} for r in con.execute('SELECT * FROM lessons ORDER BY day,slot,id')]


def check(value, all_refs, all_lessons, exclude=None):
    for key, kind in [('teacher_id', 'teachers'), ('subject_id', 'subjects'), ('room_id', 'rooms')]:
        if all_refs.get(getattr(value, key), {}).get('kind') != kind:
            raise HTTPException(422, 'Выберите существующие предмет, преподавателя и кабинет')
    if len(set(value.group_ids)) != len(value.group_ids) or any(all_refs.get(g, {}).get('kind') != 'groups' for g in value.group_ids):
        raise HTTPException(422, 'Проверьте выбранные группы')
    conflicts = []
    for row in all_lessons:
        if row['id'] == exclude or row['day'] != value.day or row['slot'] != value.slot:
            continue
        reasons = []
        if row['teacher_id'] == value.teacher_id: reasons.append('Преподаватель занят')
        if row['room_id'] == value.room_id: reasons.append('Кабинет занят')
        if set(row['group_ids']) & set(value.group_ids): reasons.append('Группа занята')
        if reasons:
            conflicts.append({'lesson_id': row['id'], 'message': ', '.join(reasons), 'room': all_refs[row['room_id']]['name'], 'groups': [all_refs[g]['name'] for g in row['group_ids']]})
    room, teacher = all_refs[value.room_id], all_refs[value.teacher_id]
    students = sum(all_refs[g]['students'] for g in value.group_ids)
    warnings = []
    if students > room['capacity']:
        warnings.append(f"В группе / потоке {students} студентов, в кабинете {room['capacity']} мест")
    allowed = {'lecture': ['lecture_hall', 'classroom'], 'practice': ['classroom', 'lecture_hall', 'computer_class'], 'lab': ['laboratory', 'computer_class', 'special']}
    if room['room_type'] not in allowed[value.lesson_type]:
        warnings.append('Тип кабинета не соответствует занятию')
    if room['room_type'] in ['laboratory', 'computer_class', 'special'] and room['department'] and teacher['department'] and room['department'] != teacher['department']:
        warnings.append(f"Кабинет закреплён за другой кафедрой: {room['department']}")
    return {'conflicts': conflicts, 'warnings': warnings}

def ensure_version(row, expected):
    if expected is None:
        raise HTTPException(428,'Обновите страницу перед сохранением')
    if row['version'] != expected:
        raise HTTPException(409,'Запись уже изменена другим сотрудником. Откройте её заново; ваши изменения не сохранены.')


def event_snapshot(token):
    with database() as con:
        valid=con.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires>?',(auth.token_hash(token),time.time())).fetchone()
        revision=con.execute('SELECT value FROM change_revision WHERE id=1').fetchone()[0]
        stamp=tuple(tuple(r) for r in con.execute('SELECT id,status FROM publications ORDER BY id DESC LIMIT 5'))
        return bool(valid), revision, stamp


async def event_stream(request):
    token=request.cookies.get(auth.COOKIE,'')
    previous=None
    heartbeat=0
    while not await request.is_disconnected():
        valid,revision,stamp=await asyncio.to_thread(event_snapshot,token)
        if not valid:
            yield 'event: expired\ndata: {}\n\n'
            return
        if previous!=(revision,stamp):
            yield f'id: {revision}\nevent: changed\ndata: {{"revision":{revision}}}\n\n'
            previous=(revision,stamp)
        elif heartbeat%20==0:
            yield ': heartbeat\n\n'
        heartbeat+=1
        await asyncio.sleep(0.5)


@app.get('/api/events')
async def events(request: Request):
    return StreamingResponse(event_stream(request),media_type='text/event-stream',headers={'Cache-Control':'no-cache, no-transform','X-Accel-Buffering':'no'})


@app.get('/api/state')
def state():
    with database() as con:
        all_refs = refs(con)
        rows = lessons(con)
        for row in rows:
            row['warnings'] = check(Lesson(**row), all_refs, [])['warnings']
        return {'references': list(all_refs.values()), 'lessons': rows, 'days': DAYS, 'room_types': TYPES, 'publication': publication.status_in(con), 'revision': con.execute('SELECT value FROM change_revision WHERE id=1').fetchone()[0]}

@app.post('/api/references/{kind}', status_code=201)
def add_reference(kind: Literal['rooms', 'groups', 'teachers', 'subjects', 'buildings', 'departments'], value: Reference):
    data = value.model_dump(exclude={'expected_version'})
    name = data.pop('name').strip()
    if not name: raise HTTPException(422, 'Введите название')
    with database(True) as con:
        try:
            row = con.execute('INSERT INTO refs(kind,name,data) VALUES(?,?,?)', (kind, name, json.dumps(data)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Такое название уже существует')
        return {'id': row.lastrowid}

@app.put('/api/references/{ref_id}')
def update_reference(ref_id: int, value: Reference):
    data = value.model_dump(exclude={'expected_version'})
    name = data.pop('name').strip()
    if not name: raise HTTPException(422, 'Введите название')
    with database(True) as con:
        previous = con.execute('SELECT * FROM refs WHERE id=?', (ref_id,)).fetchone()
        if not previous:
            raise HTTPException(404, 'Запись не найдена')
        ensure_version(previous, value.expected_version)
        try:
            con.execute('UPDATE refs SET name=?,data=? WHERE id=?', (name,json.dumps({**json.loads(previous['data']), **data}),ref_id))
            if previous['kind'] in ('departments', 'buildings'):
                field = 'department' if previous['kind']=='departments' else 'building'
                for row in con.execute("SELECT id,data FROM refs WHERE kind IN ('rooms','teachers','groups')").fetchall():
                    linked = json.loads(row['data'])
                    if linked.get(field)==previous['name']:
                        linked[field]=name
                        con.execute('UPDATE refs SET data=? WHERE id=?', (json.dumps(linked),row['id']))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Такое название уже существует')
    return {'ok': True}

@app.delete('/api/references/{ref_id}')
def delete_reference(ref_id: int, expected_version: str = Query()):
    with database(True) as con:
        previous = con.execute('SELECT * FROM refs WHERE id=?', (ref_id,)).fetchone()
        if not previous: raise HTTPException(404, 'Запись уже удалена')
        ensure_version(previous, expected_version)
        if previous and previous['kind'] in ('departments', 'buildings'):
            field = 'department' if previous['kind']=='departments' else 'building'
            if any(json.loads(r['data']).get(field)==previous['name'] for r in con.execute("SELECT data FROM refs WHERE kind IN ('rooms','teachers','groups')")):
                raise HTTPException(409, 'Запись используется в справочниках')
        try:
            con.execute('DELETE FROM refs WHERE id=?', (ref_id,))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Запись используется в расписании')
    return {'ok': True}

@app.post('/api/options')
def options(value: Lesson, exclude: int | None = None):
    with database() as con:
        all_refs, all_lessons = refs(con), lessons(con)
        result = []
        for room in all_refs.values():
            if room['kind'] != 'rooms': continue
            for hour in range(8, 21):
                candidate = value.model_copy(update={'room_id': room['id'], 'slot': hour})
                result.append({'room_id': room['id'], 'slot': hour, **check(candidate, all_refs, all_lessons, exclude)})
        return result


def save(value, lesson_id=None):
    with database(True) as con:
        if lesson_id is not None:
            previous=con.execute('SELECT * FROM lessons WHERE id=?',(lesson_id,)).fetchone()
            if not previous: raise HTTPException(404, 'Занятие уже удалено')
            ensure_version(previous,value.expected_version)
        result = check(value, refs(con), lessons(con), lesson_id)
        if result['conflicts']:
            raise HTTPException(409, result)
        if result['warnings'] and not value.accept_warnings:
            raise HTTPException(409, result)
        params = (value.teacher_id, value.subject_id, value.room_id, value.day, value.slot, value.lesson_type)
        if lesson_id is None:
            lesson_id = con.execute('INSERT INTO lessons(teacher_id,subject_id,room_id,day,slot,lesson_type) VALUES(?,?,?,?,?,?)', params).lastrowid
        else:
            con.execute('UPDATE lessons SET teacher_id=?,subject_id=?,room_id=?,day=?,slot=?,lesson_type=? WHERE id=?', (*params, lesson_id))
            con.execute('DELETE FROM lesson_groups WHERE lesson_id=?', (lesson_id,))
        con.executemany('INSERT INTO lesson_groups VALUES(?,?)', [(lesson_id,g) for g in value.group_ids])
        return {'id': lesson_id, **result}

@app.post('/api/lessons', status_code=201)
def create_lesson(value: SaveLesson):
    return save(value)

@app.put('/api/lessons/{lesson_id}')
def update_lesson(lesson_id: int, value: SaveLesson):
    return save(value, lesson_id)

@app.delete('/api/lessons/{lesson_id}')
def delete_lesson(lesson_id: int, expected_version: str = Query()):
    with database(True) as con:
        previous=con.execute('SELECT * FROM lessons WHERE id=?',(lesson_id,)).fetchone()
        if not previous: raise HTTPException(404,'Занятие уже удалено')
        ensure_version(previous,expected_version)
        con.execute('DELETE FROM lessons WHERE id=?', (lesson_id,))
    return {'ok': True}

@app.get('/api/export.xlsx')
def export(course: int = Query(ge=0, le=8)):
    from excel_export import build_workbook
    from fastapi.responses import Response
    with database() as con:
        all_refs, all_lessons = refs(con), lessons(con)
    try:
        content = build_workbook(course, all_refs, all_lessons)
    except ValueError as error:
        raise HTTPException(404 if str(error) == 'Для этого курса нет групп' else 422, str(error)) from error
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="course-{course}.xlsx"', 'Cache-Control': 'no-store'})

@app.post('/api/demo')
def demo():
    with database(True) as con:
        if con.execute('SELECT 1 FROM refs LIMIT 1').fetchone():
            raise HTTPException(409, 'Пример можно загрузить только в пустую базу')
        def add(kind, name, **kw):
            data = Reference(name=name, **kw).model_dump(); data.pop('name')
            return con.execute('INSERT INTO refs(kind,name,data) VALUES(?,?,?)', (kind,name,json.dumps(data))).lastrowid
        r1 = add('rooms','106',capacity=24); r2 = add('rooms','110',capacity=20,room_type='laboratory',department='Химия')
        add('rooms','202',capacity=60,room_type='lecture_hall'); add('rooms','213',capacity=18,room_type='computer_class',department='Информатика')
        t1 = add('teachers','Аубакирова А. К.',department='Химия'); add('teachers','Серикова М. А.',department='Информатика')
        s1 = add('subjects','Химия'); add('subjects','Информатика'); add('subjects','Математика')
        g1 = add('groups','БТ-241',students=18,course=2,department='Химия'); add('groups','БТ-242',students=22,course=2,department='Химия')
        lid = con.execute('INSERT INTO lessons(teacher_id,subject_id,room_id,day,slot,lesson_type) VALUES(?,?,?,?,?,?)',(t1,s1,r2,1,9,'lab')).lastrowid
        con.execute('INSERT INTO lesson_groups VALUES(?,?)',(lid,g1))
    return {'ok': True}


def validate_publication_lesson(row, references, rows):
    result = check(Lesson(**row), references, rows, row['id'])
    if result['conflicts']:
        raise HTTPException(409, 'Исправьте пересечения в расписании перед публикацией')

publication.database = database
publication.read_refs = refs
publication.read_lessons = lessons
publication.validate_lesson = validate_publication_lesson
app.include_router(publication.router)

app.include_router(analytics_router)
