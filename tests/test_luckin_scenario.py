import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from app.luckin_scenario import LuckinScenario
from app.life_services import ServiceUnavailable


class LuckinScenarioTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider=SimpleNamespace(call=AsyncMock(),call_confirmed=AsyncMock())
        self.transactions=Mock()
        self.transactions.prepare.return_value={'id':'plan','provider':'luckin','status':'awaiting_confirmation'}
        self.scenario=LuckinScenario(self.transactions,self.provider)
        self.store={'deptId':1,'deptName':'测试门店','longitude':116.4,'latitude':39.9}
        self.product={'productId':2,'productName':'测试饮品','skuCode':'sku-real','productAttrs':[]}
        self.session=SimpleNamespace(services={'luckin':{'stores':[self.store],'selected_store':self.store,'products':[self.product]}})
        self.events=[]

    async def dispatch(self,name,args):
        return await self.scenario.dispatch(self.session,'owner',name,args,self.events)

    async def test_prepare_binds_returned_sku_and_never_writes(self):
        self.provider.call.return_value={'discountPrice':'9.90','couponCodeList':['coupon-real']}
        result=await self.dispatch('luckin_prepare_order',{'product_index':1,'quantity':2,'budget_cents':2000})
        self.assertIn('plan',result)
        request=self.transactions.prepare.call_args.kwargs['request']
        self.assertEqual(request['productList'],[{'productId':2,'skuCode':'sku-real','amount':2}])
        self.assertEqual(self.transactions.prepare.call_args.kwargs['quote']['amount_cents'],990)
        self.provider.call_confirmed.assert_not_awaited()
        self.assertEqual(self.events[0]['type'],'action_plan')

    async def test_budget_and_boolean_quantity_reject_without_plan(self):
        self.provider.call.return_value={'discountPrice':10}
        result=await self.dispatch('luckin_prepare_order',{'product_index':1,'budget_cents':999})
        self.assertTrue(result['over_budget'])
        self.assertIn('error',await self.dispatch('luckin_prepare_order',{'product_index':1,'quantity':True}))
        self.transactions.prepare.assert_not_called()

    async def test_safe_host_error_and_candidate_invalidation(self):
        from app.actions import ActionError
        self.provider.call.return_value={'discountPrice':10}
        self.transactions.prepare.side_effect=ActionError('此前请求待核查，请查官方订单。')
        result=await self.dispatch('luckin_prepare_order',{'product_index':1})
        self.assertEqual(result['error'],'此前请求待核查，请查官方订单。')
        self.transactions.invalidate_pending.assert_called_once_with('owner')

    async def test_price_and_sku_changes_affect_confirmation_comparison(self):
        request={'deptId':1,'productList':[{'productId':2,'skuCode':'one','amount':1}],'_summary':{}}
        self.provider.call.side_effect=[{'discountPrice':10},{'discountPrice':11},{'discountPrice':11}]
        first=await self.scenario.quote('create',request)
        second=await self.scenario.quote('create',request)
        request['productList'][0]['skuCode']='two'
        third=await self.scenario.quote('create',request)
        self.assertNotEqual(first['comparison'],second['comparison'])
        self.assertNotEqual(second['comparison'],third['comparison'])
        self.assertEqual(third['request']['productList'][0]['skuCode'],'two')

    async def test_missing_store_and_delivery_request_cannot_create_plan(self):
        self.session.services={'luckin':{}}
        result=await self.dispatch('luckin_search_products',{'store_index':1,'query':'拿铁'})
        self.assertIn('请先查询',result['error'])
        result=await self.dispatch('luckin_prepare_order',{'product_index':1,'fulfillment':'delivery'})
        self.assertIn('error',result)
        self.transactions.prepare.assert_not_called()
        self.provider.call.assert_not_awaited()
        self.provider.call_confirmed.assert_not_awaited()

    async def test_closed_store_cannot_prepare_and_requote_detects_closure(self):
        self.session.services['luckin']['selected_store']['deptTags']=['打烊中']
        result=await self.dispatch('luckin_prepare_order',{'product_index':1})
        self.assertIn('打烊',result['error'])
        self.transactions.prepare.assert_not_called()
        self.provider.call.assert_not_awaited()
        self.provider.call.return_value={'discountPrice':9.9,'shopInfo':{'deptTags':['暂停接单']}}
        with self.assertRaises(ServiceUnavailable):
            await self.scenario.quote('create',{'deptId':1,'productList':[],'_summary':{}})
        self.provider.call_confirmed.assert_not_awaited()

    async def test_persisted_budget_blocks_one_cent_price_rise_and_is_not_sent(self):
        self.provider.call.return_value={'discountPrice':'15.00'}
        await self.dispatch('luckin_prepare_order',{'product_index':1,'budget_cents':1500})
        request=self.transactions.prepare.call_args.kwargs['request']
        self.assertEqual(request['_budget_cents'],1500)
        self.provider.call.return_value={'discountPrice':'15.01'}
        with self.assertRaises(ServiceUnavailable) as caught:
            await self.scenario.quote('create',request)
        self.assertIn('超过原定预算',str(caught.exception))
        self.assertNotIn('_budget_cents',self.provider.call.call_args.args[1])
        self.provider.call_confirmed.assert_not_awaited()

    async def test_changed_coupons_are_part_of_comparison(self):
        request={'deptId':1,'productList':[],'_summary':{}}
        self.provider.call.side_effect=[{'discountPrice':10,'couponCodeList':['one']},{'discountPrice':10,'couponCodeList':['two']}]
        one=await self.scenario.quote('create',request);two=await self.scenario.quote('create',request)
        self.assertNotEqual(one['comparison'],two['comparison'])

    async def test_failed_refresh_clears_old_candidates(self):
        self.provider.call.side_effect=ServiceUnavailable('unit')
        self.assertIn('error',await self.dispatch('luckin_search_stores',{'longitude':116.4,'latitude':39.9}))
        self.assertEqual(self.session.services['luckin'],{})

    async def test_switch_uses_actual_option_and_new_sku(self):
        detail={'productId':2,'productAttrs':[{'attributeId':3,'attributeName':'温度','productSubAttrs':[{'attributeId':4,'attributeName':'热','canSelected':1}]}]}
        self.provider.call.side_effect=[detail,{**self.product,'skuCode':'new-real-sku'}]
        await self.dispatch('luckin_switch_product',{'product_index':1,'attribute':'温度','value':'热'})
        args=self.provider.call.call_args.args
        self.assertEqual(args[0],'switchProduct');self.assertEqual(args[1]['attrOperationParam']['subAttr']['attributeId'],4)
        self.assertEqual(self.session.services['luckin']['products'][0]['skuCode'],'new-real-sku')
        self.provider.call_confirmed.assert_not_awaited()

    async def test_unknown_order_cannot_query_or_cancel(self):
        self.transactions.get.return_value={'provider':'luckin','status':'unknown','order':None}
        for name in ('luckin_query_order','luckin_prepare_cancel'):
            self.assertIn('error',await self.dispatch(name,{'transaction_id':'unknown'}))
        self.provider.call.assert_not_awaited();self.provider.call_confirmed.assert_not_awaited()

    async def test_unknown_cancel_fee_is_not_treated_as_zero(self):
        self.provider.call.return_value={'orderStatus':10}
        with self.assertRaises(ServiceUnavailable):await self.scenario.quote('cancel',{'order_id':'unit'})
        self.provider.call_confirmed.assert_not_awaited()

    async def test_unrecognized_write_response_attaches_evidence(self):
        self.provider.call_confirmed.return_value={'unrecognized':'response'}
        with self.assertRaises(ServiceUnavailable) as caught:
            await self.scenario.execute('create',{'deptId':1,'productList':[],'longitude':116.4,'latitude':39.9})
        self.assertEqual(caught.exception.provider_response,{'unrecognized':'response'})
        self.provider.call_confirmed.assert_awaited_once()
