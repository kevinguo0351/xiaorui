"""Real contact HTTP/SSE acceptance. Synthetic chat only, no business writes.

Run with the local server up: .venv/bin/python -m experiments.contact_live_probe
Uses a fresh browser identity; never uses the user's browser cookie.
"""
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def main():
    events=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=30,trust_env=False) as client:
        (await client.get('/api/health')).raise_for_status()
        async def consume():
            async with client.stream('GET','/api/contact/events?after=0',timeout=None) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        events.append(json.loads(line[6:]))
        receiver=asyncio.create_task(consume())
        async def until(predicate):
            async with asyncio.timeout(120):
                while not predicate():
                    await asyncio.sleep(.1)
        latencies=[]
        async def send(text):
            start=time.monotonic()
            response=await client.post('/api/contact/messages',json={'text':text,'client_id':str(uuid4())})
            response.raise_for_status()
            latencies.append(round(time.monotonic()-start,3))
            return response.json()['message_id']
        started=time.monotonic()
        try:
            first=await send('这只是聊天交互验收，不调用任何工具、不保存个人资料。请记住本轮临时口令“青竹517”，回复收到。')
            await until(lambda:any(e['type']=='started' and e['message_id']==first for e in events))
            second=await send('补充：本轮临时目的地先记杭州，不要查询。')
            third=await send('改口：最终目的地改苏州。请只回答临时口令和最终目的地，不要调用工具。')
            await until(lambda:any(e['type'] in {'completed','failed'} and third in e.get('message_ids',[e.get('message_id')]) for e in events))
            completed=[e for e in events if e['type']=='completed']
            failures=[e for e in events if e['type']=='failed']
            assert not failures, 'Real model returned a failure; inspect the UI quota/network message.'
            final=completed[-1]['response']['text']
            assert '青竹517' in final and '苏州' in final and '杭州' not in final, 'Latest correction was not reflected.'
            assert completed[0]['superseded'], 'Old result was not superseded.'
            accepted={e['message_id'] for e in events if e['type']=='accepted'}
            assert {first,second,third} <= accepted
            assert any(e['type']=='delta' for e in events), 'No real streamed text arrived.'
            state=(await client.get('/api/contact/state')).json()
            assert state['pending']==0
            assert any(e['type']=='completed' and third in e.get('message_ids',[]) for e in state['events'])
            follow=await send('不调用工具，只回答刚才本轮聊天的临时口令与最终目的地。')
            await until(lambda:any(e['type'] in {'completed','failed'} and follow in e.get('message_ids',[e.get('message_id')]) for e in events))
            follow_event=next(e for e in reversed(events) if e['type'] in {'completed','failed'})
            follow_text=follow_event.get('response',{}).get('text','')
            assert '青竹517' in follow_text and '苏州' in follow_text
            assert not any(e.get('response',{}).get('events') for e in completed), 'Unexpected business event.'
            result={'real_model':True,'http_sse':True,'three_messages_accepted':True,
                    'accepted_seconds':latencies,'superseded_old_reply':True,'streamed_delta_events':sum(e['type']=='delta' for e in events),
                    'latest_correction_reply':final,'followup_reply':follow_text,'refresh_state_restored':True,
                    'elapsed_seconds':round(time.monotonic()-started,2),'business_writes':False}
            path=ROOT/'docs/acceptance/contact-live-2026-11-04.json'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(result,ensure_ascii=False))
        finally:
            receiver.cancel()
            await asyncio.gather(receiver,return_exceptions=True)

if __name__=='__main__':
    asyncio.run(main())
