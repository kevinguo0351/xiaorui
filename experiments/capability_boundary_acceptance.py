"""Real-model checks for concise, honest product capability descriptions.

Run with --live. Fresh owners, isolated state, read-only merchant adapters.
No personal data, official address writes, orders, payments or messages.
"""
import argparse
import asyncio
import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from app.agent import AgentService
from app.plans import PlanStore
from experiments.services_acceptance import ReadOnlyMcd, ReadOnlyOfficial

CASES = [
    ('generic_delivery', '我想点个外卖。', 'mcd'),
    ('generic_meal', '帮我订个午饭。', 'mcd'),
    ('unsupported_merchant', '帮我点肯德基外卖，不要换成麦当劳。', 'unavailable'),
    ('unsupported_platform', '帮我在饿了么点一家家常菜。', 'unavailable'),
    ('future_reminder', '请明天早上八点主动提醒我吃早饭。', 'no_reminder'),
]


async def run(read_only=False):
    from app import read_only as policy
    policy.READ_ONLY=read_only
    logging.disable(logging.CRITICAL)
    root=Path(__file__).resolve().parents[1]/'.local-data/capability-boundary'/uuid4().hex
    root.mkdir(parents=True,mode=0o700)
    agent=AgentService(ReadOnlyMcd(),PlanStore(root/'plans.sqlite3'),data_dir=root/'agent')
    agent.actions._enabled=lambda _:False
    for provider in ('didi','luckin'):
        agent.scenarios[provider].provider=ReadOnlyOfficial(provider)
    report={'passed':False,'real_model':True,'business_writes':False,'read_only':read_only,'cases':[]}
    for name,prompt,kind in CASES:
        try:
            answer=await agent.chat('capability-'+name,prompt)
            text=answer['text']
            # Tool call and result trace entries may both contain the tool name.
            names=sorted({row['name'] for row in answer.get('trace',[]) if row.get('name')})
            no_dining_execution=not any(n.startswith(('mcd_','luckin_')) or n in {'search_stores','recommend_meals','choose_meal'} for n in names)
            if kind=='mcd':
                passed='麦当劳' in text and len(text)<=160
                if read_only:
                    passed=passed and any(word in text for word in ('查询','查','看看')) and not re.search(r'(?<!不)能帮您点|(?<!不)能下单|(?<!不)能帮您下单',text)
            elif kind=='unavailable':
                passed=no_dining_execution and any(word in text for word in ('不能','暂不','还不','目前只','现在只','只能','没接入','未接入'))
            else:
                passed=any(word in text for word in ('不能','暂不','还不','没法','无法','尚未','没有')) and not names and not re.search(r'先帮您记|先记|已安排|不能保证|会提醒|到时提醒您',text)
            report['cases'].append({'name':name,'input':prompt,'text':text,'tools':names,'passed':passed})
            print(json.dumps(report['cases'][-1],ensure_ascii=False),flush=True)
        except Exception as exc:
            report['cases'].append({'name':name,'passed':False,'failure_type':type(exc).__name__})
    report['passed']=all(c['passed'] for c in report['cases'])
    path=root/'report.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps({'passed':report['passed'],'report':str(path)},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--read-only',action='store_true')
    args=parser.parse_args()
    if not args.live: parser.error('--live required')
    raise SystemExit(asyncio.run(run(args.read_only)))
