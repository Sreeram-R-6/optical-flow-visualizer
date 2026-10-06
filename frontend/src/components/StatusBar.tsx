import type {Telemetry} from '../types/telemetry';
export function StatusBar({data,online}:{data:Telemetry|null;online:boolean}){
  const state=!online?'BACKEND OFFLINE':data?.simulation?'SIMULATION':data?.state.replaceAll('_',' ')||'DISCONNECTED';
  return <div className={`status ${data?.simulation?'sim':data?.connected && online?'live':''}`} role="status"><span className="status-dot"/>{state}{data?.connected&&!data.simulation?' · HEARTBEAT OK':''}</div>;
}
