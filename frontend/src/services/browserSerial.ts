// Browser byte transport only. CRC decoding and all sensor math run in Python.
export interface BrowserPort {
  readable: ReadableStream<Uint8Array>|null;
  writable: WritableStream<Uint8Array>|null;
  open(options:{baudRate:number;bufferSize:number}):Promise<void>;
  close():Promise<void>;
}
interface SerialApi {requestPort():Promise<BrowserPort>}
const serialApi=()=>typeof navigator==='undefined'?undefined:(navigator as Navigator&{serial?:SerialApi}).serial;
export const supportsBrowserUsb=()=>!!serialApi()&&globalThis.isSecureContext!==false;
export const encodeBytes=(bytes:Uint8Array)=>btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
const decodeBytes=(data:string)=>Uint8Array.from(atob(data),c=>c.charCodeAt(0));
const watched=new Set([0,1,30,32,77,100,106,132]);

export class FrameSplitter {
  private pending:number[]=[];
  push(bytes:Uint8Array):Uint8Array[]{
    for(const byte of bytes)this.pending.push(byte);
    const frames:Uint8Array[]=[];
    let cursor=0;
    while(cursor<this.pending.length){
      const magic=this.pending[cursor];
      if(magic!==254&&magic!==253){cursor++;continue;}
      const header=magic===253?10:6;
      if(this.pending.length-cursor<header)break;
      const size=header+this.pending[cursor+1]+2+(magic===253&&(this.pending[cursor+2]&1)?13:0);
      if(this.pending.length-cursor<size)break;
      const id=magic===253?this.pending[cursor+7]+256*this.pending[cursor+8]+65536*this.pending[cursor+9]:this.pending[cursor+5];
      if(watched.has(id))frames.push(Uint8Array.from(this.pending.slice(cursor,cursor+size)));
      cursor+=size;
    }
    this.pending=this.pending.slice(cursor);
    return frames;
  }
}

export interface ReceivedFrame {data:string;time:number}
export class BrowserSerial {
  private started=performance.now();
  opened=false;
  error:string|null=null;
  private port?:BrowserPort;
  private reader?:ReadableStreamDefaultReader<Uint8Array>;
  private writer?:WritableStreamDefaultWriter<Uint8Array>;
  private reading?:Promise<void>;
  private closing?:Promise<void>;
  private disposed=false;
  private frames:ReceivedFrame[]=[];
  private splitter=new FrameSplitter();
  now(){return (performance.now()-this.started)/1000;}
  async open(baud:number){
    if(!supportsBrowserUsb())throw new Error('USB needs desktop Chrome or Edge over HTTPS.');
    // Must run directly from the click, before any fetch or other awaited operation.
    const selected=serialApi()!.requestPort();
    this.port=await selected;
    if(this.disposed)return;
    try{
      await this.port.open({baudRate:baud,bufferSize:65536});
      this.started=performance.now();
      if(this.disposed){await this.port.close();return;}
      if(!this.port.readable||!this.port.writable)throw new Error('The selected device has no serial streams.');
      this.opened=true;
      this.writer=this.port.writable.getWriter();
      this.reader=this.port.readable.getReader();
      this.reading=this.read();
    }catch(error){await this.close();throw new Error(`Could not open USB: ${error instanceof Error?error.message:String(error)}. Close Mission Planner or other serial apps and retry.`);}
  }
  private async read(){
    try{
      while(this.opened){
        const {value,done}=await this.reader!.read();
        if(done)break;
        if(value)for(const frame of this.splitter.push(value))this.frames.push({data:encodeBytes(frame),time:this.now()});
        if(this.frames.length>512)throw new Error('Telemetry processing fell behind. Reconnect to restart the origin.');
      }
      if(!this.disposed)this.error='USB device disconnected. Select it again to reconnect.';
    }catch(error){if(!this.disposed)this.error=error instanceof Error?error.message:String(error);}
    finally{
      this.reader?.releaseLock();this.reader=undefined;
      if(!this.disposed)void this.close();
    }
  }
  take(){return this.frames.splice(0,128);}
  requeue(frames:ReceivedFrame[]){this.frames.unshift(...frames);if(this.frames.length>512)this.fail('Backend unavailable; telemetry queue filled. Reconnect to retry.');}
  async writeIntervals(outgoing:string[]){
    for(const encoded of outgoing){
      const bytes=decodeBytes(encoded), v2=bytes[0]===253, header=v2?10:6;
      const id=v2?bytes[7]+256*bytes[8]+65536*bytes[9]:bytes[5];
      const command=bytes[header+28]+256*bytes[header+29];
      if(![253,254].includes(bytes[0])||id!==76||command!==511||bytes[1]<32||bytes.length!==header+bytes[1]+2)
        throw new Error('Blocked an outbound packet that is not a telemetry interval request.');
      if(!this.opened)return;
      await this.writer!.write(bytes);
    }
  }
  fail(message:string){this.error=message;void this.close();}
  close():Promise<void>{
    if(this.closing)return this.closing;
    this.disposed=true;this.opened=false;
    this.closing=(async()=>{
      await this.reader?.cancel().catch(()=>{});
      await this.reading;
      if(this.writer){await this.writer.abort().catch(()=>{});this.writer.releaseLock();this.writer=undefined;}
      await this.port?.close().catch(()=>{});
    })();
    return this.closing;
  }
}
