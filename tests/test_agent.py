"""Host policy tests use temporary state and no real model or merchant calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agent import AgentService, AgentError, TOOLS
from app.plans import PlanStore
from app.nanobot_runtime import build_runtime, AgentLoop
from app.skills import SCHEMAS


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plans = PlanStore(Path(self.tmp.name) / 'plans.sqlite3')
        self.service = AsyncMock()
        self.service.stores = {}
        self.agent = AgentService(self.service, self.plans, data_dir=Path(self.tmp.name)/'agent')
        self.cfg = patch.object(self.agent, '_config', return_value={'key':'test-only', 'model':'test-only', 'base':'https://unused.invalid/v1'})
        self.cfg.start()

    def tearDown(self):
        self.cfg.stop()
        self.tmp.cleanup()

    async def test_real_nanobot_composition_has_exact_capability_and_no_commands(self):
        captured = []
        original = AgentLoop.from_config
        def capture(*args, **kwargs):
            loop = original(*args, **kwargs)
            captured.append(loop)
            return loop
        with patch('app.nanobot_runtime.AgentLoop.from_config', side_effect=capture):
            bot = build_runtime(self.agent._config(), Path(self.tmp.name)/'runtime', AsyncMock(), AsyncMock(return_value=[]))
        try:
            self.assertEqual(set(captured[0].tool_names), set(SCHEMAS))
            self.assertEqual({t['function']['name'] for t in TOOLS}, set(SCHEMAS))
            for name in ('/dream','/restart','/exec','/model'):
                self.assertIsNone(captured[0].commands.command_name(name))
            self.assertNotIn('exec', captured[0].tool_names)
        finally:
            await bot.aclose()

    async def test_unknown_write_tool_and_invalid_selection_cannot_execute(self):
        session = self.agent._session('a')
        for name,args in [('create_order',{}),('confirm',{}),('choose_meal',{'index':True}),('choose_meal',{'index':1}),('recommend_meals',{'store_code':'invented','budget_cents':3500})]:
            events=[]
            self.assertIn('error',await self.agent._tool(session,'a',name,args,events))
            self.assertEqual(events,[])
        self.service.prepare_plan.assert_not_awaited()
        self.service.create_order.assert_not_awaited()

    async def test_restart_restores_history_and_candidates_but_owners_stay_isolated(self):
        session=self.agent._session('a')
        session.stores={'unit':{'code':'unit'}}
        self.agent._run=AsyncMock(return_value='请问在哪附近？')
        await self.agent.chat('a','test private context')
        other=AgentService(self.service,self.plans,data_dir=self.agent.data_dir)
        self.assertIn('test private context',str(other.history('a')))
        self.assertNotIn('test private context',str(other.history('b')))
        self.assertIn('unit',other._session('a').stores)
        self.assertEqual(other._session('b').stores,{})

    async def test_failed_search_has_no_success_event(self):
        self.service.search_stores.side_effect=RuntimeError('private failure')
        events=[]
        result=await self.agent._tool(self.agent._session('a'),'a','search_stores',{'city':'unit','keyword':'unit'},events)
        self.assertIn('error',result)
        self.assertNotIn('private failure',str(result))
        self.assertEqual(events,[])

    async def test_plan_uses_trusted_candidate_and_hides_confirmation_token(self):
        session=self.agent._session('a');request={'store_code':'unit','product_code':'unit','quantity':1,'rounds':[]}
        session.meals=[{'request':request}]
        self.service.prepare_plan.return_value={'request':{'trusted':'unit'},'amount_cents':3500,'summary':{'product_name':'unit'}}
        events=[]
        result=await self.agent._tool(session,'a','choose_meal',{'index':1},events)
        self.service.prepare_plan.assert_awaited_once_with(request)
        self.assertNotIn('confirmation_token',str(result))
        self.assertIn('confirmation_token',events[0]['plan'])
        self.service.create_order.assert_not_awaited()

    async def test_same_owner_reentry_is_rejected(self):
        async with self.agent._session('a').lock:
            with self.assertRaises(AgentError) as caught:await self.agent.chat('a','hello')
        self.assertEqual(caught.exception.status,409)

    async def test_model_failure_preserves_real_events_and_failed_task(self):
        async def failure(owner,session,text,events,trace):
            events.append({'type':'stores','stores':[]})
            raise RuntimeError('private failure')
        self.agent._run=failure
        result=await self.agent.chat('a','find store')
        self.assertEqual(result['events'][0]['type'],'stores')
        self.assertIn('尚未下单',result['text'])
        self.assertNotIn('private failure',result['text'])
        self.assertEqual(self.agent.tasks('a')['tasks'][0]['status'],'failed')

    async def test_reset_changes_thread_but_preserves_profile(self):
        before=self.agent._session('a').conversation_id
        self.agent.store.set_fact('preference.drink','不要冰')
        await self.agent.reset('a')
        self.assertNotEqual(before,self.agent._session('a').conversation_id)
        self.assertIn('不要冰',str(self.agent.store.profile()))
