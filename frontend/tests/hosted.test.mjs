import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compiledUrl} from './compile.mjs';
const transport=compiledUrl(new URL('../src/services/websocket.ts',import.meta.url));

test('hosted transport accepts updates during manual input and stops polling on cleanup',async()=>{
  const originalFetch=globalThis.fetch;
  globalThis.document={hidden:false};
  let finish, request;
  globalThis.fetch=async(path,options)=>{
    if(path==='/api/health')return {ok:true,json:async()=>({mode:'hosted_demo'})};
    request=JSON.parse(options.body);
    return new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>({session:request.session,telemetry:{position:{},settings:request.session.settings}})});});
  };
  const {api,openTelemetry}=await import(transport);
  let close;
  try{
    await api('simulation/start',{});
    const packet=new Promise(resolve=>{close=openTelemetry(resolve,()=>{});});
    // Wait for the request to enter fetch, then send controls while it is pending.
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(request.session.active,true);
    await api('simulation/input',{mode:'manual',north:1,east:0});
    finish();
    const data=await Promise.race([packet,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Telemetry discarded during input')),1000))]);
    assert.ok(data.position);
    assert.deepEqual(await api('ports'),[]);
    await assert.rejects(api('connect',{port:'COM3'}),/local start.bat/);
  }finally{close?.();globalThis.fetch=originalFetch;delete globalThis.document;}
});
