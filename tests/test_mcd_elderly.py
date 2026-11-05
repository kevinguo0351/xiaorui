"""Older customers: fragmented address, changing one's mind and a whole meal."""
import unittest
import test_mcd_scenario as scenarios
from app.agent import AgentService
from app.speech import confirmation, action_speech


class ElderlyDiningTests(unittest.IsolatedAsyncioTestCase):
    setUp = scenarios.McdScenarioTests.setUp
    dispatch = scenarios.McdScenarioTests.dispatch
    async def test_address_spoken_in_fragments_and_corrected_without_reasking(self):
        result=await self.dispatch('mcd_address_draft',{'city':'北京'})
        self.assertEqual(result['missing_fields'][0],'address')
        self.assertEqual(result['next'],'请告诉我收餐的小区、酒店或大楼名称。')
        await self.dispatch('mcd_address_draft',{'address':'测试大楼','addressDetail':'前台'})
        await self.dispatch('mcd_address_draft',{'contactName':'测试'})
        result=await self.dispatch('mcd_address_draft',{'phone':'幺三八 零零零零 零零零零'})
        self.assertTrue(result['ready'])
        self.assertEqual(result['draft']['phone'],'13800000000')
        result=await self.dispatch('mcd_address_draft',{'addressDetail':'101室'})
        self.assertEqual(result['draft']['city'],'北京')
        self.assertEqual(result['draft']['addressDetail'],'101室')
        self.assertEqual(self.calls,[])
        self.transactions.prepare.assert_not_called()

    async def test_unclear_phone_preserves_existing_address_and_new_location_resets(self):
        await self.dispatch('mcd_address_draft',{'city':'广州','address':'测试楼'})
        result=await self.dispatch('mcd_address_draft',{'phone':'138****0000'})
        self.assertIn('error',result)
        result=await self.dispatch('mcd_address_draft',{})
        self.assertEqual(result['draft'],{'city':'广州','address':'测试楼'})
        result=await self.dispatch('mcd_address_draft',{'reset':True,'city':'北京'})
        self.assertEqual(result['draft'],{'city':'北京'})

    def cart_setup(self):
        self.session.services['mcd']={'mode':'delivery','selected_store':{'storeCode':'S','beCode':'B','storeName':'测试店'},
            'selected_address':{'addressId':'A','address':'北京市测试楼','addressDetail':'101'},
            'products':[{'code':'P','name':'麦香鱼'},{'code':'Q','name':'薯条'}]}
        self.responses['query-meal-detail']={'rounds':[]}
        self.responses['calculate-price']={'price':3500,'deliveryPrice':600}
        self.responses['delivery-query-stores']=[{'storeCode':'S','beCode':'B','businessStatus':True}]

    async def test_add_remove_change_quantity_and_quote_entire_meal_with_fees(self):
        self.cart_setup()
        await self.dispatch('mcd_cart',{'action':'add','product_index':1})
        await self.dispatch('mcd_cart',{'action':'add','product_index':2,'quantity':2})
        await self.dispatch('mcd_cart',{'action':'update','line_index':2,'quantity':1})
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False,'budget_cents':3500,'remark':'送到前台'})
        self.assertFalse(result['order_created'])
        quote=self.transactions.prepare.call_args.kwargs['quote']
        self.assertEqual(quote['request']['payload']['items'],[{'productCode':'P','quantity':1},{'productCode':'Q','quantity':1}])
        self.assertIn('麦香鱼 × 1',quote['summary']['product'])
        self.assertIn('薯条 × 1',quote['summary']['product'])
        self.assertEqual(quote['amount_cents'],3500)
        self.assertIn('6.00',quote['summary']['fee_breakdown'])
        self.assertEqual(quote['summary']['remark'],'送到前台')
        self.gateway.create_order.assert_not_awaited()
        await self.dispatch('mcd_cart',{'action':'remove','line_index':1})
        result=await self.dispatch('mcd_cart',{})
        self.assertEqual(result['cart'][0]['name'],'薯条')
        await self.dispatch('mcd_cart',{'action':'clear'})
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False})
        self.assertIn('购物车是空的',result['error'])

    async def test_cart_preserved_across_same_store_search_but_cleared_for_new_store(self):
        self.cart_setup()
        state=self.session.services['mcd']
        state['stores']=[state['selected_store'],{'storeCode':'other','beCode':'B','storeName':'另一个店'}]
        self.responses['query-meals']={'meals':{'Q':{'name':'薯条'}}}
        await self.dispatch('mcd_cart',{'action':'add','product_index':1})
        await self.dispatch('mcd_menu',{'store_index':1,'keyword':'薯条'})
        await self.dispatch('mcd_cart',{'action':'add','product_index':1})
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False})
        self.assertNotIn('error',result)
        items=self.transactions.prepare.call_args.kwargs['request']['payload']['items']
        self.assertEqual([i['productCode'] for i in items],['P','Q'])
        await self.dispatch('mcd_menu',{'store_index':2})
        self.assertFalse(state.get('cart'))

    async def test_whole_meal_budget_tableware_choices_and_changed_fee(self):
        self.cart_setup()
        await self.dispatch('mcd_cart',{'action':'add','product_index':1})
        result=await self.dispatch('mcd_prepare_cart',{})
        self.assertTrue(result['needs_tableware'])
        self.transactions.prepare.assert_not_called()
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False,'budget_cents':3000})
        self.assertIn('超过明确预算',result['error'])
        self.transactions.prepare.assert_not_called()
        self.responses['query-meal-detail']={'rounds':[{'id':'r','minQuantity':1,'maxQuantity':1,'choices':[{'code':'C','name':'配餐'}]}]}
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False})
        self.assertTrue(result['needs_choices'])
        await self.dispatch('mcd_cart',{'action':'update','line_index':1,'choices':[{'round_id':'r','code':'C'}]})
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False,'budget_cents':3500})
        self.assertNotIn('error',result)
        request=self.transactions.prepare.call_args.kwargs['request']
        self.responses['calculate-price']['price']=3501
        with self.assertRaisesRegex(ValueError,'超过明确预算'):
            await self.scenario.quote('create',request)

    async def test_cart_mutations_invalidate_confirmation_but_show_is_readonly(self):
        self.cart_setup()
        await self.dispatch('mcd_cart',{'action':'add','product_index':1})
        self.transactions.invalidate_pending.assert_called_with('owner')
        self.transactions.invalidate_pending.reset_mock()
        await self.dispatch('mcd_cart',{'action':'show'})
        self.transactions.invalidate_pending.assert_not_called()
        result=await self.dispatch('mcd_cart',{'action':'remove','line_index':2})
        self.assertIn('error',result)
        self.assertEqual(len(self.session.services['mcd']['cart']),1)

    async def test_order_list_excludes_address_creation(self):
        self.transactions.list.return_value=[{'action':'create_address'}, {'action':'create'}]
        self.transactions.public.side_effect=lambda p:p
        result=await self.dispatch('mcd_orders',{})
        self.assertEqual(result['orders'],[{'action':'create'}])

    async def test_explicit_new_city_and_administrative_prefix_not_road_name(self):
        self.responses['delivery-query-addresses']={'addresses':[
            {'addressId':'A','fullAddress':'江苏省南京市测试大楼'},
            {'addressId':'B','fullAddress':'广东省广州市南京路测试大楼'},
            {'addressId':'C','city':'南京市','address':'测试楼'}]}
        result=await self.dispatch('mcd_delivery_addresses',{'city':'南京市'})
        self.assertEqual(len(result['addresses']),2)
        self.assertEqual([a['addressId'] for a in self.session.services['mcd']['addresses']],['A','C'])
        self.gateway.search_stores.return_value=[]
        await self.dispatch('mcd_search_pickup',{'city':'南京','keyword':'测试地点'})
        self.gateway.search_stores.assert_awaited_once_with('南京','测试地点')

    async def test_adding_food_does_not_silently_drop_previously_stated_budget(self):
        self.cart_setup()
        await self.dispatch('mcd_cart',{'action':'add','product_index':1})
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False,'budget_cents':3500})
        self.assertNotIn('error',result)
        await self.dispatch('mcd_cart',{'action':'add','product_index':2})
        self.responses['calculate-price']['price']=4000
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False})
        self.assertIn('超过明确预算',result['error'])
        result=await self.dispatch('mcd_prepare_cart',{'need_tableware':False,'budget_cents':4500})
        self.assertNotIn('error',result)
        self.assertEqual(self.transactions.prepare.call_args.kwargs['request']['budget_cents'],4500)
