"""Real model: collect fictional address over three turns, never save remotely.

.venv/bin/python -m experiments.mcd_fragmented_acceptance --live
Private full report is ignored under .local-data; stdout contains only progress.
"""
import argparse
import asyncio,json,logging
from pathlib import Path
from uuid import uuid4
from app.agent import AgentService
from app.plans import PlanStore
from experiments.services_acceptance import ReadOnlyMcd,ReadOnlyOfficial

async def run():
 logging.disable(logging.CRITICAL)
 directory=Path('.local-data/mcd-fragmented-live')/uuid4().hex
 directory.mkdir(parents=True,mode=0o700)
 agent=AgentService(ReadOnlyMcd(),PlanStore(directory/'plans.sqlite3'),data_dir=directory/'agent')
 agent.actions._enabled=lambda _:False
 for provider in ('didi','luckin'): agent.scenarios[provider].provider=ReadOnlyOfficial(provider)
 report={'passed':False,'business_writes':False,'real_model':True,'turns':[]}
 try:
  for text in ('验收老人分次说新收餐地址的功能，地址联系人手机号均为虚构测试数据，只保留本地草稿，不创建地址或下单。这次在北京，请用地址草稿记下，缺项一次只问一个。', '收餐地址是王府井测试大楼，送到前台。请更新本地地址草稿，保留已经说过的城市。', '收餐人叫测试，电话幺三八零零零零零零零零。请更新本地草稿，并为完整地址生成待核对确认卡片，千万不要执行保存。'):
   result=await agent.chat('fragmented-test',text)
   report['turns'].append(result)
   print(json.dumps({'turn':len(report['turns']),'tool_names':[x.get('name') for x in result.get('trace',[]) if x.get('name')]},ensure_ascii=False),flush=True)
  draft=agent._session('fragmented-test').services['mcd']['address_draft']
  assert draft['city']=='北京' and draft['phone']=='13800000000' and draft['addressDetail']=='前台'
  plan=agent.actions.pending('fragmented-test')
  assert plan and plan['action']=='create_address' and not plan['order']
  agent.actions.cancel_local('fragmented-test',plan['id'])
  report['passed']=True
 except Exception as exc: report['failure_type']=type(exc).__name__
 path=directory/'report.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2));path.chmod(0o600)
 print(json.dumps({k:v for k,v in report.items() if k!='turns'}));print(str(path))
 return 0 if report['passed'] else 1
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--live',action='store_true')
 if not parser.parse_args().live: parser.error('--live required')
 raise SystemExit(asyncio.run(run()))
