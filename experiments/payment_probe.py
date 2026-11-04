"""Prepare concrete payment-entry tests with real queries; never creates orders.

Each provider writes a private review plan under .local-data/payment-probe.
Run providers separately. A prepare run is NOT transaction authorization.
"""
import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.life_services import OfficialMcp, ServiceUnavailable
from app.mcd import McdService
from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / '.local-data/payment-probe'


def save(provider, plan):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    DIRECTORY.chmod(0o700)
    path = DIRECTORY / (provider + '.json')
    if path.exists() and json.loads(path.read_text()).get('status') in {'submitting', 'unknown', 'created'}:
        raise RuntimeError('已有执行记录，必须先核查，不能覆盖或重试。')
    plan.update(provider=provider, status='prepared', prepared_at=time.time())
    plan['digest'] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    path.chmod(0o600)
    return {key: plan[key] for key in ('provider', 'status', 'summary', 'digest')}


async def luckin():
    service = OfficialMcp('luckin')
    # Public test location only; not the current user's measured position.
    stores = await service.call('queryShopList', {'longitude':116.397128, 'latitude':39.916527, 'deptName':'东华门'})
    if not isinstance(stores, list) or not stores:
        raise RuntimeError('没有返回测试门店。')
    store = stores[0]
    products = await service.call('searchProductForMcp', {'deptId':store['deptId'], 'query':'拿铁'})
    if not isinstance(products, list) or not products:
        raise RuntimeError('没有返回测试商品。')
    product = products[0]
    request = {'deptId':store['deptId'], 'productList':[
        {'productId':product['productId'], 'skuCode':product['skuCode'], 'amount':1}]}
    quote = await service.call('previewOrder', request)
    if not isinstance(quote, dict) or quote.get('discountPrice') is None:
        raise RuntimeError('没有取得实际核价，不能准备订单。')
    # Coordinates are the store's actual returned coordinates, not user location.
    create_request = {**request, 'longitude':store['longitude'], 'latitude':store['latitude'],
                      'couponCodeList':quote.get('couponCodeList') or []}
    summary = {'store':store['deptName'], 'address':store.get('address'),
               'product':product.get('productName'), 'quantity':1,
               'amount_yuan':str(quote['discountPrice']), 'fulfillment':'到店自取',
               'attributes':product.get('productAttrs', []),
               'purpose':'仅拟创建待支付订单检查支付入口，不付款'}
    return save('luckin', {'summary':summary, 'preview_request':request,
                           'create_request':create_request, 'quote':quote})


async def mcd():
    service = McdService()
    stores = await service.search_stores('北京', '王府井')
    store = next((item for item in stores if item.get('open')), None)
    if not store:
        raise RuntimeError('没有返回营业中的测试门店。')
    menu = await service.menu(store['code'])
    product = next((item for label in ('麦香鱼', '吉士汉堡', '汉堡包') for item in menu
                    if item['name'] == label), None)
    if not product:
        raise RuntimeError('没有找到可供核对的测试单品。')
    prepared = await service.prepare_plan({'store_code':store['code'], 'product_code':product['code'],
                                           'quantity':1, 'rounds':[]})
    return save('mcd', {'summary':{**prepared['summary'],
        'amount_yuan':f'{prepared["amount_cents"]/100:.2f}',
        'purpose':'仅拟创建待支付订单检查支付入口，不付款'},
        'create_request':prepared['request'], 'amount_cents':prepared['amount_cents']})


async def didi():
    service = OfficialMcp('didi')
    places = []
    for keyword in ('北京西站', '国贸商城'):
        data = await service.call('maps_textsearch', {'keywords':keyword, 'city':'北京市'})
        if not isinstance(data, list) or not data:
            raise RuntimeError('没有取得真实地点，不能生成跳转链接。')
        places.append(data[0])
    arguments = {}
    for prefix, place in zip(('from', 'to'), places):
        arguments.update({prefix+'_lng':str(place['location']['lng']),
                          prefix+'_lat':str(place['location']['lat'])})
    # Read-only URL generation, explicitly named; no arbitrary tool parameter.
    async with service.connection() as (session, tools):
        name = 'taxi_generate_ride_app_link'
        if name not in tools:
            raise RuntimeError('当前账号没有跳转链接工具。')
        validate(arguments, tools[name].inputSchema)
        result = await session.call_tool(name, arguments=arguments)
        if result.isError:
            raise RuntimeError('生成跳转入口失败。')
        data = result.structuredContent
        if data is None:
            values = []
            for block in result.content:
                if block.type == 'text':
                    try:
                        values.append(json.loads(block.text))
                    except ValueError:
                        pass
            if len(values) != 1:
                raise RuntimeError('跳转结果无法解析。')
            data = values[0]
    if service._credential() in json.dumps(data):
        raise RuntimeError('跳转返回包含敏感信息，停止展示。')
    return save('didi', {'summary':{'origin':places[0]['display_name'], 'destination':places[1]['display_name'],
        'purpose':'仅测试跳转入口；没有叫车，没有支付'}, 'link_result':data})


async def main(provider):
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    try:
        result = await {'luckin':luckin, 'mcd':mcd, 'didi':didi}[provider]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Never print upstream errors or credential-bearing URLs.
        print(json.dumps({'provider':provider, 'prepared':False, 'error_type':type(exc).__name__}))
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['luckin', 'mcd', 'didi'])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.provider)))
