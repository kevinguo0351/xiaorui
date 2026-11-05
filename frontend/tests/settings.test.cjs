const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
function load({states={},stored=null}={}){
 let index=0,value=stored;const writes=[];
 const hooks={useState:initial=>{const i=index++;let state=Object.hasOwn(states,i)?states[i]:(typeof initial==='function'?initial():initial);return[state,update=>{state=typeof update==='function'?update(state):update;}];},useRef:value=>({current:value}),useEffect:()=>{}};
 const module={exports:{}};
 const source=fs.readFileSync(require.resolve('../src/SettingsDialog.tsx'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{module,exports:module.exports,require:name=>name==='react'?hooks:name.endsWith('.css')?{}:require(name),
  localStorage:{getItem:()=>value,setItem:(key,data)=>{value=data;writes.push({key,data});}},console,Set,Object,JSON,AbortController});
 return{exports:module.exports,writes};
}
function all(node){if(node==null||typeof node!=='object')return[];if(Array.isArray(node))return node.flatMap(all);return[node,...all(node.props?.children)];}

test('appearance data validates persisted shape and never retains extra secret fields',()=>{
 const h=load({stored:JSON.stringify({name:' 小南 ',avatar:'sun',ARK_API_KEY:'private-marker'})});
 const {settings,updateSettings}=h.exports.useCompanionSettings();
 assert.equal(settings.name,'小南');assert.equal(settings.avatar,'sun');assert.equal(Object.hasOwn(settings,'ARK_API_KEY'),false);
 updateSettings({name:'暖暖',avatar:'leaf'});
 assert.equal(h.writes.length,1);assert.deepEqual(JSON.parse(h.writes[0].data),{name:'暖暖',avatar:'leaf'});
 assert.equal(h.writes[0].data.includes('private-marker'),false);
 const normalized=h.exports.normalizeCompanionSettings({name:'',avatar:'untrusted'});
 assert.equal(normalized.name,'小瑞');assert.equal(normalized.avatar,'portrait');
});

test('discovery success cannot be presented as a successful business query',()=>{
 const {describeConnection}=load().exports;
 const failed=describeConnection({status:'failed',discovery:'passed',query:'failed'});
 assert.match(failed,/目录可读/);assert.match(failed,/未通过/);assert.doesNotMatch(failed,/查询通过/);
 assert.match(describeConnection({status:'not_live_tested'}),/尚未验证/);
 assert.match(describeConnection({status:'passed',discovery:'passed',query:'passed'}),/公开查询通过/);
});

test('settings appearance has accessible dialog and three explicit avatar choices',()=>{
 const {SettingsDialog}=load().exports;
 const tree=SettingsDialog({open:true,onClose(){},settings:{name:'小瑞',avatar:'portrait'},onChange(){}});
 const nodes=all(tree);
 assert.equal(nodes.some(n=>n.props?.role==='dialog'&&String(n.props['aria-modal'])==='true'),true);
 assert.equal(nodes.filter(n=>n.type==='button'&&String(n.props?.className).includes('avatar-choice')).length,3);
 assert.equal(nodes.find(n=>n.props?.id==='companion-name').props.value,'小瑞');
 assert.equal(SettingsDialog({open:false,onClose(){},settings:{name:'小瑞',avatar:'portrait'},onChange(){}}),null);
});

test('family fields keep saved secrets blank, disable environment fields, and label custom MCP unavailable',()=>{
 const keys=['ARK_API_KEY','ARK_MODEL','ARK_BASE_URL','DOUBAO_SPEECH_API_KEY','MCD_MCP_TOKEN','LUCKIN_MCP_TOKEN','DIDI_MCP_KEY'];
 const fields=Object.fromEntries(keys.map(key=>[key,{configured:true,masked:'••••••••',source:key==='DIDI_MCP_KEY'?'environment':'local',editable:key!=='DIDI_MCP_KEY',...(key==='ARK_MODEL'?{value:'doubao-test'}:key==='ARK_BASE_URL'?{value:'https://ark.cn-beijing.volces.com/api/v3'}:{})}]));
 const providers=Object.fromEntries(['ark','speech','mcd','luckin','didi'].map(key=>[key,{label:key,configured:true,live_check_available:!['ark','speech'].includes(key)}]));
 const {SettingsDialog}=load({states:{0:'family',1:{fields,providers,read_only:false}}}).exports;
 const tree=SettingsDialog({open:true,onClose(){},settings:{name:'小瑞',avatar:'portrait'},onChange(){}});
 const nodes=all(tree),inputs=nodes.filter(n=>n.type==='input');
 assert.equal(inputs.filter(n=>n.props.type==='password').length,5);
 assert.equal(inputs.filter(n=>n.props.type==='password').every(n=>n.props.value===''),true);
 assert.equal(inputs.find(n=>n.props.name==='DIDI_MCP_KEY').props.disabled,true);
 assert.equal(inputs.find(n=>n.props.name==='ARK_MODEL').props.value,'doubao-test');
 const text=JSON.stringify(tree);
 assert.match(text,/自定义 MCP 和其他 API 暂未接入/);
 assert.match(text,/不会开通下单/);
 assert.equal(nodes.some(n=>n.props?.name==='MCD_ORDER_ENABLED'),false);
});
