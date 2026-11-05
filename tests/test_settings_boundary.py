"""The family credential editor remains inside the existing localhost boundary."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import settings, read_only
from app.main import app


class SettingsBoundaryTests(unittest.TestCase):
    def test_remote_hosts_and_cross_origin_cannot_read_or_change_configuration(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, 'ENV_PATH', Path(temp)/'.env'):
            with TestClient(app, base_url='http://localhost') as client:
                self.assertEqual(client.get('/api/settings').status_code, 200)
                for headers in ({'host': 'example.com'}, {'origin': 'https://example.com'}):
                    self.assertEqual(client.get('/api/settings', headers=headers).status_code, 403)
                    self.assertEqual(client.post('/api/settings', json={'values': {
                        'MCD_MCP_TOKEN': 'test-only-marker'}}, headers=headers).status_code, 403)
            self.assertFalse((Path(temp)/'.env').exists())

    def test_preview_policy_blocks_configuration_writes_at_host_boundary(self):
        with patch.object(read_only, 'READ_ONLY', True), TestClient(app, base_url='http://localhost') as client:
            self.assertEqual(client.get('/api/settings').status_code, 200)
            self.assertEqual(client.post('/api/settings', json={'values': {
                'MCD_MCP_TOKEN': 'test-only-marker'}}).status_code, 403)
            self.assertEqual(client.post('/api/settings/test/mcd', json={}).status_code, 403)
