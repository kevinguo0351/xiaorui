"""Real official reads for a multi-item meal; never creates orders/addresses.

.venv/bin/python -m experiments.mcd_elderly_acceptance --live
Uses Beijing public pickup landmark to avoid private delivery address writes.
Full private report stays ignored in .local-data; stdout contains no account data.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.actions import ActionManager
from app.mcd_scenario import McdScenario
from experiments.services_acceptance import ReadOnlyMcd

ROOT=Path(__file__).resolve().parents[1]


async def run():
    directory=ROOT/'.local-data/mcd-elderly-acceptance'/uuid4().hex
    directory.mkdir(parents=True,mode=0o700)
    manager=ActionManager(directory/'actions.sqlite3',enabled=lambda _:False)
    scenario=McdScenario(manager,ReadOnlyMcd())
    manager.register('mcd',scenario)
    session=SimpleNamespace(services={})
    report={'passed':False,'business_writes':False,'real_official_reads':True,'steps':[]}
    async def step(name,args):
        result=await scenario.dispatch(session,'elderly-readonly-test',name,args,[])
        report['steps'].append({'tool':name,'result':result})
        if 'error' in result:
            raise ValueError(name+' failed')
        return result
    try:
        await step('mcd_search_pickup',{'keyword':'王府井'})
        stores=session.services['mcd']['stores']
        index=next(i+1 for i,s in enumerate(stores) if s.get('open') is not False)
        for keyword in ('麦香鱼','薯条'):
            await step('mcd_menu',{'store_index':index,'keyword':keyword})
            products=session.services['mcd']['products']
            selected=None
            for i,product in enumerate(products):
                detail=await step('mcd_product_detail',{'product_index':i+1})
                if not detail.get('rounds'):
                    selected=i+1
                    break
            if selected is None:
                raise ValueError('no simple item available')
            await step('mcd_cart',{'action':'add','product_index':selected})
        choices=await step('mcd_prepare_cart',{'budget_cents':100000})
        way=next(w['index'] for w in choices['take_ways'] if '外带' in str(w) or '自提' in str(w))
        result=await step('mcd_prepare_cart',{'budget_cents':100000,'take_way_index':way})
        plan=result['plan']
        stored=manager.get('elderly-readonly-test',plan['id'])
        fresh=await scenario.quote('create',stored['request'])
        if len(stored['request']['payload']['items'])!=2:
            raise ValueError('cart did not retain both products')
        if fresh['comparison']!=stored['comparison']:
            raise ValueError('quote changed; needs review')
        manager.cancel_local('elderly-readonly-test',plan['id'])
        report.update(passed=True,item_count=2,amount_cents=plan['amount_cents'],requote_matches=True)
    except Exception as exc:
        report['failure_type']=type(exc).__name__
    finally:
        path=directory/'report.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        path.chmod(0o600)
    print(json.dumps({k:v for k,v in report.items() if k!='steps'},ensure_ascii=False))
    print('Private report: '+str(path))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if not args.live: parser.error('--live required')
    logging.disable(logging.CRITICAL)
    raise SystemExit(asyncio.run(run()))
