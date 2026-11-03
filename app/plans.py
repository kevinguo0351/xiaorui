"""Durable plan ownership and one-shot order execution claims."""
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path


class PlanError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


class PlanStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL)')
            for row in db.execute('SELECT id, body FROM plans').fetchall():
                p = json.loads(row['body'])
                if p['status'] == 'submitting':
                    p.update(status='unknown', error='上次下单中断，结果待核查。请勿重复下单。')
                    self.write(db, p)
                elif p['status'] == 'rechecking':
                    p.update(status='expired', error='上次核价中断，请重新生成方案。')
                    self.write(db, p)
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def write(db, plan):
        db.execute('UPDATE plans SET body=? WHERE id=?', (json.dumps(plan, ensure_ascii=False), plan['id']))

    @staticmethod
    def public(plan):
        return {k: v for k, v in plan.items() if k not in {'owner', 'request', 'request_hash'}}

    @staticmethod
    def lookup(db, plan_id, owner):
        row = db.execute('SELECT body FROM plans WHERE id=? AND owner=?', (plan_id, owner)).fetchone()
        if row is None:
            raise PlanError('找不到这个方案。', 404)
        return json.loads(row['body'])

    def create(self, owner, prepared):
        body = json.dumps(prepared['request'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        p = {'id': secrets.token_urlsafe(24), 'owner': owner, 'version': 1,
             'status': 'awaiting_confirmation', 'amount_cents': prepared['amount_cents'],
             'summary': prepared['summary'], 'request': prepared['request'],
             'request_hash': hashlib.sha256(body.encode()).hexdigest(),
             'expires_at': time.time() + 300, 'confirmation_token': secrets.token_urlsafe(32)}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT body FROM plans WHERE owner=?', (owner,)).fetchall()
            for row in rows:
                old = json.loads(row['body'])
                if old['status'] in {'rechecking', 'submitting', 'unknown'}:
                    raise PlanError('上一项操作正在处理中，请先等待结果。')
                if old['status'] in {'awaiting_confirmation', 'needs_review'}:
                    old['status'] = 'superseded'
                    self.write(db, old)
            db.execute('INSERT INTO plans VALUES (?,?,?)', (p['id'], owner, json.dumps(p, ensure_ascii=False)))
        return self.public(p)

    def get(self, plan_id, owner):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            p = self.lookup(db, plan_id, owner)
            if p['status'] in {'awaiting_confirmation', 'needs_review'} and time.time() > p['expires_at']:
                p['status'] = 'expired'
                self.write(db, p)
            return self.public(p)

    def claim(self, plan_id, owner, version, token):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            p = self.lookup(db, plan_id, owner)
            canonical = json.dumps(p['request'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            if not secrets.compare_digest(hashlib.sha256(canonical.encode()).hexdigest(), p['request_hash']):
                raise PlanError('方案内容校验失败，请重新生成。')
            if version != p['version'] or not secrets.compare_digest(token, p['confirmation_token']):
                raise PlanError('方案已变化，请重新查看并确认。')
            if p['status'] in {'rechecking', 'submitting', 'created', 'unknown', 'failed'}:
                return p, False
            if p['status'] not in {'awaiting_confirmation', 'needs_review'}:
                raise PlanError('该方案不能继续下单，请重新查询。')
            if time.time() > p['expires_at']:
                raise PlanError('方案已过期，请重新核价。')
            p['status'] = 'rechecking'
            self.write(db, p)
        return p, True

    def update(self, plan_id, owner, **fields):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            p = self.lookup(db, plan_id, owner)
            p.update(fields)
            self.write(db, p)
            return self.public(p)

    def cancel(self, plan_id, owner):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            p = self.lookup(db, plan_id, owner)
            if p['status'] in {'rechecking', 'submitting', 'created', 'unknown'}:
                raise PlanError('操作已开始或结果待核查，不能把它当作已取消订单。')
            p['status'] = 'cancelled'
            self.write(db, p)
            return self.public(p)
