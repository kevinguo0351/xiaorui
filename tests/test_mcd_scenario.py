"""Scenario contract tests: injected gateway, never merchant transactions."""
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.mcd_scenario import McdScenario


class McdScenarioTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls=[]
        self.gateway=SimpleNamespace(create_order=AsyncMock(), search_stores=AsyncMock())
        self.responses={}
        @asynccontextmanager
        async def connection():
            async def call(name,args):
                self.calls.append((name,args))
                return self.responses[name]
            yield call
        self.gateway._connection=connection
        self.transactions=Mock()
        self.transactions.prepare.return_value={'id':'plan','provider':'mcd','status':'awaiting_confirmation'}
        self.scenario=McdScenario(self.transactions,self.gateway)
        self.session=SimpleNamespace(services={})

    async def dispatch(self,name,args):
        return await self.scenario.dispatch(self.session,'owner',name,args,[])

    async def test_delivery_requires_user_address_and_does_not_guess_store(self):
        result=await self.dispatch('mcd_delivery_stores',{'address_index':1})
        self.assertIn('error',result)
        self.assertEqual(self.calls,[])
        self.responses['delivery-query-addresses']=[{'addressId':'A','city':'北京','address':'测试小区','phone':'private'}]
        result=await self.dispatch('mcd_delivery_addresses',{})
        self.assertNotIn('private',str(result))
        self.assertNotIn('private',str(self.session.services))
        self.responses['delivery-query-stores']=[{'storeCode':'S','beCode':'B','storeName':'unit'}]
        await self.dispatch('mcd_delivery_stores',{'address_index':1})
        self.assertEqual(self.calls[-1][1],{'addressId':'A','beType':2})

    async def test_pickup_requires_explicit_way_before_preparing_and_never_submits(self):
        self.session.services['mcd']={'mode':'pickup','selected_store':{'code':'S','name':'unit'},
            'products':[{'code':'P','name':'unit product'}]}
        self.responses['query-meal-detail']={'rounds':[]}
        self.responses['calculate-price']={'price':2200,'takeWayList':[{'code':'eat-in','title':'堂食'},{'code':'take-in-store','title':'外带'}]}
        result=await self.dispatch('mcd_prepare_order',{'product_index':1})
        self.assertIn('take_ways',result)
        self.transactions.prepare.assert_not_called()
        result=await self.dispatch('mcd_prepare_order',{'product_index':1,'take_way_index':2})
        self.assertFalse(result['order_created'])
        _,kwargs=self.transactions.prepare.call_args
        self.assertEqual(kwargs['request']['payload']['takeWayCode'],'take-in-store')
        self.assertEqual(kwargs['quote']['amount_cents'],2200)
        self.gateway.create_order.assert_not_awaited()

    async def test_delivery_quote_includes_address_and_real_total(self):
        self.session.services['mcd']={'mode':'delivery','selected_store':{'storeCode':'S','beCode':'B','storeName':'unit'},
            'selected_address':{'addressId':'A','address':'北京测试小区','addressDetail':'测试门牌'},
            'products':[{'code':'P','name':'unit product'}]}
        self.responses['query-meal-detail']={'rounds':[]}
        self.responses['calculate-price']={'price':2800,'deliveryFee':600}
        self.responses['delivery-query-stores']=[{'storeCode':'S','beCode':'B','businessStatus':True}]
        result=await self.dispatch('mcd_prepare_order',{'product_index':1,'need_tableware':False})
        self.assertFalse(result['order_created'])
        _,kwargs=self.transactions.prepare.call_args
        self.assertEqual(kwargs['quote']['amount_cents'],2800)
        self.assertEqual(kwargs['request']['payload']['beCode'],'B')
        self.assertEqual(kwargs['request']['payload']['addressId'],'A')
        price_args=next(args for name,args in self.calls if name=='calculate-price')
        self.assertNotIn('addressId',price_args)
        self.assertEqual(kwargs['quote']['comparison']['fees'],{'deliveryFee':600})
        changed=await self.scenario.quote('create',kwargs['request'])
        self.assertEqual(changed['comparison'],kwargs['quote']['comparison'])

    async def test_cancel_requires_owned_created_order_and_explicit_fee(self):
        self.transactions.get.return_value={'provider':'luckin','order':{'order_id':'other'}}
        self.assertIn('error',await self.dispatch('mcd_prepare_cancel',{'plan_id':'x'}))
        self.assertEqual(self.calls,[])
        self.transactions.get.return_value={'provider':'mcd','order':{'order_id':'ours'}}
        self.responses['query-order']={'orderStatus':'待支付','status':'10'}
        result=await self.dispatch('mcd_prepare_cancel',{'plan_id':'x'})
        self.assertIn('取消费用',result['error'])
        self.transactions.prepare.assert_not_called()
        self.assertTrue(all(name!='cancel-order' for name,_ in self.calls))

    async def test_order_query_hides_contact_and_address(self):
        self.responses['query-order']={'orderDetail':{'orderStatus':'待支付','mobilePhone':'private','deliveryAddress':'private','totalAmount':'22'}}
        result=await self.scenario.query_order('ours')
        self.assertEqual(result,{'orderStatus':'待支付','totalAmount':'22'})

    async def test_orders_are_public_and_refresh_invalidates_pending(self):
        self.transactions.list.return_value=[{'id':'x','request':{'private':'unit'},'confirmation_token':'unit-secret'}]
        self.transactions.public.return_value={'id':'x','status':'created'}
        result=await self.dispatch('mcd_orders',{})
        self.assertEqual(result,{'orders':[{'id':'x','status':'created'}]})
        self.gateway.search_stores.return_value=[]
        await self.dispatch('mcd_search_pickup',{'keyword':'unit'})
        self.transactions.invalidate_pending.assert_called_with('owner')

    async def test_closed_store_cannot_prepare_submission(self):
        self.session.services['mcd']={'mode':'pickup','selected_store':{'code':'S','name':'unit','open':False},
            'products':[{'code':'P','name':'unit product'}]}
        result=await self.dispatch('mcd_prepare_order',{'product_index':1,'take_way_index':1})
        self.assertIn('未营业',result['error'])
        self.transactions.prepare.assert_not_called()
        self.assertEqual(self.calls,[])

    async def test_closed_menu_is_explained_without_calling_provider(self):
        self.session.services['mcd']={'mode':'pickup','stores':[{'code':'S','name':'unit','open':False}],
            'selected_store':{'code':'old'},'products':[{'code':'old'}]}
        result=await self.dispatch('mcd_menu',{'store_index':1})
        self.assertIn('未营业',result['error'])
        self.assertEqual(self.calls,[])
        self.assertNotIn('products',self.session.services['mcd'])
        self.transactions.invalidate_pending.assert_called_with('owner')

    async def test_final_total_budget_is_enforced_on_prepare_and_requote(self):
        self.responses['delivery-query-stores']=[{'storeCode':'S','beCode':'B','businessStatus':True}]
        self.session.services['mcd']={'mode':'delivery','selected_store':{'storeCode':'S','beCode':'B','storeName':'unit'},
            'selected_address':{'addressId':'A','address':'北京测试小区'},
            'products':[{'code':'P','name':'unit product'}]}
        self.responses['query-meal-detail']={'rounds':[]}
        self.responses['calculate-price']={'price':2800,'deliveryFee':600}
        result=await self.dispatch('mcd_prepare_order',{'product_index':1,'need_tableware':False,'budget_cents':2500})
        self.assertIn('超过明确预算',result['error'])
        self.transactions.prepare.assert_not_called()
        result=await self.dispatch('mcd_prepare_order',{'product_index':1,'need_tableware':False,'budget_cents':2800})
        self.assertFalse(result['order_created'])
        request=self.transactions.prepare.call_args.kwargs['request']
        self.assertEqual(request['budget_cents'],2800)
        self.assertNotIn('budget_cents',request['payload'])
        self.responses['calculate-price']={'price':2801,'deliveryFee':600}
        with self.assertRaisesRegex(ValueError,'超过明确预算'):
            await self.scenario.quote('create',request)

    async def test_non_beijing_addresses_require_setup_without_leaking_contact(self):
        self.responses['delivery-query-addresses']={'addresses':[
            {'addressId':'A','fullAddress':'广州市北京路测试地址','phone':'private-phone','contactName':'private-name'}]}
        result=await self.dispatch('mcd_delivery_addresses',{})
        self.assertTrue(result['needs_setup'])
        self.assertEqual(result['addresses'],[])
        self.assertNotIn('private',str(result))
        self.assertEqual(self.session.services['mcd']['addresses'],[])

    async def test_guangzhou_is_explicit_and_does_not_become_default(self):
        self.responses['delivery-query-addresses']={'addresses':[
            {'addressId':'A','fullAddress':'广东省广州市测试地址'},
            {'addressId':'B','fullAddress':'北京市测试地址'}]}
        result=await self.dispatch('mcd_delivery_addresses',{'city':'广州'})
        self.assertEqual(len(result['addresses']),1)
        self.assertEqual(self.session.services['mcd']['addresses'][0]['addressId'],'A')
        result=await self.dispatch('mcd_delivery_addresses',{})
        self.assertEqual(len(result['addresses']),1)
        self.assertEqual(self.session.services['mcd']['addresses'][0]['addressId'],'B')

    async def test_delivery_uses_official_fee_units_and_explicit_tableware_and_remark(self):
        request={'payload':{'orderType':2},'labels':{'tableware':'不需要餐具','remark':'请放门口'},'budget_cents':3500}
        quote=self.scenario._quoted(request,{'price':3500,'deliveryPrice':600,'packingPrice':100,'tablewarePrice':0})
        self.assertEqual(quote['summary']['fee_breakdown'],'配送费 6.00 元；打包费 1.00 元；餐具费 0.00 元')
        self.assertEqual(quote['amount_cents'],3500)
        self.assertEqual(quote['summary']['remark'],'请放门口')
        self.assertEqual(quote['summary']['tableware'],'不需要餐具')

    async def test_confirm_rechecks_delivery_availability_before_price_or_write(self):
        request={'payload':{'orderType':2,'addressId':'A','storeCode':'S','beCode':'B'},'labels':{}}
        for stores in ([],[{'storeCode':'S','beCode':'changed','businessStatus':True}],
                       [{'storeCode':'S','beCode':'B','businessStatus':False}]):
            self.responses['delivery-query-stores']=stores
            with self.assertRaisesRegex(ValueError,'无法即时配送'):
                await self.scenario.quote('create',request)
        self.assertTrue(all(name=='delivery-query-stores' for name,_ in self.calls))
        self.gateway.create_order.assert_not_awaited()

    async def test_delivery_progress_extracts_eta_without_contact_details(self):
        self.responses['query-order']={'orderStatus':'配送中','deliveryInfo':{
            'expectDeliveryTime':'2026-11-04 12:30:00','riderNickName':'配送员',
            'mobilePhone':'private','riderMobilePhone':'private','deliveryAddress':'private'}}
        result=await self.scenario.query_order('ours')
        self.assertEqual(result['expectDeliveryTime'],'2026-11-04 12:30:00')
        self.assertNotIn('private',str(result))

    async def test_product_detail_mismatch_never_prepares(self):
        self.session.services['mcd']={'mode':'pickup','selected_store':{'code':'S'},'products':[{'code':'P','name':'test'}]}
        self.responses['query-meal-detail']={'code':'wrong','rounds':[]}
        result=await self.dispatch('mcd_prepare_order',{'product_index':1})
        self.assertIn('不一致',result['error'])
        self.transactions.prepare.assert_not_called()
