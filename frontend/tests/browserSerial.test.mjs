import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compiledUrl} from './compile.mjs';
const {FrameSplitter,BrowserSerial,encodeBytes}=await import(compiledUrl(new URL('../src/services/browserSerial.ts',import.meta.url)));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function portFixture(){
  let controller;
  const writes=[],opens=[];
  let closed=0;
  return {writes,opens,get closed(){return closed;},push:bytes=>controller.enqueue(bytes),unplug:()=>controller.error(new Error('USB unplugged')),
    port:{readable:new ReadableStream({start(c){controller=c;}}),writable:new WritableStream({write(bytes){writes.push(bytes);}}),
      async open(options){opens.push(options);},async close(){closed++;}}};
}
const heartbeat=Uint8Array.from([254,2,0,1,1,0,10,20,0,0]);

test('MAVLink framing handles noise, split headers, v1, v2 and signed packets',()=>{
  const splitter=new FrameSplitter();
  const v2=Uint8Array.from([253,2,0,0,0,1,1,30,0,0,1,2,0,0]);
  const signed=Uint8Array.from([...v2.slice(0,2),1,...v2.slice(3),...Array(13).fill(0)]);
  assert.deepEqual(splitter.push(Uint8Array.from([1,2,3,...heartbeat.slice(0,4)])),[]);
  const complete=splitter.push(Uint8Array.from([...heartbeat.slice(4),...v2,...signed]));
  assert.deepEqual(complete,[heartbeat,v2,signed]);
});

test('USB only opens after request, queues frames, blocks vehicle commands and releases locks',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  const fixture=portFixture();let picks=0;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{serial:{requestPort(){picks++;return Promise.resolve(fixture.port);}}}});
  const serial=new BrowserSerial();
  try{
    assert.equal(picks,0);
    const opening=serial.open(115200);
    assert.equal(picks,1,'The picker must run before asynchronous work');
    await opening;
    fixture.push(heartbeat.slice(0,3));fixture.push(heartbeat.slice(3));await tick();
    assert.equal(serial.take()[0].data,encodeBytes(heartbeat));
    const command=new Uint8Array(44);command[0]=253;command[1]=32;command[5]=255;command[6]=190;command[7]=76;
    command[38]=255;command[39]=1;command[40]=1;command[41]=1;
    await serial.writeIntervals([encodeBytes(command)]);
    assert.equal(fixture.writes.length,1);
    command[38]=144; // 400 = arm/disarm, explicitly forbidden.
    await assert.rejects(serial.writeIntervals([encodeBytes(command)]),/Blocked an outbound/);
    assert.equal(fixture.writes.length,1);
    await serial.close();
    assert.equal(fixture.closed,1);
    assert.equal(fixture.port.readable.locked,false);
    assert.equal(fixture.port.writable.locked,false);
    assert.equal(serial.opened,false);
    assert.equal(picks,1,'Closing cannot reconnect');
  }finally{await serial.close();if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;}
});

test('USB unplug closes the port and requires explicit reconnect',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  const fixture=portFixture();let picks=0;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{serial:{requestPort(){picks++;return Promise.resolve(fixture.port);}}}});
  const serial=new BrowserSerial();
  try{
    await serial.open(57600);fixture.unplug();await tick();await serial.close();
    assert.match(serial.error,/USB unplugged/);
    assert.equal(serial.opened,false);
    assert.equal(fixture.closed,1);
    assert.equal(picks,1);
  }finally{if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;}
});

test('Canceling the device picker does not open a port',async()=>{
  const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{serial:{requestPort(){return Promise.reject(new Error('No port selected'));}}}});
  const serial=new BrowserSerial();
  try{await assert.rejects(serial.open(115200),/No port selected/);assert.equal(serial.opened,false);}
  finally{await serial.close();if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;}
});
