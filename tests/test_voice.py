"""Offline speech protocol/boundary tests; never contact the speech provider."""
import base64
import gzip
import json
import struct
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.voice import router, tts_chunk
from app.voice_protocol import MAX_FRAME, decode_response, encode_request


def response(payload, flags=0, compressed=True):
    body = json.dumps(payload).encode()
    if compressed:
        body = gzip.compress(body)
    sequence = struct.pack('>i', -1 if flags & 2 else 1) if flags & 1 else b''
    return bytes([0x11, 0x90 | flags, 0x11 if compressed else 0x10, 0]) + sequence + struct.pack('>I', len(body)) + body


class VoiceProtocolTests(unittest.TestCase):
    def test_client_pcm_final_frame_has_correct_size_and_binary_format(self):
        frame = encode_request(b'\x01\x00' * 1600, audio=True, final=True)
        self.assertEqual(frame[:4], bytes([0x11, 0x22, 0x01, 0]))
        self.assertEqual(struct.unpack('>I', frame[4:8])[0], len(frame) - 8)
        self.assertEqual(gzip.decompress(frame[8:]), b'\x01\x00' * 1600)

    def test_json_request_preserves_utf8(self):
        raw = json.dumps({'text': '小瑞'}).encode()
        self.assertEqual(gzip.decompress(encode_request(raw)[8:]), raw)

    def test_final_response_sequence_and_compression_variants(self):
        for flags in (0, 1, 2, 3):
            for compressed in (False, True):
                with self.subTest(flags=flags, compressed=compressed):
                    value, final = decode_response(response({'result': {'text': '套餐A'}}, flags, compressed))
                    self.assertEqual(value['result']['text'], '套餐A')
                    self.assertEqual(final, bool(flags & 2))

    def test_invalid_or_truncated_frames_are_rejected(self):
        valid = response({'result': {}})
        invalid = [b'', valid[:7], valid[:-1], bytes([0x21]) + valid[1:], valid[:2] + b'\x12' + valid[3:]]
        for frame in invalid:
            with self.subTest(frame=frame[:8]), self.assertRaises(ValueError):
                decode_response(frame)

    def test_decompression_bomb_is_bounded(self):
        with self.assertRaises(ValueError):
            decode_response(response({'text': 'x' * (MAX_FRAME + 1)}))

    def test_provider_error_and_non_object_are_rejected(self):
        for payload in ({'code': 45000000, 'message': 'private upstream details'}, ['wrong']):
            with self.assertRaises(ValueError):
                decode_response(response(payload))

    def test_documented_asr_success_code_preserves_final_text(self):
        value, final = decode_response(response(
            {'code': 20000000, 'result': {'text': '帮我买麦当劳。'}}, flags=3))
        self.assertTrue(final)
        self.assertEqual(value['result']['text'], '帮我买麦当劳。')

    def test_tts_chunks_decode_base64_and_terminal_marker(self):
        encoded = base64.b64encode(b'audio-bytes').decode()
        self.assertEqual(tts_chunk('data: ' + json.dumps({'code': 0, 'data': encoded})), b'audio-bytes')
        self.assertEqual(tts_chunk('{"code":20000000}'), b'')

    def test_tts_rejects_errors_and_invalid_audio(self):
        for line in ('{"code":45000000}', '{"code":0,"data":"%%%"}', '[]'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                tts_chunk(line)


class VoiceBoundaryTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app, base_url='http://localhost')
        self.patch = patch('app.voice.config', return_value={'key': '', 'asr_resource': 'test', 'tts_resource': 'test', 'voice': 'test'})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.client.close()

    def test_unconfigured_status_and_tts_fail_without_provider_request(self):
        with patch('app.voice.httpx.AsyncClient') as network:
            status = self.client.get('/api/voice/status').json()
            self.assertFalse(status['configured'])
            self.assertNotIn('key', status)
            self.assertEqual(self.client.post('/api/voice/tts', json={'text': '您好'}).status_code, 503)
            network.assert_not_called()

    def test_tts_strict_text_bounds(self):
        for text in ('', '  ', 'x' * 1201, True, 42):
            with self.subTest(text=str(text)[:20]):
                self.assertEqual(self.client.post('/api/voice/tts', json={'text': text}).status_code, 422)

    def test_ws_cross_origin_and_missing_origin_rejected(self):
        for headers in ({}, {'Origin': 'https://evil.example'}, {'Origin': 'http://localhost:9999'}):
            with self.subTest(headers=headers), self.assertRaises(WebSocketDisconnect) as caught:
                with self.client.websocket_connect('/api/voice/asr', headers=headers):
                    pass
            self.assertEqual(caught.exception.code, 1008)

    def test_ws_missing_key_reports_truthful_error_without_upstream(self):
        with patch('app.voice.connect') as network:
            with self.client.websocket_connect('/api/voice/asr', headers={'Origin': 'http://localhost', 'Host': 'localhost'}) as ws:
                message = ws.receive_json()
                self.assertEqual(message['type'], 'error')
                self.assertIn('API Key', message['message'])
            network.assert_not_called()
