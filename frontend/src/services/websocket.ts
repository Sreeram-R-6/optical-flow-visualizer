import type {Telemetry} from '../types/telemetry';
import {defaultSettings} from '../types/telemetry';
type DemoSession={settings:Telemetry['settings'];controls:{mode:'auto'|'manual';north:number;east:number};active:boolean;revision:number;elapsed:number;north:number;east:number;flow_north:number;flow_east:number};
const newSession=():DemoSession=>({settings:{...defaultSettings},controls:{mode:'auto',north:0,east:0},active:false,revision:0,elapsed:0,north:0,east:0,flow_north:0,flow_east:0});
let session=newSession(), version=0;
const mode=()=>fetch('/api/health').then(r=>{if(!r.ok)throw new Error('Backend unavailable');return r.json();}).then(d=>d.mode==='hosted_demo');
let detected:ReturnType<typeof mode>|undefined;
async function hosted(){try{return await (detected??=mode());}catch(e){detected=undefined;throw e;}}
export async function api<T=unknown>(path:string, body?:unknown):Promise<T> {
  if(await hosted()){
    if(path!=='simulation/input'&&path!=='ports')version++;
    if(path==='ports')return [] as T;
    if(path==='settings'){
      const next=body as Telemetry['settings'];
      const axes=['flow_input','swap_xy','invert_x','invert_y','rotation','yaw_compensation','gyro_compensation'] as const;
      if(axes.some(key=>next[key]!==session.settings[key])){session.flow_north=session.flow_east=0;session.revision++;}
      if(next.source!==session.settings.source)session.revision++;
      session.settings=next;
    }
    else if(path==='simulation/start'){const settings=session.settings;session={...newSession(),settings,active:true,revision:session.revision+1};}
    else if(path==='simulation/input')session.controls=body as DemoSession['controls'];
    else if(path==='disconnect')session.active=false;
    else if(path==='reset-origin'){session.north=session.east=session.flow_north=session.flow_east=0;session.revision++;}
    else throw new Error('USB telemetry is available through the local start.bat launcher.');
    return {} as T;
  }
  const response = await fetch(`/api/${path}`, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (!response.ok) { const data = await response.json().catch(()=>({})); throw new Error(data.detail || `Request failed (${response.status})`); }
  return response.json() as Promise<T>;
}
export function openTelemetry(onPacket:(data:Telemetry)=>void,onStatus:(live:boolean)=>void) {
  let socket:WebSocket|undefined, timer:ReturnType<typeof setTimeout>, closed=false;
  const connect=()=>{
    socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/telemetry`);
    socket.onopen=()=>onStatus(true);
    socket.onmessage=e=>{try{const data=JSON.parse(e.data);if(data.position && data.settings)onPacket(data);}catch{onStatus(false);}};
    socket.onclose=()=>{onStatus(false);if(!closed)timer=setTimeout(connect,1500);};
    socket.onerror=()=>socket?.close();
  };
  let request:AbortController|undefined;
  const poll=async()=>{
    const current=version;
    request=new AbortController();
    const timeout=setTimeout(()=>request?.abort(),10000);
    try{
      const response=await fetch('/api/demo/step',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session,dt:document.hidden?0:0.2}),signal:request.signal});
      if(!response.ok)throw new Error('Demo update failed');
      const data=await response.json();
      if(!closed&&version===current){session={...data.session,controls:session.controls};onPacket(data.telemetry);onStatus(true);}
    }catch{if(!closed)onStatus(false);}finally{clearTimeout(timeout);if(!closed)timer=setTimeout(poll,200);}
  };
  const start=async()=>{try{if(await hosted()){if(!closed)void poll();}else if(!closed)connect();}catch{if(!closed){onStatus(false);timer=setTimeout(start,1500);}}};
  void start();
  return ()=>{closed=true;clearTimeout(timer);request?.abort();socket?.close();};
}
