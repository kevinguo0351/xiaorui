"""Persistent Personal Agent host; nanobot owns the model/tool execution loop."""
import asyncio
import copy
import hashlib
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from pydantic import ValidationError

from app.foundation_store import FoundationStore
from app.nanobot_runtime import build_runtime, data_context, SYSTEM
from app.plans import PlanError
from app.skills import SkillRegistry, SCHEMAS, TOOLS, catalog

ROOT = Path(__file__).resolve().parents[1]


class AgentError(Exception):
    def __init__(self, message, status=502):
        self.message, self.status = message, status


@dataclass
class Session:
    conversation_id: str = ''
    display: list = field(default_factory=list)
    stores: dict = field(default_factory=dict)
    meals: list = field(default_factory=list)
    plan_id: str | None = None
    forget_epoch: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)

    def snapshot(self):
        return {name: copy.deepcopy(getattr(self, name)) for name in (
            'conversation_id', 'display', 'stores', 'meals', 'plan_id', 'forget_epoch')}


class AgentService:
    def __init__(self, service, plans, store=None, data_dir=None):
        self.service, self.plans = service, plans
        self.data_dir = Path(data_dir or ROOT / '.local-data/personal-agent')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.chmod(0o700)
        self.store = store or FoundationStore(self.data_dir / 'foundation.sqlite3')
        self.skills = SkillRegistry(service, plans)
        self.sessions = OrderedDict()

    def _config(self):
        env = dotenv_values(ROOT / '.env')
        def get(k, default=''):
            return str(os.environ.get(k, env.get(k) or default)).strip()
        return {'key': get('ARK_API_KEY'), 'model': get('ARK_MODEL'),
                'base': get('ARK_BASE_URL', 'https://ark.cn-beijing.volces.com/api/v3').rstrip('/')}

    @property
    def configured(self):
        cfg = self._config()
        return bool(cfg['key'] and cfg['model'])

    def _session(self, owner):
        state = self.store.session(owner)
        session = self.sessions.get(owner)
        if session is None or session.conversation_id != state['conversation_id']:
            if session and session.lock.locked():
                raise AgentError('个人资料已变更，请等待当前回复结束后重新尝试。', 409)
            session = Session(**state)
            self.sessions[owner] = session
        self.sessions.move_to_end(owner)
        for key in list(self.sessions):
            if len(self.sessions) <= 64:
                break
            if key != owner and not self.sessions[key].lock.locked():
                del self.sessions[key]
        session.touched = time.monotonic()
        # Restore the adapter's lookup cache from server-owned persisted candidates.
        self.service.stores.update(session.stores)
        return session

    def _plan(self, session, owner):
        return self.plans.get(session.plan_id, owner) if session.plan_id else None

    def _guard(self, session, owner):
        return self.skills._guard(session, owner)

    async def reset(self, owner):
        session = self._session(owner)
        if session.lock.locked():
            raise AgentError('小瑞正在处理当前任务，请稍等。', 409)
        async with session.lock:
            plan = self._guard(session, owner)
            if plan and plan['status'] in {'awaiting_confirmation', 'needs_review', 'expired'}:
                self.plans.cancel(plan['id'], owner)
            self.store.new_session(owner)
            self.sessions.pop(owner, None)
        return {'ok': True}

    def history(self, owner):
        session = self._session(owner)
        messages = copy.deepcopy(session.display)
        for message in messages:
            refreshed = []
            for event in message.get('events', []):
                if event.get('type') == 'plan':
                    try:
                        event['plan'] = self.plans.get(event['plan']['id'], owner)
                    except PlanError:
                        continue
                refreshed.append(event)
            if 'events' in message:
                message['events'] = refreshed
        return {'messages': messages, 'conversation_id': session.conversation_id}

    def foundation_status(self):
        return {'runtime': 'nanobot', 'runtime_version': '0.4.0',
                'profile_id': self.store.PROFILE_ID, 'session_storage': 'persistent',
                'skills': catalog(), 'tools': list(SCHEMAS),
                'business_expansion': 'paused', 'autonomous_orders': False}

    def tasks(self, owner):
        epoch = self.store.profile()['forget_epoch']
        tasks = self.store.list_tasks(owner)
        for task in tasks:
            if task.get('forget_epoch') != epoch:
                task['input'] = '[旧资料删除前的任务，内容不再展示]'
                task['result'] = None
                task['error'] = None
        return {'tasks': tasks}

    async def _tool(self, session, owner, name, arguments, events):
        if name != 'personal_profile':
            return await self.skills.dispatch(session, owner, name, arguments, events)
        try:
            args = SCHEMAS[name][0].model_validate(arguments)
            if args.action == 'list':
                return self.store.profile()
            if args.action == 'set':
                profile = self.store.set_fact(args.key, args.value)
                return {'saved': True, 'key': args.key, 'profile': profile}
            # Invalidating the conversation generation prevents old SDK history recall.
            profile = self.store.delete_fact(args.key)
            current = self.store.session(owner)
            session.conversation_id = current['conversation_id']
            session.forget_epoch = current['forget_epoch']
            session.display.clear()
            session.stores.clear()
            session.meals.clear()
            # Keep the plan pointer while this turn finishes so writes stay guarded.
            current['plan_id'] = session.plan_id
            return {'forgotten': True, 'key': args.key, 'profile': profile,
                    'history_policy': '旧会话不再用于回答；历史审计文件未物理擦除。'}
        except (ValidationError, ValueError):
            return {'error': '资料操作参数无效，请明确要保存或忘记的内容。'}

    async def _run(self, owner, session, text, events, trace):
        async def dispatch(name, arguments):
            result = await self._tool(session, owner, name, arguments, events)
            if isinstance(result, dict) and 'error' in result:
                trace.append({'type': 'tool.error', 'name': name})
            return result

        async def context(request):
            return [data_context('canonical_profile', self.store.profile()),
                    data_context('current_candidates', {
                        'stores': list(session.stores.values()),
                        'meals': [{'index': i+1, 'name': m['name'], 'amount_cents': m['amount_cents']}
                                  for i, m in enumerate(session.meals)],
                        'plan': ({k: v for k, v in (self._plan(session, owner) or {}).items()
                                  if k in {'summary', 'amount_cents', 'status'}})})]

        owner_key = hashlib.sha256(owner.encode()).hexdigest()[:32]
        key = f'xiaorui:{owner_key}:{session.conversation_id}:e{session.forget_epoch}'
        bot = build_runtime(self._config(), self.data_dir / 'runtime', dispatch, context)
        result = None
        async with bot:
            async for event in bot.stream(text, session_key=key):
                if event.type in {'run.started', 'tool.started', 'tool.completed', 'tool.failed', 'run.completed'}:
                    trace.append({'type': event.type, **({'name': event.name} if event.name else {})})
                if event.type == 'run.completed':
                    result = event.result
        if result is None or result.error or result.stop_reason != 'completed':
            raise AgentError('小瑞本次任务尚未完成，请查看已有结果后重试。')
        if not isinstance(result.content, str) or not result.content.strip():
            raise AgentError('小瑞暂时没有生成回复，请重试。')
        return result.content.strip()

    def _answer(self, owner, session, text, answer, events, trace, task_id):
        response = {'text': answer, 'speech_text': answer[:1200], 'events': events,
                    'runtime': 'nanobot', 'task_id': task_id, 'trace': trace}
        session.display.extend([{'role': 'user', 'text': text.strip()},
                                {'role': 'assistant', **copy.deepcopy(response)}])
        session.display = session.display[-48:]
        self.store.save_session(owner, session.snapshot())
        return response

    async def chat(self, owner, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise AgentError('请发送 1 到 2000 字的消息。', 400)
        if not self.configured:
            raise AgentError('请先配置豆包文本模型，再开始对话。', 503)
        session = self._session(owner)
        if session.lock.locked():
            raise AgentError('小瑞正在回复，请稍等。', 409)
        async with session.lock:
            events, trace = [], []
            task_id = self.store.start_task(owner, session.conversation_id, text)
            try:
                async with asyncio.timeout(180):
                    answer = await self._run(owner, session, text.strip(), events, trace)
                response = self._answer(owner, session, text, answer, events, trace, task_id)
                pending = any(e['type'] == 'plan' and e['plan']['status'] in {'awaiting_confirmation', 'needs_review'} for e in events)
                status = 'waiting_confirmation' if pending else 'completed'
                self.store.finish_task(task_id, status, result={'text': answer, 'trace': trace})
                return response
            except asyncio.CancelledError:
                self.store.finish_task(task_id, 'interrupted', error='本次任务中断，未自动重试。')
                raise
            except Exception:
                # Preserve already completed real operations and cards without claiming further success.
                self.store.finish_task(task_id, 'failed', error='本次任务未完整完成，未自动重试。')
                if events:
                    answer = '已查询的真实结果见卡片，后续处理暂未完成。请核对，尚未下单。'
                    return self._answer(owner, session, text, answer, events, trace, task_id)
                raise AgentError('小瑞暂时无法完成任务，请检查模型配置或网络后重试。') from None
