import {useEffect,useRef,useState} from 'react';
import {openTelemetry} from '../services/websocket';
import type {Telemetry} from '../types/telemetry';
export function useTelemetry(){
  const latest=useRef<Telemetry|null>(null);
  const received=useRef(0);
  const [snapshot,setSnapshot]=useState<Telemetry|null>(null);
  const [online,setOnline]=useState(false);
  const [fresh,setFresh]=useState(false);
  useEffect(()=>{
    const close=openTelemetry(data=>{latest.current=data;received.current=Date.now();},setOnline);
    // Canvas reads the ref at animation rate; React widgets update only at 5 Hz.
    const timer=setInterval(()=>{setSnapshot(latest.current);setFresh(Date.now()-received.current<1500);},200);
    return ()=>{close();clearInterval(timer);};
  },[]);
  return {latest,snapshot,online:online&&fresh,received};
}
