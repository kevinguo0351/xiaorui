"""Payment-test journal guards; temporary files only, never merchant calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments import payment_submit


class PaymentJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.patch = patch.object(payment_submit, 'DIRECTORY', self.directory)
        self.patch.start()
        self.plan = {'provider':'mcd','status':'prepared','prepared_at':time.time(),
                     'summary':{'amount_yuan':'22.00','product':'unit'}}
        self.plan['digest'] = hashlib.sha256(json.dumps(self.plan, sort_keys=True).encode()).hexdigest()
        self.path = self.directory/'mcd.json'
        payment_submit.write(self.path, self.plan)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_changed_reviewed_plan_and_unknown_result_cannot_be_claimed(self):
        altered = dict(self.plan, summary={'amount_yuan':'23.00','product':'unit'})
        payment_submit.write(self.path, altered)
        with self.assertRaises(RuntimeError):
            with payment_submit.claim('mcd', self.plan['digest']):
                self.fail('tampered plan accepted')
        payment_submit.write(self.path, dict(self.plan, status='unknown'))
        with self.assertRaises(RuntimeError):
            with payment_submit.claim('mcd', self.plan['digest']):
                self.fail('unknown order retried')

    def test_concurrent_claim_is_rejected_and_journal_is_private(self):
        with payment_submit.claim('mcd', self.plan['digest']):
            with self.assertRaises(FileExistsError):
                with payment_submit.claim('mcd', self.plan['digest']):
                    self.fail('duplicate claim accepted')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.path.with_suffix('.lock').exists())
