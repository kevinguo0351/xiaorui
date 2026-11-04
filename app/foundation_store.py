"""Durable local profile, display sessions and task receipts; no automatic replay."""
import json
import re
import secrets
import sqlite3
import time
from pathlib import Path


class FoundationStore:
    PROFILE_ID = 'local-user'
    TERMINAL = {'completed', 'failed', 'interrupted', 'cancelled', 'waiting_confirmation', 'unknown'}

    def __init__(self, path, *, recover_running=True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS profile_meta (id TEXT PRIMARY KEY, version INTEGER NOT NULL, forget_epoch INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, value TEXT, deleted INTEGER NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (owner TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO profile_meta VALUES (?,0,0)', (self.PROFILE_ID,))
        if recover_running:
            self.recover_interrupted()
        self.path.chmod(0o600)

    def recover_interrupted(self):
        """Called by the owning application startup, never a read-only import."""
        with self.connect() as db:
            for row in db.execute('SELECT id,body FROM tasks').fetchall():
                task = json.loads(row['body'])
                if task['status'] == 'running':
                    task.update(status='interrupted', error='服务中断，任务未自动重放，请核查后继续。', updated_at=time.time())
                    db.execute('UPDATE tasks SET body=? WHERE id=?', (json.dumps(task, ensure_ascii=False), row['id']))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _owner(owner):
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ValueError('无效的本地会话。')

    @staticmethod
    def _new(epoch):
        return {'conversation_id': secrets.token_urlsafe(24), 'display': [], 'stores': {},
                'meals': [], 'plan_id': None, 'forget_epoch': epoch}

    def _epoch(self, db):
        return db.execute('SELECT forget_epoch FROM profile_meta WHERE id=?', (self.PROFILE_ID,)).fetchone()[0]

    def session(self, owner):
        self._owner(owner)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM sessions WHERE owner=?', (owner,)).fetchone()
            if row:
                return json.loads(row['body'])
            state = self._new(self._epoch(db))
            db.execute('INSERT INTO sessions VALUES (?,?)', (owner, json.dumps(state)))
            return state

    def save_session(self, owner, state):
        self._owner(owner)
        if not isinstance(state, dict) or not isinstance(state.get('conversation_id'), str):
            raise ValueError('会话状态无效。')
        for key, kind in [('display', list), ('stores', dict), ('meals', list)]:
            if not isinstance(state.get(key), kind):
                raise ValueError('会话状态无效。')
        encoded = json.dumps(state, ensure_ascii=False)
        if len(encoded.encode()) > 2_000_000:
            raise ValueError('会话过大，请开始新对话。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if state.get('forget_epoch') != self._epoch(db):
                raise ValueError('个人资料已删除，请重新加载会话。')
            current = db.execute('SELECT body FROM sessions WHERE owner=?', (owner,)).fetchone()
            if current and json.loads(current['body'])['conversation_id'] != state['conversation_id']:
                raise ValueError('已开始新对话，请重新加载会话。')
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (owner, encoded))

    def new_session(self, owner):
        self._owner(owner)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self._new(self._epoch(db))
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (owner, json.dumps(state)))
            return state

    def _profile(self, db):
        meta = db.execute('SELECT version,forget_epoch FROM profile_meta WHERE id=?', (self.PROFILE_ID,)).fetchone()
        rows = db.execute('SELECT key,value,deleted FROM facts ORDER BY key').fetchall()
        return {'profile_id': self.PROFILE_ID, **dict(meta),
                'facts': {r['key']: r['value'] for r in rows if not r['deleted']},
                'deleted_keys': [r['key'] for r in rows if r['deleted']]}

    def profile(self):
        with self.connect() as db:
            return self._profile(db)

    def list_facts(self):
        return self.profile()['facts']

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}', key):
            raise ValueError('资料字段须为 1–80 位小写字母、数字、点、横线或下划线。')

    def set_fact(self, key, value):
        self._key(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 1000:
            raise ValueError('资料内容须为 1–1000 字。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM facts WHERE deleted=0').fetchone()[0] >= 100 and not db.execute('SELECT 1 FROM facts WHERE key=? AND deleted=0', (key,)).fetchone():
                raise ValueError('个人资料最多保存 100 项，请先整理。')
            db.execute('INSERT OR REPLACE INTO facts VALUES (?,?,0,?)', (key, value.strip(), time.time()))
            db.execute('UPDATE profile_meta SET version=version+1 WHERE id=?', (self.PROFILE_ID,))
            return self._profile(db)

    def delete_fact(self, key):
        self._key(key)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO facts VALUES (?,NULL,1,?)', (key, time.time()))
            db.execute('UPDATE profile_meta SET version=version+1,forget_epoch=forget_epoch+1 WHERE id=?', (self.PROFILE_ID,))
            # Never restore a deleted fact from a stale display transcript.
            db.execute('DELETE FROM sessions')
            return self._profile(db)

    def start_task(self, owner, conversation_id, input):
        self._owner(owner)
        if not isinstance(input, str) or not input.strip() or len(input) > 2000:
            raise ValueError('任务内容须为 1–2000 字。')
        if not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 128:
            raise ValueError('任务会话无效。')
        now = time.time()
        task = {'id': secrets.token_urlsafe(24), 'conversation_id': conversation_id,
                'input': input, 'status': 'running', 'result': None, 'error': None,
                'created_at': now, 'updated_at': now}
        with self.connect() as db:
            task['forget_epoch'] = self._epoch(db)
            db.execute('INSERT INTO tasks VALUES (?,?,?)', (task['id'], owner, json.dumps(task, ensure_ascii=False)))
        return task['id']

    def finish_task(self, id, status, result=None, error=None):
        if status not in self.TERMINAL:
            raise ValueError('任务状态无效。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM tasks WHERE id=?', (id,)).fetchone()
            if not row:
                raise ValueError('找不到任务。')
            task = json.loads(row['body'])
            if task['status'] != 'running':
                if task['status'] == status:
                    return task
                raise ValueError('任务已结束或中断，不可静默覆盖执行结果。')
            task.update(status=status, result=result, error=error, updated_at=time.time())
            body = json.dumps(task, ensure_ascii=False)
            if len(body.encode()) > 2_000_000:
                raise ValueError('任务结果过大。')
            db.execute('UPDATE tasks SET body=? WHERE id=?', (body, id))
            return task

    def get_task(self, owner, id):
        self._owner(owner)
        with self.connect() as db:
            row = db.execute('SELECT body FROM tasks WHERE id=? AND owner=?', (id, owner)).fetchone()
            if not row:
                raise ValueError('找不到任务。')
            return json.loads(row['body'])

    def list_tasks(self, owner, limit=50):
        self._owner(owner)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('任务数量须为 1–100。')
        with self.connect() as db:
            return [json.loads(r['body']) for r in db.execute('SELECT body FROM tasks WHERE owner=? ORDER BY rowid DESC LIMIT ?', (owner, limit))]

    def get(self, owner, id):
        return self.get_task(owner, id)

    def list(self, owner, limit=50):
        return self.list_tasks(owner, limit)
