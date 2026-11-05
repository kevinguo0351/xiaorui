const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
function harness(options={}){
 const state=[],cleanups=[],intervals=[],sockets=[],players=[],requests=[],flushes=[];let index=0,now=10000,stopped=0,worklet;
 const hooks={useRef:v=>({current:v}),useState:v=>{const i=index++;state[i]=v;return[v,x=>{state[i]=typeof x==='function'?x(state[i]):x}];},useEffect:f=>cleanups.push(f())};
 class Socket{static OPEN=1;constructor(){this.readyState=1;this.bufferedAmount=0;this.sent=[];sockets.push(this);}send(v){this.sent.push(v);}close(){this.readyState=3;}receive(data){this.onmessage?.({data:JSON.stringify(data)});}}
 class Worklet{constructor(){this.port={postMessage:message=>{if(message?.type==='flush'){flushes.push(message.id);if(!options.delayFlush)this.port.onmessage?.({data:{type:'flushed',id:message.id}});}}};worklet=this;}connect(){}disconnect(){}}
 class Context{constructor(){this.audioWorklet={addModule:async()=>{}};this.destination={};}async resume(){}async close(){}createMediaStreamSource(){return{connect(){}};}createGain(){return{gain:{value:0},connect(){}};}}
 class Audio{constructor(){players.push(this);}play(){return Promise.resolve();}pause(){this.paused=true;}dispatchEvent(e){if(e.type==='ended')this.onended?.();}}
 const module={exports:{}};const context={module,exports:module.exports,require:n=>n==='react'?hooks:require(n),
  fetch:async(url,init)=>{if(url==='/api/voice/tts'){requests.push(init);if(options.tts)return options.tts(init,requests.length);}return{ok:true,json:async()=>({asr_configured:true,tts_configured:true}),blob:async()=>new Blob(['test-only'])};},
  navigator:{mediaDevices:{getUserMedia:async()=>{const stream={getTracks:()=>[{stop(){stopped++;}}]};return options.getUserMedia?options.getUserMedia(stream):stream;}}},
  WebSocket:Socket,AudioWorkletNode:Worklet,AudioContext:Context,Audio,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
  location:{protocol:'http:',host:'localhost:8000'},Blob,AbortController,DOMException,Event,ArrayBuffer,Date:{now:()=>now},
  setInterval:f=>{intervals.push(f);return 1;},clearInterval(){},setTimeout:()=>1,clearTimeout(){},console};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/useVoice.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,context);
 const received=[],errors=[];let interruptions=0;const voice=module.exports.useVoice(t=>received.push(t),e=>errors.push(e),()=>interruptions++);
 return{voice,sockets,players,requests,flushes,flushMic(id){worklet.port.onmessage({data:{type:'flushed',id}});},received,errors,state,get stopped(){return stopped;},get interruptions(){return interruptions;},
  loud(){for(let i=0;i<6;i++)worklet.port.onmessage?.({data:{level:.06}});},audio(){worklet.port.onmessage?.({data:new ArrayBuffer(6400)});},
  silence(ms=3000){now+=ms;worklet.port.onmessage?.({data:{level:0}});intervals.forEach(f=>f());},flush:async()=>{for(let i=0;i<8;i++)await Promise.resolve();},cleanup:()=>cleanups.forEach(f=>f?.())};
}
test('one call accepts multiple turns, with no microphone restart and exact final deduplication',async()=>{
 const h=harness();await h.voice.startCall();h.loud();h.audio();assert.equal(h.sockets.length,1);
 h.sockets[0].receive({type:'ready'});h.sockets[0].receive({type:'partial',text:'想吃午饭'});h.silence();
 assert.ok(h.sockets[0].sent.some(v=>typeof v==='string'&&v.includes('finish')));
 h.sockets[0].receive({type:'final',text:'想吃午饭'});assert.deepEqual(h.received,['想吃午饭']);assert.equal(h.stopped,0);
 h.loud();h.audio();h.sockets[1].receive({type:'ready'});h.silence();h.sockets[1].receive({type:'final',text:'三十元以内'});
 assert.deepEqual(h.received,['想吃午饭','三十元以内']);h.voice.endCall();assert.equal(h.stopped,1);assert.deepEqual(h.errors,[]);h.cleanup();
});
test('speech playback keeps the microphone active; user speech interrupts audio',async()=>{
 const h=harness();await h.voice.startCall();const playback=h.voice.speak('您好。');await h.flush();assert.equal(h.players.length,1);assert.equal(h.stopped,0);
 h.loud();await playback;assert.equal(h.players[0].paused,true);assert.equal(h.interruptions,1);assert.equal(h.stopped,0);h.cleanup();assert.equal(h.stopped,1);
});
test('hangup during pending ASR closes socket and does not send unfinished transcript',async()=>{
 const h=harness();await h.voice.startCall();h.loud();h.audio();h.sockets[0].receive({type:'ready'});h.sockets[0].receive({type:'partial',text:'尚未说完'});
 h.voice.endCall();h.sockets[0].receive({type:'final',text:'不能再提交'});assert.deepEqual(h.received,[]);assert.equal(h.sockets[0].readyState,3);assert.equal(h.stopped,1);h.cleanup();
});

test('single voice message waits for stop, submits once, then releases microphone',async()=>{
 const h=harness();await h.voice.startRecording();assert.equal(h.sockets.length,1);h.sockets[0].receive({type:'ready'});h.audio();h.silence();
 assert.equal(h.sockets[0].sent.some(v=>typeof v==='string'&&v.includes('finish')),false);
 h.voice.stopRecording();assert.equal(h.stopped,1);assert.deepEqual(h.received,[]);assert.equal(h.sockets[0].readyState,1);assert.equal(h.sockets[0].sent.some(v=>typeof v==='string'&&v.includes('finish')),true);
 h.sockets[0].receive({type:'final',text:'一条语音消息'});h.sockets[0].receive({type:'final',text:'不能重复'});assert.deepEqual(h.received,['一条语音消息']);assert.equal(h.stopped,1);assert.equal(h.sockets.length,1);h.cleanup();
});
test('switching away cancels a voice message without sending partial text',async()=>{
 const h=harness();await h.voice.startRecording();h.sockets[0].receive({type:'ready'});h.sockets[0].receive({type:'partial',text:'不要发送'});h.voice.cancelRecording();
 assert.deepEqual(h.received,[]);assert.equal(h.stopped,1);h.cleanup();
});

test('one-sentence lookahead starts while current audio plays and stays bounded',async()=>{
 const h=harness();const speech=h.voice.speak('第一句。第二句。第三句。');await h.flush();
 assert.equal(h.players.length,1);assert.equal(h.requests.length,2);
 assert.deepEqual(h.requests.map(r=>JSON.parse(r.body).text),['第一句。','第二句。']);
 h.players[0].dispatchEvent(new Event('ended'));await h.flush();
 assert.equal(h.players.length,2);assert.equal(h.requests.length,3);
 h.players[1].dispatchEvent(new Event('ended'));await h.flush();
 assert.equal(h.players.length,3);h.players[2].dispatchEvent(new Event('ended'));await speech;
 assert.deepEqual(h.errors,[]);
 assert.equal(h.voice.speechMetrics.current.filter(m=>m.stage==='tts_audio_ready').length,3);
 assert.equal(h.voice.speechMetrics.current.some(m=>'text'in m),false);h.cleanup();
});
test('cancelling playback aborts the pending prefetch and ignores its late result',async()=>{
 let finishPrefetch;const h=harness({tts:(_,n)=>n===2?new Promise(resolve=>{finishPrefetch=resolve;}):Promise.resolve({ok:true,blob:async()=>new Blob(['first'])})});
 const speech=h.voice.speak('第一句。第二句。');await h.flush();assert.equal(h.players.length,1);assert.equal(h.requests.length,2);
 h.voice.stopSpeech();assert.equal(h.requests[1].signal.aborted,true);await speech;
 finishPrefetch({ok:true,blob:async()=>new Blob(['stale'])});await h.flush();
 assert.equal(h.players.length,1);assert.equal(h.players[0].paused,true);assert.deepEqual(h.errors,[]);h.cleanup();
});
test('superseded first-audio fetch cannot play after a newer response',async()=>{
 let finishOld;const h=harness({tts:(_,n)=>n===1?new Promise(resolve=>{finishOld=resolve;}):Promise.resolve({ok:true,blob:async()=>new Blob(['new'])})});
 const old=h.voice.speak('旧回复。');await h.flush();const current=h.voice.speak('新回复。');await h.flush();
 assert.equal(h.requests[0].signal.aborted,true);assert.equal(h.players.length,1);
 finishOld({ok:true,blob:async()=>new Blob(['old'])});await old;assert.equal(h.players.length,1);
 h.players[0].dispatchEvent(new Event('ended'));await current;assert.deepEqual(h.errors,[]);h.cleanup();
});
test('ASR final before the user finishes is rejected rather than submitted',async()=>{
 for(const mode of ['startRecording','startCall']){const h=harness();await h.voice[mode]();if(mode==='startCall'){h.loud();h.audio();}
 h.sockets[0].receive({type:'ready'});h.sockets[0].receive({type:'final',text:'还没说完'});
 assert.deepEqual(h.received,[]);assert.equal(h.stopped,1);assert.equal(h.errors.length,1);assert.match(h.errors[0],/提前结束/);h.cleanup();}
});
test('manual call finish flushes once and does not end the next turn early',async()=>{
 const h=harness();await h.voice.startCall();h.loud();h.audio();h.sockets[0].receive({type:'ready'});h.voice.finish();h.voice.finish();h.audio();
 assert.equal(h.sockets[0].sent.filter(v=>typeof v==='string'&&v.includes('finish')).length,1);
 h.sockets[0].receive({type:'final',text:'第一轮'});h.silence();h.loud();h.audio();h.sockets[1].receive({type:'ready'});
 assert.equal(h.sockets[1].sent.some(v=>typeof v==='string'&&v.includes('finish')),false);h.cleanup();
});

test('continuous call allows a thinking pause until the initial three-second threshold',async()=>{
 const h=harness();await h.voice.startCall();h.loud();h.audio();h.sockets[0].receive({type:'ready'});
 h.silence(1800);assert.equal(h.sockets[0].sent.some(v=>typeof v==='string'&&v.includes('finish')),false);
 h.silence(1199);assert.equal(h.sockets[0].sent.some(v=>typeof v==='string'&&v.includes('finish')),false);
 h.silence(1);assert.equal(h.sockets[0].sent.filter(v=>typeof v==='string'&&v.includes('finish')).length,1);
 h.silence(3000);assert.equal(h.sockets[0].sent.filter(v=>typeof v==='string'&&v.includes('finish')).length,1);h.cleanup();
});

test('a delayed flush acknowledgement cannot finish a newer turn',async()=>{
 const h=harness({delayFlush:true});await h.voice.startCall();h.loud();h.audio();h.sockets[0].receive({type:'ready'});h.voice.finish();const old=h.flushes[0];
 h.silence();h.sockets[0].receive({type:'final',text:'第一轮'});h.loud();h.audio();h.sockets[1].receive({type:'ready'});h.voice.finish();const current=h.flushes[1];
 h.flushMic(old);assert.equal(h.sockets[1].sent.some(v=>typeof v==='string'&&v.includes('finish')),false);
 h.flushMic(current);h.flushMic(current);assert.equal(h.sockets[1].sent.filter(v=>typeof v==='string'&&v.includes('finish')).length,1);h.cleanup();
});

test('message stop releases capture immediately while waiting for ASR final',async()=>{
 const h=harness();await h.voice.startRecording();h.sockets[0].receive({type:'ready'});h.loud();h.audio();h.voice.stopRecording();
 assert.equal(h.stopped,1);assert.deepEqual(h.received,[]);assert.equal(h.sockets[0].readyState,1);
 for(let i=0;i<45;i++)h.audio();assert.deepEqual(h.errors,[]);assert.equal(h.sockets.length,1);
 h.sockets[0].receive({type:'final',text:'等识别结果再发送'});assert.deepEqual(h.received,['等识别结果再发送']);assert.equal(h.stopped,1);h.cleanup();
});
test('message stop before ASR ready releases microphone and finishes after readiness',async()=>{
 const h=harness();await h.voice.startRecording();h.audio();h.voice.stopRecording();assert.equal(h.stopped,1);assert.deepEqual(h.received,[]);
 h.sockets[0].receive({type:'ready'});assert.equal(h.sockets[0].sent.filter(v=>typeof v==='string'&&v.includes('finish')).length,1);
 h.sockets[0].receive({type:'final',text:'连接前已经说完'});assert.deepEqual(h.received,['连接前已经说完']);h.cleanup();
});

test('a message stop during microphone permission also releases a late granted stream',async()=>{
 let grant;const h=harness({getUserMedia:stream=>new Promise(resolve=>{grant=()=>resolve(stream);})});
 const start=h.voice.startRecording();await h.flush();h.voice.stopRecording();grant();await start;
 assert.equal(h.stopped,1);assert.deepEqual(h.received,[]);h.sockets[0].receive({type:'ready'});
 assert.equal(h.sockets[0].sent.filter(v=>typeof v==='string'&&v.includes('finish')).length,1);h.cleanup();
});
