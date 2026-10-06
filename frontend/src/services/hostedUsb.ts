import {BrowserSerial} from './browserSerial';
import type {Settings,Telemetry} from '../types/telemetry';
interface UsbMemory {times?:Record<string,number>;[key:string]:unknown}
export class HostedUsb {
  private serial=new BrowserSerial();
  private memory:UsbMemory={};
  private reset=false;
  private watchdog?:ReturnType<typeof setInterval>;
  private closeOnLeave=()=>{void this.close();};
  private lastHeartbeat:number|undefined;
  constructor(readonly baud:number){}
  get error(){return this.serial.error;}
  get opened(){return this.serial.opened;}
  async open(){
    await this.serial.open(this.baud);
    if(!this.opened)return;
    window.addEventListener('pagehide',this.closeOnLeave);
    this.watchdog=setInterval(()=>{
      if(!this.opened){clearInterval(this.watchdog);return;}
      const now=this.serial.now();
      if(this.lastHeartbeat===undefined&&now>12)this.serial.fail('No vehicle HEARTBEAT in 12 seconds. Check baud and MAVLink configuration.');
      else if(this.lastHeartbeat!==undefined&&now-this.lastHeartbeat>5)this.serial.fail('MAVLink heartbeat lost. Connect explicitly to retry.');
    },500);
  }
  resetOrigin(){this.reset=true;}
  async step(settings:Settings,signal:AbortSignal):Promise<Telemetry>{
    const frames=this.serial.take(), reset=this.reset;
    this.reset=false;
    try{
      const response=await fetch('/api/usb/step',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({session:this.memory,frames,now:this.serial.now(),settings,reset_origin:reset,open:this.opened,error:this.error,baud:this.baud}),signal});
      if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:`USB processing failed (${response.status})`);}
      const data=await response.json();
      this.memory=data.session;
      this.lastHeartbeat=this.memory.times?.HEARTBEAT;
      if(this.opened){
        try{await this.serial.writeIntervals(data.outgoing);}catch(error){this.serial.fail(error instanceof Error?error.message:String(error));throw error;}
        if(['ERROR','CONNECTION_LOST'].includes(data.telemetry.state))this.serial.fail(data.telemetry.error||'MAVLink connection lost.');
      }
      return data.telemetry;
    }catch(error){this.serial.requeue(frames);if(reset)this.reset=true;throw error;}
  }
  async close(){clearInterval(this.watchdog);window.removeEventListener('pagehide',this.closeOnLeave);await this.serial.close();}
}
