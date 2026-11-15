"use client";

import { useState } from "react";
import { getApiUrl } from "@/lib/api";

type Source = { checked: boolean; status: string; source?: string; reference_date?: string | null; imported_at?: string | null; feature_count?: number };
type Match = { source: string; name?: string | null; external_id?: string | null; relation: string; overlap_m2: number; distance_m: number; bbox_geojson?: string };
type Suggestion = {vertex:string;source:string;neighbor_id?:string|null;neighbor_name?:string|null;old_lon:number;old_lat:number;proposed_lon:number;proposed_lat:number;displacement_m:number;classification:string;applied:boolean};
type Report = { status: string; complete: boolean; sources: Record<string, Source>; matches: Match[]; suggestions:Suggestion[]; note: string; auto_adjustment_applied: boolean };

export function OfficialOverlapCheck({ geometry, vertices = [], onNext, onReport, onOpenMap }: {
  geometry: {type:"Polygon";coordinates:number[][][]} | null;
  vertices?: Array<{name:string;latitude:number;longitude:number}>;
  onNext?: () => void;
  onOpenMap?: () => void;
  onReport?: (report: {status:string; complete:boolean; count:number}) => void;
}) {
  const [loading,setLoading]=useState(false);
  const [maxAdjust,setMaxAdjust]=useState("0.5");
  const [error,setError]=useState("");
  const [report,setReport]=useState<Report|null>(null);
  const [showLayers,setShowLayers]=useState<Record<string,boolean>>({
    "SIGEF Mensais":true,"SIGEF Brasil":true,
  });
  const run=async()=>{
    setLoading(true);setError("");setReport(null);
    try {
      if(!geometry)throw new Error("Feche a poligonal PS4 no mapa antes de verificar sobreposições.");
      const res=await fetch(`${getApiUrl()}/technical-pieces/official-overlaps/check`,{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({geometry,near_m:3,include_touching:true,
          ps4_vertices:vertices.map(v=>({name:v.name,latitude:v.latitude,longitude:v.longitude})),
          max_adjust_m:Number(maxAdjust)}),
      });
      const payload=await res.json().catch(()=>null);
      if(!res.ok)throw new Error(typeof payload?.detail==="string"?payload.detail:
        "Serviço SIGEF indisponível nesta homologação. Nenhuma verificação foi declarada.");
      setReport(payload as Report);
      onReport?.({status:payload.status,complete:Boolean(payload.complete),count:Number(payload.count||0)});
    }catch(e){setError(e instanceof Error?e.message:"Falha de verificação.");}
    finally{setLoading(false);}
  };
  const overlaps=report?.matches.filter(v=>v.relation==="SOBREPOSICAO")??[];
  return <section className="pecas-card geo96-main-card" aria-label="Conferência de sobreposição com parcelas oficiais">
    <div className="geo96-section-heading">
      <small>ETAPA 5 · CONFERÊNCIA ESPACIAL</small>
      <h3>Sobreposições com parcelas SIGEF</h3>
      <p>Consulte as parcelas vizinhas antes de preparar a planta. Somente bases vetoriais
        oficiais efetivamente disponíveis são consideradas. A ausência de feições em uma fonte
        indisponível não significa ausência de sobreposição.</p>
    </div>
    <div className="geo96-next-step">
      <strong>Poligonal de trabalho:</strong> {geometry
        ? "Fechamento PS4 disponível para conferência espacial." :
          "Ainda não existe uma poligonal PS4 fechada; volte ao espaço de construção."}
    </div>
    <div className="pecas-card geo96-task-card">
      <h4>Fontes oficiais obrigatórias</h4>
      <p>Selecione quais bases visualizar no relatório. As duas são verificadas quando
        existem versões vetoriais utilizáveis; desligar a visualização não elimina uma pendência.</p>
      {["SIGEF Mensais","SIGEF Brasil"].map(name=><label className="pecas-check" key={name}>
        <input type="checkbox" checked={showLayers[name]}
          onChange={e=>setShowLayers(prev=>({...prev,[name]:e.target.checked}))}/>
        {name}
        <span style={{marginLeft:8,color:"#536a64",fontSize:12}}>
          {report ? (report.sources[name]?.checked?"Consultada":"Indisponível como vetor"):"Ainda não consultada"}
        </span>
      </label>)}
      <label className="pecas-field"><span>Distância máxima para gerar SUGESTÕES de encaixe (m)</span>
        <select value={maxAdjust} onChange={e=>setMaxAdjust(e.target.value)}>
          <option value="0">Não gerar sugestões</option>
          <option value="0.2">0,20 m</option>
          <option value="0.5">0,50 m</option>
          <option value="1">1,00 m (exige análise)</option>
          <option value="3">3,00 m (exige análise)</option>
          <option value="9">9,00 m (exige análise)</option>
        </select>
      </label>
      <p className="pecas-note">Até 0,50 m: cenário de possível inclusão automática
        em alinhamento certificado, sujeito à aplicabilidade do procedimento.
        Acima de 0,50 m exige análise. Nenhuma geometria é deslocada automaticamente.</p>
      <button type="button" className="pecas-primary" disabled={loading||!geometry}
        onClick={()=>void run()}>{loading?"Analisando versões oficiais…":"Verificar sobreposições SIGEF"}</button>
      {error&&<p role="alert" className="pecas-warning">{error}</p>}
    </div>
    {report&&<div aria-live="polite">
      <div role={report.complete&&!overlaps.length?"status":"alert"}
        className={report.complete&&!overlaps.length?"geo96-next-step":"pecas-warning"}
        style={{padding:13,borderRadius:10}}>
        <strong>{overlaps.length?
          `Encontradas ${overlaps.length} interseção(ões) territorial(is)`:
          report.complete?"Sem interseções nas versões locais consultadas":
          "Verificação incompleta — não liberar conclusão de ausência de sobreposição"}</strong>
        <p>{report.note}</p>
      </div>
      <div className="pecas-card geo96-task-card">
        <h4>Rastreabilidade das fontes</h4>
        <div className="pecas-table-wrap"><table className="pecas-table">
          <thead><tr><th>Fonte</th><th>Situação</th><th>Data de referência</th><th>Feições na versão</th></tr></thead>
          <tbody>{Object.entries(report.sources).map(([name,s])=><tr key={name}>
            <td>{name}</td><td>{s.checked?s.status:"SEM BASE VETORIAL"}</td>
            <td>{s.reference_date??"—"}</td><td>{s.feature_count??"—"}</td>
          </tr>)}</tbody>
        </table></div>
      </div>
      {report.matches.length>0&&<div className="pecas-card geo96-task-card">
        <h4>Ocorrências e vizinhos detectados</h4>
        <div className="pecas-table-wrap"><table className="pecas-table">
          <thead><tr><th>Camada</th><th>Parcela</th><th>Relação</th><th>Interseção (m²)</th><th>Distância (m)</th></tr></thead>
          <tbody>{report.matches.filter(m=>showLayers[m.source]).map((m,i)=><tr key={m.source+i}>
            <td>{m.source}</td><td>{m.name||m.external_id||"Identificador indisponível"}</td>
            <td>{m.relation}</td><td>{m.overlap_m2.toLocaleString("pt-BR")}</td>
            <td>{m.distance_m.toLocaleString("pt-BR")}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="pecas-note">Distâncias e interseções são medidas da versão disponível no banco.
          Não representam autorização de deslocamento. Ajustes devem ser documentados e aprovados pelo RT.</p>
      </div>}
      {report.suggestions?.length>0&&<div className="pecas-card geo96-task-card">
        <h4>Sugestões automáticas de encaixe — sem aplicação</h4>
        <p>Os pontos abaixo podem ser inspecionados e comparados com a linha
          oficialmente cadastrada. Os deslocamentos são propostas; precisam de
          decisão técnica explícita e não alteram a geometria atual.</p>
        <div className="pecas-table-wrap"><table className="pecas-table">
          <thead><tr><th>Vértice V</th><th>Base</th><th>Parcela vizinha</th>
            <th>Deslocamento (m)</th><th>Classificação</th></tr></thead>
          <tbody>{report.suggestions.filter(v=>showLayers[v.source]).map((v,i)=><tr key={v.vertex+v.source+i}>
            <td>{v.vertex}</td><td>{v.source}</td><td>{v.neighbor_name||v.neighbor_id||"—"}</td>
            <td>{v.displacement_m.toLocaleString("pt-BR")}</td>
            <td>{v.classification==="ATE_0_50_M_REVISAO_RT"?
              "Até 0,50 m · conferir alinhamento":"Acima de 0,50 m · análise obrigatória"}</td>
          </tr>)}</tbody>
        </table></div>
      </div>}
      <p className="pecas-note">Ajuste automático de vértices: <strong>DESABILITADO</strong>
        enquanto não houver dados posicionais e critérios de tolerância comprovados.
        Uma discrepância admissível não autoriza deslocar uma divisa.</p>
    </div>}
    {onOpenMap&&<button type="button" className="pecas-secondary" onClick={onOpenMap}>
      Abrir mapa principal para consultar outras camadas
    </button>}
    <button type="button" className="pecas-secondary" onClick={onNext}>
      Continuar para revisão da parcela preliminar
    </button>
  </section>;
}
