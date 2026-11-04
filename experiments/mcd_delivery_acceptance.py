"""Real, read-only delivery walkthrough. Never creates an order.

Run from repository root: .venv/bin/python -m experiments.mcd_delivery_acceptance
Select indices explicitly to progress; no default address/store/product choice.
Private candidates stay in .local-data/mcd-delivery-development/report.json.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
from types import SimpleNamespace

from app.actions import ActionManager
from app.mcd import McdService
from app.mcd_scenario import McdScenario

ROOT=Path(__file__).resolve().parents[1]
READS={'delivery-query-addresses','delivery-query-stores','query-meals','query-meal-detail','calculate-price'}


class ReadOnlyMcd(McdService):
    @asynccontextmanager
    async def _connection(self):
        async with super()._connection() as upstream:
            async def call(name,args):
                if name not in READS:
                    raise ValueError('验收脚本禁止写入或调用未审核工具。')
                return await upstream(name,args)
            yield call

    async def create_order(self,payload):
        raise RuntimeError('只读验收绝不创建订单。')


async def run(args):
    directory=ROOT/'.local-data/mcd-delivery-development'
    directory.mkdir(parents=True,exist_ok=True)
    directory.chmod(0o700)
    manager=ActionManager(directory/'actions.sqlite3',enabled=lambda _:False)
    scenario=McdScenario(manager,ReadOnlyMcd())
    session=SimpleNamespace(services={})
    results=[]

    async def step(name,parameters):
        result=await scenario.dispatch(session,'read-only-delivery-acceptance',name,parameters,[])
        results.append({'tool':name,'result':result})
        report=directory/'report.json'
        report.write_text(json.dumps(results,ensure_ascii=False,indent=2))
        report.chmod(0o600)
        summary={'tool':name,'ok':'error' not in result}
        for key in ('addresses','stores','products','rounds'):
            if isinstance(result.get(key),list):summary[key+'_count']=len(result[key])
        for key in ('needs_setup','needs_choices','needs_tableware'):
            if key in result:summary[key]=result[key]
        if 'plan' in result:
            summary.update(amount_cents=result['plan']['amount_cents'],execution_enabled=False,order_created=False)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        if 'error' in result:
            raise ValueError('只读步骤未通过；详情保存在本地私有报告中。')
        return result

    addresses=await step('mcd_delivery_addresses',{'city':args.city})
    if addresses.get('needs_setup') or args.address_index is None:return
    await step('mcd_delivery_stores',{'address_index':args.address_index})
    if args.store_index is None:return
    await step('mcd_menu',{'store_index':args.store_index,'keyword':args.keyword})
    if args.product_index is None:return
    detail=await step('mcd_product_detail',{'product_index':args.product_index})
    if args.tableware is None:return
    choices=json.loads(args.choices)
    if detail.get('rounds') and not choices:
        print('套餐需要明确选择各项目；本次停在真实详情，不自动代选。')
        return
    await step('mcd_prepare_order',{'product_index':args.product_index,'budget_cents':args.budget_cents,
        'quantity':args.quantity,'choices':choices,'need_tableware':args.tableware=='yes','remark':args.remark})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--city',choices=['北京','广州'],default='北京')
    for name in ('address-index','store-index','product-index'):
        parser.add_argument('--'+name,type=int)
    parser.add_argument('--keyword',default='')
    parser.add_argument('--quantity',type=int,default=1)
    parser.add_argument('--budget-cents',type=int,default=3500)
    parser.add_argument('--tableware',choices=['yes','no'])
    parser.add_argument('--remark',default='')
    parser.add_argument('--choices',default='[]',help='JSON list of explicit round_id/code selections')
    logging.disable(logging.CRITICAL)
    asyncio.run(run(parser.parse_args()))
