from pathlib import Path
import sqlite3
import tempfile
import unittest
import main
import auth
from import_timetable import import_records
from fastapi.testclient import TestClient

class ImportTests(unittest.TestCase):
    def test_preserves_ids_duplicates_and_repeat_import(self):
        with tempfile.TemporaryDirectory() as temp:
            self.addCleanup(setattr,main,'DB',main.DB)
            main.DB=Path(temp)/'target.sqlite'
            source=Path(temp)/'source.sqlite'
            with sqlite3.connect(source) as con:
                con.executescript('''
                CREATE TABLE departments(id INTEGER,name TEXT);
                CREATE TABLE buildings(id INTEGER,name TEXT);
                CREATE TABLE rooms(id INTEGER,number TEXT,capacity INTEGER,building_id INTEGER,department_id INTEGER,room_type TEXT);
                CREATE TABLE teachers(id INTEGER,full_name TEXT,department_id INTEGER);
                CREATE TABLE student_groups(id INTEGER,code TEXT,students_count INTEGER,course INTEGER,department_id INTEGER);
                CREATE TABLE subjects(id INTEGER,name TEXT);
                INSERT INTO departments VALUES(1,'Химия');
                INSERT INTO buildings VALUES(1,'А'),(2,'Б');
                INSERT INTO rooms VALUES(1,'101',30,1,1,'classroom'),(2,'101',20,2,1,'other');
                INSERT INTO teachers VALUES(1,'Преподаватель',1);
                INSERT INTO student_groups VALUES(1,'Г-1',20,1,1),(2,'Г-1',25,0,1);
                INSERT INTO subjects VALUES(1,'Химия');
                ''')
            auth.configure_account('admin','test-password-12345')
            client=TestClient(main.app)
            client.post('/api/auth/login',json={'login':'admin','password':'test-password-12345'})
            client.post('/api/demo')
            before=client.get('/api/state').json()
            source_bytes=source.read_bytes()
            result=import_records(source)
            self.assertTrue(Path(result['backup']).exists())
            first=client.get('/api/state').json()
            self.assertEqual(before['lessons'],first['lessons'])
            self.assertEqual(import_records(source)['created'],0)
            second=client.get('/api/state').json()
            self.assertEqual([{k:v for k,v in r.items() if k!='version'} for r in first['references']],[{k:v for k,v in r.items() if k!='version'} for r in second['references']])
            imported_current=second['references']
            self.assertEqual(source_bytes,source.read_bytes())
            imported=[r for r in first['references'] if r.get('source')=='timetable-system']
            self.assertEqual(len(imported),9)
            self.assertEqual({r['name'] for r in imported if r['kind']=='rooms'},{'А / 101','Б / 101'})
            self.assertEqual({r['course'] for r in imported if r['kind']=='groups'},{0,1})
            dept=next(r for r in imported_current if r['kind']=='departments')
            self.assertEqual(client.delete('/api/references/'+str(dept['id']),params={'expected_version':dept['version']}).status_code,409)
            self.assertEqual(client.put('/api/references/'+str(dept['id']),json={'name':'Новая кафедра','expected_version':dept['version']}).status_code,200)
            rows=client.get('/api/state').json()['references']
            self.assertTrue(all(r['department']=='Новая кафедра' for r in rows if r.get('source')=='timetable-system' and r['kind'] in ['rooms','teachers','groups']))

if __name__=='__main__':unittest.main()
