import type {Telemetry} from '../types/telemetry';
export async function api<T=unknown>(path:string, body?:unknown):Promise<T> {
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
  };connect();
  return ()=>{closed=true;clearTimeout(timer);socket?.close();};
}
