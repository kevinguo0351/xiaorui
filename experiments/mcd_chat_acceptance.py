"""Real model + production HTTP routes + official McDonald's reads.

python -m experiments.mcd_chat_acceptance --live
Uses isolated data and a fresh HTTP cookie; never confirms or creates orders.
Stops at a reviewable confirmation card, then cancels the local proposal.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import time
from uuid import uuid4

import httpx

from app.agent import AgentService
from app.plans import PlanStore
from experiments.services_acceptance import ReadOnlyMcd, ReadOnlyOfficial

ROOT = Path(__file__).resolve().parents[1]


async def main():
    logging.disable(logging.CRITICAL)
    from app import main as host
    directory = ROOT / '.local-data/mcd-chat-acceptance' / uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    agent = AgentService(ReadOnlyMcd(), PlanStore(directory / 'plans.sqlite3'),
                         data_dir=directory / 'agent')
    agent.actions._enabled = lambda _: False
    for provider in ('luckin', 'didi'):
        agent.scenarios[provider].provider = ReadOnlyOfficial(provider)
    host.agent = agent
    report = {'real_model': True, 'production_http_routes': True,
              'real_mcd_queries': True, 'business_writes': False,
              'test_location': 'public-beijing-landmark-not-user-location',
              'turns': [], 'passed': False}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host.app),
                                     base_url='http://127.0.0.1:8000', timeout=210) as client:
            async def send(text):
                started = time.monotonic()
                response = await client.post('/api/chat', json={'text': text})
                response.raise_for_status()
                answer = response.json()
                turn = {'input': text, 'response': answer,
                        'seconds': round(time.monotonic() - started, 2)}
                report['turns'].append(turn)
                print(json.dumps({'turn': len(report['turns']), 'seconds': turn['seconds'],
                                  'tools': [x.get('name') for x in answer.get('trace', []) if x.get('name')],
                                  'events': [x['type'] for x in answer.get('events', [])]}, ensure_ascii=False), flush=True)
                return answer

            await client.get('/api/health')
            owner = client.cookies.get('pa_session')
            await send('用北京王府井这个公开测试地点验收麦当劳接口，不保存为个人地址。请查附近门店让我选。我要一份麦香鱼单品，预算35元，到店自取外带；本次只看方案，不创建订单。')
            state = agent._session(owner).services.get('mcd', {})
            store_index = next(i+1 for i, s in enumerate(state.get('stores', [])) if s.get('open') is not False)
            await send(f'选择刚才第{store_index}家门店，请查询麦香鱼单品的菜单和实际选项，不选套餐。')
            state = agent._session(owner).services.get('mcd', {})
            product_index = next(i+1 for i, p in enumerate(state.get('products', [])) if p['name'] == '麦香鱼')
            await send(f'选择第{product_index}项麦香鱼单品，一份，外带，预算35元。请核价并生成待确认方案，不执行下单。')
            plans = (await client.get('/api/actions')).json()['actions']
            pending = [p for p in plans if p['provider'] == 'mcd' and p['status'] == 'awaiting_confirmation']
            if not pending:
                await send('取餐方式选官方返回的外带、店内自提。请生成待确认卡片；本次不下单。')
                plans = (await client.get('/api/actions')).json()['actions']
                pending = [p for p in plans if p['provider'] == 'mcd' and p['status'] == 'awaiting_confirmation']
            if len(pending) != 1:
                raise RuntimeError('expected-one-confirmation-card')
            plan = pending[0]
            if plan.get('order') or not 0 < plan['amount_cents'] <= 3500 or plan['summary']['product'] != '麦香鱼':
                raise RuntimeError('incorrect-plan')
            restored = (await client.get('/api/actions/' + plan['id'])).json()['plan']
            if restored['version'] != plan['version'] or restored['amount_cents'] != plan['amount_cents']:
                raise RuntimeError('plan-refresh-mismatch')
            cancelled = await client.post('/api/actions/' + plan['id'] + '/cancel-plan', json={})
            cancelled.raise_for_status()
            report.update(passed=True, amount_cents=plan['amount_cents'], summary=plan['summary'],
                          confirmation_card_restored=True, local_plan_cancelled=True)
    except Exception as exc:
        report['failure_type'] = type(exc).__name__
    finally:
        path = directory / 'report.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
    print(json.dumps({k:v for k,v in report.items() if k != 'turns'}, ensure_ascii=False))
    print('Private report: ' + str(path))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required; calls real model and service APIs')
    raise SystemExit(asyncio.run(main()))
