import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app import main, read_only
from app.contact import ContactService


class PhoneApiTests(unittest.TestCase):
    def test_call_owner_scope_end_idempotency_and_read_only_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=ContactService(main.agent, Path(tmp)/'contact.db')
            with patch.object(main,'contact',service), patch.object(read_only,'READ_ONLY',True), TestClient(app,base_url='http://localhost') as client:
                call=client.post('/api/contact/calls',json={})
                self.assertEqual(call.status_code,200)
                call=call.json()
                self.assertEqual(client.post('/api/contact/calls',json={}).json()['id'],call['id'])
                cookie=client.cookies.get('pa_session')
                client.cookies.clear()
                self.assertEqual(client.post(f"/api/contact/calls/{call['id']}/end",json={}).status_code,404)
                client.cookies.clear();client.cookies.set('pa_session',cookie)
                ended=client.post(f"/api/contact/calls/{call['id']}/end",json={})
                self.assertEqual(ended.status_code,200)
                self.assertEqual(client.post(f"/api/contact/calls/{call['id']}/end",json={}).json(),ended.json())
                self.assertEqual(len([e for e in client.get('/api/contact/state').json()['events'] if e['type']=='call_ended']),1)
                self.assertEqual(client.post('/api/actions/missing/confirm',json={}).status_code,403)
