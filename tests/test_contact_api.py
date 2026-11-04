"""Contact HTTP boundary tests; all model work is a test-only adapter."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from app.contact import ContactService


class ContactApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import app.main as api
        self.tmp=tempfile.TemporaryDirectory()
        async def chat(owner,text,**kw):
            return {'text':'test-only reply','events':[]}
        fake=SimpleNamespace(chat=chat,actions=SimpleNamespace(pending=Mock(return_value=None),invalidate_pending=Mock()),
                             _session=lambda _:SimpleNamespace(lock=asyncio.Lock()),_plan=lambda *_:None)
        self.contact=ContactService(fake,Path(self.tmp.name)/'contact.db')
        self.patch=patch.object(api,'contact',self.contact);self.patch.start()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://localhost')
        await self.client.get('/api/health')

    async def asyncTearDown(self):
        await self.contact.close()
        await self.client.aclose()
        self.patch.stop();self.tmp.cleanup()

    async def test_acceptance_precedes_execution_and_foreign_cookie_cannot_read_messages(self):
        body={'text':'test-only private fragment','client_id':'contact-api-0001'}
        first=await self.client.post('/api/contact/messages',json=body)
        self.assertEqual(first.status_code,202)
        duplicate=await self.client.post('/api/contact/messages',json=body)
        self.assertEqual(first.json(),duplicate.json())
        state=(await self.client.get('/api/contact/state')).json()
        self.assertEqual(state['pending'],1)
        self.assertEqual([e['type'] for e in state['events']],['accepted'])
        self.client.cookies.clear()
        foreign=(await self.client.get('/api/contact/state')).json()
        self.assertEqual(foreign['events'],[])

    async def test_cross_origin_and_invalid_input_are_rejected(self):
        path='/api/contact/messages'
        body={'text':'test','client_id':'contact-api-0001'}
        self.assertEqual((await self.client.post(path,json=body,headers={'Origin':'https://foreign.invalid'})).status_code,403)
        self.assertEqual((await self.client.post(path,json={**body,'text':'   '})).status_code,400)
        self.assertEqual((await self.client.post(path,json={**body,'client_id':'../invalid'})).status_code,422)
        self.assertEqual((await self.client.post(path,content='not-json')).status_code,415)
