import type {Telemetry} from '../types/telemetry';
import {value} from './TelemetryPanel';
export function FlowPanel({data,online}:{data:Telemetry|null;online:boolean}){
  const f=data?.flow,q=f?.quality;
  const label=q==null?'NO DATA':q<=50?'POOR':q<=120?'LOW':q<=200?'OK':'GOOD';
  return <section className="telemetry-group"><div className="section-heading"><h2>Optical flow</h2><span>{!online&&f?.age_ms!=null?'STALE':f?.status||'NO DATA'}</span></div>
    <dl><dt>opt_m_x</dt><dd>{value(f?.opt_m_x,5,' rad/s')}</dd><dt>opt_m_y</dt><dd>{value(f?.opt_m_y,5,' rad/s')}</dd>
    {f?.input_message==='OPTICAL_FLOW_RAD'&&<><dt>Integrated X</dt><dd>{value(f.integrated_x,4,' rad')}</dd><dt>Integrated Y</dt><dd>{value(f.integrated_y,4,' rad')}</dd></>}
    <dt>Quality</dt><dd>{q??'N/A'} / 255 · {label}</dd><dt>Ground distance</dt><dd>{value(f?.ground_distance,2,' m')}</dd><dt>Update rate</dt><dd>{value(f?.rate_hz,1,' Hz')}</dd><dt>Data age</dt><dd>{value(f?.age_ms,0,' ms')}</dd></dl>
    <small>opt_m values: {!online&&f?.opt_m_x!=null?'STALE':f?.opt_status||'NO DATA'} · ArduPilot angular rates</small>
    <small>Distance: {f?.distance_source||'NO DATA'}</small>
    <meter min="0" max="255" value={q||0} aria-label="Optical flow quality"/><small>Quality labels describe data only.</small></section>;
}
