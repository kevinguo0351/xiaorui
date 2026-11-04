"""Scheduler lifecycle and no-replay checks; no network or real user jobs."""
import tempfile
import unittest
from unittest.mock import AsyncMock
from nanobot.cron.types import CronJob, CronPayload, CronSchedule
from nanobot.cron.service import CronJobSkippedError
from app.foundation_scheduler import FoundationScheduler


def job():
    return CronJob(id='xiaorui-maintenance-test', name='test-only',
                   schedule=CronSchedule(kind='at', at_ms=1),
                   payload=CronPayload(kind='system_event', message='maintenance'))


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_stop_and_restart_have_no_default_jobs(self):
        with tempfile.TemporaryDirectory() as path:
            scheduler = FoundationScheduler(path)
            await scheduler.start()
            self.assertTrue(scheduler.status()['running'])
            self.assertEqual(scheduler.status()['jobs'], 0)
            await scheduler.stop()
            other = FoundationScheduler(path)
            await other.start()
            self.assertEqual(other.status()['jobs'], 0)
            self.assertFalse(other.status()['delivery_configured'])
            await other.stop()

    async def test_failed_callback_is_not_replayed_after_restart(self):
        with tempfile.TemporaryDirectory() as path:
            callback = AsyncMock(side_effect=RuntimeError('private details'))
            scheduler = FoundationScheduler(path, callback)
            with self.assertRaises(RuntimeError):
                await scheduler.dispatch(job())
            other = FoundationScheduler(path, callback)
            with self.assertRaises(CronJobSkippedError):
                await other.dispatch(job())
            callback.assert_awaited_once()
            self.assertEqual(other.status()['receipts'], {'failed': 1})

    async def test_arbitrary_agent_job_has_no_callback(self):
        with tempfile.TemporaryDirectory() as path:
            callback = AsyncMock()
            scheduler = FoundationScheduler(path, callback)
            candidate = job()
            candidate.payload.kind = 'agent_turn'
            with self.assertRaises(CronJobSkippedError):
                await scheduler.dispatch(candidate)
            callback.assert_not_awaited()
