"""Local voice gateway to official Doubao ASR and TTS services.

Only PCM16 mono 16kHz is accepted; microphone bytes and synthesized audio are
kept in memory for the request and never written to disk. Configuration status
means a key is present, not that its remote permissions have been verified.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from websockets.asyncio.client import connect

from app.voice_protocol import encode_request, decode_response

router = APIRouter(prefix='/api/voice')
ASR_URL = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async'
TTS_URL = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'
MAX_AUDIO_BYTES = 60 * 16000 * 2
MAX_TTS_BYTES = 8_000_000


def config() -> dict[str, str]:
    local = dotenv_values(Path(__file__).resolve().parents[1] / '.env')
    def value(name, default=''):
        return str(os.environ.get(name, local.get(name) or default)).strip()
    return {'key': value('DOUBAO_SPEECH_API_KEY'),
            'asr_resource': value('DOUBAO_ASR_RESOURCE_ID', 'volc.seedasr.sauc.duration'),
            'tts_resource': value('DOUBAO_TTS_RESOURCE_ID', 'seed-tts-2.0'),
            'voice': value('DOUBAO_TTS_VOICE', 'zh_female_vv_uranus_bigtts')}


def headers(cfg, resource):
    return {'X-Api-Key': cfg['key'], 'X-Api-Resource-Id': resource,
            'X-Api-Request-Id': str(uuid4())}


@router.get('/status')
async def status():
    cfg = config()
    return {'configured': bool(cfg['key']), 'asr_configured': bool(cfg['key']),
            'tts_configured': bool(cfg['key']), 'provider': 'doubao',
            'max_recording_seconds': 60}


def allowed_socket(socket: WebSocket) -> bool:
    host = socket.headers.get('host', '')
    try:
        if urlsplit('http://' + host).hostname not in {'localhost', '127.0.0.1', '::1'}:
            return False
    except ValueError:
        return False
    scheme = 'https' if socket.url.scheme == 'wss' else 'http'
    # Require browser Origin, preventing cross-site microphone/billing access.
    return socket.headers.get('origin') == f'{scheme}://{host}'


@router.websocket('/asr')
async def recognize(socket: WebSocket):
    if not allowed_socket(socket):
        await socket.close(code=1008)
        return
    await socket.accept()
    cfg = config()
    if not cfg['key']:
        await socket.send_json({'type': 'error', 'message': '请先配置豆包语音 API Key。'})
        await socket.close(code=1008)
        return
    tasks = []
    try:
        async with asyncio.timeout(80):
            async with connect(ASR_URL, additional_headers=headers(cfg, cfg['asr_resource']),
                               open_timeout=10, close_timeout=2, max_size=1_000_000) as upstream:
                payload = {'user': {'uid': 'xiaorui-local'},
                           'audio': {'format': 'pcm', 'codec': 'raw', 'rate': 16000,
                                     'bits': 16, 'channel': 1},
                           'request': {'model_name': 'bigmodel', 'enable_itn': True,
                                       'enable_punc': True, 'show_utterances': True,
                                       'enable_nonstream': True, 'result_type': 'full',
                                       'end_window_size': 2000}}
                await upstream.send(encode_request(json.dumps(payload).encode()))
                await socket.send_json({'type': 'ready'})

                async def upload():
                    total = 0
                    async with asyncio.timeout(65):
                        while True:
                            message = await socket.receive()
                            if message['type'] == 'websocket.disconnect':
                                return 'cancel'
                            chunk = message.get('bytes')
                            if chunk is not None:
                                total += len(chunk)
                                if not chunk or len(chunk) % 2 or len(chunk) > 32000 or total > MAX_AUDIO_BYTES:
                                    raise ValueError('Invalid microphone audio')
                                await upstream.send(encode_request(chunk, audio=True))
                            else:
                                raw = message.get('text', '')
                                if len(raw) > 128:
                                    raise ValueError('Invalid voice command')
                                command = json.loads(raw)
                                if command == {'type': 'cancel'}:
                                    return 'cancel'
                                if command != {'type': 'finish'}:
                                    raise ValueError('Invalid voice command')
                                await upstream.send(encode_request(b'', audio=True, final=True))
                                return 'finish'

                async def download():
                    last = ''
                    async for frame in upstream:
                        if not isinstance(frame, bytes):
                            raise ValueError('Invalid provider response')
                        data, final = decode_response(frame)
                        body = data.get('payload_msg', data)
                        result = body.get('result', {})
                        if isinstance(result, list):
                            text = ''.join(str(r.get('text', '')) for r in result if isinstance(r, dict))
                        else:
                            text = result.get('text', '') if isinstance(result, dict) else ''
                        if not isinstance(text, str) or len(text) > 8000:
                            raise ValueError('Invalid transcription')
                        last = text or last
                        if final:
                            await socket.send_json({'type': 'final', 'text': last})
                            return
                        if text:
                            await socket.send_json({'type': 'partial', 'text': text})
                    raise ValueError('Speech provider ended without final result')

                up = asyncio.create_task(upload())
                down = asyncio.create_task(download())
                tasks = [up, down]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if up in done:
                    if await up == 'finish':
                        await asyncio.wait_for(down, timeout=15)
                else:
                    await down
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await socket.send_json({'type': 'error', 'message': '语音识别未完成，请检查语音服务权限或网络后重试。'})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await socket.close()
        except RuntimeError:
            pass


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=1200, strict=True)


def tts_chunk(line: str) -> bytes:
    if line.startswith('data:'):
        line = line[5:].strip()
    data = json.loads(line)
    if not isinstance(data, dict) or data.get('code') not in (0, 20000000):
        raise ValueError('Speech provider rejected text')
    audio = data.get('data')
    return base64.b64decode(audio, validate=True) if audio else b''


@router.post('/tts')
async def synthesize(body: SpeechRequest):
    cfg = config()
    if not cfg['key']:
        raise HTTPException(503, '请先配置豆包语音 API Key。')
    try:
        async with asyncio.timeout(45):
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as client:
                async with client.stream('POST', TTS_URL, headers=headers(cfg, cfg['tts_resource']),
                                         json={'req_params': {'text': body.text, 'speaker': cfg['voice'],
                                                              'audio_params': {'format': 'mp3', 'sample_rate': 24000,
                                                                               'speech_rate': -10}}}) as response:
                    response.raise_for_status()
                    audio = bytearray()
                    pending = b''
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > MAX_TTS_BYTES * 2:
                            raise ValueError('Speech response too large')
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            line = line.strip()
                            if line and not line.startswith((b'event:', b':')):
                                audio.extend(tts_chunk(line.decode()))
                            if len(audio) > MAX_TTS_BYTES:
                                raise ValueError('Speech audio too large')
                        if len(pending) > MAX_TTS_BYTES * 2:
                            raise ValueError('Speech response too large')
                    if pending.strip():
                        audio.extend(tts_chunk(pending.decode().strip()))
                    if not audio or len(audio) > MAX_TTS_BYTES:
                        raise ValueError('Speech provider returned no valid audio')
                    return Response(bytes(audio), media_type='audio/mpeg', headers={'Cache-Control': 'no-store'})
    except Exception:
        raise HTTPException(502, '语音播报暂时不可用，请检查语音服务权限或网络后重试。') from None
