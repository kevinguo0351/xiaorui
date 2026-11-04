"""Durable foundation tests; no network, model, or real-user data."""
import json
import tempfile
import unittest
from pathlib import Path

from app.foundation_store import FoundationStore


class FoundationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'foundation.sqlite3'
        self.store = FoundationStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_and_profile_survive_restart_and_are_detached(self):
        state = self.store.session('owner-a')
        state['display'] = [{'role': 'user', 'text': 'unit test'}]
        self.store.save_session('owner-a', state)
        self.store.set_fact('home.address', 'unit test address')
        state['display'].clear()
        restarted = FoundationStore(self.path)
        self.assertEqual(restarted.session('owner-a')['display'][0]['text'], 'unit test')
        self.assertEqual(restarted.profile()['facts']['home.address'], 'unit test address')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_reset_keeps_profile_but_rotates_thread_and_rejects_late_save(self):
        old = self.store.session('a')
        self.store.set_fact('drink', 'unit test preference')
        new = self.store.new_session('a')
        self.assertNotEqual(old['conversation_id'], new['conversation_id'])
        self.assertEqual(new['display'], [])
        self.assertIn('drink', self.store.list_facts())
        with self.assertRaises(ValueError):
            self.store.save_session('a', old)

    def test_delete_tombstones_invalidates_all_host_sessions(self):
        self.store.set_fact('home.address', 'unit old address')
        old_a, old_b = self.store.session('a'), self.store.session('b')
        state = self.store.delete_fact('home.address')
        self.assertNotIn('home.address', state['facts'])
        self.assertIn('home.address', state['deleted_keys'])
        self.assertEqual(state['forget_epoch'], 1)
        for owner, old in [('a', old_a), ('b', old_b)]:
            self.assertNotEqual(self.store.session(owner)['conversation_id'], old['conversation_id'])
            with self.assertRaises(ValueError):
                self.store.save_session(owner, old)
        with self.store.connect() as db:
            row = db.execute('SELECT value FROM facts WHERE key=?', ('home.address',)).fetchone()
            self.assertIsNone(row['value'])

    def test_explicit_resave_revives_tombstone_with_new_value(self):
        self.store.set_fact('drink', 'unit old')
        self.store.delete_fact('drink')
        profile = self.store.set_fact('drink', 'unit new')
        self.assertEqual(profile['facts']['drink'], 'unit new')
        self.assertNotIn('drink', profile['deleted_keys'])
        self.assertEqual(profile['version'], 3)

    def test_task_recovery_does_not_reexecute_and_owner_isolation(self):
        session = self.store.session('a')
        first = self.store.start_task('a', session['conversation_id'], 'unit in flight')
        second = self.store.start_task('a', session['conversation_id'], 'unit complete')
        self.store.finish_task(second, 'completed', {'answer': 'unit success'})
        restarted = FoundationStore(self.path)
        self.assertEqual(restarted.get_task('a', first)['status'], 'interrupted')
        self.assertEqual(restarted.get_task('a', second)['status'], 'completed')
        self.assertEqual(restarted.list_tasks('b'), [])
        with self.assertRaises(ValueError):
            restarted.get_task('b', first)
        with self.assertRaises(ValueError):
            restarted.finish_task(first, 'completed')
        self.assertEqual(len(restarted.list_tasks('a')), 2)

    def test_terminal_receipt_is_idempotent_without_result_overwrite(self):
        task = self.store.start_task('a', 'unit-thread', 'unit request')
        self.store.finish_task(task, 'completed', result='first')
        repeated = self.store.finish_task(task, 'completed', result='second')
        self.assertEqual(repeated['result'], 'first')
        with self.assertRaises(ValueError):
            self.store.finish_task(task, 'running')

    def test_validation_rejects_invalid_profile_and_limits(self):
        for key in ('', '../.env', 'Mixed Case', 'a'*81, True):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.set_fact(key, 'unit')
        for value in ('', '   ', 'a'*1001, True):
            with self.subTest(value=str(value)[:15]), self.assertRaises(ValueError):
                self.store.set_fact('valid', value)
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                self.store.list_tasks('a', limit)
        self.assertEqual(self.store.profile()['version'], 0)
