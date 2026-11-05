import React, {useEffect, useRef, useState} from 'react';

type Field = {key:string;label:string;section:string;limit:number;kind?:string;placeholder?:string;value:string;confirmed_at:number|null};
type Card = {version:number;fields:Field[]};
type Stage = 'view'|'edit'|'review';

async function request(body?:unknown):Promise<Card> {
 const response=await fetch('/api/profile/card', body===undefined?undefined:{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!response.headers.get('content-type')?.includes('application/json'))throw Error('资料卡暂时无法连接，请稍后重试。');
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'请核对填写的内容后再保存。');
 return data;
}

export function ProfileCard({onClose,onSaved}:{onClose:()=>void;onSaved:()=>void}) {
 const dialog=useRef<HTMLDialogElement>(null);
 const [card,setCard]=useState<Card>();
 const [draft,setDraft]=useState<Record<string,string>>({});
 const [stage,setStage]=useState<Stage>('view');
 const [loading,setLoading]=useState(true);
 const [saving,setSaving]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [conflict,setConflict]=useState(false);
 useEffect(()=>{
  const previous=document.activeElement as HTMLElement|null;
  dialog.current?.showModal();
  const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
  let alive=true;
  request().then(data=>{if(alive){setCard(data);setDraft(Object.fromEntries(data.fields.map(f=>[f.key,f.value])));}})
   .catch(e=>{if(alive)setError(e.message);}).finally(()=>{if(alive)setLoading(false);});
  return()=>{alive=false;document.body.style.overflow=overflow;previous?.focus();};
 },[]);
 async function reload(){setLoading(true);setError('');try{const data=await request();setCard(data);setDraft(Object.fromEntries(data.fields.map(f=>[f.key,f.value])));setStage('view');setConflict(false);}catch(e){setError(e instanceof Error?e.message:'读取资料失败。');}finally{setLoading(false);}}
 async function save(){
  if(!card||saving)return;setSaving(true);setError('');
  try{const data=await request({version:card.version,fields:draft,confirmation_text:'确认保存资料'});setCard(data);setDraft(Object.fromEntries(data.fields.map(f=>[f.key,f.value])));setStage('view');setNotice('资料已保存，小瑞会以这里确认的信息为准。');setConflict(false);onSaved();}
  catch(e){const message=e instanceof Error?e.message:'保存未完成，填写的内容还在，请稍后重试。';setError(message);if(message.includes('其他页面'))setConflict(true);}
  finally{setSaving(false);}
 }
 function review(e:React.FormEvent){e.preventDefault();setError('');setNotice('');setStage('review');dialog.current?.querySelector('.profile-scroll')?.scrollTo({top:0});}
 const groups=card?[...new Set(card.fields.map(f=>f.section))]:[];
 const filled=card?.fields.filter(f=>f.value&&f.confirmed_at).length||0;
 return <dialog className="profile-dialog" ref={dialog} aria-labelledby="profile-title" onCancel={e=>{e.preventDefault();if(!saving)onClose();}} onClick={e=>{if(e.target===dialog.current&&!saving)onClose();}}>
  <div className="profile-panel">
   <div className="profile-heading"><div><p className="profile-eyebrow">小瑞 · 重要资料</p><h2 id="profile-title">{stage==='review'?'核对后再保存':'我的资料卡'}</h2></div><button type="button" className="profile-close" aria-label="关闭资料卡" disabled={saving} onClick={onClose}>×</button></div>
   <form className="profile-form" onSubmit={stage==='edit'?review:e=>{e.preventDefault();if(stage==='review')void save();}}>
    <div className="profile-scroll">
     <div className="profile-intro"><span className="profile-mark" aria-hidden="true">✓</span><div><strong>{stage==='review'?'请逐项核对地址和电话号码':'重要的信息，亲自核对'}</strong><p>{stage==='review'?'请本人或子女检查以下内容。确认保存后，小瑞将使用这些资料。':'由您或子女填写确认。小瑞不会根据聊天猜填或自动改写。'}</p></div></div>
     {loading?<p className="profile-loading" role="status">正在读取资料…</p>:card&&<>
      {stage==='view'&&<p className="profile-count">已核对 {filled} 项 · 未填写的资料，小瑞会先询问您</p>}
      {groups.map(group=><section className="profile-group" key={group}><h3>{group}</h3>{card.fields.filter(f=>f.section===group).map(field=>
       <div className="profile-field" key={field.key}>
        <label htmlFor={'profile-'+field.key}>{field.label}</label>
        {stage==='edit'?(field.kind==='textarea'?<textarea id={'profile-'+field.key} value={draft[field.key]||''} placeholder={field.placeholder||'暂时不填也可以'} maxLength={field.limit} rows={3} autoComplete="off" onChange={e=>setDraft({...draft,[field.key]:e.target.value})}/>:<input id={'profile-'+field.key} type={field.kind==='tel'?'tel':'text'} inputMode={field.kind==='tel'?'tel':'text'} value={draft[field.key]||''} maxLength={field.limit} placeholder="暂时不填也可以" autoComplete="off" onChange={e=>setDraft({...draft,[field.key]:e.target.value})}/>):<>
         <p className={'profile-value'+(!(stage==='review'?draft[field.key]:field.value)?' unfilled':'')}>{(stage==='review'?draft[field.key]:field.value)||'未填写'}</p>
         {stage==='view'&&field.value&&<small className={field.confirmed_at?'profile-verified':'profile-unverified'}>{field.confirmed_at?'已人工核对 · '+new Date(field.confirmed_at*1000).toLocaleDateString('zh-CN'):'旧记录待核对，小瑞暂不使用'}</small>}
         {stage==='review'&&draft[field.key]!==field.value&&<small className="profile-change">{field.value?<>原资料：{field.value} → {draft[field.key]?'修改':'清除'}</>:'本次新增'}</small>}
        </>}
       </div>)}</section>)}
      {stage==='edit'&&<p className="profile-footnote">不确定的内容可以留空。清空已有字段并确认保存，会移除该项当前资料。</p>}
      {stage==='view'&&<p className="profile-footnote">资料保存在本机。小瑞办事时，相关资料可能发送给模型或服务平台；它不会据此自动拨打联系人电话。</p>}
     </>}
     {notice&&<p className="profile-success" role="status">{notice}</p>}
     {error&&<div className="profile-error" role="alert">{error}{(!card||conflict)&&<button type="button" onClick={()=>void reload()}>重新读取资料</button>}</div>}
    </div>
    {!loading&&card&&<div className="profile-footer">{stage==='view'?<><button type="button" onClick={onClose}>返回聊天</button><button type="button" className="primary" onClick={e=>{e.preventDefault();setStage('edit');setNotice('');setError('');}}>填写或修改</button></>:stage==='edit'?<><button type="button" onClick={()=>{setDraft(Object.fromEntries(card.fields.map(f=>[f.key,f.value])));setStage('view');setError('');}}>取消修改</button><button className="primary" type="submit">下一步，核对资料</button></>:<><button type="button" disabled={saving} onClick={()=>{setStage('edit');setError('');}}>返回修改</button><button className="primary" type="submit" disabled={saving||conflict}>{saving?'正在保存…':'确认保存资料'}</button></>}</div>}
   </form>
  </div>
 </dialog>;
}
