const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const moduleUnderTest={exports:{}};
const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/main.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
vm.runInNewContext(code,{module:moduleUnderTest,exports:moduleUnderTest.exports,require:name=>{
 if(name==='react-dom/client')return{createRoot:()=>({render(){}})};
 if(name==='./useVoice'||name==='./ProfileCard'||name==='./location')return{};
 if(name==='./ActionCard'||name==='./Companion'||name==='./SettingsDialog'||name==='./HoldToTalk')return{};
 if(name.endsWith('.css'))return{};
 return require(name);
},document:{getElementById:()=>({})}});
const {ActivityStrip}=moduleUnderTest.exports;
const base={voice:{phase:'idle',recording:false,inCall:false,speaking:false,loadingSpeech:false,transcript:''},pending:0,busy:'',progress:'',notice:'',ready:true,onStopSpeech(){},onCancelRecording(){}};
const render=props=>renderToStaticMarkup(React.createElement(ActivityStrip,{...base,...props,voice:{...base.voice,...props?.voice}}));
function buttons(node){if(!node||typeof node!=='object')return[];return[node.type==='button'?node:null,...React.Children.toArray(node.props?.children).flatMap(buttons)].filter(Boolean);}
test('idle strip offers simple guidance, without progress theatre or cancel task',()=>{
 const html=render();assert.match(html,/小瑞在这里/);assert.match(html,/可以打字/);assert.match(html,/aria-live="polite"/);assert.doesNotMatch(html,/取消任务|终止任务|\d+%/);
});
test('recording and recognition retain explicit cancel recording, never cancel a pending task',()=>{
 const html=render({voice:{phase:'listening',recording:true,transcript:'找附近的门店'},pending:1});
 assert.match(html,/正在听您说话/);assert.match(html,/取消录音/);assert.match(html,/听到：找附近的门店/);assert.doesNotMatch(html,/取消任务|已终止/);
 const finishing=render({voice:{phase:'finishing',recording:false}});assert.match(finishing,/正在识别您刚才的话/);assert.match(finishing,/取消录音/);
});
test('preparing and playing speech expose the same stop playback action',()=>{
 for(const voice of [{loadingSpeech:true},{speaking:true}]){let stopped=0;const props={...base,voice:{...base.voice,...voice},onStopSpeech:()=>stopped++};const tree=ActivityStrip(props);const stop=buttons(tree).find(b=>b.props.children==='停止播报');assert.ok(stop);stop.props.onClick();assert.equal(stopped,1);}
});
test('cancel recording invokes only the recording callback, not stop playback',()=>{
 let cancelled=0,stopped=0;const tree=ActivityStrip({...base,voice:{...base.voice,recording:true,phase:'connecting'},onCancelRecording:()=>cancelled++,onStopSpeech:()=>stopped++});
 const cancel=buttons(tree).find(b=>b.props.children==='取消录音');assert.ok(cancel);cancel.props.onClick();assert.equal(cancelled,1);assert.equal(stopped,0);
});
test('call uses hangup elsewhere, and pending progress remains truthful after hangup',()=>{
 assert.doesNotMatch(render({voice:{inCall:true,phase:'listening'}}),/取消录音/);
 const html=render({pending:1,progress:'正在查询附近门店',notice:'已挂断，已停止收音和播报。已接收的消息仍会继续处理。'});
 assert.match(html,/正在查询附近门店/);assert.match(html,/已接收的消息仍会继续处理/);assert.doesNotMatch(html,/已取消任务|任务已终止/);
});

test('recognition and connecting remain cancellable after microphone is released',()=>{
 for(const phase of ['connecting','finishing']){let cancelled=0;const tree=ActivityStrip({...base,voice:{...base.voice,recording:false,phase},onCancelRecording:()=>cancelled++});const cancel=buttons(tree).find(b=>b.props.children==='取消录音');assert.ok(cancel);cancel.props.onClick();assert.equal(cancelled,1);}
});
