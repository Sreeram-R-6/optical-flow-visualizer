import {useEffect,useRef} from 'react';
import type {RefObject} from 'react';
import type {MapPreferences,Telemetry,TrailPoint} from '../types/telemetry';
import {autoScale,validPoint,worldToScreen} from '../mapMath';
interface Props {latest:RefObject<Telemetry|null>;received:RefObject<number>;preferences:MapPreferences;paused:boolean;clearToken:number;online:boolean}
export function DroneMap(props:Props){
  const canvas=useRef<HTMLCanvasElement>(null), propsRef=useRef(props);propsRef.current=props;
  useEffect(()=>{
    const c=canvas.current!,ctx=c.getContext('2d')!;
    let w=0,h=0,frame=0,points:TrailPoint[]=[],revision=-1,lastStamp=0,lastClear=-1,current:TrailPoint|null=null,yaw=0;
    const observer=new ResizeObserver(()=>{const r=c.getBoundingClientRect();w=r.width;h=r.height;const dpr=Math.min(devicePixelRatio,2);c.width=w*dpr;c.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);});observer.observe(c);
    const render=()=>{
      const {latest,received,preferences:p,paused,clearToken,online}=propsRef.current,data=latest.current;
      const transportFresh=online&&Date.now()-received.current<1500;
      if(clearToken!==lastClear){points=[];lastClear=clearToken;}
      if(data&&revision!==data.revision){points=[];current=null;revision=data.revision;lastStamp=0;}
      if(!paused&&data?.position.available&&transportFresh){
        const pos=data.position;
        const point={x:pos.east!,y:pos.north!,timestamp:data.timestamp,quality:data.flow.quality??undefined};
        if(validPoint(point)){
          current=point;
          if(data.attitude.yaw!==null)yaw=data.attitude.yaw;
          const tail=points.at(-1);
          if(point.timestamp!==lastStamp&&(!tail||Math.hypot(tail.x-point.x,tail.y-point.y)>0.002||point.timestamp-tail.timestamp>0.5)){
            points.push(point);if(points.length>10000)points=points.filter((_,i)=>i===0||i%2===1);lastStamp=point.timestamp;
          }
        }
      }
      const scale=p.scale==='Auto'?autoScale(points,current,p.width,p.height,p.boundary):+p.scale;
      const cx=w/2,cy=h/2,ppm=Math.max(1,Math.min(w-130,h-110)/(scale*2));
      const toScreen=(e:number,n:number)=>worldToScreen(e,n,cx,cy,ppm);
      ctx.clearRect(0,0,w,h);ctx.fillStyle='#111b1e';ctx.fillRect(0,0,w,h);
      const step=10**Math.floor(Math.log10(scale/3));const gridStep=scale/step>12?step*5:scale/step>6?step*2:step;
      ctx.font='11px Consolas, monospace';ctx.textAlign='left';
      for(let i=-Math.ceil(scale/gridStep);i<=Math.ceil(scale/gridStep);i++){
        const meters=i*gridStep,[x,y]=toScreen(meters,meters);ctx.strokeStyle=i===0?'#415459':'#26363a';ctx.lineWidth=i===0?1.5:1;
        ctx.beginPath();ctx.moveTo(x,35);ctx.lineTo(x,h-35);ctx.moveTo(40,y);ctx.lineTo(w-40,y);ctx.stroke();
        if(i!==0){ctx.fillStyle='#8da5aa';ctx.fillText(`${meters.toFixed(gridStep<1?1:0)} m`,x+4,cy+17);ctx.fillText(`${meters.toFixed(gridStep<1?1:0)} m`,cx+5,y-5);}
      }
      ctx.strokeStyle='#96adb1';ctx.beginPath();ctx.arc(cx,cy,4,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#a5b9bd';ctx.fillText('ORIGIN',cx+9,cy-10);
      if(p.boundary){const [x,y]=toScreen(-p.width/2,p.height/2);const outside=current&&(Math.abs(current.x)>p.width/2||Math.abs(current.y)>p.height/2);ctx.strokeStyle=outside?'#f1b776':'#789397';ctx.setLineDash([6,5]);ctx.strokeRect(x,y,p.width*ppm,p.height*ppm);ctx.setLineDash([]);if(outside){ctx.fillStyle='#f1b776';ctx.fillText('OUTSIDE TEST AREA',18,54);}}
      if(p.showTrail&&points.length){ctx.beginPath();points.forEach((point,i)=>{const [x,y]=toScreen(point.x,point.y);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.strokeStyle='#63c7b0';ctx.lineWidth=2;ctx.lineJoin='round';ctx.stroke();const [x,y]=toScreen(points[0].x,points[0].y);ctx.fillStyle='#b5eadc';ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fill();}
      if(current){const [x,y]=toScreen(current.x,current.y);ctx.save();ctx.translate(x,y);ctx.rotate(yaw*Math.PI/180);ctx.beginPath();ctx.moveTo(0,-14);ctx.lineTo(10,10);ctx.lineTo(0,5);ctx.lineTo(-10,10);ctx.closePath();ctx.fillStyle=transportFresh&&data?.position.available?'#7fe0c4':'#8a989c';ctx.fill();ctx.strokeStyle='#0c1416';ctx.lineWidth=2;ctx.stroke();ctx.restore();ctx.fillStyle='#d7e9e5';const labelX=Math.min(Math.max(x+17,8),w-150),labelY=Math.min(Math.max(y,60),h-50);ctx.fillText(`E ${current.x.toFixed(3)} m`,labelX,labelY);ctx.fillText(`N ${current.y.toFixed(3)} m`,labelX,labelY+16);}
      ctx.fillStyle='#bbcecf';ctx.font='12px Segoe UI, sans-serif';ctx.textAlign='center';ctx.fillText('NORTH ↑',cx,23);ctx.fillText('SOUTH',cx,h-16);ctx.fillText('WEST',28,cy-18);ctx.fillText('EAST',w-28,cy-18);ctx.textAlign='left';ctx.font='11px Consolas, monospace';ctx.fillText(`VIEW ±${scale.toFixed(1)} m · ${points.length} points`,18,h-17);
      if(!data?.position.available||!transportFresh||paused){ctx.fillStyle='#d1b78b';ctx.textAlign='right';ctx.fillText(paused?'VISUALIZATION PAUSED':!transportFresh?'TELEMETRY OFFLINE':'POSITION UNAVAILABLE',w-18,h-17);ctx.textAlign='left';}
      frame=requestAnimationFrame(render);
    };frame=requestAnimationFrame(render);
    return ()=>{cancelAnimationFrame(frame);observer.disconnect();};
  },[]);
  return <canvas ref={canvas} aria-label="Drone movement map: North up, East right" role="img"/>;
}
