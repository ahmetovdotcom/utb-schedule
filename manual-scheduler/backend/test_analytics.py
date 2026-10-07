import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
import main
import analytics
import test_publication as setup
from app.routers.analytics import UsageEvent

class AnalyticsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = setup.PublicationTests.asyncSetUp
    asyncTearDown = setup.PublicationTests.asyncTearDown
    publish = setup.PublicationTests.publish

    async def report(self, days=7):
        real_client = httpx.AsyncClient
        def client(**kwargs):
            return real_client(transport=httpx.ASGITransport(app=setup.student_app), **kwargs)
        with patch.object(analytics.httpx, 'AsyncClient', client):
            return await self.staff.get('/api/analytics', params={'days':days})

    async def test_reporting_access_and_empty_days(self):
        with TestClient(main.app) as anon:
            self.assertEqual(anon.get('/api/analytics').status_code,401)
        self.assertEqual((await self.students.get('/api/v1/analytics/summary')).status_code,401)
        self.assertEqual((await self.staff.get('/api/analytics?days=181')).status_code,422)
        response = await self.report()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        data = response.json()
        self.assertEqual(data['totals']['visitors'],0)
        self.assertEqual(len(data['daily']),7)
        self.assertIsNone(data['first_event_at'])
        self.assertNotIn(setup.KEY,response.text)

    async def test_visitors_visits_views_and_deduplication(self):
        await self.publish()
        groups = (await self.students.get('/api/v1/groups')).json()
        visitor, visit = str(uuid4()),str(uuid4())
        event = dict(id=str(uuid4()),visitor=visitor,visit=visit,kind='open',mode='student',device='phone',browser='Safari')
        async def record(data):
            result=await self.students.post('/api/v1/analytics/events',json=data)
            self.assertEqual(result.status_code,204,result.text)
        await record(event);await record(event)
        await record({**event,'id':str(uuid4()),'kind':'schedule','target_id':groups[0]['id']})
        await record({**event,'id':str(uuid4()),'visit':str(uuid4())})
        await record({**event,'id':str(uuid4()),'visitor':str(uuid4()),'visit':str(uuid4()),'device':'desktop'})
        data=(await self.report()).json()
        self.assertEqual(data['totals'],dict(visitors=2,visits=3,opens=3,schedule_views=1,errors=0,active=2,returning=1))
        self.assertEqual(sum(row['visits'] for row in data['daily']),3)
        self.assertEqual(data['groups'][0]['name'],groups[0]['title'])
        self.assertEqual(data['groups'][0]['count'],1)
        self.assertEqual(data['devices'][0],{'name':'phone','count':2})
        async with self.sessions() as db:
            rows=(await db.scalars(select(UsageEvent))).all()
            self.assertEqual(len(rows),4)
            self.assertTrue(all(row.visitor!=visitor and row.visit!=visit for row in rows))

    async def test_proxy_connection_failure_is_not_empty_report(self):
        def offline(request):raise httpx.ConnectError('offline',request=request)
        real_client=httpx.AsyncClient
        with patch.object(analytics.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(offline),**kw)):
            response=await self.staff.get('/api/analytics')
        self.assertEqual(response.status_code,502)
        self.assertNotIn(setup.KEY,response.text)

if __name__=='__main__':unittest.main()
