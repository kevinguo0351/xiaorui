import {useEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent,ReactNode} from 'react';

// Initial gesture design estimates, to be checked on target devices/users.
const HOLD_DELAY_MS=350;
const SCROLL_SLOP_PX=12;
const CANCEL_UP_PX=64;
type Props={children:ReactNode;onStart:()=>void|Promise<void>;onFinish:()=>void;onCancel:()=>void;onHoldChange?:(holding:boolean)=>void;disabled?:boolean;className?:string;resetKey?:string|number};
type Press={pointerId:number;x:number;y:number;target:HTMLDivElement;timer?:ReturnType<typeof setTimeout>;holding:boolean};

/** Observe textarea presses without cancelling short taps, selection or scrolling.
 * The ordinary accessible voice button remains the keyboard alternative.
 * disabled must express external availability, not recording/connecting state.
 */
export function HoldToTalk(props:Props){
 const latest=useRef(props);latest.current=props;
 const press=useRef<Press|undefined>(undefined),mounted=useRef(true),suppressUntil=useRef(0);
 const [holding,setHolding]=useState(false);
 function end(send:boolean){const current=press.current;if(!current)return;press.current=undefined;clearTimeout(current.timer);
  if(current.holding){suppressUntil.current=Date.now()+700;try{if(current.target.hasPointerCapture(current.pointerId))current.target.releasePointerCapture(current.pointerId);}catch{/* pointer already released */}
   if(mounted.current)setHolding(false);latest.current.onHoldChange?.(false);if(send)latest.current.onFinish();else latest.current.onCancel();}}
 function down(event:ReactPointerEvent<HTMLDivElement>){
  if(latest.current.disabled||press.current||!event.isPrimary||event.button!==0||!(event.target instanceof HTMLTextAreaElement)||event.target.disabled||event.target.readOnly)return;
  suppressUntil.current=0;
  const current:Press={pointerId:event.pointerId,x:event.clientX,y:event.clientY,target:event.currentTarget,holding:false};press.current=current;
  current.timer=setTimeout(()=>{if(press.current!==current)return;if(latest.current.disabled||document.visibilityState==='hidden')return end(false);
   current.holding=true;setHolding(true);latest.current.onHoldChange?.(true);
   try{current.target.setPointerCapture(current.pointerId);}catch{/* document release/cancel listener remains available */}
   try{Promise.resolve(latest.current.onStart()).catch(()=>{if(press.current===current)end(false);});}catch{if(press.current===current)end(false);}
  },HOLD_DELAY_MS);
 }
 function move(event:ReactPointerEvent<HTMLDivElement>){const current=press.current;if(!current||current.pointerId!==event.pointerId)return;
  if(!current.holding){if(Math.hypot(event.clientX-current.x,event.clientY-current.y)>SCROLL_SLOP_PX)end(false);return;}
  // Prevent scrolling only after the hold has claimed this gesture.
  event.preventDefault();if(event.clientY-current.y<=-CANCEL_UP_PX)end(false);
 }
 function up(event:{pointerId:number;preventDefault:()=>void}){const current=press.current;if(!current||current.pointerId!==event.pointerId)return;if(current.holding)event.preventDefault();end(true);}
 function cancelled(event:{pointerId:number}){if(press.current?.pointerId===event.pointerId)end(false);}
 useEffect(()=>{mounted.current=true;
  const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&press.current){if(press.current.holding)event.preventDefault();end(false);}};
  const hidden=()=>{if(document.visibilityState==='hidden')end(false);};
  const blur=()=>end(false);
  document.addEventListener('pointerup',up,true);document.addEventListener('pointercancel',cancelled,true);document.addEventListener('keydown',key);document.addEventListener('visibilitychange',hidden);window.addEventListener('blur',blur);
  return()=>{mounted.current=false;end(false);document.removeEventListener('pointerup',up,true);document.removeEventListener('pointercancel',cancelled,true);document.removeEventListener('keydown',key);document.removeEventListener('visibilitychange',hidden);window.removeEventListener('blur',blur);};
 },[]);
 useEffect(()=>{if(props.disabled)end(false);},[props.disabled]);
 useEffect(()=>{end(false);},[props.resetKey]);
 return <div className={['hold-to-talk',props.className].filter(Boolean).join(' ')} data-holding={holding?'true':'false'}
  onPointerDownCapture={down} onPointerMoveCapture={move} onPointerUpCapture={up} onPointerCancelCapture={cancelled}
  onLostPointerCapture={event=>{if(press.current?.holding&&press.current.pointerId===event.pointerId)end(false);}}
  onPointerLeave={event=>{if(press.current?.pointerId===event.pointerId&&!press.current.holding)end(false);}}
  onContextMenuCapture={event=>{if(press.current?.holding||Date.now()<suppressUntil.current){event.preventDefault();event.stopPropagation();}}}
  onClickCapture={event=>{if(Date.now()<suppressUntil.current){event.preventDefault();event.stopPropagation();suppressUntil.current=0;}}}
 >{props.children}</div>;
}
