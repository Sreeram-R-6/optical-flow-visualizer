import {readFileSync} from 'node:fs';
import ts from 'typescript';
const cache=new Map();
export function compiledUrl(file){
  const key=file.href;
  if(cache.has(key))return cache.get(key);
  let output=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  output=output.replace(/from (['"])(\.[^'"]+)\1/g,(_,quote,path)=>`from ${JSON.stringify(compiledUrl(new URL(`${path}.ts`,file)))}`);
  const url=`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
  cache.set(key,url);
  return url;
}
