"""Lifecycle host for nanobot cron. No user jobs, delivery, model or transactions."""
import asyncio
import sqlite3
from pathlib import Path
from nanobot.cron.service import CronService, CronJobSkippedError


class FoundationScheduler:
    def __init__(self, directory, maintenance=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        self.receipts = self.directory / 'receipts.sqlite3'
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (job_id TEXT PRIMARY KEY, status TEXT NOT NULL)')
        self.receipts.chmod(0o600)
        self.maintenance = maintenance
        self.engine = CronService(self.directory / 'jobs.json', on_job=self.dispatch)
        self.running = False

    def _db(self):
        return sqlite3.connect(self.receipts)

    async def start(self):
        if self.running:
            return
        with self._db() as db:
            db.execute("UPDATE runs SET status='interrupted' WHERE status='running'")
        await self.engine.start()
        self.engine.store_path.chmod(0o600)
        self.running = True

    async def stop(self):
        self.engine.stop()
        self.running = False
        await asyncio.sleep(0)

    def status(self):
        state = self.engine.status()
        with self._db() as db:
            counts = dict(db.execute('SELECT status, count(*) FROM runs GROUP BY status'))
        return {'engine': 'nanobot.cron', 'running': self.running, 'jobs': state['jobs'],
                'delivery_configured': False, 'user_scheduling_enabled': False,
                'receipts': counts}

    async def dispatch(self, job):
        # This phase accepts only host-owned, one-shot maintenance events. No
        # arbitrary prompt, shell, periodic replay, or delivery target is admitted.
        if (job.payload.kind != 'system_event' or job.schedule.kind != 'at'
                or job.payload.message != 'maintenance' or not job.id.startswith('xiaorui-maintenance-')
                or job.payload.deliver or job.payload.channel or job.payload.to):
            raise CronJobSkippedError('Unsupported foundation job')
        with self._db() as db:
            try:
                db.execute("INSERT INTO runs VALUES (?, 'running')", (job.id,))
            except sqlite3.IntegrityError:
                raise CronJobSkippedError('Job already claimed; no automatic replay') from None
        try:
            if self.maintenance:
                await self.maintenance()
        except asyncio.CancelledError:
            self._finish(job.id, 'interrupted')
            raise
        except Exception:
            self._finish(job.id, 'failed')
            raise RuntimeError('Foundation maintenance failed; manual review required') from None
        else:
            self._finish(job.id, 'completed')
            return 'Foundation maintenance completed'

    def _finish(self, job_id, status):
        with self._db() as db:
            db.execute('UPDATE runs SET status=? WHERE job_id=?', (status, job_id))
