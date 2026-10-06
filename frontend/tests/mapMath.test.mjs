import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
// Compile the actual TypeScript module, not a duplicate of the implementation.
const source=readFileSync(new URL('../src/mapMath.ts',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}});
const {worldToScreen,validPoint,autoScale}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
test('maps East right and North up',()=>assert.deepEqual(worldToScreen(2,3,100,100,10),[120,70]));
test('rejects invalid trail points',()=>{assert.equal(validPoint({x:NaN,y:0,timestamp:1}),false);assert.equal(validPoint({x:0,y:Infinity,timestamp:1}),false);});
test('fits current position, history and test boundary',()=>{assert.ok(autoScale([{x:20,y:0,timestamp:1}],null,5,3,false)>20);assert.ok(autoScale([],null,10,3,true)>5);});
