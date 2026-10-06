import {useEffect,useRef,useState} from 'react';
import {api} from '../services/websocket';
export function SimulationControls(){
  const [manual,setManual]=useState(false),[error,setError]=useState('');
  const keys=useRef(new Set<string>());
  useEffect(()=>{
    keys.current.clear();
    const send=()=>{const k=keys.current;void api('simulation/input',{mode:manual?'manual':'auto',north:Number(k.has('w'))-Number(k.has('s')),east:Number(k.has('d'))-Number(k.has('a'))}).catch(e=>setError(String(e)));};
    const down=(e:KeyboardEvent)=>{if(manual && !(e.target instanceof HTMLInputElement||e.target instanceof HTMLSelectElement||e.target instanceof HTMLTextAreaElement)&&['w','a','s','d'].includes(e.key.toLowerCase())){e.preventDefault();keys.current.add(e.key.toLowerCase());}};
    const up=(e:KeyboardEvent)=>keys.current.delete(e.key.toLowerCase());
    const blur=()=>keys.current.clear();
    window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',blur);
    send();const timer=setInterval(send,150);
    return ()=>{clearInterval(timer);keys.current.clear();window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',blur);};
  },[manual]);
  return <div className="simulation-controls"><strong>SIMULATION ONLY</strong><label className="check"><input type="checkbox" checked={manual} onChange={e=>setManual(e.target.checked)}/>Manual movement</label>{manual&&<><span>Hold W/A/S/D or a direction:</span>{[['w','Forward'],['a','Left'],['s','Back'],['d','Right']].map(([key,label])=><button key={key} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);keys.current.add(key);}} onPointerUp={()=>keys.current.delete(key)} onPointerCancel={()=>keys.current.delete(key)} onKeyDown={e=>{if(e.key===' '||e.key==='Enter')keys.current.add(key);}} onKeyUp={()=>keys.current.delete(key)} onBlur={()=>keys.current.delete(key)}>{label}</button>)}</>}{error&&<span className="error">{error}</span>}</div>;
}
