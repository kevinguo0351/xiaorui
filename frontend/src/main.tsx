import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {useVoice} from './useVoice';

type Store={code:string;name:string;address:string;open?:boolean};
type Selection={store_code:string;product_code:string;quantity:number;rounds:{round_id:string;code:string;quantity:number}[]};
type Meal={product_code:string;name:string;image?:string;amount_cents:number;choices:string[];request:Selection};
type Plan={id:string;version:number;status:string;amount_cents:number;summary:{store_name:string;store_address:string;product_name:string;quantity:number;choices:string[];take_way:string};expires_at:number;confirmation_token:string;order?:{order_id?:string;payment_url?:string};error?:string};
type Message={id:number;role:'user'|'assistant';text:string;speech_text?:string;kind?:'stores'|'meals'|'plan';stores?:Store[];meals?:Meal[];plan?:Plan};
type Health={order_execution_enabled:boolean;mcd_configured:boolean;agent_configured?:boolean};
type ChatEvent={type:'stores';stores:Store[]}|{type:'meals';meals:Meal[]}|{type:'plan';plan:Plan};
type ChatResponse={text:string;speech_text?:string;events:ChatEvent[]};
const yuan=(n:number)=>`¥${(n/100).toFixed(2)}`;
const labels:Record<string,string>={awaiting_confirmation:'请您确认',needs_review:'价格有变化，请再次确认',rechecking:'正在重新核价',submitting:'正在创建订单',created:'订单已创建，待支付',unknown:'订单结果待核查',failed:'未能创建订单',cancelled:'方案已取消',superseded:'方案已替换',expired:'报价已过期'};
async function api<T>(url:string,body?:unknown):Promise<T>{const r=await fetch(url,{method:body===undefined?'GET':'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'这一步暂时没有完成，请稍后重试。');return d}
function Mic(){return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="8" y="2" width="8" height="13" rx="4"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>}
function App(){
 const [health,setHealth]=useState<Health>();const [messages,setMessages]=useState<Message[]>([]);const [input,setInput]=useState('');const [stores,setStores]=useState<Store[]>([]);const [busy,setBusy]=useState('正在恢复对话');const [error,setError]=useState('');const [meals,setMeals]=useState<Meal[]>([]);const [plan,setPlan]=useState<Plan>();const [modal,setModal]=useState(false);const [now,setNow]=useState(Date.now());const counter=useRef(0);const lock=useRef(false);const end=useRef<HTMLDivElement>(null);const dialog=useRef<HTMLDivElement>(null);
 const [inputMode,setInputMode]=useState<'text'|'voice'>('text');
 const voice=useVoice(text=>{void send(text)},setError);
 const add=(m:Omit<Message,'id'>)=>setMessages(old=>[...old,{...m,id:++counter.current}]);
 useEffect(()=>{
  let alive=true;
  Promise.all([api<Health>('/api/health'),api<{messages:({role:'user'|'assistant'}&ChatResponse)[]}>('/api/chat/history')]).then(([h,history])=>{
   if(!alive)return;setHealth(h);
   for(const message of history.messages){if(message.role==='user')add({role:'user',text:message.text});else displayResponse(message)}
  }).catch(()=>{if(alive)setError('未能恢复对话，请检查本地服务后刷新页面。')}).finally(()=>{if(alive)setBusy('')});
  const t=setInterval(()=>setNow(Date.now()),1000);return()=>{alive=false;clearInterval(t)}
 },[]);
 useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth',block:'end'})},[messages,busy]);
 useEffect(()=>{if(!modal)return;const previous=document.activeElement as HTMLElement|null;const el=dialog.current;el?.querySelector<HTMLButtonElement>('button')?.focus();function key(e:KeyboardEvent){if(e.key==='Escape')setModal(false);if(e.key==='Tab'&&el){const b=Array.from(el.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));if(!b.length)return;const first=b[0],last=b[b.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}}document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus()}},[modal]);
 const blocked=Boolean(plan&&['unknown','submitting','rechecking'].includes(plan.status));
 async function task(title:string,fn:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(title);setError('');try{await fn()}catch(e){setError(e instanceof Error?e.message:'暂时没有完成，请重试。')}finally{setBusy('');lock.current=false}}
 function update(p:Plan){setPlan(p);setMessages(old=>old.map(m=>m.plan?.id===p.id?{...m,plan:p}:m))}
 async function release(){if(plan&&['awaiting_confirmation','needs_review','expired'].includes(plan.status)){const d=await api<{plan:Plan}>(`/api/plans/${plan.id}/cancel`,{});update(d.plan)}}
 function displayResponse(d:ChatResponse){
   const response:Omit<Message,'id'>={role:'assistant',text:d.text,speech_text:d.speech_text};
   const events=d.events??[];
   if(!events.length)add(response);
   events.forEach((event,i)=>{
    const message:Omit<Message,'id'>={role:'assistant',text:i===0?d.text:'',speech_text:i===0?d.speech_text:undefined};
    if(event.type==='stores'){setStores(event.stores);setMeals([]);message.kind='stores';message.stores=event.stores}
    if(event.type==='meals'){setMeals(event.meals);message.kind='meals';message.meals=event.meals}
    if(event.type==='plan'){update(event.plan);message.kind='plan';message.plan=event.plan}
    add(message);
   });
 }
 async function send(spoken?:string){
  const text=(spoken??input).trim();if(!text||busy||lock.current||blocked)return;
  voice.cancel();voice.stopSpeech();setInput('');
  await task('小瑞正在处理',async()=>{
   add({role:'user',text});
   const d=await api<ChatResponse>('/api/chat',{text});
   displayResponse(d);
   const events=d.events??[];
   // Refresh a pending plan after an Agent cancellation/replacement.
   if(plan&&!events.some(event=>event.type==='plan')){
    try{const current=await api<{plan:Plan}>(`/api/plans/${plan.id}`);update(current.plan)}catch{}
   }
   if(d.speech_text)void voice.speak(d.speech_text);
  });
 }
 async function chooseStore(s:Store){await send(`选择门店：${s.name}。`)}
 async function selectMeal(m:Meal,index:number){await send(`选第${index+1}份套餐，${m.name}。`)}
 async function cancel(p:Plan){await task('正在取消方案',async()=>{const d=await api<{plan:Plan}>(`/api/plans/${p.id}/cancel`,{});update(d.plan);add({role:'assistant',text:'这份方案已取消，没有创建订单。您可以重新选择。'})})}
 async function confirm(){if(!plan)return;setModal(false);await task('正在核实价格并创建订单，请勿重复操作',async()=>{try{const d=await api<{plan:Plan}>(`/api/plans/${plan.id}/confirm`,{version:plan.version,confirmation_token:plan.confirmation_token,confirmation_text:'确认下单'});update(d.plan)}catch(e){try{const d=await api<{plan:Plan}>(`/api/plans/${plan.id}`);update(d.plan)}catch{}throw e}})}
 async function fresh(){if(blocked)return;voice.cancel();voice.stopSpeech();await task('正在开始新对话',async()=>{await release();await api('/api/chat/reset',{});setMessages([]);setStores([]);setMeals([]);setPlan(undefined);setModal(false);setInput('')})}
 function planCard(p:Plan){const current=p.id===plan?.id;const review=['awaiting_confirmation','needs_review'].includes(p.status);const expired=p.expires_at*1000<=now;const payment=p.order?.payment_url;return <div className="order-card"><div className="card-overline">{labels[expired&&review?'expired':p.status]||p.status}</div><h3>{p.summary.product_name} <small>×{p.summary.quantity}</small></h3><ul>{p.summary.choices.map((s,i)=><li key={i}>{s}</li>)}</ul><div className="pickup"><strong>{p.summary.store_name}</strong><span>{p.summary.store_address}</span><span>{p.summary.take_way}</span></div><div className="total"><span>本次总价</span><strong>{yuan(p.amount_cents)}</strong></div>{p.error&&<p className="note">{p.error}</p>}{review&&!health?.order_execution_enabled&&<p className="note">当前仅查看真实报价，下单尚未开启。</p>}{p.status==='unknown'&&<p className="note">请到麦当劳官方渠道核查，暂时不要重复下单。</p>}{p.status==='created'&&<><p>订单号：{p.order?.order_id}，尚未代表支付成功。</p>{payment?.startsWith('https://')&&<a className="primary link-button" href={payment} target="_blank" rel="noreferrer">前往官方支付页面 ↗</a>}</>}{review&&current&&<div className="card-actions"><button className="primary" disabled={!!busy||expired||!health?.order_execution_enabled} onClick={()=>setModal(true)}>确认这个方案</button><button disabled={!!busy} onClick={()=>cancel(p)}>取消方案</button></div>}<small className="disclaimer">到店自取 · 官方核价 · 下单前再次核实</small></div>}
 return <div className={messages.length?"app":"app empty"}><header><a href="/" className="brand">小瑞</a><button className="new-chat" onClick={fresh} disabled={!!busy||blocked}>＋ 新对话</button></header><main className={messages.length?'conversation':'welcome'}>{!messages.length?<div className="greeting"><h1>小瑞</h1></div>:messages.map(m=><article className={'message '+m.role} key={m.id}><div className="avatar" aria-hidden="true">{m.role==='assistant'?'瑞':'您'}</div><div className="message-body">{m.text&&<p className="message-text">{m.text}</p>}{m.speech_text&&<button className="speech-button" type="button" onClick={()=>voice.speaking||voice.loadingSpeech?voice.stopSpeech():void voice.speak(m.speech_text!)}>{voice.loadingSpeech?'停止生成语音':voice.speaking?'停止播报':'▶ 听小瑞说'}</button>}{m.stores&&<div className="store-list">{m.stores.map(s=><button className="store-card" key={s.code} onClick={()=>chooseStore(s)} disabled={!!busy||blocked||s.open===false||m.stores!==stores}><strong>{s.name}</strong><span>{s.address}{s.open===false?' · 暂未营业':''}</span><small>在这家取餐 →</small></button>)}</div>}{m.meals&&<div className="meal-grid">{m.meals.map((meal,i)=><div className="meal-card" key={meal.product_code}><div className="meal-image">{meal.image?<img src={meal.image} alt={meal.name} loading="lazy"/>:<span>暂无餐品图片</span>}<span className="letter">{String.fromCharCode(65+i)}</span></div><div className="meal-content"><h3>{meal.name}</h3><p>{meal.choices.join(' · ')}</p><strong className="meal-price">{yuan(meal.amount_cents)}</strong><small>到店自取 · 本次官方核价</small><button disabled={!!busy||blocked||m.meals!==meals} onClick={()=>selectMeal(meal,i)}>选 {String.fromCharCode(65+i)} 这份</button></div></div>)}</div>}{m.plan&&planCard(m.plan)}</div></article>)}{busy&&<div className="busy" role="status"><span className="spinner"/>{busy}…</div>}{error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')}>知道了</button></div>}{!health?.mcd_configured&&health&&<p className="error">请先在本地 .env 配置麦当劳 Token。</p>}<div ref={end}/></main><div className="composer-wrap"><form className={"composer "+(inputMode==='voice'?'voice-mode':'')} onSubmit={e=>{e.preventDefault();if(inputMode==='text')void send()}}>
{inputMode==='text'?<><label className="sr-only" htmlFor="chat-input">发消息给小瑞</label><textarea id="chat-input" value={input} onChange={e=>setInput(e.target.value)} placeholder="发消息给小瑞" rows={1} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send()}}}/><button type="button" className="mode-switch" disabled={!!busy||blocked} onClick={()=>setInputMode('voice')} aria-label="切换到语音模式" title="语音输入"><Mic/></button><button className="send" disabled={!input.trim()||!!busy||blocked} aria-label="发送消息">↑</button></>:<><button type="button" className="mode-switch" aria-label="切换到文字模式" title="文字输入" onClick={()=>{voice.cancel();setInputMode('text')}}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="3"/><path d="M5 9h2m2 0h2m2 0h2m2 0h2M5 12h2m2 0h2m2 0h2m2 0h2M7 15h10"/></svg></button><button type="button" className={"record-line "+(voice.phase==='listening'?'is-listening':'')} onClick={()=>void voice.start()} disabled={!!busy||blocked||voice.phase==='connecting'||voice.phase==='finishing'} aria-label={voice.phase==='listening'?'停止录音并发送':'开始录音'}><span className="record-indicator" aria-hidden="true">{voice.phase==='listening'?<span className="stop-square"/>:<Mic/>}</span><span className="record-caption" role="status">{voice.phase==='listening'?(voice.transcript||'正在听，点击停止'):voice.phase==='connecting'?'正在连接…':voice.phase==='finishing'?'正在识别…':'点击开始说话'}</span>{voice.phase==='listening'&&<span className="sound-bars" aria-hidden="true"><i/><i/><i/><i/><i/></span>}</button></>}
</form></div>{modal&&plan&&<div className="modal-backdrop"><div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><h2 id="confirm-title">最后确认一次</h2><p>{plan.summary.product_name}，共 {yuan(plan.amount_cents)}，在 {plan.summary.store_name} {plan.summary.take_way}。</p><p>确认后将创建真实待支付订单，支付仍在官方页面完成。</p><button onClick={()=>setModal(false)}>先不下单，返回看看</button><button className="primary" onClick={confirm} disabled={!!busy||!health?.order_execution_enabled}>确认下单 · {yuan(plan.amount_cents)}</button></div></div>}</div>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
