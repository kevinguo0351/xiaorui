"""Isolated real-model dialogue probe. Forces read-only; never creates transactions."""
import os
os.environ['XIAORUI_READ_ONLY'] = '1'
import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from app import read_only
from app.agent import AgentService
from app.contact_events import contact_call
from app.mcd import McdService
from app.plans import PlanStore

TURNS = [
    ('陪伴与自然追问', '我一个人在家有点闷，想找你聊会儿。'),
    ('没听清与短句复述', '我耳朵不太好，刚才没听清楚，你一句一句说。'),
    ('不会点屏幕与任务切换', '先不说这个，我想吃午饭，可我不太会点屏幕。先告诉我该怎么跟你说，别替我下单。'),
    ('改口撤回与主动聊天', '算了，今天不点了。咱们接着聊，你先问我一个简单的问题吧。'),
]

async def run():
    assert read_only.READ_ONLY
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(), 'scope':'isolated-real-model-read-only-dialogue',
            'hardware_voice_tested':False,'transactions_attempted':0,'turns':[]}
    with tempfile.TemporaryDirectory(prefix='xiaorui-elder-dialogue-') as temp:
        root=Path(temp)
        agent=AgentService(McdService(),PlanStore(root/'plans.db'),data_dir=root/'agent')
        if not agent.configured:
            return {**report,'status':'not_configured'}
        token=contact_call.set('isolated-elderly-probe')
        try:
            for scenario,text in TURNS:
                started=time.monotonic()
                try:
                    result=await asyncio.wait_for(agent.chat('synthetic-elderly-user',text),65)
                    item={'scenario':scenario,'input':text,'answer':result['text'],'speech':result.get('speech_text',''),
                          'events':[e['type'] for e in result.get('events',[])],
                          'elapsed_seconds':round(time.monotonic()-started,2),'status':'responded'}
                except Exception as exc:
                    item={'scenario':scenario,'input':text,'status':'failed','error_type':type(exc).__name__,
                          'elapsed_seconds':round(time.monotonic()-started,2)}
                report['turns'].append(item)
                print(json.dumps(item,ensure_ascii=False),flush=True)
            report['status']='completed' if all(t['status']=='responded' for t in report['turns']) else 'partial_failure'
            report['action_count']=len(agent.actions.list('synthetic-elderly-user'))
            assert report['action_count']==0, 'Read-only dialogue created an action'
        finally:
            contact_call.reset(token)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=asyncio.run(run());args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Result:',result['status'],flush=True)
