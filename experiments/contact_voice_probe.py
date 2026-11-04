"""Synthetic speech through real TTS -> ASR -> contact -> TTS, two turns.

No physical microphone recording; this does not validate room echo or human VAD.
"""
import asyncio
import argparse
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect

ROOT=Path(__file__).resolve().parents[1]

async def main(voice_only=False):
    records=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',trust_env=False,timeout=60) as client:
        (await client.get('/api/health')).raise_for_status()
        with tempfile.TemporaryDirectory() as tmp:
            for number,text in enumerate(['这是语音通话测试，请只回复你好，不查询服务，不保存资料。',
                                         '再补充，我现在只测试连续通话，请简短回答收到。'],1):
                response=await client.post('/api/voice/tts',json={'text':text});response.raise_for_status()
                mp3=Path(tmp)/'test.mp3';wav=Path(tmp)/'test.wav';mp3.write_bytes(response.content)
                subprocess.run(['/usr/bin/afconvert','-f','WAVE','-d','LEI16@16000','-c','1',str(mp3),str(wav)],check=True,capture_output=True)
                with wave.open(str(wav),'rb') as audio:
                    assert audio.getframerate()==16000 and audio.getsampwidth()==2 and audio.getnchannels()==1
                    pcm=audio.readframes(audio.getnframes())
                partials=0
                async with connect('ws://127.0.0.1:8000/api/voice/asr',origin='http://127.0.0.1:8000',proxy=None) as socket:
                    ready=json.loads(await asyncio.wait_for(socket.recv(),30));assert ready['type']=='ready',ready.get('message','ASR failed')
                    async def upload():
                        for index in range(0,len(pcm),6400):
                            await socket.send(pcm[index:index+6400]);await asyncio.sleep(.2)
                        await socket.send(json.dumps({'type':'finish'}))
                    sender=asyncio.create_task(upload())
                    try:
                        async with asyncio.timeout(60):
                            while True:
                                message=json.loads(await socket.recv())
                                if message['type']=='partial':partials+=1
                                elif message['type']=='final':
                                    transcript=message['text'];break
                                elif message['type']=='error':raise RuntimeError(message['message'])
                    finally:
                        if not sender.done():sender.cancel()
                        await asyncio.gather(sender,return_exceptions=True)
                assert transcript.strip()
                if voice_only:
                    records.append({'turn':number,'transcript':transcript,'partial_events':partials,'input_audio_bytes':len(response.content)})
                    continue
                sent=await client.post('/api/contact/messages',json={'text':transcript,'client_id':str(uuid4())});sent.raise_for_status()
                mid=sent.json()['message_id']
                async with asyncio.timeout(120):
                    while True:
                        state=(await client.get('/api/contact/state')).json()
                        terminal=[e for e in state['events'] if e['type'] in {'completed','failed'} and mid in e.get('message_ids',[e.get('message_id')])]
                        if terminal:break
                        await asyncio.sleep(.2)
                assert terminal[-1]['type']=='completed',terminal[-1].get('text','Model failed')
                reply=terminal[-1]['response']['text'];assert not terminal[-1]['response']['events']
                speech=await client.post('/api/voice/tts',json={'text':reply[:160]});speech.raise_for_status()
                records.append({'turn':number,'transcript':transcript,'partial_events':partials,'reply':reply,'reply_audio_bytes':len(speech.content)})
        result={'real_tts_asr':True,'real_model':not voice_only,'turns':records,'physical_microphone':False,'browser_echo_or_vad_verified':False,'business_writes':False}
        (ROOT/'docs/acceptance/contact-voice-live-2026-11-04.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--voice-only',action='store_true',help='Check real TTS and ASR without model requests')
    asyncio.run(main(parser.parse_args().voice_only))
