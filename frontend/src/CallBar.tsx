import React from 'react';
export type PhoneCall={id:string;started_at:number;ended_at?:number;duration_seconds?:number};
export function callDuration(seconds:number){const value=Math.max(0,Math.floor(seconds));return `${Math.floor(value/60).toString().padStart(2,'0')}:${(value%60).toString().padStart(2,'0')}`;}
export function CallBar({name,elapsed,connecting,speaking,loading,processing,progress,onFinish,onHangup}:{name:string;elapsed:number;connecting:boolean;speaking:boolean;loading:boolean;processing:boolean;progress?:string;onFinish:()=>void;onHangup:()=>void}){
 const status=connecting?'正在接通':speaking?`${name}正在说`:loading?'正在准备语音':progress?progress:processing?`${name}在听，也在帮您处理`:'您说，我在听';
 return <section className="phone-island" aria-label="语音通话"><div className="phone-island-copy" role="status"><span className="phone-pulse" aria-hidden="true"/><div><strong>{connecting?'正在接通':'通话中'} <time>{callDuration(elapsed)}</time></strong><span>{status}</span></div></div><div className="phone-island-controls"><button type="button" onClick={onFinish} disabled={connecting||speaking}>我说完了</button><button type="button" className="phone-hangup" onClick={onHangup}>挂断</button></div></section>;
}
