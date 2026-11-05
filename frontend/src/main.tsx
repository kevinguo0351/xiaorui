import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {useVoice} from './useVoice';
import {ActionCard,ActionPlan} from './ActionCard';
import {Companion,CompanionAvatar,companionMood} from './Companion';
import {SettingsDialog,useCompanionSettings} from './SettingsDialog';
import {HoldToTalk} from './HoldToTalk';

type Store={code:string;name:string;address:string;open?:boolean};
type Selection={store_code:string;product_code:string;quantity:number;rounds:{round_id:string;code:string;quantity:number}[]};
type Meal={product_code:string;name:string;image?:string;amount_cents:number;choices:string[];request:Selection};
type Plan={id:string;version:number;status:string;amount_cents:number;summary:{store_name:string;store_address:string;product_name:string;quantity:number;choices:string[];take_way:string};expires_at:number;confirmation_token:string;order?:{order_id?:string;payment_url?:string};error?:string};
type ChoiceCard={label:string;detail?:string;image?:string;prompt:string};
type ImageMessage={id:string;url:string};
type Message={images?:ImageMessage[];client_id?:string;message_id?:string;delivery?:string;id:number;role:'user'|'assistant';text:string;speech_text?:string;kind?:'stores'|'meals'|'plan';stores?:Store[];meals?:Meal[];plan?:Plan;actionPlan?:ActionPlan;choices?:ChoiceCard[]};
type Health={order_execution_enabled:boolean;mcd_configured:boolean;agent_configured?:boolean};
type ChatEvent={type:'stores';stores:Store[]}|{type:'meals';meals:Meal[]}|{type:'plan';plan:Plan}|{type:'action_plan';plan:ActionPlan}|{type:'service_choices';choices:ChoiceCard[]}|{type:'service_result';provider:string;data:unknown}|{type:'query_result';provider:string;tool:string;success:boolean;source:string;data:unknown};
type ChatResponse={text:string;speech_text?:string;events:ChatEvent[];conversation_reset?:boolean};
const yuan=(n:number)=>`¥${(n/100).toFixed(2)}`;
const labels:Record<string,string>={awaiting_confirmation:'请您确认',needs_review:'价格有变化，请再次确认',rechecking:'正在重新核价',submitting:'正在创建订单',created:'订单已创建，待支付',unknown:'订单结果待核查',failed:'未能创建订单',cancelled:'方案已取消',superseded:'方案已替换',expired:'报价已过期'};
async function api<T>(url:string,body?:unknown):Promise<T>{const r=await fetch(url,{method:body===undefined?'GET':'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!r.headers.get('content-type')?.includes('application/json'))throw Error('本地服务暂时不可用，请稍后重试。');const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'这一步暂时没有完成，请稍后重试。');return d}
function Mic(){return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="8" y="2" width="8" height="13" rx="4"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>}
function Keyboard(){return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="2" y="5" width="20" height="14" rx="3"/><path d="M5 9h2m2 0h2m2 0h2m2 0h2M5 12h2m2 0h2m2 0h2m2 0h2M7 15h10"/></svg>}
function Photo(){return <svg viewBox="0 0 28 28" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="3" y="4" width="22" height="20" rx="3"/><circle cx="10" cy="10" r="2"/><path d="m4 21 7-7 4 4 4-6 6 8"/></svg>}
function Phone(){return <svg viewBox="0 0 28 28" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M7 4 3.5 7.5c-1 6 11 18 17 17L24 21l-5-5-3 2c-3-1-5-3-6-6l2-3-5-5Z"/></svg>}
type ActivityVoice=Pick<ReturnType<typeof useVoice>,'phase'|'recording'|'inCall'|'speaking'|'loadingSpeech'|'transcript'>;
export function ActivityStrip({voice,pending,busy,progress,notice,ready,onStopSpeech,onCancelRecording,holdActive=false,name='小瑞'}:{holdActive?:boolean;name?:string;voice:ActivityVoice;pending:number;busy:string;progress:string;notice:string;ready:boolean;onStopSpeech:()=>void;onCancelRecording:()=>void}){
 const messageCaptureActive=!voice.inCall&&voice.phase!=='idle';
 let title=`${name}在这里`,detail='可以打字，也可以点麦克风说话。',active=false;
 if(voice.phase==='connecting'){title='正在连接语音';detail='请稍等，麦克风准备好后就可以说话。';active=true;}
 else if(voice.phase==='finishing'){title='正在识别您刚才的话';detail='识别完成后会发送给小瑞。';active=true;}
 else if(voice.recording){title='正在听您说话';detail=holdActive?'松开发送，向上滑动取消。':'说完点「停止录音并发送」；不想发送可取消录音。';active=true;}
 else if(voice.speaking){title=`${name}正在说`;detail='想安静看文字，可以停止播报。';active=true;}
 else if(voice.loadingSpeech){title='正在准备语音';detail='文字已经保留，语音准备好后会播放。';active=true;}
 else if(pending>0){title=progress||'正在处理消息';detail=`已收到 ${pending} 条消息，您可以继续补充。`;active=true;}
 else if(busy){title=busy;detail='请稍等。';active=true;}
 else if(voice.inCall){title='正在听您说话';detail='慢慢说，说完可点「我说完了」，也会在停顿后发送。';active=true;}
 else if(!ready){title=`还没有连上${name}`;detail='请检查本地服务，连接后就可以发消息。';}
 return <section className={'activity-strip '+(active?'activity-active':'')} aria-label="小瑞当前状态"><div className="activity-copy" role="status" aria-live="polite" aria-atomic="true"><strong>{title}</strong><span>{detail}</span>{messageCaptureActive&&voice.transcript&&<span className="activity-transcript">听到：{voice.transcript}</span>}{notice&&<span className="activity-notice">{notice}</span>}</div>{(voice.speaking||voice.loadingSpeech)&&<button type="button" className="stop-playback" onClick={onStopSpeech}>停止播报</button>}{messageCaptureActive&&<button type="button" className="cancel-recording" onClick={onCancelRecording}>取消录音</button>}</section>;
}
export function App(){
 const [health,setHealth]=useState<Health>();const [messages,setMessages]=useState<Message[]>([]);const [input,setInput]=useState('');const [stores,setStores]=useState<Store[]>([]);const [busy,setBusy]=useState('正在恢复对话');const [error,setError]=useState('');const [meals,setMeals]=useState<Meal[]>([]);const [plan,setPlan]=useState<Plan>();const [modal,setModal]=useState(false);const [now,setNow]=useState(Date.now());const counter=useRef(0);const lock=useRef(false);const end=useRef<HTMLDivElement>(null);const dialog=useRef<HTMLDivElement>(null);
 const [ready,setReady]=useState(false);const [chatPending,setChatPending]=useState(0);const [liveReply,setLiveReply]=useState('');const [contactStatus,setContactStatus]=useState('');const pendingIds=useRef(new Set<string>());const interrupted=useRef(false);
 const [inputMode,setInputMode]=useState<'text'|'voice'>('text');const [extrasOpen,setExtrasOpen]=useState(false);const [attachments,setAttachments]=useState<ImageMessage[]>([]);const [uploading,setUploading]=useState(false);const imageInput=useRef<HTMLInputElement>(null);
 const [activeAction,setActiveAction]=useState('');
 const [activeChoices,setActiveChoices]=useState<ChoiceCard[]>();
 const {settings,updateSettings}=useCompanionSettings();const [settingsOpen,setSettingsOpen]=useState(false);const [holdActive,setHoldActive]=useState(false);const [voiceErrorGeneration,setVoiceErrorGeneration]=useState(0);
 const [voiceNotice,setVoiceNotice]=useState('');const autoplayAllowed=useRef(true);const composerWrap=useRef<HTMLDivElement>(null);
 const voice=useVoice(text=>{void send(text)},text=>{setVoiceErrorGeneration(old=>old+1);setError(text==='请先配置豆包语音服务。'?'语音还没接通，请家人帮忙完成设置。您可以继续打字。':text);},()=>{autoplayAllowed.current=false;interrupted.current=true;setLiveReply('');});
 const messageCaptureActive=!voice.inCall&&voice.phase!=='idle';
 useEffect(()=>{document.title=`${settings.name} · 您的生活小帮手`;},[settings.name]);
 const add=(m:Omit<Message,'id'>)=>setMessages(old=>[...old,{...m,id:++counter.current}]);
 function receive(e:any,replay=false){
  if(e.type==='accepted'){
   pendingIds.current.add(e.message_id);
   setMessages(old=>old.some(m=>m.client_id===e.client_id)?old.map(m=>m.client_id===e.client_id?{...m,message_id:e.message_id,delivery:'已送达',images:e.images}:m):[...old,{id:++counter.current,role:'user',text:e.text,images:e.images,client_id:e.client_id,message_id:e.message_id,delivery:'已送达'}]);
  }else if(e.type==='started'){interrupted.current=false;setLiveReply('');setContactStatus('小瑞正在处理，您可以继续说');}
  else if(e.type==='delta'&&!interrupted.current){setLiveReply(old=>(old+e.text).slice(-12000));}
  else if(e.type==='progress'){setContactStatus(e.text);}
  else if(e.type==='completed'||e.type==='failed'){
   for(const id of e.message_ids||[e.message_id])pendingIds.current.delete(id);
   setContactStatus('');setLiveReply('');
   if(e.type==='failed'){const message=e.text==='请先配置豆包文本模型，再开始对话。'?'小瑞还没接通对话服务，请家人帮忙完成设置。':e.text;add({role:'assistant',text:message,speech_text:message});if(!replay&&(voice.inCall||inputMode==='voice')&&!voice.recording&&!messageCaptureActive&&!interrupted.current&&autoplayAllowed.current)void voice.speak(message);}
   else if(!e.superseded){const d=e.response as ChatResponse;if(d.conversation_reset){setMessages([]);setStores([]);setMeals([]);setPlan(undefined);setModal(false);}displayResponse(d);if(!replay&&(voice.inCall||inputMode==='voice')&&!voice.recording&&!messageCaptureActive&&!interrupted.current&&autoplayAllowed.current&&d.speech_text)void voice.speak(d.speech_text);}
   if(!replay)void api<{actions:ActionPlan[]}>('/api/actions').then(d=>d.actions.forEach(updateAction)).catch(()=>{});
  }
  setChatPending(pendingIds.current.size);
 }
 const receiver=useRef(receive);receiver.current=receive;
 useEffect(()=>{
  let alive=true;let source:EventSource|undefined;
  api<Health>('/api/health').then(async h=>{
   const state=await api<{events:any[];cursor:number;pending:number}>('/api/contact/state');
   if(!alive)return;setHealth(h);
   if(state.events.length){state.events.forEach(e=>receiver.current(e,true));}else{const history=await api<{messages:({role:'user'|'assistant'}&ChatResponse)[]}>('/api/chat/history');if(!alive)return;for(const message of history.messages){if(message.role==='user')add({role:'user',text:message.text});else displayResponse(message);}}
   if(!alive)return;setChatPending(state.pending);setReady(true);setBusy('');
   source=new EventSource(`/api/contact/events?after=${state.cursor}`);
   source.onmessage=e=>{try{receiver.current(JSON.parse(e.data));}catch{setError('消息显示异常，请刷新恢复记录。');}};
   source.onerror=()=>setContactStatus('消息连接正在恢复，已接收的消息仍会继续处理。');
   source.onopen=()=>setContactStatus('');
   const actions=await api<{actions:ActionPlan[]}>('/api/actions');if(alive)actions.actions.forEach(updateAction);
  }).catch(()=>{if(alive){setError('未能连接小瑞，请检查服务后刷新页面。');setBusy('');}});
  const t=setInterval(()=>setNow(Date.now()),1000);return()=>{alive=false;source?.close();clearInterval(t);};
 },[]);
 useEffect(()=>{const element=composerWrap.current;if(!element)return;const measure=()=>document.documentElement.style.setProperty('--composer-height',`${element.getBoundingClientRect().height}px`);measure();const observer=new ResizeObserver(measure);observer.observe(element);return()=>{observer.disconnect();document.documentElement.style.removeProperty('--composer-height');};},[]);
 useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth',block:'end'})},[messages,busy,liveReply]);
 useEffect(()=>{if(!modal)return;const previous=document.activeElement as HTMLElement|null;const el=dialog.current;el?.querySelector<HTMLButtonElement>('button')?.focus();function key(e:KeyboardEvent){if(e.key==='Escape')setModal(false);if(e.key==='Tab'&&el){const b=Array.from(el.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));if(!b.length)return;const first=b[0],last=b[b.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}}document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus()}},[modal]);
 useEffect(()=>{if(!extrasOpen)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape')setExtrasOpen(false);};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);},[extrasOpen]);
 const blocked=Boolean(plan&&['unknown','submitting','rechecking'].includes(plan.status));
 async function task(title:string,fn:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(title);setError('');try{await fn()}catch(e){setError(e instanceof Error?e.message:'暂时没有完成，请重试。')}finally{setBusy('');lock.current=false}}
 function update(p:Plan){setPlan(p);setMessages(old=>old.map(m=>m.plan?.id===p.id?{...m,plan:p}:m))}
 function updateAction(p:ActionPlan){setMessages(old=>old.map(m=>m.actionPlan?.id===p.id?{...m,actionPlan:p}:m))}
 async function release(){if(plan&&['awaiting_confirmation','needs_review','expired'].includes(plan.status)){const d=await api<{plan:Plan}>(`/api/plans/${plan.id}/cancel`,{});update(d.plan)}}
 function displayResponse(d:ChatResponse){
   const response:Omit<Message,'id'>={role:'assistant',text:d.text,speech_text:d.speech_text};
   const events=(d.events??[]).filter(event=>['stores','meals','plan','action_plan','service_choices'].includes(event.type));
   if(!events.length&&(d.text||d.speech_text))add(response);
   events.forEach((event,i)=>{
    const message:Omit<Message,'id'>={role:'assistant',text:i===0?d.text:'',speech_text:i===0?d.speech_text:undefined};
    if(event.type==='stores'){setStores(event.stores);setMeals([]);message.kind='stores';message.stores=event.stores}
    if(event.type==='meals'){setMeals(event.meals);message.kind='meals';message.meals=event.meals}
    if(event.type==='plan'){update(event.plan);message.kind='plan';message.plan=event.plan}
    if(event.type==='action_plan'){updateAction(event.plan);setActiveAction(event.plan.id);message.actionPlan=event.plan}
    if(event.type==='service_choices'){message.choices=event.choices;setActiveChoices(event.choices)}
    add(message);
   });
 }
 async function send(spoken?:string){
  const outgoingImages=spoken===undefined?attachments:[];const text=(spoken??input).trim()||(outgoingImages.length?'请看看这张图片。':'');if(!text||!ready||uploading)return;
  if(outgoingImages.length)setAttachments([]);setExtrasOpen(false);
  voice.stopSpeech();autoplayAllowed.current=true;setVoiceNotice('');interrupted.current=true;setLiveReply('');setInput('');setActiveChoices(undefined);setActiveAction('');setPlan(undefined);setModal(false);
  const client_id=crypto.randomUUID();add({role:'user',text,client_id,images:outgoingImages,delivery:'正在发送'});
  await transmit(text,client_id,outgoingImages);
 }
 async function transmit(text:string,client_id:string,images:ImageMessage[]=[]){
  try{await api('/api/contact/messages',{text,client_id,image_ids:images.map(i=>i.id)});}
  catch(e){setMessages(old=>old.map(m=>m.client_id===client_id&&m.delivery!=='已送达'?{...m,delivery:'发送结果待核实'}:m));setError(e instanceof Error?e.message:'连接已断开，可以点击消息旁重试；不会重复提交同一条消息。');}
 }
 async function selectImages(files:FileList|null){
  if(!files?.length)return;setExtrasOpen(false);setUploading(true);setError('');
  try{if(files.length+attachments.length>4)throw Error('每条消息最多发送四张图片。');
   for(const file of Array.from(files)){
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>8_000_000)throw Error('请选择 8 MB 以内的 JPG、PNG 或 WebP 图片。');
    const data_url=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(Error('图片读取失败，请重新选择。'));reader.readAsDataURL(file);});
    const image=await api<ImageMessage>('/api/contact/images',{data_url});setAttachments(old=>[...old,image]);
   }
  }catch(e){setError(e instanceof Error?e.message:'图片暂时无法发送。');}finally{setUploading(false);if(imageInput.current)imageInput.current.value='';}
 }
 function playReply(text:string){autoplayAllowed.current=false;setVoiceNotice('');void voice.speak(text);}
 function stopPlayback(){autoplayAllowed.current=false;voice.stopSpeech();setVoiceNotice('已停止播报，文字消息仍然保留。');}
 function cancelVoiceMessage(){autoplayAllowed.current=false;interrupted.current=true;voice.cancelRecording();setVoiceNotice('已取消这段录音，没有发送。');}
 function hangup(){autoplayAllowed.current=false;interrupted.current=true;voice.endCall();setVoiceNotice('已挂断，已停止收音和播报。'+(chatPending?'已接收的消息仍会继续处理。':''));}
 function switchInput(){if(messageCaptureActive)cancelVoiceMessage();setInputMode(old=>old==='text'?'voice':'text');setExtrasOpen(false);}
 async function chooseStore(s:Store){await send(`选择门店：${s.name}。`)}
 async function selectMeal(m:Meal,index:number){await send(`选第${index+1}份套餐，${m.name}。`)}
 async function cancel(p:Plan){await task('正在取消方案',async()=>{const d=await api<{plan:Plan}>(`/api/plans/${p.id}/cancel`,{});update(d.plan);add({role:'assistant',text:'这份方案已取消，没有创建订单。您可以重新选择。'})})}
 async function confirm(){if(!plan)return;setModal(false);await task('正在核实价格并创建订单，请勿重复操作',async()=>{try{const d=await api<{plan:Plan}>(`/api/plans/${plan.id}/confirm`,{version:plan.version,confirmation_token:plan.confirmation_token,confirmation_text:'确认下单'});update(d.plan)}catch(e){try{const d=await api<{plan:Plan}>(`/api/plans/${plan.id}`);update(d.plan)}catch{}throw e}})}
 async function fresh(){if(blocked||chatPending)return;voice.cancel();voice.stopSpeech();await task('正在开始新对话',async()=>{await release();await api('/api/chat/reset',{});setMessages([]);setStores([]);setMeals([]);setPlan(undefined);setModal(false);setInput('');setAttachments([]);setExtrasOpen(false)})}
 function planCard(p:Plan){const current=p.id===plan?.id;const review=['awaiting_confirmation','needs_review'].includes(p.status);const expired=p.expires_at*1000<=now;const payment=p.order?.payment_url;return <div className="order-card"><div className="card-overline">{labels[expired&&review?'expired':p.status]||p.status}</div><h3>{p.summary.product_name} <small>×{p.summary.quantity}</small></h3><ul>{p.summary.choices.map((s,i)=><li key={i}>{s}</li>)}</ul><div className="pickup"><strong>{p.summary.store_name}</strong><span>{p.summary.store_address}</span><span>{p.summary.take_way}</span></div><div className="total"><span>本次总价</span><strong>{yuan(p.amount_cents)}</strong></div>{p.error&&<p className="note">{p.error}</p>}{review&&!health?.order_execution_enabled&&<p className="note">当前仅查看真实报价，下单尚未开启。</p>}{p.status==='unknown'&&<p className="note">请到麦当劳官方渠道核查，暂时不要重复下单。</p>}{p.status==='created'&&<><p>订单号：{p.order?.order_id}，尚未代表支付成功。</p>{payment?.startsWith('https://')&&<a className="primary link-button" href={payment} target="_blank" rel="noreferrer">前往官方支付页面 ↗</a>}</>}{review&&current&&<div className="card-actions"><button className="primary" disabled={!!busy||expired||!health?.order_execution_enabled} onClick={()=>setModal(true)}>确认这个方案</button><button disabled={!!busy} onClick={()=>cancel(p)}>取消方案</button></div>}<small className="disclaimer">到店自取 · 官方核价 · 下单前再次核实</small></div>}
 const mood=companionMood({phase:voice.phase,recording:voice.recording,speaking:voice.speaking,loadingSpeech:voice.loadingSpeech,pending:chatPending,context:contactStatus+' '+(messages.filter(m=>m.role==='user').at(-1)?.text||'')});
 const companionLabel=messageCaptureActive||voice.inCall?'慢慢说，我在这里':voice.speaking?'正在说给您听':voice.loadingSpeech?'正在准备语音':chatPending?contactStatus||'正在帮您处理':'今天也陪着您';
 function openSettings(){if(messageCaptureActive)cancelVoiceMessage();if(voice.inCall)hangup();voice.stopSpeech();autoplayAllowed.current=false;setSettingsOpen(true);}
 return <div className={messages.length?'app':'app empty'}>
  <aside className="sidebar" aria-label="陪伴与设置">
   <div className="sidebar-wordmark"><span className="wordmark-spark" aria-hidden="true">✳</span><span>生活，慢一点也好</span></div>
   <button type="button" className="identity-button" onClick={openSettings} aria-label={`设置${settings.name}的名字、头像和服务`}>
    <CompanionAvatar variant={settings.avatar} name={settings.name}/><span className="identity-copy"><strong>{settings.name}</strong><span>您的生活小帮手</span></span><svg className="identity-settings" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m10 3-1 3-3 1-2 3 2 3v4l3 1 3 3 3-2 3-1v-4l2-3-2-3-3-1-2-3-3 1Z"/><circle cx="12" cy="12" r="3"/></svg>
   </button>
   <div className="sidebar-companion"><Companion mood={mood} label={companionLabel} name={settings.name}/></div>
   <div className="sidebar-links"><button type="button" className="sidebar-link is-current" onClick={()=>end.current?.scrollIntoView({behavior:'smooth',block:'end'})}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M5 5h14v11H9l-4 4V5Z"/><path d="M9 9h6M9 12h4"/></svg><span>我们的对话</span><span className="nav-indicator"/></button><button type="button" className="sidebar-link" onClick={openSettings}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M4 11 12 4l8 7v9h-6v-6h-4v6H4v-9Z"/></svg><span>设置与家人协助</span></button></div>
   <div className="sidebar-note"><span className="note-line"/><p>小事交给我<br/>日子慢慢过。</p><span>一份安心，随时在身边</span></div>
  </aside>
  <div className="workspace">
   <header className="workspace-header"><div className="workspace-label"><span className="connection-dot" data-connected={ready}/><span>陪您把小事办好</span></div><button className="new-chat" onClick={fresh} disabled={!!busy||blocked||!!chatPending}><span aria-hidden="true">＋</span> 新对话</button></header>
   <main className={messages.length?'conversation':'welcome'} onClick={()=>setExtrasOpen(false)}>
    {!messages.length?<div className="greeting"><div className="hero-eyebrow"><span/>今天也有我陪您</div><h1>日子里的小事，<br/>我们一起安排<span className="hero-period">。</span></h1><p>您好，我是{settings.name}。<br className="mobile-break"/>想办点事，或聊聊今天，都可以。</p><div className="suggestions-label">从一件小事开始</div><div className="suggestion-grid">
     <button type="button" className="suggestion-card" disabled={!ready||!!busy} onClick={()=>void send('帮我查查附近的麦当劳，请先问我所在的位置。')}><span className="suggestion-icon icon-dining"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M5 3v7m3-7v7M3 7h7m-4 3v11M17 3v18m0-18c-5 4-5 9 0 9"/></svg></span><strong>吃点喜欢的</strong><span className="suggestion-detail">帮您查门店和菜单</span><span className="suggestion-arrow" aria-hidden="true">↗</span></button>
     <button type="button" className="suggestion-card" disabled={!ready||!!busy} onClick={()=>void send('我想打车，请先问我出发地和目的地。')}><span className="suggestion-icon icon-travel"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m5 9 2-5h10l2 5m-16 1h18v8H3v-8Zm2 8v3m14-3v3M7 13h1m8 0h1M10 4V2h4v2"/></svg></span><strong>安心出个门</strong><span className="suggestion-detail">先确认从哪儿到哪儿</span><span className="suggestion-arrow" aria-hidden="true">↗</span></button>
     <button type="button" className="suggestion-card" disabled={!ready||!!busy} onClick={()=>void send('陪我聊会儿天吧。')}><span className="suggestion-icon icon-chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M4 4h16v12h-9l-6 4v-4H4V4Z"/><path d="M8 9h8m-8 3h5"/></svg></span><strong>陪我聊一会儿</strong><span className="suggestion-detail">说说今天的新鲜事</span><span className="suggestion-arrow" aria-hidden="true">↗</span></button>
    </div></div>:messages.map(m=><article className={'message '+m.role} key={m.id}><div className="avatar" aria-hidden="true">{m.role==='assistant'?settings.name.slice(0,1):'您'}</div><div className="message-body">{!!m.images?.length&&<div className="message-images">{m.images.map(image=><a href={image.url} target="_blank" rel="noreferrer" key={image.id}><img src={image.url} alt="发送的图片"/></a>)}</div>}{m.text&&<p className="message-text">{m.text}</p>}{m.delivery&&<small className="delivery">{m.delivery}{m.delivery==='发送结果待核实'&&m.client_id&&<button type="button" onClick={()=>void transmit(m.text,m.client_id!,m.images)}>重试发送</button>}</small>}{m.speech_text&&<button className="speech-button" type="button" onClick={()=>voice.speaking||voice.loadingSpeech?stopPlayback():playReply(m.speech_text!)}>{voice.loadingSpeech?'停止生成语音':voice.speaking?'停止播报':`▶ 听${settings.name}说`}</button>}{m.stores&&<div className="store-list">{m.stores.map(s=><button className="store-card" key={s.code} onClick={()=>chooseStore(s)} disabled={!!busy||blocked||s.open===false||m.stores!==stores}><strong>{s.name}</strong><span>{s.address}{s.open===false?' · 暂未营业':''}</span><small>在这家取餐 →</small></button>)}</div>}{m.meals&&<div className="meal-grid">{m.meals.map((meal,i)=><div className="meal-card" key={meal.product_code}><div className="meal-image">{meal.image?<img src={meal.image} alt={meal.name} loading="lazy"/>:<span>暂无餐品图片</span>}<span className="letter">{String.fromCharCode(65+i)}</span></div><div className="meal-content"><h3>{meal.name}</h3><p>{meal.choices.join(' · ')}</p><strong className="meal-price">{yuan(meal.amount_cents)}</strong><small>到店自取 · 本次官方核价</small><button disabled={!!busy||blocked||m.meals!==meals} onClick={()=>selectMeal(meal,i)}>选 {String.fromCharCode(65+i)} 这份</button></div></div>)}</div>}{m.plan&&planCard(m.plan)}{m.actionPlan&&<ActionCard plan={m.actionPlan} active={m.actionPlan.id===activeAction&&chatPending===0} onChange={updateAction} speak={playReply}/>} {m.choices&&<div className="service-choice-grid">{m.choices.map((c,i)=><button className="store-card" key={i} disabled={!!busy||m.choices!==activeChoices} onClick={()=>void send(c.prompt)}>{c.image&&<img src={c.image} alt={c.label} loading="lazy"/>}<strong>{c.label}</strong>{c.detail&&<span>{c.detail}</span>}</button>)}</div>}</div></article>)}
    {liveReply&&<article className="message assistant"><div className="avatar" aria-hidden="true">{settings.name.slice(0,1)}</div><div className="message-body"><p className="message-text">{liveReply}</p></div></article>}
    {busy&&messages.length>0&&<div className="busy" role="status"><span className="spinner"/>{busy}…</div>}
    {error&&<div className="error" role="alert">{error}<button type="button" onClick={()=>setError('')}>知道了</button></div>}
    <div ref={end}/>
   </main>
   <div className="composer-wrap" ref={composerWrap}><ActivityStrip voice={voice} pending={chatPending} busy={busy} progress={contactStatus} notice={voiceNotice} ready={ready} onStopSpeech={stopPlayback} onCancelRecording={cancelVoiceMessage} holdActive={holdActive} name={settings.name}/>{voice.inCall&&<div className="call-bar" role="status"><span className="call-dot"/><div><strong>{voice.phase==='connecting'?`正在接通${settings.name}`:`与${settings.name}通话中`}</strong><span>{voice.transcript||'挂断只停止收音和播报；已接收的消息仍会处理。'}</span></div><div className="call-controls"><button type="button" onClick={voice.finish} disabled={voice.phase!=='listening'}>我说完了</button><button type="button" className="hangup" onClick={hangup}>挂断</button></div></div>}{attachments.length>0&&<div className="attachment-tray">{attachments.map(image=><div key={image.id}><img src={image.url} alt="待发送图片"/><button type="button" aria-label="移除这张图片" onClick={()=>setAttachments(old=>old.filter(i=>i.id!==image.id))}>×</button></div>)}<span>图片将随下一条消息发送</span></div>}{uploading&&<div className="upload-progress" role="status">正在准备图片…</div>}
<form className="composer wechat-composer" onSubmit={e=>{e.preventDefault();void send();}}>
<button type="button" className="mode-switch" disabled={!ready||voice.inCall} onClick={switchInput} aria-label={inputMode==='text'?'切换到语音输入':'切换到文字输入'} title={inputMode==='text'?'语音输入':'文字输入'}>{inputMode==='text'?<Mic/>:<Keyboard/>}</button>
{inputMode==='text'||voice.inCall?<><label className="sr-only" htmlFor="chat-input">发消息给小瑞</label><HoldToTalk resetKey={voiceErrorGeneration} disabled={settingsOpen||modal||!ready||voice.inCall||(messageCaptureActive&&!holdActive)} onStart={()=>{setVoiceNotice('');return voice.startRecording();}} onFinish={voice.stopRecording} onCancel={cancelVoiceMessage} onHoldChange={setHoldActive}><textarea id="chat-input" value={input} onFocus={()=>setExtrasOpen(false)} onChange={e=>setInput(e.target.value)} placeholder={voice.inCall?'通话中也可以打字补充':`和${settings.name}说点什么…`} rows={1} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send();}}}/></HoldToTalk></>:<button type="button" className={'record-line '+(voice.recording?'is-listening':'')} disabled={!ready||voice.phase==='finishing'} onClick={()=>{if(voice.recording)voice.stopRecording();else{setVoiceNotice('');void voice.startRecording();}}} aria-label={voice.phase==='finishing'?'正在识别语音':voice.recording?'停止录音并发送':'开始语音输入'}><span className="record-indicator">{voice.recording?<span className="stop-square"/>:<Mic/>}</span><span className="record-caption">{voice.phase==='finishing'?'正在识别…':voice.phase==='connecting'?'正在连接…':voice.recording?'停止录音并发送':'点击说话'}</span></button>}
<button className="send" disabled={!ready||uploading||(!input.trim()&&!attachments.length)} aria-label="发送消息"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button>
<button type="button" className={'mode-switch plus-button '+(extrasOpen?'expanded':'')} disabled={!ready} aria-label={extrasOpen?'收起更多功能':'更多功能'} aria-expanded={extrasOpen} aria-controls="composer-extras" onClick={()=>{if(messageCaptureActive)cancelVoiceMessage();setExtrasOpen(old=>!old);}}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v10M7 12h10"/></svg></button>
<input ref={imageInput} type="file" hidden style={{display:'none'}} tabIndex={-1} accept="image/jpeg,image/png,image/webp" multiple aria-label="选择图片" onChange={e=>void selectImages(e.target.files)}/>
</form>{extrasOpen&&<div id="composer-extras" className="composer-extras" aria-label="更多功能"><button type="button" disabled={uploading} onClick={()=>imageInput.current?.click()}><span className="extra-icon"><Photo/></span><span>图片</span></button><button type="button" onClick={()=>{setExtrasOpen(false);setInputMode('text');if(voice.inCall)hangup();else{setVoiceNotice('');void voice.startCall();}}}><span className="extra-icon"><Phone/></span><span>{voice.inCall?'结束通话':'语音通话'}</span></button></div>}<p className="composer-guide">轻点打字 · 按住输入框说话，上滑取消</p></div>
  </div>
  <SettingsDialog open={settingsOpen} onClose={()=>{setSettingsOpen(false);void api<Health>('/api/health').then(setHealth).catch(()=>{});}} settings={settings} onChange={updateSettings}/>
  {modal&&plan&&<div className="modal-backdrop"><div ref={dialog} className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><h2 id="confirm-title">最后确认一次</h2><p>{plan.summary.product_name}，共 {yuan(plan.amount_cents)}，在 {plan.summary.store_name} {plan.summary.take_way}。</p><p>确认后将创建真实待支付订单，支付仍在官方页面完成。</p><button onClick={()=>setModal(false)}>先不下单，返回看看</button><button className="primary" onClick={confirm} disabled={!!busy||!health?.order_execution_enabled}>确认下单 · {yuan(plan.amount_cents)}</button></div></div>}
 </div>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
