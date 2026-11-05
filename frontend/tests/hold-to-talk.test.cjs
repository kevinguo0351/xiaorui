const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
function harness(options={}){
 let now=0,nextTimer=0,hook=0,element;const refs=[],effects=[],pendingEffects=[],timers=new Map(),events=[],listeners=new Map();
 const hooks={useRef(value){const index=hook++;return refs[index]||(refs[index]={current:value});},useState(value){const index=hook++;refs[index]??=value;return[refs[index],next=>{refs[index]=next;}];},useEffect(effect,deps){const index=hook++;const old=effects[index];if(!old||deps.some((d,i)=>d!==old.deps[i]))pendingEffects.push(()=>{old?.cleanup?.();effects[index]={deps,cleanup:effect()};});}};
 const doc={visibilityState:'visible',addEventListener(name,handler){if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(handler);},removeEventListener(name,handler){listeners.get(name)?.delete(handler);}};
 const win={addEventListener:(name,fn)=>doc.addEventListener(`window:${name}`,fn),removeEventListener:(name,fn)=>doc.removeEventListener(`window:${name}`,fn)};
 class TextArea{disabled=false;readOnly=false;}
 const target=new TextArea(),captured=new Set();const wrapper={setPointerCapture:id=>captured.add(id),hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id)};
 const module={exports:{}};
 const context={module,exports:module.exports,require:name=>name==='react'?hooks:name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props})}:require(name),document:doc,window:win,HTMLTextAreaElement:TextArea,Promise,Math,Date:{now:()=>now},setTimeout:(fn,delay)=>{const id=++nextTimer;timers.set(id,{at:now+delay,fn});return id;},clearTimeout:id=>timers.delete(id)};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../src/HoldToTalk.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(code,context);
 let props={children:'textarea',onStart:()=>{events.push('start');return options.start?.();},onFinish:()=>events.push('finish'),onCancel:()=>events.push('cancel'),onHoldChange:holding=>events.push(holding?'holding':'released')};
 function render(extra={}){props={...props,...extra};hook=0;element=module.exports.HoldToTalk(props);while(pendingEffects.length)pendingEffects.shift()();}
 render();
 function event(extra={}){let prevented=0,stopped=0;return{target,currentTarget:wrapper,isPrimary:true,button:0,pointerId:1,clientX:10,clientY:100,preventDefault(){prevented++;},stopPropagation(){stopped++;},get prevented(){return prevented;},get stopped(){return stopped;},...extra};}
 return{events,target,captured,timers,get element(){return element;},event,render,
  down(extra){const e=event(extra);element.props.onPointerDownCapture(e);return e;},
  move(extra){const e=event(extra);element.props.onPointerMoveCapture(e);return e;},
  up(extra){const e=event(extra);element.props.onPointerUpCapture(e);return e;},
  tick(ms){const end=now+ms;for(;;){const due=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();}now=end;},
  emit(name,extra={}){const e=event(extra);for(const listener of listeners.get(name)||[])listener(e);return e;},
  hidden(){doc.visibilityState='hidden';for(const listener of listeners.get('visibilitychange')||[])listener({});},
  unmount(){for(const effect of effects)effect?.cleanup?.();},flush:async()=>{for(let i=0;i<5;i++)await Promise.resolve();},listeners};
}
test('short tap keeps default focus/edit behaviour and never starts audio',()=>{
 const h=harness();assert.equal(h.down().prevented,0);h.tick(349);assert.equal(h.up().prevented,0);h.tick(1);assert.deepEqual(h.events,[]);assert.equal(h.captured.size,0);h.unmount();
});
test('hold starts at350ms, captures pointer, release finishes once',()=>{
 const h=harness();h.down();h.tick(349);assert.deepEqual(h.events,[]);h.tick(1);assert.deepEqual(h.events,['holding','start']);assert.equal(h.captured.has(1),true);
 assert.equal(h.up().prevented,1);h.emit('pointerup');assert.deepEqual(h.events,['holding','start','released','finish']);assert.equal(h.captured.size,0);h.unmount();
});
test('moving to scroll before threshold leaves browser gesture untouched',()=>{
 const h=harness();h.down();assert.equal(h.move({clientY:120}).prevented,0);h.tick(400);h.up();assert.deepEqual(h.events,[]);h.unmount();
});
test('sliding upward while holding cancels without sending',()=>{
 const h=harness();h.down();h.tick(350);assert.equal(h.move({clientY:35}).prevented,1);h.up();assert.deepEqual(h.events,['holding','start','released','cancel']);h.unmount();
});
test('pointercancel,Escape,hidden tab,blur,unmount all discard active audio',()=>{
 for(const action of ['pointercancel','Escape','hidden','blur','unmount']){const h=harness();h.down();h.tick(350);
 if(action==='pointercancel')h.emit('pointercancel');else if(action==='Escape')h.emit('keydown',{key:'Escape'});else if(action==='hidden')h.hidden();else if(action==='blur')h.emit('window:blur');else h.unmount();
 assert.deepEqual(h.events,['holding','start','released','cancel'],action);h.up();h.unmount();assert.equal(h.events.filter(e=>e==='cancel').length,1);}
});
test('release during pending microphone permission finishes promptly and late failure does not cancel another turn',async()=>{
 let reject;const h=harness({start:()=>new Promise((_,fail)=>{reject=fail;})});h.down();h.tick(350);h.up();assert.equal(h.events.at(-1),'finish');reject(Error('late'));await h.flush();assert.equal(h.events.includes('cancel'),false);h.unmount();
});
test('external disabled/reset cancels but normal recording rerender does not',()=>{
 const h=harness();h.down();h.tick(350);h.render({className:'recording'});assert.equal(h.events.includes('cancel'),false);h.render({disabled:true});assert.equal(h.events.at(-1),'cancel');h.unmount();
 const reset=harness();reset.down();reset.tick(350);reset.render({resetKey:1});assert.equal(reset.events.at(-1),'cancel');reset.unmount();
});
test('only holding suppresses context menu/click, a new short tap restores defaults',()=>{
 const h=harness();let e=h.event();h.element.props.onContextMenuCapture(e);assert.equal(e.prevented,0);h.down();h.tick(350);e=h.event();h.element.props.onContextMenuCapture(e);assert.equal(e.prevented,1);h.up();e=h.event();h.element.props.onClickCapture(e);assert.equal(e.prevented,1);
 h.down();h.up();e=h.event();h.element.props.onClickCapture(e);assert.equal(e.prevented,0);h.unmount();
});
test('disabled/read-only textareas and other controls do not start recording',()=>{
 const h=harness();h.render({disabled:true});h.down();h.tick(400);h.render({disabled:false});h.target.readOnly=true;h.down();h.tick(400);h.target.readOnly=false;h.down({target:{}});h.tick(400);assert.deepEqual(h.events,[]);h.unmount();
});
test('unmount clears pending hold timer and document/window listeners',()=>{
 const h=harness();h.down();h.unmount();h.tick(400);assert.deepEqual(h.events,[]);assert.equal(h.timers.size,0);for(const entries of h.listeners.values())assert.equal(entries.size,0);
});
