"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type GNSSMark = { name: string; longitude: number | null; latitude: number | null };
type Point = { longitude: number; latitude: number };
type Check = { name: string; gnss_longitude: number; gnss_latitude: number; image_longitude: number; image_latitude: number; used_for_orthorectification: false };
type Result = {status:string;count:number;rms_e_m:number|null;rms_n_m:number|null;rms_horizontal_m:number|null;screening_reference_count?:number;screening_missing_count?:number;max_radial_error_m?:number|null;warnings:string[];checkpoints:{name:string;delta_e_m:number;delta_n_m:number;radial_error_m:number}[]};

export function Ps4CheckpointAnalysis({
  pieceId, marks, rasterSha256, sceneId, lastImageClick, capturing, onCapture,
}: {
  pieceId: string | null | undefined;
  marks: GNSSMark[];
  rasterSha256: string | null;
  sceneId: string;
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
  const [removalReason,setRemovalReason] = useState<Record<string,string>>({});
  const [persistedNames,setPersistedNames] = useState<string[]>([]);
  const [pendingExclusions,setPendingExclusions] = useState<{name:string;reason:string}[]>([]);
  const [exclusionLog,setExclusionLog] = useState<{name:string;reason:string;excluded_at:string}[]>([]);
  useEffect(()=>{ if(lastImageClick) setImagePoint(lastImageClick); },[lastImageClick]);
  useEffect(()=>{
    setResult(null);setChecks([]);setImagePoint(null);setConfirmed(false);
    setPersistedNames([]);setPendingExclusions([]);setExclusionLog([]);
    if(!pieceId || !rasterSha256)return;
    const controller=new AbortController();
    fetch(`${getApiUrl()}/technical-pieces/${pieceId}/ps4`,{
      credentials:"include",cache:"no-store",signal:controller.signal,
    }).then(r=>r.ok?r.json():null).then(json=>{
      if(controller.signal.aborted)return;
      const stored=json?.checkpoint_analysis;
      if(stored?.raster_sha256!==rasterSha256)return;
      if(Array.isArray(stored.checkpoints)){
        const accepted=stored.checkpoints.filter((c:Check)=>c.used_for_orthorectification===false);
        setChecks(accepted);
        setPersistedNames(accepted.map((c:Check)=>c.name));
      }
      if(stored.result)setResult(stored.result as Result);
      if(Array.isArray(stored.exclusion_log))setExclusionLog(stored.exclusion_log);
    }).catch(()=>{});
    return ()=>controller.abort();
  },[rasterSha256,pieceId,sceneId]);
  const selected=marks.find(m=>m.name===markName);
  const add = () => {
    if(!selected || selected.longitude==null || selected.latitude==null || !imagePoint || !confirmed)return;
    if(checks.some(v=>v.name===selected.name)) {setError("Este marco já participa da checagem.");return;}
    setChecks(old=>[...old,{name:selected.name,gnss_longitude:selected.longitude!,gnss_latitude:selected.latitude!,image_longitude:imagePoint.longitude,image_latitude:imagePoint.latitude,used_for_orthorectification:false}]);
    setPendingExclusions(old=>old.filter(p=>p.name!==selected.name));
    setImagePoint(null);setConfirmed(false);setResult(null);setError("");
  };
  const removeCheck = (name:string) => {
    const reason=(removalReason[name]??"").trim();
    if(reason.length<8){setError(`Justifique a exclusão de ${name} (mínimo 8 caracteres). Não remova pontos só para reduzir o EMQ.`);return;}
    if(persistedNames.includes(name)){
      setPendingExclusions(old=>[...old.filter(p=>p.name!==name),{name,reason}]);
    }
    setChecks(old=>old.filter(r=>r.name!==name));
    setResult(null);
    setError(`Ponto ${name} retirado da análise atual. Motivo informado: ${reason}. Registre esta justificativa no relatório técnico; a alteração só será persistida ao recalcular.`);
  };
  const analyze=async()=>{
    if(!pieceId || !rasterSha256 || (!checks.length && !pendingExclusions.length))return;
    setBusy(true);setError("");
    try{
      const r=await fetch(`${getApiUrl()}/technical-pieces/${pieceId}/ps4/checkpoint-analysis`,{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({checkpoints:checks,exclusions:pendingExclusions}),cache:"no-store",
      });
      const payload=await r.json().catch(()=>null);
      if(!r.ok)throw new Error(typeof payload?.detail==="string"?payload.detail:"Não foi possível calcular os resíduos.");
      setResult(payload.result as Result);
      setPersistedNames(checks.map(c=>c.name));
      setExclusionLog(old=>[...old,...pendingExclusions.map(p=>({...p,excluded_at:new Date().toISOString()}))]);
      setPendingExclusions([]);
      setRemovalReason({});
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
      {checks.map(c=><div key={c.name} style={{display:"flex",flexWrap:"wrap",alignItems:"center",gap:8}}>
        <strong>{c.name}</strong>
        <input aria-label={`Motivo para excluir ${c.name}`} style={{minWidth:220,flex:1}}
          placeholder="Justificativa técnica para exclusão"
          value={removalReason[c.name]??""}
          onChange={e=>setRemovalReason(old=>({...old,[c.name]:e.target.value}))}/>
        <button type="button" className="pecas-secondary" onClick={()=>removeCheck(c.name)}>Excluir da análise</button></div>)}
    </div>}
    <button type="button" className="pecas-primary"
      disabled={(!checks.length && !pendingExclusions.length) || busy} onClick={()=>void analyze()}>
      {busy?"Calculando resíduos...":"Calcular EMQ dos pontos de checagem"}</button>
    {error && <p className="ps4-alert-red" role="alert">{error}</p>}
    {!!pendingExclusions.length && <p role="status">
      {pendingExclusions.length} exclusão(ões) pendente(s) de registro: recalcule o EMQ para persistir a justificativa.
    </p>}
    {!!exclusionLog.length && <details>
      <summary>Histórico de exclusões justificadas ({exclusionLog.length})</summary>
      <ul>{exclusionLog.map((item,index)=><li key={index}>
        <strong>{item.name}</strong>: {item.reason} · {item.excluded_at}
      </li>)}</ul>
    </details>}
    {result && <div role="status" className="ps4-checkpoint-result">
      <strong>EMQ amostral horizontal: {result.rms_horizontal_m?.toLocaleString("pt-BR",{maximumFractionDigits:4})??"—"} m</strong>
      <p>EMQ E: {result.rms_e_m?.toLocaleString("pt-BR")??"—"} m · EMQ N: {result.rms_n_m?.toLocaleString("pt-BR")??"—"} m · {result.count} ponto(s).</p>
      <div className="ps4-alert-red" role="status">
        <strong>{result.status==="INSUFFICIENT_CHECKPOINTS"?"Triagem amostral insuficiente":"Triagem quantitativa atingida — requer revisão técnica"}</strong>
        <p>{result.count} de {result.screening_reference_count??20} pontos da referência de triagem interna.
        {result.status==="INSUFFICIENT_CHECKPOINTS"
          ?` Faltam ${result.screening_missing_count??Math.max(0,20-result.count)} para essa referência, sem garantia de suficiência técnica.`
          :" Quantidade, distribuição espacial, independência e metodologia exigem avaliação do RT."}</p>
        <p>Esta referência de 20 pontos NÃO é mínimo universal do INCRA e não libera PS4 nem ODS automaticamente.</p>
        <p>Maior discrepância radial: {result.max_radial_error_m?.toLocaleString("pt-BR",{maximumFractionDigits:4})??"—"} m. Investigue discrepâncias, sem excluir pontos apenas para reduzir o EMQ.</p>
      </div>
      <details><summary>Advertências e critérios da avaliação</summary>
        <ul>{result.warnings?.map((warning,i)=><li key={i}>{warning}</li>)}</ul>
      </details>
      <table><thead><tr><th>Marco</th><th>ΔE (m)</th><th>ΔN (m)</th><th>Erro radial (m)</th></tr></thead>
        <tbody>{result.checkpoints.map(p=><tr key={p.name}><td>{p.name}</td><td>{p.delta_e_m.toLocaleString("pt-BR")}</td><td>{p.delta_n_m.toLocaleString("pt-BR")}</td><td>{p.radial_error_m.toLocaleString("pt-BR")}</td></tr>)}</tbody></table>
    </div>}
  </div>;
}
