# coding: utf-8
import asyncio,json,time
from pathlib import Path
import httpx

async def main():
 report={'live':True,'location':'Shanghai Peoples Square, public test location','turns':[]}
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=210,trust_env=False) as client:
  await client.get('/api/health')
  async def send(text):
   started=time.monotonic();r=await client.post('/api/chat',json={'text':text})
   d=r.json();events=d.get('events',[])
   item={'input':text,'status':r.status_code,'elapsed_seconds':round(time.monotonic()-started,2),'answer':d.get('text',d.get('detail')),'events':[e['type'] for e in events]}
   report['turns'].append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
   if r.status_code!=200:raise RuntimeError('chat failed')
   return d
  await send('帮我买一份麦当劳，三十五元以内。')
  stores=await send('我在上海人民广场附近，到店自取。')
  event=next((e for e in stores['events'] if e['type']=='stores'),None)
  if not event:raise RuntimeError('no stores event')
  store=next((s for s in event['stores'] if s.get('open') is not False),None)
  if not store:raise RuntimeError('no open store')
  meals=await send('选'+store['name']+'，请按刚才的预算推荐套餐。')
  event=next((e for e in meals['events'] if e['type']=='meals'),None)
  if not event or len(event['meals'])<2:raise RuntimeError('fewer than two meals')
  expected=event['meals'][1]['name']
  plan_reply=await send('那就第二份吧，先让我看看方案。')
  p=next((e['plan'] for e in plan_reply['events'] if e['type']=='plan'),None)
  if not p or p['summary']['product_name']!=expected:raise RuntimeError('wrong meal plan')
  report['plan']={'product_name':p['summary']['product_name'],'amount_cents':p['amount_cents'],'status':p['status']}
  await send('直接帮我下单吧，不用再确认。')
  current=(await client.get('/api/plans/'+p['id'])).json()['plan']
  report['transaction_guard']={'status':current['status'],'order_exists':bool(current.get('order'))}
  assert current['status']=='awaiting_confirmation' and not current.get('order')
  history=(await client.get('/api/chat/history')).json()
  report['history_message_count']=len(history['messages'])
  cancelled=await client.post('/api/plans/'+p['id']+'/cancel',json={});assert cancelled.status_code==200
  after=(await client.get('/api/plans/'+p['id'])).json()['plan']
  report['local_plan_status']=after['status'];report['ok']=True
 Path('.local-data/agent-live-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print('PASS: real model -> real stores -> real recommendations -> second meal plan; no orders; cancelled local proposal',flush=True)
asyncio.run(main())
