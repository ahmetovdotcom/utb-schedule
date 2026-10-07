import asyncio
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import main, auth

class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(setattr,main,'DB',main.DB)
        main.DB=Path(self.temp.name)/'db.sqlite'
        auth.configure_account('admin','shared-password-123')
        self.a=TestClient(main.app);self.b=TestClient(main.app)
        for client in (self.a,self.b):
            response=client.post('/api/auth/login',json={'login':'admin','password':'shared-password-123'})
            self.assertEqual(response.status_code,200)
            self.assertIn('HttpOnly',response.headers['set-cookie'])
        self.a.post('/api/demo')

    def test_auth_protects_data_and_logout_is_per_browser(self):
        anon=TestClient(main.app)
        for url in ['/api/state','/api/events','/api/export.xlsx?course=2']:
            self.assertEqual(anon.get(url).status_code,401)
        self.assertEqual(anon.post('/api/demo').status_code,401)
        self.a.post('/api/auth/logout')
        self.assertEqual(self.a.get('/api/state').status_code,401)
        self.assertEqual(self.b.get('/api/state').status_code,200)
        auth.configure_account('admin','changed-password-123')
        self.assertEqual(self.b.get('/api/state').status_code,401)

    def test_stale_update_and_delete_do_not_overwrite(self):
        state=self.a.get('/api/state').json();row=state['lessons'][0]
        payload={**row,'expected_version':row['version'],'slot':10}
        self.assertEqual(self.a.put('/api/lessons/'+str(row['id']),json=payload).status_code,200)
        self.assertEqual(self.b.put('/api/lessons/'+str(row['id']),json={**payload,'slot':11}).status_code,409)
        self.assertEqual(self.b.delete('/api/lessons/'+str(row['id']),params={'expected_version':row['version']}).status_code,409)
        after=self.b.get('/api/state').json()
        self.assertEqual(after['lessons'][0]['slot'],10)
        self.assertGreater(after['revision'],state['revision'])
        self.assertNotEqual(after['lessons'][0]['version'],row['version'])
        self.assertEqual(self.a.put('/api/lessons/'+str(row['id']),json={k:v for k,v in payload.items() if k!='expected_version'}).status_code,428)

    def test_failed_login_throttle(self):
        client=TestClient(main.app)
        for _ in range(10):self.assertEqual(client.post('/api/auth/login',json={'login':'admin','password':'bad'}).status_code,401)
        self.assertEqual(client.post('/api/auth/login',json={'login':'admin','password':'bad'}).status_code,429)

    def test_events_follow_commits_and_revocation(self):
        token=self.b.cookies.get(auth.COOKIE)
        class Request:
            cookies={auth.COOKIE:token}
            async def is_disconnected(self):return False
        async def run():
            stream=main.event_stream(Request())
            initial=await anext(stream)
            self.assertIn('event: changed',initial)
            # Change through the same transaction used by HTTP, visible across connections.
            main.add_reference('subjects',main.Reference(name='Новый предмет'))
            changed=await asyncio.wait_for(anext(stream),2)
            self.assertIn('event: changed',changed)
            self.assertNotEqual(initial,changed)
            auth.configure_account('admin','changed-password-123')
            self.assertIn('event: expired',await asyncio.wait_for(anext(stream),2))
            await stream.aclose()
        asyncio.run(run())

if __name__=='__main__':unittest.main()
