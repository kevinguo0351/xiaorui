"""Real ASGI boundary checks with isolated state and no external requests."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx

from app.agent import AgentService
from app.plans import PlanStore


class ActionApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import app.main as api
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        agent=AgentService(SimpleNamespace(stores={}),PlanStore(root/'plans.sqlite3'),data_dir=root/'agent')
        agent.actions._enabled=lambda _:True
        self.quote={'request':{},'summary':{'商品':'unit'},'amount_cents':1000,'comparison':{'amount':1000}}
        self.adapter=SimpleNamespace(quote=AsyncMock(return_value=self.quote),execute=AsyncMock(return_value={'order_id':'unit-order'}))
        agent.actions.register('mcd',self.adapter)
        self.agent=agent
        self.patch=patch.object(api,'agent',agent);self.patch.start()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://localhost')
        await self.client.get('/api/health')
        self.owner=self.client.cookies['pa_session']
        self.plan=agent.actions.prepare(self.owner,'mcd','create',{},self.quote)

    async def asyncTearDown(self):
        await self.client.aclose();self.patch.stop();self.tmp.cleanup()

    def body(self):
        return {'version':self.plan['version'],'confirmation_token':self.plan['confirmation_token'],'confirmation_text':'确认下单'}

    async def test_foreign_cookie_and_boolean_version_cannot_execute(self):
        url=f'/api/actions/{self.plan["id"]}/confirm'
        body=self.body();body['version']=True
        self.assertEqual((await self.client.post(url,json=body)).status_code,422)
        self.client.cookies.clear()
        self.assertEqual((await self.client.post(url,json=self.body())).status_code,404)
        self.adapter.execute.assert_not_awaited()

    async def test_exact_card_confirmation_executes_once(self):
        url=f'/api/actions/{self.plan["id"]}/confirm'
        first=await self.client.post(url,json=self.body())
        second=await self.client.post(url,json=self.body())
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json()['plan']['status'],'created')
        self.assertEqual(second.json()['plan']['status'],'created')
        self.adapter.execute.assert_awaited_once()

    async def test_cancel_conditions_owner_bound_and_never_submit(self):
        plan=self.agent.actions.prepare(self.owner,'didi','create',{},self.quote)
        scenario=self.agent.scenarios['didi']
        scenario.dispatch=AsyncMock(return_value={'error':'平台未返回明确取消费，请到滴滴官方订单页核对。'})
        url=f'/api/actions/{plan["id"]}/prepare-cancel'
        result=await self.client.post(url,json={})
        self.assertEqual(result.status_code,409)
        self.assertIn('取消费',result.json()['detail'])
        scenario.dispatch.assert_awaited_once()
        scenario.dispatch.reset_mock()
        self.client.cookies.clear()
        self.assertEqual((await self.client.post(url,json={})).status_code,404)
        scenario.dispatch.assert_not_awaited()

    async def test_cancel_conditions_return_proposal_not_execution(self):
        plan=self.agent.actions.prepare(self.owner,'didi','create',{},self.quote)
        proposal=self.agent.actions.prepare(self.owner,'didi','cancel',{},self.quote)
        scenario=self.agent.scenarios['didi']
        scenario.dispatch=AsyncMock(return_value={'plan':proposal})
        result=await self.client.post(f'/api/actions/{plan["id"]}/prepare-cancel',json={})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['plan']['confirmation_text'],'确认取消')
        self.assertEqual(result.json()['plan']['status'],'awaiting_confirmation')
        self.adapter.execute.assert_not_awaited()

    async def test_address_confirmation_http_with_orders_disabled(self):
        self.agent.actions._enabled=lambda _:False
        request=dict(city='北京',address='测试大楼',addressDetail='101',contactName='测试',phone='13800000000')
        scenario=self.agent.scenarios['mcd']
        self.agent.actions.register('mcd',scenario)
        events=[]
        result=await scenario.dispatch(self.agent._session(self.owner),self.owner,'mcd_prepare_address',request,events)
        plan=result['plan']
        scenario.execute=AsyncMock(return_value={'address_id':'new-address','status':'address_created'})
        url=f'/api/actions/{plan["id"]}/confirm'
        body=dict(version=plan['version'],confirmation_token=plan['confirmation_token'],confirmation_text='确认新增地址')
        result=await self.client.post(url,json=body)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['plan']['status'],'address_created')
        self.assertIn('地址',result.json()['speech_text'])
        result=await self.client.post(url,json=body)
        self.assertEqual(result.json()['plan']['status'],'address_created')
        scenario.execute.assert_awaited_once_with('create_address',request)
