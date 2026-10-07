"""End-to-end manual-scheduler → UTB2, isolated SQLite databases only."""
import asyncio
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import main
import auth
import publication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'UTB2/backend'))
KEY = 'test-only-publication-secret-key-123456'
with patch.dict(os.environ, {'POSTGRES_USER':'test','POSTGRES_PASSWORD':'test',
    'POSTGRES_HOST':'localhost','POSTGRES_PORT':'5432','POSTGRES_DB':'test','PUBLISH_SECRET_KEY':KEY}):
    from app.main import app as student_app
    from app.core.database import Base, get_db
    from app.models.models import Group, Schedule, PublicationState, PublishedGroupLink, ManualPublicationSource
from app.core.config import settings


class PublicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(setattr, main, 'DB', main.DB)
        main.DB = Path(self.temp.name)/'manual.db'
        auth.configure_account('admin','test-password-123')
        self.staff = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://manual')
        await self.staff.post('/api/auth/login',json={'login':'admin','password':'test-password-123'})
        await self.staff.post('/api/demo')
        self.engine = create_async_engine(f'sqlite+aiosqlite:///{self.temp.name}/students.db')
        @event.listens_for(self.engine.sync_engine,'connect')
        def fks(connection,_):connection.execute('PRAGMA foreign_keys=ON')
        async with self.engine.begin() as con:await con.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine,expire_on_commit=False)
        async def db():
            async with self.sessions() as s:yield s
        student_app.dependency_overrides[get_db]=db
        self.addCleanup(student_app.dependency_overrides.clear)
        self.students=httpx.AsyncClient(transport=httpx.ASGITransport(app=student_app),base_url='http://localhost')
        self.env=patch.dict(os.environ,{'STUDENT_PUBLISH_URL':'http://localhost/api/v1/manual-publication','PUBLISH_SECRET_KEY':KEY})
        self.env.start();self.addCleanup(self.env.stop)
        self.key=patch.object(settings,'PUBLISH_SECRET_KEY',KEY);self.key.start();self.addCleanup(self.key.stop)
        real_send,real_client=publication.send_publication,httpx.AsyncClient
        async def send(url,key,payload):
            def local_client(**kwargs):return real_client(transport=httpx.ASGITransport(app=student_app),**kwargs)
            with patch.object(publication.httpx,'AsyncClient',local_client):return await real_send(url,key,payload)
        self.sender=patch.object(publication,'send_publication',send);self.sender.start();self.addCleanup(self.sender.stop)
        self.headers={'Authorization':f'Bearer {KEY}'}

    async def asyncTearDown(self):
        await self.staff.aclose();await self.students.aclose();await self.engine.dispose()

    async def publish(self):
        response=await self.staff.post('/api/publication')
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    async def test_online_publication_retains_connection_details(self):
        row=(await self.staff.get('/api/state')).json()['lessons'][0]
        data=dict(row,delivery='online',online_url='https://example.com/join',meeting_id='123456789',passcode='001',expected_version=row['version'])
        response=await self.staff.put('/api/lessons/'+str(row['id']),json=data)
        self.assertEqual(response.status_code,200,response.text)
        await self.publish()
        groups=(await self.students.get('/api/v1/groups')).json()
        found=[]
        for group in groups:
            found.extend((await self.students.get(f"/api/v1/schedules/{group['id']}?day=1")).json())
        self.assertTrue(found)
        teacher=(await self.students.get(f"/api/v1/teachers/{row['teacher_id']}/schedule?day=1")).json()
        for lesson in found+teacher:
            for key in ('delivery','online_url','meeting_id','passcode'):
                self.assertEqual(lesson[key],data[key])

    async def test_handover_streams_drafts_stable_ids_and_removal(self):
        old_source=str(uuid4())
        async with self.sessions() as s:
            s.add(Group(id=80,title='БТ-241'));await s.flush()
            s.add(PublishedGroupLink(source_id=str(uuid4()),group_id=80))
            s.add(Schedule(group_id=80,day_of_week=1,time='08:00-08:50',subject='Old',room='Old'))
            s.add(PublicationState(id=1,source_id=old_source,revision=999,published_at='2026-01-01T00:00:00+00:00',payload_hash='old',groups_count=1,lessons_count=1))
            await s.commit()
        state=(await self.staff.get('/api/state')).json()
        row=state['lessons'][0];groups=[r for r in state['references'] if r['kind']=='groups']
        subject=next(r for r in state['references'] if r['id']==row['subject_id'])
        long_name='Предмет '+('длинное название '*22)
        self.assertEqual((await self.staff.put('/api/references/'+str(subject['id']),json={**subject,'name':long_name,'expected_version':subject['version']})).status_code,200)
        self.assertEqual((await self.staff.put('/api/lessons/'+str(row['id']),json={**row,'group_ids':[g['id'] for g in groups],'accept_warnings':True,'expected_version':row['version']})).status_code,200)
        result=await self.publish()
        self.assertEqual(result['lessons_count'],2)
        self.assertEqual(result['revision'],1)  # independent sequence after legacy rev 999
        public_groups=(await self.students.get('/api/v1/groups')).json()
        self.assertEqual(next(g['id'] for g in public_groups if g['title']=='БТ-241'),80)
        for group in public_groups:
            lesson=(await self.students.get(f"/api/v1/schedules/{group['id']}?day=1")).json()[0]
            self.assertEqual(lesson['time'],'09:00-09:50');self.assertEqual(lesson['subject'],long_name.strip())
            self.assertEqual(lesson['room'],'Главный корпус · 110')
        teacher=(await self.students.get(f"/api/v1/teachers/{row['teacher_id']}/schedule?day=1")).json()
        self.assertEqual(len(teacher),1);self.assertEqual(len(teacher[0]['groups']),2)
        self.assertFalse((await self.staff.get('/api/publication')).json()['dirty'])
        group=next(g for g in groups if g['name']=='БТ-241')
        await self.staff.put('/api/references/'+str(group['id']),json={**group,'name':'Переименована','expected_version':group['version']})
        self.assertTrue((await self.staff.get('/api/publication')).json()['dirty'])
        self.assertEqual((await self.students.get('/api/v1/groups')).json(),public_groups)
        await self.publish()
        self.assertEqual(next(g['id'] for g in (await self.students.get('/api/v1/groups')).json() if g['title']=='Переименована'),80)
        current=(await self.staff.get('/api/state')).json()['lessons'][0]
        await self.staff.delete('/api/lessons/'+str(current['id']),params={'expected_version':current['version']})
        self.assertTrue((await self.students.get('/api/v1/schedules/80?day=1')).json())
        await self.publish()
        self.assertEqual((await self.students.get('/api/v1/schedules/80?day=1')).json(),[])
        self.assertEqual((await self.students.get(f"/api/v1/teachers/{row['teacher_id']}/schedule?day=1")).json(),[])

    async def test_auth_legacy_block_replay_sources_out_of_order_and_rollback(self):
        with TestClient(main.app) as anonymous:
            self.assertEqual(anonymous.post('/api/publication').status_code,401)
        payload=publication.prepare()
        self.assertEqual((await self.students.post('/api/v1/publication',json=payload,headers=self.headers)).status_code,410)
        self.assertEqual((await self.students.post('/api/v1/manual-publication',json=payload)).status_code,401)
        async def failing_commit(_):raise RuntimeError('test rollback')
        with patch.object(AsyncSession,'commit',failing_commit):
            with self.assertRaises(RuntimeError):
                await self.students.post('/api/v1/manual-publication',json=payload,headers=self.headers)
        async with self.sessions() as s:self.assertIsNone(await s.get(ManualPublicationSource,1))
        async def deliver(value):return await self.students.post('/api/v1/manual-publication',json=value,headers=self.headers)
        self.assertEqual((await deliver(payload)).status_code,200)
        self.assertEqual((await deliver(payload)).status_code,200)
        changed=deepcopy(payload);changed['groups'][0]['title']='Changed'
        self.assertEqual((await deliver(changed)).status_code,409)
        other=deepcopy(payload);other['source_id']=str(uuid4())
        self.assertEqual((await deliver(other)).status_code,409)
        newer=publication.prepare();older=deepcopy(newer);older['revision']+=10;newer['revision']+=11
        results=await asyncio.gather(deliver(newer),deliver(older))
        self.assertTrue(all(r.status_code in (200,409) for r in results))
        self.assertEqual((await self.students.get('/api/v1/publication')).json()['revision'],newer['revision'])
        before=(await self.students.get('/api/v1/groups')).json()
        bad=deepcopy(newer);bad['revision']+=1;bad['groups']=[];bad['teachers']=[]
        with patch.object(AsyncSession,'commit',failing_commit):
            with self.assertRaises(RuntimeError):await deliver(bad)
        self.assertEqual((await self.students.get('/api/v1/groups')).json(),before)

    async def test_connection_failure_receipt_and_consistent_snapshot(self):
        await self.publish()
        before=(await self.students.get('/api/v1/groups')).json()
        async def offline(*_):raise httpx.ConnectError('offline')
        with patch.object(publication,'send_publication',offline):
            self.assertEqual((await self.staff.post('/api/publication')).status_code,502)
        self.assertEqual((await self.students.get('/api/v1/groups')).json(),before)
        self.assertEqual((await self.staff.get('/api/publication')).json()['last_status'],'unconfirmed')
        real=publication.send_publication
        async def edit_during_delivery(url,key,payload):
            main.add_reference('groups',main.Reference(name='Новая группа'))
            return await real(url,key,payload)
        with patch.object(publication,'send_publication',edit_during_delivery):await self.publish()
        self.assertEqual((await self.students.get('/api/v1/groups')).json(),before)
        self.assertTrue((await self.staff.get('/api/publication')).json()['dirty'])
        await self.publish()
        self.assertEqual(len((await self.students.get('/api/v1/groups')).json()),3)
        with patch.dict(os.environ,{'STUDENT_PUBLISH_URL':''}):
            self.assertEqual((await self.staff.post('/api/publication')).status_code,503)

    def test_contract_and_safe_destinations(self):
        self.assertEqual((ROOT/'UTB2/backend/app/schemas/publication.py').read_bytes(),Path(publication.__file__).with_name('publication_schema.py').read_bytes())
        for url,internal,allowed in [('https://okak.asia/api/v1/manual-publication','false',True),
             ('http://student-api:8000/api/v1/manual-publication','true',True),
             ('http://student-api:8000/api/v1/manual-publication','false',False),
             ('http://external.test/api/v1/manual-publication','true',False),
             ('http://localhost/api/v1/publication','false',False),
             ('https://secret:key@host/api/v1/manual-publication','false',False)]:
            with patch.dict(os.environ,{'STUDENT_PUBLISH_URL':url,'STUDENT_PUBLISH_ALLOW_INTERNAL_HTTP':internal}):
                if allowed:self.assertEqual(publication.destination()[0],url)
                else:
                    from fastapi import HTTPException
                    with self.assertRaises(HTTPException):publication.destination()

if __name__=='__main__':unittest.main()
