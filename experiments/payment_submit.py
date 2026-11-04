"""Submit one explicitly approved private payment-test plan, never pay or ride.

Only use after the user confirms that exact merchant/item/store/amount. Required
digest binds the reviewed plan. No automatic retries, no payment tools, no DiDi.
"""
import argparse
import asyncio
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.life_services import OfficialMcp
from app.mcd import McdService, McdRejectedError
from jsonschema import validate

DIRECTORY = Path(__file__).resolve().parents[1] / '.local-data/payment-probe'


def write(path, plan):
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        json.dump(plan, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


@contextmanager
def claim(provider, digest):
    path = DIRECTORY / (provider + '.json')
    lock = path.with_suffix('.lock')
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        plan = json.loads(path.read_text())
        payload = dict(plan)
        stored = payload.pop('digest')
        if (plan['status'] != 'prepared' or digest != stored or
                hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() != digest):
            raise RuntimeError('方案已变化或执行过，不能提交。')
        if time.time() - plan['prepared_at'] > 1800:
            raise RuntimeError('方案已过期，请重新查询并核对。')
        yield path, plan
    finally:
        lock.unlink()


async def luckin_preflight(plan):
    service = OfficialMcp('luckin')
    quote = await service.call('previewOrder', plan['preview_request'])
    if not isinstance(quote, dict) or Decimal(str(quote.get('discountPrice'))) != Decimal(plan['summary']['amount_yuan']):
        raise RuntimeError('瑞幸报价变化，必须重新确认。')
    # An old coupon selection must not silently change during submission.
    if (quote.get('couponCodeList') or []) != (plan['quote'].get('couponCodeList') or []):
        raise RuntimeError('瑞幸优惠方案变化，必须重新确认。')
    return service


async def main(provider, digest):
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    with claim(provider, digest) as (path, plan):
        # Everything before the submitting marker is read-only.
        if provider == 'luckin':
            service = await luckin_preflight(plan)
            async with service.connection() as (session, tools):
                if 'createOrder' not in tools:
                    raise RuntimeError('账号未开放创建订单工具。')
                validate(plan['create_request'], tools['createOrder'].inputSchema)
                plan.update(status='submitting', submitted_at=time.time())
                write(path, plan)
                try:
                    result = await session.call_tool('createOrder', arguments=plan['create_request'])
                    # Persist the response before parsing so an unfamiliar shape
                    # can be reconciled without issuing another creation request.
                    encoded = json.dumps(result.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False)
                    plan['provider_response'] = json.loads(encoded.replace(service._credential(), '[REDACTED]'))
                    write(path, plan)
                    # Preserve uncertain outcomes; never call creation again.
                    payload = result.structuredContent
                    if payload is None:
                        values = []
                        for block in result.content:
                            if block.type == 'text':
                                try:
                                    values.append(json.loads(block.text))
                                except ValueError:
                                    pass
                        payload = values[0] if len(values) == 1 else None
                    if result.isError or not isinstance(payload, dict) or payload.get('code') != 0 or payload.get('success') is False:
                        raise RuntimeError('创建结果需要核查。')
                    data = payload.get('data')
                    if not isinstance(data, dict) or not data.get('orderId'):
                        raise RuntimeError('创建结果缺少订单号。')
                    plan.update(status='created', order={key:data[key] for key in (
                        'orderId', 'orderIdStr', 'payOrderUrl', 'payOrderQrCodeUrl', 'needPay', 'discountPrice') if key in data})
                except BaseException:
                    plan['status'] = 'unknown'
                    write(path, plan)
                    raise
        else:
            service = McdService()
            quote = await service.requote(plan['create_request'])
            if quote['amount_cents'] != plan['amount_cents'] or plan['create_request']['takeWayCode'] not in quote['take_way_codes']:
                raise RuntimeError('麦当劳价格或取餐方式变化，必须重新确认。')
            plan.update(status='submitting', submitted_at=time.time())
            write(path, plan)
            try:
                data = await service.create_order(plan['create_request'])
                plan['provider_response'] = data
                write(path, plan)
                if not data.get('order_id'):
                    raise RuntimeError('创建结果缺少订单号。')
                plan.update(status='created', order={'order_id':data['order_id'], 'payment_url':data.get('payment_url')})
            except McdRejectedError:
                plan['status'] = 'rejected'
                write(path, plan)
                raise
            except BaseException:
                plan['status'] = 'unknown'
                write(path, plan)
                raise
        write(path, plan)
        print(json.dumps({'provider':provider, 'status':plan['status'],
            'payment_action_executed':False, 'order':plan['order']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['luckin', 'mcd'])
    parser.add_argument('--approved-digest', required=True,
                        help='Exact digest of the plan explicitly confirmed by the user')
    args = parser.parse_args()
    try:
        asyncio.run(main(args.provider, args.approved_digest))
    except Exception as exc:
        print(json.dumps({'provider':args.provider, 'error_type':type(exc).__name__,
                          'note':'未自动重试。请查看本地执行记录；unknown/submitting 不可再次提交。'},ensure_ascii=False))
        raise SystemExit(1)
