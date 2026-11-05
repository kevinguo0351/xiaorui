"""Measure real model + TTS latency with synthetic dialogue and isolated state.

python -m experiments.voice_latency_probe --live
No personal profile is loaded; no business tools or model-driven writes allowed.
First MP3 chunk is not a measurement of browser playback or microphone latency.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from uuid import uuid4

from app.agent import AgentService
from app.contact_events import contact_observer
from app.mcd import McdService
from app.plans import PlanStore
from app.voice import config, speech_audio

ROOT=Path(__file__).resolve().parents[1]


async def main():
    logging.disable(logging.CRITICAL)
    root=ROOT/'.local-data/voice-latency'/('stream-'+uuid4().hex)
    agent=AgentService(McdService(),PlanStore(root/'plans.db'),data_dir=root/'agent')
    agent.actions._enabled=lambda _:False
    async def no_tools(*args, **kwargs):
        return {'error':'本次只测试聊天延迟，不允许调用工具。'}
    agent._tool=no_tools
    metrics={'checked_at':datetime.now(timezone.utc).isoformat(),
             'synthetic_dialogue':True,'business_writes':False,'human_voice':False}
    start=time.monotonic()
    def observe(event):
        if event.get('type')=='delta' and 'first_text_seconds' not in metrics:
            metrics['first_text_seconds']=round(time.monotonic()-start,3)
    token=contact_observer.set(observe)
    compose=agent.speech.compose
    async def timed(*args,**kwargs):
        begin=time.monotonic()
        result=await compose(*args,**kwargs)
        metrics['narration_seconds']=round(time.monotonic()-begin,3)
        return result
    agent.speech.compose=timed
    try:
        answer=await agent.chat('synthetic-latency-test','今天有点闷，陪我聊两句吧。不查询服务，不保存资料。')
        metrics.update(reply_seconds=round(time.monotonic()-start,3),answer_chars=len(answer['text']),
                       speech_chars=len(answer['speech_text']),speech_source=answer['speech_source'])
        begin=time.monotonic()
        stream=speech_audio(answer['speech_text'],config())
        size=0
        async for chunk in stream:
            if not size:
                metrics['first_audio_chunk_seconds']=round(time.monotonic()-begin,3)
                metrics['server_reply_plus_first_chunk_seconds']=round(time.monotonic()-start,3)
            size+=len(chunk)
        metrics.update(full_audio_seconds=round(time.monotonic()-begin,3),audio_bytes=size,passed=size>0)
    except Exception as exc:
        metrics.update(passed=False,error_type=type(exc).__name__)
    finally:
        contact_observer.reset(token)
    path=root/'report.json';path.write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps(metrics,ensure_ascii=False))
    return 0 if metrics.get('passed') else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    if not parser.parse_args().live:
        parser.error('--live is required; calls real model and speech services')
    raise SystemExit(asyncio.run(main()))
