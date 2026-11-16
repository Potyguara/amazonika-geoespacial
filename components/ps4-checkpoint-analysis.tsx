"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type GNSSMark = { name: string; longitude: number | null; latitude: number | null };
type Point = { longitude: number; latitude: number };
type Check = { name: string; gnss_longitude: number; gnss_latitude: number; image_longitude: number; image_latitude: number; used_for_orthorectification: false };
type Result = {status:string;count:number;rms_e_m:number|null;rms_n_m:number|null;rms_horizontal_m:number|null;warnings:string[];checkpoints:{name:string;delta_e_m:number;delta_n_m:number;radial_error_m:number}[]};

export function Ps4CheckpointAnalysis({
  pieceId, marks, rasterSha256, lastImageClick, capturing, onCapture,
}: {
  pieceId: string | null | undefined;
  marks: GNSSMark[];
  rasterSha256: string | null;
  lastImageClick: Point | null;
  capturing: boolean;
  onCapture: (active:boolean)=>void;
}) {
  const [markName,setMarkName] = useState("");
  const [imagePoint,setImagePoint] = useState<Point | null>(null);
  const [checks,setChecks] = useState<Check[]>([]);
  const [result,setResult] = useState<Result | null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [confirmed,setConfirmed] = useState(false);
  useEffect(()=>{ if(lastImageClick) setImagePoint(lastImageClick); },[lastImageClick]);
  useEffect(()=>{setResult(null);setChecks([]);setImagePoint(null);setConfirmed(false);},[rasterSha256,pieceId]);
  const selected=marks.find(m=>m.name===markName);
  const add = () => {
    if(!selected || selected.longitude==null || selected.latitude==null || !imagePoint || !confirmed)return;
    if(checks.some(v=>v.name===selected.name)) {setError("Este marco já participa da checagem.");return;}
    setChecks(old=>[...old,{name:selected.name,gnss_longitude:selected.longitude!,gnss_latitude:selected.latitude!,image_longitude:imagePoint.longitude,image_latitude:imagePoint.latitude,used_for_orthorectification:false}]);
    setImagePoint(null);setConfirmed(false);setResult(null);setError("");
  };
  const analyze=async()=>{
    if(!pieceId || !rasterSha256 || !checks.length)return;
    setBusy(true);setError("");
    try{
      const r=await fetch(`${getApiUrl()}/technical-pieces/${pieceId}/ps4/checkpoint-analysis`,{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({checkpoints:checks}),cache:"no-store",
      });
      const payload=await r.json().catch(()=>null);
      if(!r.ok)throw new Error(typeof payload?.detail==="string"?payload.detail:"Não foi possível calcular os resíduos.");
      setResult(payload.result as Result);
    }catch(e){setError(e instanceof Error?e.message:"Falha na avaliação.");}
    finally{setBusy(false);}
  };
  return <div className="pecas-card ps4-checkpoint-card">
    <h4>Validação posicional própria · GNSS × imagem</h4>
    <p>Selecione um marco M fotoidentificável e clique no mesmo alvo sobre o GeoTIFF. A API calcula os resíduos UTM e o EMQ dos pontos independentes. Não use o marco se ele já participou da ortorretificação.</p>
    <label className="pecas-field"><span>Marco M de referência GNSS</span>
      <select value={markName} onChange={e=>{setMarkName(e.target.value);setImagePoint(null);setConfirmed(false);}}>
        <option value="">Selecione o marco identificável</option>
        {marks.filter(m=>m.longitude!==null && m.latitude!==null).map(m=><option key={m.name} value={m.name}>{m.name}</option>)}
      </select>
    </label>
    <div className="ps4-checkpoint-actions">
      <button type="button" className={capturing?"pecas-primary":"pecas-secondary"}
        disabled={!selected || !rasterSha256}
        onClick={()=>onCapture(!capturing)}>{capturing?"Clique no alvo correspondente no mapa →":"Marcar feição correspondente no mapa"}</button>
      {imagePoint && <small>Imagem: {imagePoint.latitude.toFixed(7)}°, {imagePoint.longitude.toFixed(7)}°</small>}
    </div>
    <label className="pecas-check"><input type="checkbox" checked={confirmed}
      onChange={e=>setConfirmed(e.target.checked)}/>
      Confirmo que o ponto é inequivocamente fotoidentificável e NÃO foi utilizado para ajustar esta ortoimagem.
    </label>
    <button type="button" className="pecas-secondary"
      disabled={!selected || !imagePoint || !confirmed} onClick={add}>
      Adicionar checagem independente</button>
    {!!checks.length && <div className="ps4-checkpoint-rows">
      <strong>{checks.length} referência(s) associada(s)</strong>
      {checks.map(c=><div key={c.name}><span>{c.name}</span>
        <button type="button" className="pecas-secondary" onClick={()=>{setChecks(old=>old.filter(r=>r.name!==c.name));setResult(null);}}>Remover</button></div>)}
    </div>}
    <button type="button" className="pecas-primary"
      disabled={!checks.length || busy} onClick={()=>void analyze()}>
      {busy?"Calculando resíduos...":"Calcular EMQ dos pontos de checagem"}</button>
    {error && <p className="ps4-alert-red" role="alert">{error}</p>}
    {result && <div role="status" className="ps4-checkpoint-result">
      <strong>EMQ amostral horizontal: {result.rms_horizontal_m?.toLocaleString("pt-BR",{maximumFractionDigits:4})??"—"} m</strong>
      <p>EMQ E: {result.rms_e_m?.toLocaleString("pt-BR")??"—"} m · EMQ N: {result.rms_n_m?.toLocaleString("pt-BR")??"—"} m · {result.count} ponto(s).</p>
      <p className="ps4-alert-red">{result.status==="INSUFFICIENT_CHECKPOINTS"
        ?"Amostra insuficiente para demonstrar acurácia da imagem. Não libera PS4."
        :"Amostra sujeita a avaliação da distribuição, independência e revisão RT. Não libera automaticamente PS4."}</p>
      <table><thead><tr><th>Marco</th><th>ΔE (m)</th><th>ΔN (m)</th><th>Erro radial (m)</th></tr></thead>
        <tbody>{result.checkpoints.map(p=><tr key={p.name}><td>{p.name}</td><td>{p.delta_e_m.toLocaleString("pt-BR")}</td><td>{p.delta_n_m.toLocaleString("pt-BR")}</td><td>{p.radial_error_m.toLocaleString("pt-BR")}</td></tr>)}</tbody></table>
    </div>}
  </div>;
}
