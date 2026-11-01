"use client";
import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";
import { FileUp, FileDown, Layers3, Trash2 } from "lucide-react";

type Layer = { name: string; source: string; color: string; role: "property" | "theme"; geometry: Record<string,unknown>; features: number };
type Template = { code: string; title: string };
const API = getApiUrl();
const COLORS = ["#73c6ad","#e7b75a","#8bb4df","#ce94c4","#9dc464","#e59c8b","#a6a0d6","#7eb8b2"];
export function ThematicMapsModule() {
  const [templates,setTemplates] = useState<Template[]>([]);
  const [template,setTemplate] = useState("situacao");
  const [layers,setLayers] = useState<Layer[]>([]);
  const [title,setTitle] = useState("MAPA DE SITUAÇÃO");
  const [subtitle,setSubtitle] = useState("");
  const [sourceText,setSourceText] = useState("");
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  useEffect(() => {
    void fetch(`${API}/thematic-maps/templates`,{credentials:"include"})
      .then(r=>r.json()).then(setTemplates).catch(()=>setMessage("Falha ao carregar modelos."));
  },[]);
  const importFile=async(file:File,role:"property"|"theme")=>{
    setBusy(true);setMessage("");
    try {
      const data=new FormData();data.append("file",file);
      const r=await fetch(`${API}/thematic-maps/import`,{method:"POST",credentials:"include",body:data});
      const result=await r.json();
      if(!r.ok)throw new Error(result.detail||"Não foi possível importar.");
      setLayers(existing=>[...existing,{name:file.name.replace(/\.(zip|gpkg|kml|geojson)$/i,""),source:"Arquivo enviado pelo usuário: "+file.name,
        color:role==="property"?"#cb2424":COLORS[existing.length%COLORS.length],
        geometry:result.geometry,features:result.features,role}]);
      setMessage(`${file.name}: ${result.features} feições importadas.`);
    } catch(e){setMessage(e instanceof Error?e.message:"Erro de importação.");}
    finally{setBusy(false);}
  };
  const exportPdf=async()=>{
    setBusy(true);setMessage("");
    try{
      const r=await fetch(`${API}/thematic-maps/pdf`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({title,subtitle,source_text:sourceText,layers:layers.map(({features,...layer})=>layer)})});
      if(!r.ok){const e=await r.json().catch(()=>null);throw new Error(e?.detail||"Não foi possível emitir PDF.");}
      const url=URL.createObjectURL(await r.blob());
      const a=document.createElement("a");a.href=url;a.download="mapa-tematico.pdf";a.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),30000);
    }catch(e){setMessage(e instanceof Error?e.message:"Erro na exportação.");}finally{setBusy(false);}
  };
  return <section className="thematic-module">
    <header className="settings-hero"><div><p className="eyebrow">CARTOGRAFIA AUTOMÁTICA</p>
      <h2>Mapas Temáticos</h2><p>Modelo único A3 paisagem, com grade UTM, escala, norte, legenda e fontes.</p></div><Layers3 size={28}/></header>
    <div className="thematic-card">
      <h3>1. Escolha o modelo</h3>
      <div className="thematic-template-grid">
        {templates.map(t=><button type="button" key={t.code} className={template===t.code?"active":""}
          onClick={()=>{setTemplate(t.code);setTitle(t.title.toUpperCase());}}>{t.title}</button>)}
      </div>
      <h3>2. Importe os vetores georreferenciados</h3>
      <p>Arquivos ZIP Shapefile, GeoPackage, KML ou GeoJSON com SRC definido. Importe a propriedade primeiro e quantas camadas temáticas precisar.</p>
      <div className="thematic-imports">
        {(["property","theme"] as const).map(role=><label key={role} className="thematic-upload">
          <FileUp size={18}/>{role==="property"?"Importar propriedade":"Adicionar camada temática"}
          <input type="file" accept=".zip,.gpkg,.kml,.geojson" disabled={busy}
            onChange={e=>{const f=e.target.files?.[0];if(f)void importFile(f,role);e.currentTarget.value="";}}/>
        </label>)}
      </div>
      <div className="thematic-layer-list">
        {layers.map((l,i)=><div key={i} className="thematic-layer-row">
          <input type="color" aria-label="Cor da camada" value={l.color} onChange={e=>setLayers(v=>v.map((x,j)=>j===i?{...x,color:e.target.value}:x))}/>
          <input aria-label="Nome da camada" value={l.name} onChange={e=>setLayers(v=>v.map((x,j)=>j===i?{...x,name:e.target.value}:x))}/>
          <small>{l.role==="property"?"Propriedade":"Temática"} · {l.features} feições</small>
          <button type="button" title="Excluir camada" onClick={()=>setLayers(v=>v.filter((_,j)=>j!==i))}><Trash2 size={16}/></button>
        </div>)}
      </div>
      <h3>3. Composição cartográfica</h3>
      <div className="thematic-fields">
        <label>Título<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
        <label>Subtítulo<input value={subtitle} onChange={e=>setSubtitle(e.target.value)}/></label>
        <label className="wide">Fonte dos dados<input value={sourceText} placeholder="Ex.: IBGE (2024); CPRM (2023); levantamento próprio" onChange={e=>setSourceText(e.target.value)}/></label>
      </div>
      {message&&<p role="status">{message}</p>}
      <button type="button" className="thematic-export" disabled={busy||!layers.some(l=>l.role==="property")||!layers.some(l=>l.role==="theme")}
        onClick={()=>void exportPdf()}><FileDown size={18}/>{busy?"Processando…":"Gerar mapa temático PDF — A3"}</button>
      <p className="thematic-note">Primeira versão: composição PDF a partir de vetores importados. Pré-visualização interativa, projetos salvos e seleção de camadas oficiais serão integrados na próxima etapa.</p>
    </div>
  </section>;
}
