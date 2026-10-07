"""Presentation and validation for remote lessons (no network requests)."""
from urllib.parse import urlsplit


def validate_url(value):
    value = value.strip()
    if value:
        try:
            url = urlsplit(value)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or any(c.isspace() for c in value):
                raise ValueError()
        except ValueError:
            raise ValueError('Укажите ссылку http:// или https:// без пробелов') from None
    return value


def online_label(lesson, include_url=True):
    parts = ['Онлайн']
    if include_url and lesson.get('online_url'):
        parts.append(lesson['online_url'])
    if lesson.get('meeting_id'):
        parts.append('ID: ' + lesson['meeting_id'])
    if lesson.get('passcode'):
        parts.append('Код: ' + lesson['passcode'])
    return '\n'.join(parts)


def migrate(con):
    """Make room optional without changing IDs, links or optimistic versions."""
    columns = {r['name']: r for r in con.execute('PRAGMA table_info(lessons)')}
    if columns['room_id']['notnull']:
        con.execute('PRAGMA foreign_keys=OFF')
        try:
            con.execute('BEGIN IMMEDIATE')
            columns = {r['name']: r for r in con.execute('PRAGMA table_info(lessons)')}
            if columns['room_id']['notnull']:
                con.execute('''CREATE TABLE lessons_online_migration (
                  id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES refs(id),
                  subject_id INTEGER NOT NULL REFERENCES refs(id), room_id INTEGER REFERENCES refs(id),
                  day INTEGER NOT NULL, slot INTEGER NOT NULL, lesson_type TEXT NOT NULL,
                  version TEXT NOT NULL DEFAULT '')''')
                version = 'version' if 'version' in columns else "''"
                con.execute(f'INSERT INTO lessons_online_migration SELECT id,teacher_id,subject_id,room_id,day,slot,lesson_type,{version} FROM lessons')
                con.execute('DROP TABLE lessons')
                con.execute('ALTER TABLE lessons_online_migration RENAME TO lessons')
                if con.execute('PRAGMA foreign_key_check').fetchone():
                    raise RuntimeError('Ошибка связей при обновлении базы')
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.execute('PRAGMA foreign_keys=ON')


def parse_location(value):
    """Recognize explicit conference details; ambiguous text remains unresolved."""
    import re
    text = value.strip()
    url = ''
    match = re.search(r'https?://[^\s]+', text, re.I)
    if match:
        url = match[0]
        try:
            validate_url(url)
        except ValueError:
            return None
        text = text[:match.start()] + text[match.end():]
    code = re.search(r'код(?:\s+доступа)?\s*:?\s*([\w-]+)', text, re.I)
    passcode = code[1] if code else ''
    if code:
        text = text[:code.start()] + text[code.end():]
    text = re.sub(r'^(?:zoom|идентификатор(?:\s+конференции)?|id)\s*:?\s*', '', text.strip(), flags=re.I)
    text = text.strip(' ,;\n\t')
    meeting_id = re.sub(r'\s+', '', text)
    if meeting_id and not re.fullmatch(r'\d{9,13}', meeting_id):
        return None
    if not url and not meeting_id:
        return None
    return dict(delivery='online', room_id=None, online_url=url, meeting_id=meeting_id, passcode=passcode)
