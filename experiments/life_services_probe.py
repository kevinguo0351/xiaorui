"""Discover real official account capabilities, without calling business writes.

Usage: .venv/bin/python experiments/life_services_probe.py luckin|didi
Only credential-free diagnostics are printed; no URL containing a Key is logged.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.life_services import OfficialMcp, ServiceUnavailable
from app.service_skills import LifeSkills


async def beijing_didi():
    skills, session = LifeSkills(), SimpleNamespace(services={})
    for purpose, keyword in [('origin', '北京西站'), ('destination', '国贸商城')]:
        response = await skills.dispatch(session, 'didi_search_places', {
            'purpose': purpose, 'keyword': keyword})
        if 'error' in response:
            raise ServiceUnavailable(response['error'])
        if not response.get('places'):
            raise ServiceUnavailable('北京公开地点未返回候选。')
    # First candidates are selected only for this read-only probe, not a ride.
    response = await skills.dispatch(session, 'didi_estimate_ride', {
        'origin_index': 1, 'destination_index': 1})
    if 'error' in response:
        raise ServiceUnavailable(response['error'])
    data = response['estimate']
    if not isinstance(data, dict) or not isinstance(data.get('items'), list) or not data['items']:
        raise ServiceUnavailable('估价未返回可用车型，不能视为真实估价通过。')
    return {'location_source': 'public-landmarks-not-user-location',
            'origin': session.services['didi']['origin'][0]['display_name'],
            'destination': session.services['didi']['destination'][0]['display_name'],
            'estimates': [{'product': item.get('productName'), 'price': item.get('priceText')}
                          for item in data['items']],
            'order_created': False}


async def main(provider, beijing=False):
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    result = {'provider': provider, 'connected': False}
    try:
        result = await OfficialMcp(provider).discover()
        if beijing and provider == 'didi':
            result['beijing_read_validation'] = await beijing_didi()
        if beijing and provider == 'luckin':
            skills, session = LifeSkills(), SimpleNamespace(services={})
            # Public Beijing test coordinate from DiDi's official examples.
            # This is not a location measurement of the current user.
            stores = await skills.dispatch(session, 'luckin_search_stores', {
                'longitude':116.397128,'latitude':39.916527})
            if 'error' in stores:
                raise ServiceUnavailable(stores['error'])
            if not stores['stores']:
                raise ServiceUnavailable('北京公开测试点没有返回门店。')
            products = await skills.dispatch(session, 'luckin_search_products', {
                'store_index':1,'query':'拿铁'})
            if 'error' in products:
                raise ServiceUnavailable(products['error'])
            if not products['products']:
                raise ServiceUnavailable('所选测试门店没有返回饮品。')
            preview = await skills.dispatch(session, 'luckin_preview', {'product_index':1})
            if 'error' in preview:
                raise ServiceUnavailable(preview['error'])
            result['beijing_read_validation'] = {
                'location_source':'public-test-coordinate-not-user-location',
                'stores_returned':len(stores['stores']),
                'store_name':stores['stores'][0]['name'],
                'products_returned':len(products['products']),
                'product_name':products['products'][0].get('productName'),
                'preview_ok':True, 'order_created':False,
                'amount':preview['preview'].get('discountPrice'),
            }
    except ServiceUnavailable as exc:
        print(json.dumps({**result, 'validation_passed': False, 'error': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['luckin', 'didi'])
    parser.add_argument('--beijing', action='store_true', help='北京真实查询验证：瑞幸查店饮品预览，滴滴地点与估价；不下单')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.provider, args.beijing)))
