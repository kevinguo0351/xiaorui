const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const moduleUnderTest={exports:{}};
const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/Companion.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
vm.runInNewContext(code,{module:moduleUnderTest,exports:moduleUnderTest.exports,require});
const {Companion,CompanionAvatar,companionMood}=moduleUnderTest.exports;
const idle={phase:'idle',recording:false,speaking:false,loadingSpeech:false,pending:0,context:''};
test('mascot intent never claims work without an accepted pending message',()=>{
 assert.equal(companionMood({...idle,context:'我要打车'}),'idle');
 assert.equal(companionMood({...idle,pending:1,context:'正在查询滴滴目的地'}),'taxi');
 assert.equal(companionMood({...idle,pending:1,context:'查麦当劳门店菜单'}),'dining');
 assert.equal(companionMood({...idle,pending:1,context:'处理一条消息'}),'working');
 assert.equal(companionMood({...idle,phase:'finishing',pending:1,context:'查麦当劳'}),'listening');
 assert.equal(companionMood({...idle,speaking:true}),'speaking');
});
test('all scenes use delivered images and retain truthful label and accessible character name',()=>{
 for(const [mood,path] of [['idle','working'],['working','working'],['listening','working'],['speaking','working'],['taxi','taxi'],['dining','dining']]){
  const html=renderToStaticMarkup(React.createElement(Companion,{mood,label:'正在查询门店',name:'小安'}));
  assert.match(html,new RegExp(`/mascot/xiaorui-${path}.png`));assert.match(html,/小安的陪伴形象/);assert.match(html,/正在查询门店/);assert.match(html,new RegExp(`data-state="${mood}"`));assert.doesNotMatch(html,/xiaorui-idle.png|已下单|已叫车/);
 }
});
test('avatar presets have a real portrait and decorative native alternate icons',()=>{
 assert.match(renderToStaticMarkup(React.createElement(CompanionAvatar,{variant:'portrait',name:'小安'})),/xiaorui-working.png/);
 for(const variant of ['leaf','sun']){const html=renderToStaticMarkup(React.createElement(CompanionAvatar,{variant}));assert.match(html,/<svg/);assert.match(html,/aria-hidden="true"/);}
});
