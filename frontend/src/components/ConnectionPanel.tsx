import {useEffect,useState} from 'react';
import {api} from '../services/websocket';
import type {Telemetry} from '../types/telemetry';
export function ConnectionPanel({data,run,busy}:{data:Telemetry|null;run:(path:string,body?:unknown)=>Promise<void>;busy:boolean}){
  const [ports,setPorts]=useState<{device:string;description:string}[]>([]);
  const [port,setPort]=useState('');
  const [baud,setBaud]=useState(()=>Number(localStorage.getItem('of-baud'))||115200);
  const [error,setError]=useState('');
  const refresh=async()=>{try{setPorts(await api('ports'));setError('');}catch(e){setError(String(e));}};
  useEffect(()=>{void refresh();},[]);
  const active=!!data && ['CONNECTING','WAITING_FOR_HEARTBEAT','CONNECTED'].includes(data.state);
  return <div className="connection"><label>COM port<select value={port} disabled={active||busy} onChange={e=>setPort(e.target.value)}><option value="">Select port</option>{ports.map(p=><option key={p.device} value={p.device}>{p.device} · {p.description}</option>)}</select></label>
    <label>Baud rate<select value={baud} disabled={active||busy} onChange={e=>{setBaud(+e.target.value);localStorage.setItem('of-baud',e.target.value);}}>{[57600,115200,230400,460800,921600].map(b=><option key={b}>{b}</option>)}</select></label>
    <button disabled={busy} onClick={()=>void refresh()} title="Discover currently available Windows COM ports">Refresh ports</button>
    <button className="primary" disabled={busy||(!active&&!port)} onClick={()=>void run(active?'disconnect':'connect',active?{}:{port,baud})}>{busy?'Working…':active?'Disconnect':'Connect'}</button>
    <button disabled={busy||active} onClick={()=>void run('simulation/start',{})}>Start simulation</button>
    {data?.port&&active&&<span className="muted">{data.port} / {data.baud}</span>}{error&&<span className="error">{error}</span>}
  </div>;
}
