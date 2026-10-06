import {useEffect,useRef,useState} from 'react';
import {ConnectionPanel} from './components/ConnectionPanel';
import {StatusBar} from './components/StatusBar';
import {DroneMap} from './components/DroneMap';
import {TelemetryPanel} from './components/TelemetryPanel';
import {SettingsPanel} from './components/SettingsPanel';
import {SimulationControls} from './components/SimulationControls';
import {Diagnostics} from './components/Diagnostics';
import {useTelemetry} from './hooks/useTelemetry';
import {api} from './services/websocket';
import {defaultSettings} from './types/telemetry';
import type {Settings,MapPreferences} from './types/telemetry';
function saved<T>(key:string,fallback:T):T{try{return {...fallback,...JSON.parse(localStorage.getItem(key)||'{}')};}catch{return fallback;}}
export default function App(){
  const {latest,snapshot,online,received}=useTelemetry();
  const [settings,setSettings]=useState<Settings>(()=>saved('of-settings',defaultSettings));
  const [prefs,setPrefs]=useState<MapPreferences>(()=>saved('of-map',{scale:'Auto',showTrail:true,boundary:false,width:5,height:3}));
  const [paused,setPaused]=useState(false),[clearToken,setClearToken]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const initialized=useRef(false),settingsQueue=useRef(Promise.resolve());
  const desiredSettings=useRef<Settings|null>(null);
  const run=async(path:string,body:unknown={})=>{setBusy(true);setError('');try{await api(path,body);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
  // First browser client restores preferences once. Existing live backend state
  // wins on refresh/additional tabs, so opening a tab cannot reset live axes.
  useEffect(()=>{
    if(!snapshot)return;
    if(!initialized.current){
      initialized.current=true;
      if(snapshot.state==='DISCONNECTED'){
        desiredSettings.current=settings;
        void api('settings',settings).catch(e=>{desiredSettings.current=null;setError(String(e));});
        return;
      }
    }
    if(desiredSettings.current&&JSON.stringify(snapshot.settings)!==JSON.stringify(desiredSettings.current))return;
    desiredSettings.current=null;
    if(JSON.stringify(settings)!==JSON.stringify(snapshot.settings))setSettings(snapshot.settings);
  },[snapshot,settings]);
  useEffect(()=>{localStorage.setItem('of-map',JSON.stringify(prefs));},[prefs]);
  const changeSettings=(next:Settings)=>{
    setSettings(next);localStorage.setItem('of-settings',JSON.stringify(next));
    desiredSettings.current=next;
    settingsQueue.current=settingsQueue.current.then(async()=>{try{await api('settings',next);setError('');}catch(e){desiredSettings.current=null;setError(String(e));}});
  };
  const transportLive=online&&Date.now()-received.current<1500;
  return <main><header><div className="brand"><span className="brand-icon">⌖</span><div><h1>Optical Flow Visualizer</h1><p>TELEMETRY VISUALIZER · READ ONLY</p></div></div><StatusBar data={snapshot} online={transportLive}/></header>
    <ConnectionPanel data={snapshot} run={run} busy={busy}/>
    {(error||snapshot?.error)&&<div className="error-banner" role="alert">{error||snapshot?.error}</div>}
    {!transportLive&&<div className="notice">Waiting for backend telemetry. Data shown below may be stale.</div>}
    {snapshot?.simulation&&<div className="sim-banner">SIMULATION · Generated telemetry · No flight controller connected</div>}
    <div className="workspace"><section className="map-panel"><div className="map-toolbar"><div><h2>Horizontal movement</h2><span className="muted">North up · East right · {settings.flow_input==='mission_planner'?'opt_m_x / opt_m_y':'OPTICAL_FLOW_RAD'}</span></div><label>Position source<select value={settings.source} onChange={e=>changeSettings({...settings,source:e.target.value as Settings['source']})}><option value="optical_flow">Optical Flow Integrated</option><option value="local_position">LOCAL_POSITION_NED</option></select></label><label>Scale<select value={prefs.scale} onChange={e=>setPrefs({...prefs,scale:e.target.value})}><option>Auto</option>{[0.5,1,2,5,10,20,50].map(s=><option value={s} key={s}>±{s} m</option>)}</select></label></div>
    <div className="canvas-wrap"><DroneMap latest={latest} received={received} preferences={prefs} paused={paused} clearToken={clearToken} online={transportLive}/>{!snapshot&&<div className="empty-message">Connect a COM port or start simulation to see movement.</div>}</div>
    <div className="map-controls"><button disabled={busy} onClick={()=>{setPaused(false);void run('reset-origin',{});}} title="Sets the current location to 0,0 without changing anything on the flight controller">Reset origin</button><button onClick={()=>setClearToken(t=>t+1)} title="Clears the displayed path but keeps the current origin">Clear trail</button><button onClick={()=>setPaused(p=>!p)} aria-pressed={paused}>{paused?'Resume visualization':'Pause visualization'}</button><label className="check"><input type="checkbox" checked={prefs.showTrail} onChange={e=>setPrefs({...prefs,showTrail:e.target.checked})}/>Show trail</label><span className="muted">X = East · Y = North</span></div>
    {snapshot?.simulation&&<SimulationControls/>}</section><TelemetryPanel data={snapshot} online={transportLive}/></div>
    <SettingsPanel settings={settings} onSettings={changeSettings} prefs={prefs} onPrefs={setPrefs}/><Diagnostics data={snapshot}/>
    <footer>{snapshot?.mode==='hosted_demo'?'Browser USB / simulation · Up to 5 Hz display updates':'Local display only · 25 Hz telemetry'} · Flow integration is a debugging estimate, not navigation truth · Canvas animation</footer>
  </main>;
}
