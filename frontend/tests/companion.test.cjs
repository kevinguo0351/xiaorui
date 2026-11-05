const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const moduleUnderTest={exports:{}};
const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/Companion.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
vm.runInNewContext(code,{module:moduleUnderTest,exports:moduleUnderTest.exports,require});
const {companionMood,Companion,CompanionAvatar}=moduleUnderTest.exports;
const state={phase:'idle',recording:false,speaking:false,loadingSpeech:false,pending:0,context:''};
test('companion follows actual capture, speech and task state instead of declaring success',()=>{
 for(const phase of ['connecting','listening','finishing'])assert.equal(companionMood({...state,phase}),'listening');
 assert.equal(companionMood({...state,speaking:true}),'speaking');
 assert.equal(companionMood({...state,pending:1,context:'查滴滴车型'}),'taxi');
 assert.equal(companionMood({...state,pending:1,context:'查瑞幸咖啡'}),'dining');
 assert.equal(companionMood({...state,context:'刚刚叫过车'}),'idle');
 const html=renderToStaticMarkup(React.createElement(Companion,{mood:'taxi',label:'正在查询车型',name:'小暖'}));
 assert.match(html,/xiaorui-taxi.png/);assert.match(html,/正在查询车型/);assert.doesNotMatch(html,/下单成功|叫车成功/);
});
test('all selected avatar variants render and the customized name is escaped',()=>{
 for(const variant of ['portrait','leaf','sun'])assert.match(renderToStaticMarkup(React.createElement(CompanionAvatar,{variant,name:'<小暖>'})),new RegExp('avatar-'+variant));
 const html=renderToStaticMarkup(React.createElement(Companion,{mood:'idle',label:'陪着您',name:'<小暖>'}));
 assert.match(html,/&lt;小暖&gt;/);assert.doesNotMatch(html,/<小暖>/);
});
