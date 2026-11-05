"""New delivery address approval and continuation; no merchant writes in tests."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

from app.actions import ActionManager, ActionError
from app.mcd_scenario import McdScenario


class AddressTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = ActionManager(Path(self.tmp.name)/'actions.sqlite3', enabled=lambda _:False)
        self.calls = []
        self.response = {'addressId':'new-address'}
        @asynccontextmanager
        async def connection():
            async def call(name, args):
                self.calls.append((name,args))
                if name == 'delivery-query-addresses':
                    return {'addresses':[{'addressId':'new-address','fullAddress':'北京市测试大楼 101'}]}
                if name == 'delivery-query-stores':
                    return [{'storeCode':'S','beCode':'B','businessStatus':True}]
                return self.response
            yield call
        self.map = SimpleNamespace(call=AsyncMock(return_value={'formatted_address':'北京市测试大楼'}))
        self.scenario = McdScenario(self.manager, SimpleNamespace(_connection=connection),
            lambda owner: {'longitude':116.3,'latitude':39.9,'accuracy':35} if owner=='owner' else None, self.map)
        self.manager.register('mcd',self.scenario)
        self.session = SimpleNamespace(services={})
        self.address = dict(city='北京',address='测试大楼',addressDetail='101',contactName='测试',phone='13800000000')

    async def prepare(self):
        events=[]
        result=await self.scenario.dispatch(self.session,'owner','mcd_prepare_address',self.address,events)
        self.assertEqual(events[0]['type'],'action_plan')
        return result['plan']

    async def confirm(self,p,owner='owner',text='确认新增地址'):
        return await self.manager.confirm(owner,p['id'],p['version'],p['confirmation_token'],text)

    async def test_confirm_once_then_select_new_address_and_query_delivery(self):
        p=await self.prepare()
        self.assertEqual(self.calls,[])
        self.assertTrue(p['execution_enabled'])
        self.assertEqual(p['summary']['phone'],self.address['phone'])
        with self.assertRaises(ActionError): await self.confirm(p,owner='other')
        with self.assertRaises(ActionError): await self.confirm(p,text='确认下单')
        result=await self.confirm(p)
        self.assertEqual(result['status'],'address_created')
        self.assertEqual(result['order']['address_id'],'new-address')
        await self.confirm(p)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0],('delivery-create-address',self.address))
        await self.scenario.dispatch(self.session,'owner','mcd_delivery_addresses',{},[])
        result=await self.scenario.dispatch(self.session,'owner','mcd_delivery_stores',{'address_index':1},[])
        self.assertNotIn('error',result)
        self.assertEqual(self.calls[-1][1]['addressId'],'new-address')
        self.assertFalse(any(n=='create-order' for n,_ in self.calls))

    async def test_unknown_result_blocks_repeated_creation_even_after_restart(self):
        p=await self.prepare()
        self.response={}
        result=await self.confirm(p)
        self.assertEqual(result['status'],'unknown')
        self.manager.recover_interrupted()
        await self.confirm(p)
        result=await self.scenario.dispatch(self.session,'owner','mcd_prepare_address',self.address,[])
        self.assertIn('error',result)
        self.assertEqual(len(self.calls),1)

    async def test_required_details_and_full_phone(self):
        for key in ('city','address','addressDetail','contactName','phone'):
            args={k:v for k,v in self.address.items() if k!=key}
            result=await self.scenario.dispatch(self.session,'owner','mcd_prepare_address',args,[])
            self.assertIn('error',result)
        self.address['phone']='138****0000'
        result=await self.scenario.dispatch(self.session,'owner','mcd_prepare_address',self.address,[])
        self.assertIn('error',result)
        self.assertEqual(self.calls,[])

    async def test_location_owner_and_geocoder(self):
        events=[]
        result=await self.scenario.dispatch(self.session,'other','mcd_current_location',{},events)
        self.assertEqual(events,[{'type':'location_request'}])
        self.map.call.assert_not_awaited()
        result=await self.scenario.dispatch(self.session,'owner','mcd_current_location',{},[])
        self.assertEqual(result['accuracy_meters'],35)
        self.map.call.assert_awaited_once_with('maps_regeocode',{'location':'116.3,39.9'})
        self.assertEqual(self.calls,[])
