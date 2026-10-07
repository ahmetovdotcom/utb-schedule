from pathlib import Path
import sqlite3
import tempfile
import unittest
from io import BytesIO
from openpyxl import load_workbook
from fastapi.testclient import TestClient
import main
import auth
from excel_export import build_workbook
from online import parse_location


class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = main.DB
        main.DB = Path(self.tmp.name)/'test.sqlite'
        auth.configure_account('admin', 'test-password-123')
        self.client = TestClient(main.app)
        self.client.post('/api/auth/login', json={'login':'admin','password':'test-password-123'})
        self.client.post('/api/demo')
        self.state = self.client.get('/api/state').json()
        self.base = dict(self.state['lessons'][0], day=2, delivery='online', meeting_id='9028766192', passcode='DD57YJ')

    def tearDown(self):
        self.client.close()
        main.DB = self.old
        self.tmp.cleanup()

    def test_create_conflicts_options_and_switch(self):
        response = self.client.post('/api/lessons', json=self.base)
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['warnings'], [])
        current = next(l for l in self.client.get('/api/state').json()['lessons'] if l['id']==response.json()['id'])
        self.assertIsNone(current['room_id'])
        other_teacher = next(r['id'] for r in self.state['references'] if r['kind']=='teachers' and r['id']!=current['teacher_id'])
        other_group = next(r['id'] for r in self.state['references'] if r['kind']=='groups' and r['id'] not in current['group_ids'])
        second = dict(self.base, teacher_id=other_teacher, group_ids=[other_group])
        self.assertEqual(self.client.post('/api/lessons',json=second).status_code,201)
        for fields in ({}, {'teacher_id':other_teacher}, {'group_ids':[other_group]}, {'delivery':'in_person'}):
            self.assertEqual(self.client.post('/api/lessons',json=dict(self.base,**fields)).status_code,409)
        options = self.client.post('/api/options',json=second).json()
        self.assertEqual(len(options),13)
        self.assertTrue(all(o['room_id'] is None for o in options))
        changed = dict(current, delivery='in_person', room_id=self.base['room_id'], accept_warnings=True, expected_version=current['version'])
        self.assertEqual(self.client.put('/api/lessons/'+str(current['id']),json=changed).status_code,200)
        updated = next(l for l in self.client.get('/api/state').json()['lessons'] if l['id']==current['id'])
        self.assertEqual(updated['meeting_id'],'')
        self.assertEqual(updated['passcode'],'')
        self.assertNotEqual(updated['version'],current['version'])
        self.assertEqual(self.client.put('/api/lessons/'+str(current['id']),json=changed).status_code,409)

    def test_validation_and_excel(self):
        for fields in ({'meeting_id':''}, {'online_url':'javascript:alert(1)'}, {'online_url':'https://user:pass@example.com'}):
            self.assertEqual(self.client.post('/api/lessons',json=dict(self.base,**fields)).status_code,422)
        row = dict(self.base, online_url='https://example.com/join')
        with main.database() as con:
            refs = main.refs(con)
        course = refs[row['group_ids'][0]]['course']
        book = load_workbook(BytesIO(build_workbook(course,refs,[row])))
        strings = [str(c.value) for sheet in book for cells in sheet for c in cells]
        self.assertTrue(any('Онлайн\nhttps://example.com/join\nID: 9028766192\nКод: DD57YJ'==s for s in strings))

    def test_legacy_migration_preserves_links_and_versions(self):
        old = Path(self.tmp.name)/'legacy.sqlite'
        con = sqlite3.connect(old)
        con.executescript('''CREATE TABLE refs(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,data TEXT NOT NULL, version TEXT NOT NULL);
        INSERT INTO refs VALUES(1,'teachers','T','{}','a'),(2,'subjects','S','{}','b'),(3,'rooms','R','{}','c'),(4,'groups','G','{}','d');
        CREATE TABLE lessons(id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES refs(id), subject_id INTEGER NOT NULL REFERENCES refs(id), room_id INTEGER NOT NULL REFERENCES refs(id), day INTEGER NOT NULL,slot INTEGER NOT NULL,lesson_type TEXT NOT NULL,version TEXT NOT NULL);
        INSERT INTO lessons VALUES(7,1,2,3,1,8,'lecture','original');
        CREATE TABLE lesson_groups(lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,group_id INTEGER NOT NULL REFERENCES refs(id),PRIMARY KEY(lesson_id,group_id));
        INSERT INTO lesson_groups VALUES(7,4);''')
        con.close()
        main.DB = old
        for _ in range(2):
            with main.database() as con:
                row = main.lessons(con)[0]
                self.assertEqual((row['id'],row['version'],row['group_ids']), (7,'original',[4]))
                self.assertEqual(row['delivery'],'in_person')
                self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(con.execute('PRAGMA foreign_keys').fetchone()[0],1)
        with main.database(True) as con:
            con.execute("UPDATE lessons SET room_id=NULL,delivery='online',meeting_id='123456789' WHERE id=7")
            self.assertNotEqual(con.execute('SELECT version FROM lessons').fetchone()[0],'original')

    def test_parse_remote_details(self):
        for value in ('9028766192, код: DD57YJ','902 876 6192\nКод доступа DD57YJ'):
            parsed = parse_location(value)
            self.assertEqual(parsed['meeting_id'],'9028766192')
            self.assertEqual(parsed['passcode'],'DD57YJ')
        self.assertEqual(parse_location('https://example.com/j/1?pwd=x\nКод: 001')['passcode'],'001')
        for value in ('с/з','1/302','Онлайн','https://example.com непонятная приписка'):
            self.assertIsNone(parse_location(value))
