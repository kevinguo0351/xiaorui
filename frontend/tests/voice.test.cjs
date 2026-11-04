const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
function harness(){
 const state=[],cleanups=[],intervals=[],sockets=[],players=[];let index=0,now=10000,stopped=0,worklet;
 const hooks={useRef:v=>({current:v}),useState:v=>{const i=index++;state[i]=v;return[v,x=>{state[i]=typeof x==='function'?x(state[i]):x}];},useEffect:f=>cleanups.push(f())};
 class Socket{static OPEN=1;constructor(){this.readyState=1;this.bufferedAmount=0;this.sent=[];sockets.push(this);}send(v){this.sent.push(v);}close(){this.readyState=3;}receive(data){this.onmessage?.({data:JSON.stringify(data)});}}
 class Worklet{constructor(){this.port={postMessage:message=>{if(message==='flush')this.port.onmessage?.({data:'flushed'});}};worklet=this;}connect(){}disconnect(){}}
 class Context{constructor(){this.audioWorklet={addModule:async()=>{}};this.destination={};}async resume(){}async close(){}createMediaStreamSource(){return{connect(){}};}createGain(){return{gain:{value:0},connect(){}};}}
 class Audio{constructor(){players.push(this);}play(){return Promise.resolve();}pause(){this.paused=true;}dispatchEvent(e){if(e.type==='ended')this.onended?.();}}
 const module={exports:{}};const context={module,exports:module.exports,require:n=>n==='react'?hooks:require(n),
  fetch:async url=>({ok:true,json:async()=>({asr_configured:true,tts_configured:true}),blob:async()=>new Blob(['test-only'])}),
  navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){stopped++;}}]})}},
  WebSocket:Socket,AudioWorkletNode:Worklet,AudioContext:Context,Audio,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
  location:{protocol:'http:',host:'localhost:8000'},Blob,AbortController,DOMException,Event,ArrayBuffer,Date:{now:()=>now},
  setInterval:f=>{intervals.push(f);return 1;},clearInterval(){},setTimeout:()=>1,clearTimeout(){},console};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/useVoice.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,context);
 const received=[],errors=[];let interruptions=0;const voice=module.exports.useVoice(t=>received.push(t),e=>errors.push(e),()=>interruptions++);
 return{voice,sockets,players,received,errors,state,get stopped(){return stopped;},get interruptions(){return interruptions;},
  loud(){for(let i=0;i<6;i++)worklet.port.onmessage({data:{level:.06}});},audio(){worklet.port.onmessage({data:new ArrayBuffer(6400)});},
  silence(){now+=2000;worklet.port.onmessage({data:{level:0}});intervals.forEach(f=>f());},flush:async()=>{for(let i=0;i<8;i++)await Promise.resolve();},cleanup:()=>cleanups.forEach(f=>f?.())};
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
 h.voice.stopRecording();assert.equal(h.sockets[0].sent.some(v=>typeof v==='string'&&v.includes('finish')),true);
 h.sockets[0].receive({type:'final',text:'一条语音消息'});h.sockets[0].receive({type:'final',text:'不能重复'});assert.deepEqual(h.received,['一条语音消息']);assert.equal(h.stopped,1);assert.equal(h.sockets.length,1);h.cleanup();
});
test('switching away cancels a voice message without sending partial text',async()=>{
 const h=harness();await h.voice.startRecording();h.sockets[0].receive({type:'ready'});h.sockets[0].receive({type:'partial',text:'不要发送'});h.voice.cancelRecording();
 assert.deepEqual(h.received,[]);assert.equal(h.stopped,1);h.cleanup();
});
