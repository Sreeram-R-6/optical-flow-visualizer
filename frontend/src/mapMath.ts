import type {TrailPoint} from './types/telemetry';
// East increases right. North increases up; browser Y increases down.
export function worldToScreen(east:number,north:number,cx:number,cy:number,ppm:number):[number,number]{return [cx+east*ppm,cy-north*ppm];}
export function validPoint(p:TrailPoint){return Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.timestamp);}
export function autoScale(points:TrailPoint[],current:TrailPoint|null,width:number,height:number,boundary:boolean){
  let extent=0.4;
  for(const p of points)extent=Math.max(extent,Math.abs(p.x),Math.abs(p.y));
  if(current)extent=Math.max(extent,Math.abs(current.x),Math.abs(current.y));
  if(boundary)extent=Math.max(extent,width/2,height/2);
  return Math.ceil(extent*1.25*10)/10;
}
