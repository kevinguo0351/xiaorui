"""Boundary tests with injected responses, never real transactions or credentials."""
import tempfile
import logging
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agent import AgentService
from app.life_services import OfficialMcp, ServiceUnavailable, CredentialFilter
from app.plans import PlanStore


class LifeServicesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        service = SimpleNamespace(stores={})
        self.agent = AgentService(service, PlanStore(Path(self.tmp.name)/'plans.sqlite3'),
                                  data_dir=Path(self.tmp.name)/'agent')
        self.agent.life_skills.luckin.call = AsyncMock()
        self.agent.life_skills.didi.call = AsyncMock()

    def tearDown(self):
        self.tmp.cleanup()

    async def tool(self, name, args, owner='a'):
        return await self.agent._tool(self.agent._session(owner), owner, name, args, [])

    async def test_remote_write_denied_before_connection(self):
        for provider, name in [('luckin', 'createOrder'), ('luckin', 'cancelOrder'), ('didi', 'taxi_create_order')]:
            adapter = OfficialMcp(provider)
            with patch.object(adapter, 'connection') as connection:
                with self.assertRaises(ServiceUnavailable):
                    await adapter.call(name, {})
                connection.assert_not_called()

    async def test_credentials_redacted_from_transport_exception_log(self):
        guard = CredentialFilter()
        guard.secrets.add('unit-private-key')
        try:
            raise RuntimeError('https://example.invalid/?key=unit-private-key')
        except RuntimeError:
            import sys
            record = logging.LogRecord('httpx', logging.ERROR, '', 0,
                'request failed: %s', ('unit-private-key',), sys.exc_info())
        guard.filter(record)
        self.assertNotIn('unit-private-key', logging.Formatter().format(record))

    async def test_encoded_credentials_redacted_from_message_and_exception(self):
        import sys
        from urllib.parse import quote_plus
        secret = 'offline-only+/= value'
        encoded = quote_plus(secret)
        guard = CredentialFilter()
        guard.secrets.add(secret)
        try:
            raise RuntimeError('https://example.invalid/?key=' + encoded.lower())
        except RuntimeError:
            record = logging.LogRecord('httpx', logging.ERROR, '', 0,
                'request URL https://example.invalid/?key=%s&other=kept', (encoded,), sys.exc_info())
        guard.filter(record)
        rendered = logging.Formatter().format(record)
        for marker in (secret, encoded, encoded.lower()):
            self.assertNotIn(marker, rendered)
        self.assertIn('other=kept', rendered)
        self.assertIn('[REDACTED]', rendered)

    async def test_luckin_foreign_or_fabricated_choice_cannot_reach_provider(self):
        call = self.agent.life_skills.luckin.call
        call.return_value = [{'deptId': 123, 'deptName': 'unit'}]
        await self.tool('luckin_search_stores', {'longitude':116.4,'latitude':39.9})
        call.reset_mock()
        result = await self.tool('luckin_search_products', {'store_index':1,'query':'unit'}, 'b')
        self.assertIn('error', result)
        call.assert_not_awaited()
        result = await self.tool('luckin_preview', {'product_index':True})
        self.assertIn('error', result)
        call.assert_not_awaited()

    async def test_luckin_preview_uses_exact_server_product(self):
        call = self.agent.life_skills.luckin.call
        call.side_effect = [[{'deptId':123,'deptName':'unit'}],
                            [{'productId':456,'skuCode':'official-sku','productName':'unit'}],
                            {'discountPrice':10}]
        await self.tool('luckin_search_stores', {'longitude':116.4,'latitude':39.9})
        await self.tool('luckin_search_products', {'store_index':1,'query':'unit'})
        result = await self.tool('luckin_preview', {'product_index':1,'quantity':2})
        call.assert_awaited_with('previewOrder', {'deptId':123,'productList':[
            {'productId':456,'skuCode':'official-sku','amount':2}]})
        self.assertFalse(result['order_created'])
        self.assertFalse(result['paid'])

    async def test_failed_store_refresh_invalidates_old_candidates(self):
        call = self.agent.life_skills.luckin.call
        call.return_value = [{'deptId':123}]
        await self.tool('luckin_search_stores', {'longitude':116.4,'latitude':39.9})
        call.side_effect = ServiceUnavailable('unit failure')
        await self.tool('luckin_search_stores', {'longitude':116.4,'latitude':39.9})
        call.reset_mock()
        self.assertIn('error', await self.tool('luckin_search_products', {'store_index':1,'query':'unit'}))
        call.assert_not_awaited()

    async def test_didi_requires_both_scoped_places_and_uses_returned_coordinates(self):
        call = self.agent.life_skills.didi.call
        call.side_effect = [[{'display_name':'unit-origin','location':{'lng':116.4,'lat':39.9}}],
                            [{'display_name':'unit-destination','location':{'lng':116.5,'lat':39.95}}],
                            {'items':[{'priceText':'10'}], 'routes':[{'latitude':39.9}],
                             'phoneNumberSuffix':'unit-private', 'traceId':'unit-trace',
                             'to':{'name':'unit-platform-destination'}}]
        await self.tool('didi_search_places', {'purpose':'origin','keyword':'unit origin'})
        missing = await self.tool('didi_estimate_ride', {'origin_index':1,'destination_index':1})
        self.assertIn('error', missing)
        await self.tool('didi_search_places', {'purpose':'destination','keyword':'unit destination'})
        result = await self.tool('didi_estimate_ride', {'origin_index':1,'destination_index':1})
        call.assert_awaited_with('taxi_estimate', {'from_lng':'116.4','from_lat':'39.9',
            'from_name':'unit-origin','to_lng':'116.5','to_lat':'39.95','to_name':'unit-destination'})
        self.assertFalse(result['order_created'])
        self.assertEqual(result['actual_places']['to']['name'], 'unit-platform-destination')
        for key in ('routes', 'phoneNumberSuffix', 'traceId'):
            self.assertNotIn(key, result)

    async def test_service_candidates_survive_restart_and_reset(self):
        session = self.agent._session('a')
        session.services = {'luckin': {'stores':[{'deptId':123}]}}
        self.agent.store.save_session('a', session.snapshot())
        other = AgentService(self.agent.service, self.agent.plans, data_dir=self.agent.data_dir)
        self.assertEqual(other._session('a').services, session.services)
        self.assertEqual(other._session('b').services, {})
        await other.reset('a')
        self.assertEqual(other._session('a').services, {})

    async def test_business_failure_is_not_returned_as_success(self):
        adapter = OfficialMcp('luckin')
        fake_session = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
            isError=False, structuredContent={'code':403,'data':[]}, content=[])))
        @asynccontextmanager
        async def connection():
            yield fake_session, {'queryShopList':SimpleNamespace(inputSchema={'type':'object'})}
        with patch.object(adapter, 'connection', connection):
            with self.assertRaises(ServiceUnavailable):
                await adapter.call('queryShopList', {})
