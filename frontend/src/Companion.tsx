import React,{useState} from 'react';

export type CompanionMood='idle'|'working'|'taxi'|'dining'|'listening'|'speaking';
export function companionMood({phase,recording,speaking,loadingSpeech,pending,context}:{phase:string;recording:boolean;speaking:boolean;loadingSpeech:boolean;pending:number;context:string}):CompanionMood{
 if(recording||phase==='connecting'||phase==='finishing'||phase==='listening')return 'listening';
 if(speaking||loadingSpeech)return 'speaking';
 if(!pending)return 'idle';
 if(/打车|叫车|司机|出发|目的地|出行|滴滴/.test(context))return 'taxi';
 if(/麦当劳|菜单|门店|点餐|吃|餐|咖啡/.test(context))return 'dining';
 return 'working';
}
export function CompanionAvatar({variant='portrait',name='小瑞'}:{variant?:'portrait'|'leaf'|'sun';name?:string}){
 const [failed,setFailed]=useState(false);
 return <span className={'companion-avatar avatar-'+variant} aria-hidden="true">{variant==='portrait'?failed?<span>{name.slice(0,1)}</span>:<img src="/mascot/xiaorui-working.png" alt="" onError={()=>setFailed(true)}/>:variant==='leaf'?<svg viewBox="0 0 32 32" fill="none"><path d="M25 6C12 4 5 11 8 20c8 6 18 0 17-14Z" fill="currentColor" opacity=".2"/><path d="M9 25 23 10M13 19l-1-6m6 1 5 1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>:<svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="6" fill="currentColor" opacity=".3"/><circle cx="16" cy="16" r="5" stroke="currentColor" strokeWidth="1.6"/><path d="M16 3v3m0 20v3M3 16h3m20 0h3M7 7l2 2m14 14 2 2M7 25l2-2M23 9l2-2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>}</span>;
}
function DrawnCompanion(){return <svg className="drawn-companion" viewBox="0 0 240 250" fill="none" aria-hidden="true"><ellipse cx="120" cy="231" rx="67" ry="7" fill="#DAD8CD" opacity=".65"/><path d="m98 180-5 42m48-42 5 42" stroke="#43554D" strokeWidth="17" strokeLinecap="round"/><path d="M76 226c5-10 12-12 21-11l4 14H76Zm65-11c10-2 16 1 22 12h-27l5-12Z" fill="#283E36"/><path d="M85 110c8-12 55-12 67 0l11 65c-11 18-67 18-85-1l7-64Z" fill="#B9785F"/><path d="m91 115-15 37m72-37 17 38" stroke="#B9785F" strokeWidth="20" strokeLinecap="round"/><path d="m77 151 16 13m70-11-16 11" stroke="#E5B69A" strokeWidth="12" strokeLinecap="round"/><path d="M101 91v17c6 7 26 7 33 0V91" fill="#DDA88B"/><ellipse cx="118" cy="68" rx="35" ry="39" fill="#EBC7AB"/><path d="M83 66c-7-31 15-52 39-48 25 0 40 17 34 44-14 1-21-17-23-22-10 18-29 13-42 17l-2 15-6-6Z" fill="#374940"/><path d="M84 70c-13-5-11 15 2 15m69-15c13-5 11 15-2 15" fill="#EBC7AB"/><path d="M102 71h1m29 0h1" stroke="#36483D" strokeWidth="4" strokeLinecap="round"/><path d="M110 86c5 4 12 4 17-1" stroke="#AC7158" strokeWidth="2.5" strokeLinecap="round"/><path d="m116 73-2 7 4 1" stroke="#D69E7F" strokeWidth="2" strokeLinecap="round"/><rect x="76" y="143" width="90" height="49" rx="6" fill="#F4EADC" stroke="#A38568" strokeWidth="2"/><path d="M83 148h76" stroke="#fff" strokeOpacity=".7"/><circle cx="90" cy="163" r="5" fill="#E7BA9B"/><circle cx="151" cy="163" r="5" fill="#E7BA9B"/></svg>}
export function Companion({mood,label,name}:{mood:CompanionMood;label:string;name:string}){
 const [failedSource,setFailedSource]=useState('');
 const asset=mood==='taxi'?'taxi':mood==='dining'?'dining':mood==='working'||mood==='listening'?'working':'working';
 const source=`/mascot/xiaorui-${asset}.png`;
 return <div className={'companion-scene scene-'+mood} data-state={mood}>
  <div className="companion-halo" aria-hidden="true"/>
  <div className="companion-figure">{failedSource===source?<DrawnCompanion/>:<img className="mascot-image" src={source} alt={`${name}的陪伴形象`} onError={()=>setFailedSource(source)}/>}</div>
  <div className="companion-prop" aria-hidden="true">{mood==='taxi'?<svg viewBox="0 0 60 38"><path d="m10 15 7-10h25l8 10 6 4v12H4V20l6-5Z" fill="#CCA45F"/><path d="m21 9-5 8h29l-6-8H21Z" fill="#F5EEE1"/><circle cx="15" cy="30" r="6" fill="#34463E"/><circle cx="45" cy="30" r="6" fill="#34463E"/></svg>:mood==='dining'?<svg viewBox="0 0 44 52"><path d="M8 7h28v40H8z" fill="#F0E5D4" stroke="#B68C67" strokeWidth="2"/><path d="M14 16h16M14 23h16M14 30h10" stroke="#8B9C87" strokeWidth="2"/><path d="M14 37h16" stroke="#BE765B" strokeWidth="3"/></svg>:mood==='working'?<span className="thought-dots">···</span>:null}</div>
  <div className="companion-sign" aria-hidden="true">{mood==='listening'?'慢慢说，我在听':mood==='speaking'?'说给您听':mood==='idle'?'有我在，慢慢来':'正在认真帮您'}</div>
  <p className="companion-caption"><span className={mood==='idle'?'':'is-active'} aria-hidden="true"/>{label}</p>
 </div>;
}
