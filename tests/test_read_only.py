"""Companion preview policy tests: no model or upstream requests."""
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app import read_only
from app.actions import ActionError, ActionManager
from app.agent import AgentService
from app.main import app
from app.mcd import McdService, mcd_token
from app.nanobot_runtime import AgentLoop, build_runtime
from app.plans import PlanStore
from app.skills import SCHEMAS


class ReadOnlyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.policy = patch.object(read_only, 'READ_ONLY', True)
        self.policy.start()

    def tearDown(self):
        self.policy.stop()
        self.temp.cleanup()

    async def test_runtime_only_registers_explicit_queries(self):
        captured = []
        original = AgentLoop.from_config
        def capture(*args, **kwargs):
            loop = original(*args, **kwargs)
            captured.append(loop)
            return loop
        with patch('app.nanobot_runtime.AgentLoop.from_config', side_effect=capture):
            bot = build_runtime({'model':'test', 'key':'test', 'base':'https://unused.invalid/v1'},
                                self.root/'runtime', AsyncMock(), AsyncMock(return_value=[]))
        try:
            self.assertEqual(set(captured[0].tool_names), read_only.QUERY_TOOLS)
        finally:
            await bot.aclose()

    async def test_host_denies_every_nonquery_tool_even_with_forged_dispatch(self):
        merchant = AsyncMock()
        merchant.stores = {}
        agent = AgentService(merchant, PlanStore(self.root/'plans.sqlite3'), data_dir=self.root/'agent')
        for name in set(SCHEMAS) - read_only.QUERY_TOOLS | {'create_order', 'pay', 'exec'}:
            with self.subTest(name=name):
                events = []
                result = await agent._tool(agent._session('owner'), 'owner', name, {}, events)
                self.assertIn('error', result)
                self.assertEqual(events, [])
        merchant.create_order.assert_not_awaited()

    async def test_query_receipts_distinguish_success_from_tool_error(self):
        merchant = AsyncMock()
        merchant.stores = {}
        agent = AgentService(merchant, PlanStore(self.root/'plans.sqlite3'), data_dir=self.root/'agent')
        scenario = agent.scenario_tools['mcd_product_detail']
        for result in ({'name': '官方餐品', 'rounds': []}, {'error': '请先选择本轮餐品'}):
            events = []
            with patch.object(scenario, 'dispatch', new_callable=AsyncMock, return_value=result):
                await agent._tool(agent._session('owner'), 'owner', 'mcd_product_detail', {}, events)
            receipt = next(e for e in events if e['type'] == 'query_result')
            self.assertEqual(receipt['success'], 'error' not in result)
            self.assertEqual(receipt['source'], 'https://open.mcd.cn/mcp')
            self.assertEqual(receipt['data'], result)

    async def test_voice_confirmation_cannot_reach_old_pending_action(self):
        merchant = AsyncMock()
        merchant.stores = {}
        agent = AgentService(merchant, PlanStore(self.root/'plans.sqlite3'), data_dir=self.root/'agent')
        with patch.object(agent, '_config', return_value={'key':'test', 'model':'test'}), \
             patch.object(agent.actions, 'confirm', new_callable=AsyncMock) as confirm:
            for phrase in ('确认下单', '确认叫车', '确认取消'):
                result = await agent.chat('owner', phrase)
                self.assertIn('只读', result['text'])
            confirm.assert_not_awaited()

    async def test_action_gateway_blocks_before_plan_lookup_even_if_execution_enabled(self):
        actions = ActionManager(self.root/'actions.sqlite3', enabled=lambda _: True)
        with self.assertRaises(ActionError):
            actions.prepare('owner', 'mcd', 'create', {}, {})
        with self.assertRaises(ActionError) as caught:
            await actions.confirm('owner', 'missing', 1, 'token', '确认下单')
        self.assertEqual(caught.exception.status, 403)

    async def test_legacy_merchant_mutation_blocks_before_connection(self):
        service = McdService()
        with patch.object(service, '_connection') as connect:
            with self.assertRaisesRegex(RuntimeError, '只读'):
                await service.create_order({})
            connect.assert_not_called()

    async def test_http_blocks_mutations_and_health_reports_effective_policy(self):
        with TestClient(app, base_url='http://localhost') as client:
            for path in ('/api/plans', '/api/plans/old/confirm', '/api/actions/old/confirm',
                         '/api/actions/old/cancel-plan', '/api/contact/images'):
                response = client.post(path, json={})
                self.assertEqual(response.status_code, 403, path)
            response = client.delete('/api/plans/old')
            self.assertEqual(response.status_code, 403)
            health = client.get('/api/health').json()
            self.assertTrue(health['read_only'])
            self.assertFalse(health['order_execution_enabled'])
            self.assertEqual(client.get('/api/voice/status').status_code, 200)
            self.assertEqual(client.post('/api/mcd/stores', json={}).status_code, 422)


class McdConfigurationTests(unittest.TestCase):
    def test_environment_overrides_file_and_whitespace_is_not_configured(self):
        with patch('app.mcd.dotenv_values', return_value={'MCD_MCP_TOKEN':' file-test '}), \
             patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mcd_token(), 'file-test')
            with patch.dict(os.environ, {'MCD_MCP_TOKEN':' env-test '}):
                self.assertEqual(mcd_token(), 'env-test')
            for empty in ('', '   '):
                with patch.dict(os.environ, {'MCD_MCP_TOKEN':empty}):
                    self.assertFalse(mcd_token())
                    with TestClient(app, base_url='http://localhost') as client:
                        self.assertFalse(client.get('/api/health').json()['mcd_configured'])

    def test_environment_only_credentials_report_configured(self):
        with patch('app.mcd.dotenv_values', return_value={}), \
             patch.dict(os.environ, {'MCD_MCP_TOKEN':' env-test '}):
            self.assertTrue(mcd_token())
            with TestClient(app, base_url='http://localhost') as client:
                self.assertTrue(client.get('/api/health').json()['mcd_configured'])
