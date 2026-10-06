import type {Telemetry} from '../types/telemetry';
import {FlowPanel} from './FlowPanel';
export function value(v:unknown,digits=2,unit=''){return typeof v==='number'&&Number.isFinite(v)?`${v.toFixed(digits)}${unit}`:'NO DATA';}
export function TelemetryPanel({data,online}:{data:Telemetry|null;online:boolean}){
  const p=data?.position,a=data?.attitude,v=data?.velocity;
  return <aside className="telemetry"><section className="telemetry-group"><div className="section-heading"><h2>Connection</h2><span>{online?'BACKEND ONLINE':'OFFLINE'}</span></div><dl><dt>Vehicle</dt><dd>{data?.simulation?'SIMULATED':data?.connected&&online?'Heartbeat OK':'Not connected'}</dd><dt>Port / baud</dt><dd>{data?.port||'N/A'} / {data?.baud||115200}</dd><dt>System ID</dt><dd>{data?.system_id??'N/A'}</dd><dt>Heartbeat age</dt><dd>{value(data?.heartbeat_age_ms,0,' ms')}</dd></dl></section>
    <FlowPanel data={data} online={online}/><section className="telemetry-group"><div className="section-heading"><h2>Relative position</h2><span>{p?.available&&online?'LIVE':'UNAVAILABLE'}</span></div><dl><dt>North (Y)</dt><dd>{value(p?.north,3,' m')}</dd><dt>East (X)</dt><dd>{value(p?.east,3,' m')}</dd><dt>From origin</dt><dd>{value(p?.distance,3,' m')}</dd></dl>{(!p?.available||!online)&&<small>{!online?'Backend telemetry offline; last values retained.':p?.reason||'Connect a vehicle or start simulation.'}</small>}</section>
    <section className="telemetry-group"><div className="section-heading"><h2>Rangefinder</h2><span>{!online&&data?.rangefinder.distance!=null?'STALE':data?.rangefinder.status||'NO DATA'}</span></div><div className="large-value">{value(data?.rangefinder.distance,2,' m')}</div><small>DISTANCE_SENSOR only · downward-facing</small></section>
    <section className="telemetry-group"><div className="section-heading"><h2>Attitude</h2><span>{!online&&a?.yaw!=null?'STALE':a?.status||'NO DATA'}</span></div><dl><dt>Roll</dt><dd>{value(a?.roll,1,'°')}</dd><dt>Pitch</dt><dd>{value(a?.pitch,1,'°')}</dd><dt>Yaw</dt><dd>{value(a?.yaw,1,'°')}</dd></dl><small>Raw flow accuracy degrades with tilt.</small></section>
    <section className="telemetry-group"><h2>Horizontal velocity</h2><dl><dt>VX · North</dt><dd>{value(v?.vx,3,' m/s')}</dd><dt>VY · East</dt><dd>{value(v?.vy,3,' m/s')}</dd><dt>Speed</dt><dd>{value(v?.speed,3,' m/s')}</dd></dl></section>
  </aside>;
}
