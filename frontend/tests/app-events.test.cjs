const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const React=require('react');
const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/main.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
function harness(){
 const slots=[];let index=0,callbacks,source;
 const spoken=[];const requests=[];let cancellations=0;
 const voice={phase:'listening',inCall:true,recording:false,transcript:'',speaking:false,loadingSpeech:false,speak:async text=>spoken.push(text),stopSpeech(){},cancel(){},cancelRecording(){cancellations++;voice.phase='idle';voice.recording=false;},endCall(){}};
 const hooks={...React,useState(initial){const i=index++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return[slots[i],value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];},useRef(value){const i=index++;if(!(i in slots))slots[i]={current:value};return slots[i];},useEffect(effect,deps){const i=index++;const old=slots[i];if(!old||!deps||deps.some((value,n)=>value!==old[n])){slots[i]=deps;effect();}}};
 class EventSource{constructor(){source=this;}close(){}}
 const module={exports:{}};
 const fetch=async (url,options)=>{requests.push({url,options});return{ok:true,headers:{get:()=> 'application/json'},json:async()=>url==='/api/health'?{mcd_configured:true,agent_configured:true}:url==='/api/contact/state'?{events:[],cursor:0,pending:0}:url==='/api/chat/history'?{messages:[]}:url==='/api/actions'?{actions:[]}: {accepted:true}};};
 vm.runInNewContext(code,{module,exports:module.exports,require:name=>name==='react'?hooks:name==='react-dom/client'?{createRoot:()=>({render(){}})}:name==='./useVoice'?{useVoice:(onFinal,onError,onSpeechStart)=>{callbacks={onFinal,onError,onSpeechStart};return voice;}}:name==='./Companion'?{Companion(){},CompanionAvatar(){},companionMood:()=> 'idle'}:name==='./SettingsDialog'?{SettingsDialog(){},useCompanionSettings:()=>({settings:{name:'小瑞',avatar:'portrait'},updateSettings(){}})}:name==='./ProfileCard'?{ProfileCard(){}}:name==='./location'?{locate:async()=>10}:name==='./ActionCard'?{}:name.endsWith('.css')?{}:require(name),document:{getElementById:()=>({})},EventSource,fetch,crypto:require('node:crypto'),setInterval:()=>1,clearInterval(){},console});
 const render=()=>{index=0;return module.exports.App();};
 const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
 return{render,flush,spoken,voice,requests,get cancellations(){return cancellations;},get callbacks(){return callbacks;},emit:event=>source.onmessage({data:JSON.stringify(event)})};
}
function all(node,predicate){if(!node||typeof node!=='object')return[];return[predicate(node)?node:null,...React.Children.toArray(node.props?.children).flatMap(child=>all(child,predicate))].filter(Boolean);}
const reply=(id,text,events=[])=>({type:'completed',message_id:id,response:{text,speech_text:text,events}});
test('caller speech blocks late autoplay even when an old started event arrives afterwards; new final permits its own reply',async()=>{
 const h=harness();h.render();await h.flush();h.render();
 h.callbacks.onSpeechStart();
 h.emit({type:'accepted',message_id:'old',client_id:'old',text:'旧问题'});
 h.emit({type:'started',message_id:'old'});
 h.emit(reply('old','旧问题的迟到回答'));
 assert.deepEqual(h.spoken,[]);
 h.render();h.callbacks.onFinal('我刚刚说完的新问题');await h.flush();h.render();
 h.emit({type:'started',message_id:'new'});h.emit(reply('new','新问题的回答'));
 assert.deepEqual(h.spoken,['新问题的回答']);
});
test('nonvisual query receipts do not make empty bubbles and reply text appears once',async()=>{
 const h=harness();h.render();await h.flush();h.render();
 const receipt={type:'query_result',provider:'mcd',tool:'stores',success:true,source:'https://open.mcd.cn/mcp',data:{}};
 h.emit(reply('a','门店查好了',[receipt,{type:'stores',stores:[]},receipt,{type:'service_result',provider:'mcd',data:{}}]));
 let tree=h.render();
 const messages=()=>all(tree,node=>node.type==='article'&&node.props.className==='message assistant');
 assert.equal(messages().length,1);
 assert.equal(all(tree,node=>node.type==='p'&&node.props.className==='message-text'&&node.props.children==='门店查好了').length,1);
 h.emit(reply('b','还有一条查询结果',[receipt]));tree=h.render();assert.equal(messages().length,2);
 h.emit(reply('c','',[receipt]));tree=h.render();assert.equal(messages().length,2);
});

const buttonByLabel=(tree,label)=>all(tree,node=>node.type==='button'&&node.props['aria-label']===label)[0];
test('switch input or open more functions cancels pending single-message recognition after mic release',async()=>{
 for(const label of ['切换到文字输入','更多功能']){
  const h=harness();h.render();await h.flush();h.voice.inCall=false;h.voice.phase='idle';let tree=h.render();
  buttonByLabel(tree,'切换到语音输入').props.onClick();h.voice.phase='finishing';h.voice.recording=false;tree=h.render();
  const record=buttonByLabel(tree,'正在识别语音');assert.ok(record);assert.equal(record.props.disabled,true);
  assert.equal(all(record,node=>node.type==='span'&&node.props.className==='record-caption')[0].props.children,'正在识别…');
  buttonByLabel(tree,label).props.onClick();assert.equal(h.cancellations,1);assert.equal(h.voice.phase,'idle');
 }
});
test('late reply cannot autoplay during single-message recognition with microphone already released',async()=>{
 const h=harness();h.render();await h.flush();h.voice.inCall=false;h.voice.phase='idle';let tree=h.render();
 buttonByLabel(tree,'切换到语音输入').props.onClick();h.voice.phase='finishing';h.voice.recording=false;h.render();
 h.emit({type:'started',message_id:'old'});h.emit(reply('old','不得在识别期间自动播放'));assert.deepEqual(h.spoken,[]);
 h.voice.phase='idle';h.render();h.callbacks.onFinal('新的语音最终结果');await h.flush();h.render();
 h.emit({type:'started',message_id:'new'});h.emit(reply('new','新的语音回复'));assert.deepEqual(h.spoken,['新的语音回复']);
});

test('identity opens settings and closing refreshes configuration health without submitting a query',async()=>{
 const h=harness();h.render();await h.flush();let tree=h.render();
 const identity=all(tree,node=>node.type==='button'&&node.props.className==='brand companion-settings-entry')[0];assert.match(identity.props['aria-label'],/外观与家人设置/);identity.props.onClick();tree=h.render();
 const dialog=all(tree,node=>node.type?.name==='SettingsDialog')[0];assert.equal(dialog.props.open,true);
 const before=h.requests.filter(r=>r.url==='/api/health').length;dialog.props.onClose();await h.flush();
 assert.equal(h.requests.filter(r=>r.url==='/api/health').length,before+1);assert.equal(h.requests.filter(r=>r.url==='/api/contact/messages').length,0);
});
