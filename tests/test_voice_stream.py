"""Progressive audio delivery and private one-use tickets; no live speech API."""
import asyncio
import base64
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from app import voice


class ProgressiveAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_chunk_does_not_wait_for_provider_completion_and_close_releases_stream(self):
        gate=asyncio.Event()
        class Chunks(httpx.AsyncByteStream):
            closed=False
            async def __aiter__(self):
                yield (json.dumps({'code':0,'data':base64.b64encode(b'first-audio').decode()})+'\n').encode()
                await gate.wait()
                yield b'{"code":20000000}\n'
            async def aclose(self):
                self.closed=True
        upstream=Chunks()
        def handler(request):
            return httpx.Response(200,stream=upstream)
        original=httpx.AsyncClient
        cfg={'key':'test-only','tts_resource':'test-only','voice':'test-only'}
        with patch('app.voice.httpx.AsyncClient',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs)):
            stream=voice.speech_audio('合成测试文字',cfg)
            first=await asyncio.wait_for(anext(stream),1)
            self.assertEqual(first,b'first-audio')
            self.assertFalse(gate.is_set())
            await stream.aclose()
            self.assertTrue(upstream.closed)

    async def test_truncated_provider_audio_is_not_reported_as_success(self):
        def handler(request):
            return httpx.Response(200,content=b'{"code":0,"data":"YXVkaW8="}\n')
        original=httpx.AsyncClient
        cfg={'key':'test-only','tts_resource':'test-only','voice':'test-only'}
        with patch('app.voice.httpx.AsyncClient',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs)):
            with self.assertRaises(ValueError):
                _=[chunk async for chunk in voice.speech_audio('测试',cfg)]


class SpeechTicketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app=FastAPI()
        @app.middleware('http')
        async def test_identity(request,call_next):
            request.state.owner=request.headers.get('X-Test-Owner','test-a')
            return await call_next(request)
        app.include_router(voice.router)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost')
        self.config=patch('app.voice.config',return_value={'key':'test-only','voice':'test-only','tts_resource':'test-only'})
        self.config.start()
        voice._speech_tickets.clear()

    async def asyncTearDown(self):
        self.config.stop()
        voice._speech_tickets.clear()
        await self.client.aclose()

    async def test_stream_is_owner_bound_single_use_and_text_not_in_url(self):
        async def audio(*args):
            yield b'first';yield b'second'
        prepared=await self.client.post('/api/voice/tts/prepare',json={'text':'测试私有播报内容'})
        self.assertEqual(prepared.status_code,200)
        url=prepared.json()['url']
        self.assertNotIn('测试',url)
        with patch('app.voice.speech_audio',audio):
            self.assertEqual((await self.client.get(url,headers={'X-Test-Owner':'test-b'})).status_code,404)
            response=await self.client.get(url)
            self.assertEqual(response.content,b'firstsecond')
            self.assertEqual(response.headers['content-type'],'audio/mpeg')
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual((await self.client.get(url)).status_code,404)

    async def test_expired_ticket_does_not_start_cloud_synthesis(self):
        response=await self.client.post('/api/voice/tts/prepare',json={'text':'测试'})
        url=response.json()['url'];token=url.rsplit('/',1)[1]
        voice._speech_tickets[token]['expires']=0
        with patch('app.voice.speech_audio') as upstream:
            self.assertEqual((await self.client.get(url)).status_code,404)
        upstream.assert_not_called()

    async def test_provider_failure_before_first_chunk_returns_error(self):
        async def failure(*args):
            raise ValueError('private-provider-diagnostic')
            yield b''
        response=await self.client.post('/api/voice/tts/prepare',json={'text':'测试'})
        with patch('app.voice.speech_audio',failure):
            result=await self.client.get(response.json()['url'])
        self.assertEqual(result.status_code,502)
        self.assertNotIn('private-provider-diagnostic',result.text)


if __name__=='__main__':
    unittest.main()
