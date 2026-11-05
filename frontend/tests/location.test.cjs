const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
function setup({allowed=true,denied=false}={}){
 const requests=[];let timer;
 const module={exports:{}};
 const ctx={module,exports:module.exports,document:{permissionsPolicy:{allowsFeature:()=>allowed}},
  navigator:{geolocation:{getCurrentPosition(ok,fail){if(denied)fail({code:1});else ok({coords:{latitude:39.9,longitude:116.4,accuracy:20},timestamp:12345});}}},
  setTimeout:f=>{timer=f;return 1},clearTimeout:()=>{timer=null},
  fetch:async(url,body)=>{requests.push({url,body});return{ok:true,json:async()=>({ok:true})}}};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/location.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,ctx);
 return{locate:module.exports.locate,requests,get timer(){return timer}};
}
test('unsupported embedded policy gives actionable browser guidance without uploading location',async()=>{
 const h=setup({allowed:false});await assert.rejects(h.locate(),/Safari.*Chrome/);assert.equal(h.requests.length,0);
});
test('denial without a prompt gives permission guidance and does not upload',async()=>{
 const h=setup({denied:true});await assert.rejects(h.locate(),/没有弹窗/);assert.equal(h.requests.length,0);assert.equal(h.timer,null);
});
test('successful user gesture uploads actual coordinates and clears the watchdog',async()=>{
 const h=setup();assert.equal(await h.locate(),20);assert.equal(h.requests.length,1);
 assert.equal(h.requests[0].url,'/api/location');assert.equal(JSON.parse(h.requests[0].body.body).longitude,116.4);assert.equal(h.timer,null);
});
