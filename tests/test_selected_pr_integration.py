"""Selected PR features work with the newer main capability surface."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import read_only, voice


class SelectedIntegrationTests(unittest.TestCase):
    def test_built_homepage_and_companion_assets_are_served(self):
        with TestClient(app, base_url='http://localhost') as client:
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            import re
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', response.text)
            self.assertGreaterEqual(len(assets), 2)
            for asset in assets:
                self.assertEqual(client.get(asset).status_code, 200, asset)
            for scene in ('working', 'taxi', 'dining'):
                self.assertEqual(client.get(f'/mascot/xiaorui-{scene}.png').status_code, 200)

    def test_read_only_allows_stream_preparation_but_not_new_address_or_location_writes(self):
        with patch.object(read_only, 'READ_ONLY', True), \
             patch.object(voice, 'config', return_value={'key': 'isolated-test'}), \
             patch.object(voice, '_speech_tickets', {}), \
             TestClient(app, base_url='http://localhost') as client:
            prepared = client.post('/api/voice/tts/prepare', json={'text': '测试播报'})
            self.assertEqual(prepared.status_code, 200)
            self.assertTrue(prepared.json()['url'].startswith('/api/voice/tts/stream/'))
            for path in ('/api/location', '/api/actions/missing/confirm'):
                self.assertEqual(client.post(path, json={}).status_code, 403)
            from app.actions import ActionError
            from app.main import agent
            with self.assertRaises(ActionError):
                agent.actions.prepare('isolated-test', 'mcd', 'create_address', {}, {})
