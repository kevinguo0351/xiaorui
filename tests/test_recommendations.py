"""Offline tests with an isolated adapter double; no real accounts or orders."""
import unittest
from app.recommendations import default_rounds, recommend


class CatalogDouble:
    def __init__(self):
        self.stores = {'test': {'code': 'test', 'name': '测试门店', 'address': '', 'open': True}}
        self.products = [
            {'code': str(i), 'name': f'单人套餐{i}', 'price_yuan': '20', 'image': f'https://example.invalid/{i}.png'}
            for i in range(8)
        ]
        self.quoted = []
        self.detail_calls = 0
        self.amount = 2000
        self.network_failure = False
        self.missing_default = False

    async def menu(self, store_code):
        return self.products

    async def detail(self, store_code, product_code):
        self.detail_calls += 1
        if self.network_failure:
            raise RuntimeError('unit test connection failure')
        return {'rounds': [{'id': 1, 'minQuantity': 1, 'maxQuantity': 1,
                            'choices': [{'code': 'real-choice-from-double',
                                         'isDefault': 0 if self.missing_default else 1}]}]}

    async def prepare_plan(self, request):
        self.quoted.append(request)
        return {'amount_cents': self.amount,
                'summary': {'product_name': '核价返回的名称', 'choices': ['主食', '小食', '饮料']}}


class RecommendationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_quote_amount_and_composition_are_returned(self):
        service = CatalogDouble()
        service.amount = 2300
        result = await recommend(service, 'test', 3500, 2)
        self.assertEqual(len(result['recommendations']), 2)
        self.assertEqual(len(service.quoted), 2)
        self.assertEqual(result['recommendations'][0]['amount_cents'], 2300)
        self.assertEqual(result['recommendations'][0]['name'], '核价返回的名称')
        self.assertEqual(result['recommendations'][0]['choices'], ['主食', '小食', '饮料'])
        self.assertEqual(result['mode'], 'pickup')
        self.assertNotIn('plan', result)

    async def test_stale_menu_hint_cannot_override_actual_over_budget_quote(self):
        service = CatalogDouble()
        service.amount = 3600
        result = await recommend(service, 'test', 3500, 3)
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(service.detail_calls, 5)

    async def test_missing_defaults_are_not_invented(self):
        service = CatalogDouble()
        service.missing_default = True
        result = await recommend(service, 'test')
        self.assertEqual(result['recommendations'], [])
        self.assertEqual(service.quoted, [])

    async def test_all_network_failures_do_not_become_empty_success(self):
        service = CatalogDouble()
        service.network_failure = True
        with self.assertRaises(RuntimeError):
            await recommend(service, 'test')

    async def test_non_meals_duplicate_and_unaffordable_hints_filtered(self):
        service = CatalogDouble()
        service.products = [service.products[0], service.products[0],
                            {'code': 'drink', 'name': '可乐', 'price_yuan': '10'},
                            {'code': 'expensive', 'name': '大套餐', 'price_yuan': '99'}]
        result = await recommend(service, 'test')
        self.assertEqual(len(result['recommendations']), 1)
        self.assertEqual(len(service.quoted), 1)

    async def test_unknown_store_rejected_before_query(self):
        service = CatalogDouble()
        with self.assertRaises(ValueError):
            await recommend(service, 'unknown')
        self.assertEqual(service.detail_calls, 0)

    def test_multi_select_or_duplicate_rounds_not_silently_reduced(self):
        row = {'id': 1, 'minQuantity': 1, 'maxQuantity': 2,
               'choices': [{'code': 'a', 'isDefault': 1}]}
        self.assertIsNone(default_rounds({'rounds': [row]}))
        row['maxQuantity'] = 1
        self.assertIsNone(default_rounds({'rounds': [row, row]}))
