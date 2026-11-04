"""Image upload ownership, decoding and real media propagation; no cloud calls."""
import asyncio
import base64
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

import httpx
from PIL import Image
from app.agent import AgentError
from app.attachments import ImageStore
from app.contact import ContactService
from app.contact_events import contact_media


def test_image():
    data=io.BytesIO();Image.new('RGB',(30,20),'red').save(data,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(data.getvalue()).decode()


class AttachmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.images=ImageStore(self.root/'images');self.media=[]
        async def chat(*args,**kwargs):
            self.media.append(contact_media.get())
            return {'text':'test-only','events':[]}
        self.agent=SimpleNamespace(chat=chat,actions=SimpleNamespace(pending=Mock(return_value=None),invalidate_pending=Mock()),
            _session=lambda _:SimpleNamespace(lock=asyncio.Lock()),_plan=lambda *_:None)
        self.contact=ContactService(self.agent,self.root/'contact.db',self.images)

    async def asyncTearDown(self):
        await self.contact.close();self.tmp.cleanup()

    async def test_images_are_reencoded_and_foreign_owner_cannot_read_or_send(self):
        image=self.images.save('a',test_image());path=self.images.resolve('a',image['id'])
        with Image.open(path) as decoded:
            self.assertEqual(decoded.format,'JPEG');self.assertEqual(decoded.size,(30,20))
        self.assertNotIn('path',image)
        with self.assertRaises(AgentError):self.images.resolve('b',image['id'])
        with self.assertRaises(AgentError):self.contact.enqueue('b','图片','image-test-1',[image['id']])
        self.contact.enqueue('a','请看图片','image-test-2',[image['id']])
        await self.contact.workers['a']
        self.assertEqual(self.media,[[path]])
        state=self.contact.state('a');accepted=state['events'][0]
        self.assertEqual(accepted['images'],[image])
        self.assertIsNone(contact_media.get())

    async def test_invalid_or_unsupported_images_are_rejected(self):
        for value in ['data:image/png;base64,%%%%','data:image/svg+xml;base64,PHN2Zz4=',
                      'data:image/png;base64,'+base64.b64encode(b'not an image').decode()]:
            with self.assertRaises(AgentError):self.images.save('a',value)

    async def test_image_message_cannot_carry_a_host_confirmation(self):
        image=self.images.save('a',test_image())
        self.contact.enqueue('a','确认下单','image-test-3',[image['id']])
        await self.contact.workers['a']
        self.agent.actions.pending.assert_not_called()
        self.agent.actions.invalidate_pending.assert_called()

    async def test_http_upload_is_owned_and_has_no_cross_origin_access(self):
        import app.main as api
        with patch.object(api,'images',self.images):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://localhost') as client:
                await client.get('/api/health')
                result=await client.post('/api/contact/images',json={'data_url':test_image()})
                self.assertEqual(result.status_code,201)
                url=result.json()['url']
                own=await client.get(url)
                self.assertEqual(own.status_code,200)
                self.assertEqual(own.headers['content-type'],'image/jpeg')
                self.assertEqual((await client.post('/api/contact/images',json={'data_url':test_image()},headers={'Origin':'https://foreign.invalid'})).status_code,403)
                client.cookies.clear()
                self.assertEqual((await client.get(url)).status_code,404)
