"""Real service walkthroughs up to a confirmation card; never submit orders.

Run: python -m experiments.services_acceptance --live [mcd luckin didi]
Public Beijing landmarks and deterministic selections are test inputs only.
This validates production scenario adapters, not human/browser usability.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.actions import ActionManager
from app.didi_scenario import DidiScenario
from app.life_services import OfficialMcp
from app.life_services import ServiceUnavailable
from app.luckin_scenario import LuckinScenario
from app.mcd import McdService
from app.mcd_scenario import McdScenario

ROOT = Path(__file__).resolve().parents[1]
MCD_READS = {'query-nearby-stores', 'query-meals', 'query-meal-detail', 'calculate-price'}


class ReadOnlyMcd(McdService):
    @asynccontextmanager
    async def _connection(self):
        async with super()._connection() as upstream:
            async def call(name, args):
                if name not in MCD_READS:
                    raise RuntimeError('Read-only acceptance blocked this tool')
                return await upstream(name, args)
            yield call

    async def create_order(self, payload):
        raise RuntimeError('Read-only acceptance cannot create orders')


class ReadOnlyOfficial(OfficialMcp):
    async def call_confirmed(self, name, arguments):
        raise RuntimeError('Read-only acceptance cannot execute transactions')


async def walkthrough(provider, directory):
    manager = ActionManager(directory / 'actions.sqlite3', enabled=lambda _: False)
    adapters = {
        'mcd': lambda: McdScenario(manager, ReadOnlyMcd()),
        'luckin': lambda: LuckinScenario(manager, ReadOnlyOfficial('luckin')),
        'didi': lambda: DidiScenario(manager, ReadOnlyOfficial('didi')),
    }
    adapter = adapters[provider]()
    session, events, steps = SimpleNamespace(services={}), [], []
    owner = 'read-only-acceptance'
    report = {'provider': provider, 'scope': 'real-scenario-adapter',
              'test_location': 'public-beijing-landmarks-not-user-location',
              'steps': steps, 'passed': False, 'business_writes': False}

    async def step(name, **arguments):
        result = await adapter.dispatch(session, owner, name, arguments, events)
        # Persist only a summary, never raw account responses or capabilities.
        item = {'tool': name, 'ok': 'error' not in result}
        for key in ('stores', 'products', 'places', 'vehicles', 'take_ways'):
            if isinstance(result.get(key), list):
                item[key + '_count'] = len(result[key])
        steps.append(item)
        if 'error' in result:
            raise RuntimeError('scenario-step-failed')
        return result

    def choose(items):
        candidate = next((x for x in items if x.get('open') is not False), None)
        if candidate is None:
            raise RuntimeError('no-available-candidates')
        return candidate['index']

    try:
        async with asyncio.timeout(240):
            if provider == 'mcd':
                stores = await step('mcd_search_pickup', keyword='王府井')
                store = choose(stores['stores'])
                products = await step('mcd_menu', store_index=store, keyword='麦香鱼')
                product = next((p['index'] for p in products['products'] if p['name'] == '麦香鱼'), None)
                if product is None:
                    raise RuntimeError('test-single-item-not-available')
                detail = await step('mcd_product_detail', product_index=product)
                if detail.get('rounds'):
                    raise RuntimeError('test-single-item-requires-options')
                args = {'product_index': product, 'quantity': 1, 'budget_cents': 3500}
                ways = await step('mcd_prepare_order', **args)
                takeaway = next((x for x in ways.get('take_ways', [])
                                 if '外带' in str(x) or '打包' in str(x)), None)
                if takeaway is None:
                    raise RuntimeError('no-takeaway-choice')
                result = await step('mcd_prepare_order', **args, take_way_index=takeaway['index'])
            elif provider == 'luckin':
                stores = await step('luckin_search_stores', longitude=116.397128,
                                    latitude=39.916527, keyword='东华门')
                products = await step('luckin_search_products', store_index=choose(stores['stores']), query='拿铁')
                product = choose(products['products'])
                await step('luckin_product_detail', product_index=product)
                result = await step('luckin_prepare_order', product_index=product,
                                    quantity=1, budget_cents=3500)
            else:
                origin = await step('didi_search_places', purpose='origin', keyword='北京西站')
                destination = await step('didi_search_places', purpose='destination', keyword='国贸商城')
                vehicles = await step('didi_estimate_ride', origin_index=choose(origin['places']),
                                      destination_index=choose(destination['places']))
                result = await step('didi_prepare_ride', vehicle_index=choose(vehicles['vehicles']))
            plan = result.get('plan')
            if not plan or plan['status'] != 'awaiting_confirmation' or plan.get('order'):
                raise RuntimeError('missing-valid-confirmation-card')
            stored = manager.get(owner, plan['id'])
            steps.append({'tool': 'host_requote', 'ok': False})
            quote = await adapter.quote(stored['action'], stored['request'])
            steps[-1]['ok'] = True
            report.update(confirmation_card=True, amount_cents=plan['amount_cents'],
                          summary=plan['summary'], requote_received=True,
                          requote_unchanged=quote['comparison'] == stored['comparison'])
            if quote['comparison'] != stored['comparison']:
                raise RuntimeError('quote-changed-requires-new-review')
            manager.cancel_local(owner, plan['id'])
            report.update(passed=True, local_plan_cancelled=True)
    except Exception as exc:
        report['failure_type'] = type(exc).__name__
        if isinstance(exc, ServiceUnavailable):
            report['failure_reason'] = str(exc)
            if hasattr(exc, 'diagnostic'):
                report['diagnostic'] = exc.diagnostic
        report['failed_after'] = steps[-1]['tool'] if steps else 'initialization'
    return report


async def main(providers):
    logging.disable(logging.CRITICAL)
    directory = ROOT / '.local-data/service-acceptance' / uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'live': True,
              'business_writes': False, 'results': []}
    for provider in providers:
        result = await walkthrough(provider, directory / provider)
        report['results'].append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        path = directory / 'report.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        path.chmod(0o600)
    print('Private report: ' + str(directory / 'report.json'))
    return 0 if all(x['passed'] for x in report['results']) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Call real read-only APIs')
    parser.add_argument('providers', nargs='*', metavar='PROVIDER', help='mcd luckin didi; 默认全部')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required; no mock fallback')
    if any(p not in {'mcd', 'luckin', 'didi'} for p in args.providers):
        parser.error('providers must be mcd, luckin, or didi')
    raise SystemExit(asyncio.run(main(args.providers or ['mcd', 'luckin', 'didi'])))
