"use client";
import {useEffect,useRef,useState} from "react";
import Map from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import Polygon from "ol/geom/Polygon";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import OSM from "ol/source/OSM";
import VectorSource from "ol/source/Vector";
import {fromLonLat} from "ol/proj";
import {Style,Stroke,Fill,Circle as CircleStyle,Text,RegularShape} from "ol/style";

type Mark={name:string;longitude:number|null;latitude:number|null;point_role:string;sigef_vertex_code?:string};
export function BoundaryOrderMap({points,ordered}:{points:Mark[];ordered:Mark[]}){
  const target=useRef<HTMLDivElement>(null);
  const map=useRef<Map|null>(null);
  const source=useRef(new VectorSource());
  const lastFit=useRef("");
  const [base,setBase]=useState(true);
  const [showControl,setShowControl]=useState(false);
  const tiles=useRef<TileLayer<OSM>|null>(null);
  const valid=(p:Mark)=>typeof p.longitude==="number"&&typeof p.latitude==="number"&&Number.isFinite(p.longitude)&&Number.isFinite(p.latitude);
  const selected=ordered.filter(valid);
  const xy=selected.map(p=>fromLonLat([p.longitude!,p.latitude!]));
  // Orientation and proper segment crossings in the projected preview; not SIGEF validation.
  const cross=(a:number[],b:number[],c:number[])=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const intersects=(a:number[],b:number[],c:number[],d:number[])=>cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0;
  let crossing=false;
  for(let i=0;i<xy.length;i++)for(let j=i+2;j<xy.length;j++){
    if(i===0&&j===xy.length-1)continue;
    if(intersects(xy[i],xy[(i+1)%xy.length],xy[j],xy[(j+1)%xy.length]))crossing=true;
  }
  const area=xy.length>2?xy.reduce((sum,p,i)=>sum+cross(xy[0],p,xy[(i+1)%xy.length]),0):0;
  const fit=()=>{const extent=source.current.getExtent();if(map.current&&extent.every(Number.isFinite))map.current.getView().fit(extent,{padding:[55,55,55,55],maxZoom:18,duration:200});};
  useEffect(()=>{
    if(!target.current)return;
    const layer=new TileLayer({source:new OSM()});tiles.current=layer;
    const vector=new VectorLayer({source:source.current,style:f=>{
      const kind=f.get("kind");
      if(kind==="polygon")return new Style({fill:new Fill({color:"rgba(14,116,94,.16)"})});
      if(kind==="line")return new Style({stroke:new Stroke({color:f.get("bad")?"#b42318":"#0b806c",width:3,lineDash:f.get("closing")?[7,5]:undefined})});
      if(kind==="arrow")return new Style({image:new RegularShape({points:3,radius:8,rotation:f.get("rotation"),rotateWithView:true,fill:new Fill({color:f.get("bad")?"#b42318":"#0b806c"}),stroke:new Stroke({color:"#fff",width:1})})});
      const chosen=f.get("chosen");
      const control=f.get("control");
      return new Style({image:new CircleStyle({radius:chosen?12:6,fill:new Fill({color:chosen?"#095e51":control?"#64748b":"#fff"}),stroke:new Stroke({color:chosen?"#fff":"#627d75",width:2})}),text:new Text({text:String(f.get("label")),offsetY:chosen?-22:-14,font:"bold 12px sans-serif",fill:new Fill({color:"#17463d"}),stroke:new Stroke({color:"#fff",width:4})})});
    }});
    const m=new Map({target:target.current,layers:[layer,vector],view:new View({center:fromLonLat([-51,0]),zoom:8,maxZoom:20})});
    map.current=m;
    return()=>{m.setTarget(undefined);map.current=null;lastFit.current="";};
  },[]);
  useEffect(()=>{tiles.current?.setVisible(base);},[base]);
  useEffect(()=>{
    const features:Feature[]=[];
    const bad=crossing;
    if(xy.length>=3&&!bad)features.push(new Feature({geometry:new Polygon([[...xy,xy[0]]]),kind:"polygon"}));
    for(let i=0;i<(xy.length>=3?xy.length:Math.max(0,xy.length-1));i++){
      const a=xy[i],b=xy[(i+1)%xy.length];
      features.push(new Feature({geometry:new LineString([a,b]),kind:"line",closing:i===xy.length-1,bad}));
      features.push(new Feature({geometry:new Point([(a[0]+b[0])/2,(a[1]+b[1])/2]),kind:"arrow",rotation:Math.atan2(b[0]-a[0],b[1]-a[1]),bad}));
    }
    for(const p of points.filter(p=>valid(p)&&(showControl||p.point_role!=="CONTROL"))){
      const i=ordered.findIndex(v=>v.name===p.name);
      const label=(i>=0?(i+1)+" · ":"")+(ordered[i]?.sigef_vertex_code||p.name);
      features.push(new Feature({geometry:new Point(fromLonLat([p.longitude!,p.latitude!])),kind:"point",chosen:i>=0,control:p.point_role==="CONTROL",label}));
    }
    source.current.clear();source.current.addFeatures(features);
    const key=JSON.stringify(points.map(p=>[p.name,p.longitude,p.latitude]));
    if(key!==lastFit.current){lastFit.current=key;fit();}
  },[points,ordered,showControl]);
  return <section className="pecas-card geo115-boundary-map">
    <h3>Composição do perímetro</h3><p className="pecas-note">Acompanhe a sequência dos marcos em tempo real. As setas indicam o sentido do caminhamento.</p>
    <div style={{position:"relative"}}><div ref={target} style={{height:440,width:"100%",background:"#edf2ef",borderRadius:10,overflow:"hidden"}}/><span style={{position:"absolute",right:12,top:12,background:"#fff",padding:"6px 10px",borderRadius:6,color:"#17463d",fontWeight:700}}>↑ N</span></div>
    <div style={{display:"flex",flexWrap:"wrap",gap:8,marginTop:12}}><button type="button" className="pecas-secondary" onClick={fit}>Enquadrar marcos</button><label className="pecas-check"><input type="checkbox" checked={base} onChange={e=>setBase(e.target.checked)}/>Mapa de fundo OSM</label><label className="pecas-check"><input type="checkbox" checked={showControl} onChange={e=>setShowControl(e.target.checked)}/>Mostrar bases de controle (não entram no perímetro)</label></div>
    <p className="pecas-note">Verde: selecionados · Branco: não selecionados · Cinza: bases de controle (ocultas por padrão) · Tracejado: fechamento provisório.</p>
    <p role="status" className={crossing?"pecas-warning":"geo96-next-step"}>{crossing?"Segmentos cruzados. Reordene os vértices antes de avançar.":selected.length<3?"Selecione pelo menos três marcos para visualizar o fechamento.":area===0?"Perímetro degenerado: confira os marcos.":(area<0?"Sentido horário":"Sentido anti-horário")+" · "+selected.length+" marcos. Fechamento ilustrativo antes da construção dos V."}</p>
  </section>;
}
