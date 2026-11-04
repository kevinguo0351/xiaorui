"""Real narrator/TTS acceptance with clearly synthetic cards; no business calls."""
import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import dotenv_values
from app.speech import SpeechComposer
import app.speech as speech_module
original_valid=speech_module.valid
def inspect_test_output(text,data):
    accepted=original_valid(text,data)
    if not accepted:print(json.dumps({"rejected_synthetic_speech":text},ensure_ascii=False),flush=True)
    return accepted
speech_module.valid=inspect_test_output

ROOT=Path(__file__).resolve().parents[1]

async def main(audio=False):
    import os
    local=dotenv_values(ROOT/'.env')
    settings={'key':os.environ.get('ARK_API_KEY',local.get('ARK_API_KEY') or ''),
              'model':os.environ.get('ARK_MODEL',local.get('ARK_MODEL') or ''),
              'base':os.environ.get('ARK_BASE_URL',local.get('ARK_BASE_URL') or 'https://ark.cn-beijing.volces.com/api/v3')}
    assert settings['key'] and settings['model'], 'Configure local model credentials first.'
    cards=[{'type':'service_choices','choices':[
        {'label':'快车','detail':'本次预估52元，实际费用以平台为准','prompt':'选择第1个车型'},
        {'label':'优享','detail':'本次预估78元，实际费用以平台为准','prompt':'选择第2个车型'},
        {'label':'专车','detail':'本次预估110元，实际费用以平台为准','prompt':'选择第3个车型'}]}]
    cases=[
      ('vehicle_choices','就按刚才的预算，看看有哪些车。','可选车型：快车52元；优享78元；专车110元。请从下方选择。',cards,[{'role':'user','text':'预算55元，不要替我叫车，先看看。'}]),
      ('read_aloud','我看不清屏幕，请把车型和费用念一下。','车型和费用见卡片。',cards,[]),
      ('correction','改成只看看，不要叫车。','下面是几种车型和预估费用：快车52元；优享78元；专车110元。',cards,[{'role':'user','text':'帮我叫辆车'}]),
      ('long_answer','给我说说在家休息能做什么，别讲太多。','可以根据您的精力和兴趣选择：\n1. 看喜欢的书，保持舒适姿势，注意休息。\n2. 听熟悉的音乐，让自己放松。\n3. 给朋友打电话，聊聊近况。\n4. 整理旧照片，回忆开心的事情。\n5. 在身体允许的情况下做些轻松活动。\n不用一次做很多，选喜欢的一件就好；也可以什么都不安排，安静休息。',[],[]),
    ]
    records=[]
    for name,user,screen,events,history in cases:
        start=time.monotonic()
        result=await SpeechComposer().compose(settings,user,screen,events,history)
        records.append({'case':name,**result,'elapsed_seconds':round(time.monotonic()-start,2)})
        print(json.dumps(records[-1],ensure_ascii=False),flush=True)
    result={'synthetic_cards':True,'real_narrator_requests':True,'business_calls':False,'cases':records,
            'all_model_rewrites':all(r['source']=='model' for r in records)}
    output=ROOT/'docs/acceptance/speech-live-2026-11-05.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    if audio and records[0]['source']=='model':
        from app.voice import SpeechRequest,synthesize
        response=await synthesize(SpeechRequest(text='这是一段测试播报。'+records[0]['text']))
        dest=ROOT/'.local-data/speech-demo-2026-11-05.mp3';dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(response.body)
        print(json.dumps({'demo_audio':str(dest),'bytes':len(response.body)},ensure_ascii=False))
    assert result['all_model_rewrites'],'Narrator fell back; inspect safe output and model availability.'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true',required=True);parser.add_argument('--audio',action='store_true')
    args=parser.parse_args();asyncio.run(main(args.audio))
