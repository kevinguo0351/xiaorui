const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const mod={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/CallBar.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:mod,exports:mod.exports,require});
const {CallBar,callDuration}=mod.exports;
test('top phone island shows call state and duration without conversation transcripts',()=>{
 const html=renderToStaticMarkup(React.createElement(CallBar,{name:'小瑞',elapsed:65,connecting:false,speaking:false,loading:false,processing:false,onFinish(){},onHangup(){}}));
 assert.match(html,/phone-island/);assert.match(html,/通话中/);assert.match(html,/01:05/);assert.match(html,/挂断/);assert.doesNotMatch(html,/textarea|听到：|chat-input/);
 assert.equal(callDuration(-2),'00:00');assert.equal(callDuration(3601),'60:01');
});
