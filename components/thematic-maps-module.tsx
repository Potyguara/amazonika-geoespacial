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
  const [packageId,setPackageId] = useState("");
  const [packageLayers,setPackageLayers] = useState<string[]>([]);
  const [selectedPackageLayers,setSelectedPackageLayers] = useState<string[]>([]);
  const [includeBranding,setIncludeBranding] = useState(false);
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  useEffect(() => {
    void fetch(`${API}/thematic-maps/templates`,{credentials:"include"})
      .then(r=>r.json()).then(setTemplates).catch(()=>setMessage("Falha ao carregar modelos."));
  },[]);
  const importPackage=async(file:File)=>{
    setBusy(true);setMessage("");
    try {
      const data=new FormData();data.append("file",file);
      const r=await fetch(`${API}/thematic-maps/package`,{method:"POST",credentials:"include",body:data});
      const payload=await r.json();
      if(!r.ok)throw new Error(payload.detail||"Falha no pacote GeoPackage.");
      setPackageId(payload.package_id);
      setPackageLayers(payload.layers.map((layer:{name:string})=>layer.name));
      setSelectedPackageLayers(payload.layers.map((layer:{name:string})=>layer.name));
      setMessage(`Pacote carregado: ${payload.layers.length} camadas. Marque as camadas desejadas.`);
    } catch(err) {setMessage(err instanceof Error?err.message:"Erro no pacote.");}
    finally {setBusy(false);}
  };
  const suggestLayers=async()=>{
    if(!packageId)return;
    setBusy(true);
    try {
      const r=await fetch(`${API}/thematic-maps/package/suggestions`,{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({package_id:packageId,property_geometry:layers.find(l=>l.role==="property")?.geometry,
          title:template,selected_layers:selectedPackageLayers.length?selectedPackageLayers:packageLayers})});
      const result=await r.json();
      if(!r.ok)throw new Error(result.detail||"Falha nas sugestões.");
      if(result.suggested_layers.length)setSelectedPackageLayers(result.suggested_layers);
      setMessage(result.suggested_layers.length?`Sugestão: ${result.suggested_layers.join(", ")}. Confira antes de exportar.`:
        "Nenhuma camada identificada automaticamente; escolha manualmente.");
    }catch(err){setMessage(err instanceof Error?err.message:"Falha nas sugestões.");}
    finally{setBusy(false);}
  };
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
      const property=layers.find(l=>l.role==="property");
      const endpoint=packageId ? "package/pdf" : "pdf";
      const body=packageId ? {
        package_id:packageId,property_geometry:property?.geometry,title,subtitle,
        selected_layers:selectedPackageLayers,include_branding:includeBranding,source_text:sourceText
      } : {title,subtitle,source_text:sourceText,include_branding:includeBranding,
        layers:layers.map(({features,...layer})=>layer)};
      const r=await fetch(`${API}/thematic-maps/${endpoint}`,{method:"POST",credentials:"include",
        headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
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
      <h3>2. Importe a propriedade (arquivo separado)</h3>
      <p>Importe o perímetro da propriedade em ZIP Shapefile, GeoPackage, KML ou GeoJSON. A propriedade não precisa estar no pacote temático.</p>
      <div className="thematic-imports">
        {(["property"] as const).map(role=><label key={role} className="thematic-upload">
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
      <h3>3. Pacote temático único (.gpkg)</h3>
      <p>Importe um GeoPackage contendo as camadas de hidrografia, acessos, solos, vegetação, unidades de conservação e demais temas. O servidor filtra as geometrias para o entorno da propriedade.</p>
      <label className="thematic-upload"><FileUp size={18}/> Importar GeoPackage temático
        <input type="file" accept=".gpkg" disabled={busy}
          onChange={e=>{const file=e.target.files?.[0];if(file)void importPackage(file);e.currentTarget.value="";}}/>
      </label>
      {packageId&&<div className="thematic-package-list">
        <button type="button" onClick={()=>void suggestLayers()} disabled={busy||!layers.some(l=>l.role==="property")}>
          Sugerir camadas automaticamente
        </button>
        {packageLayers.map(name=><label key={name}>
          <input type="checkbox" checked={selectedPackageLayers.includes(name)}
            onChange={e=>setSelectedPackageLayers(current=>e.target.checked?[...current,name]:current.filter(x=>x!==name))}/>
          {name}
        </label>)}
      </div>}
      <h3>4. Composição cartográfica</h3>
      <div className="thematic-fields">
        <label>Título<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
        <label>Subtítulo<input value={subtitle} onChange={e=>setSubtitle(e.target.value)}/></label>
        <label className="wide">Fonte dos dados<input value={sourceText} placeholder="Ex.: IBGE (2024); CPRM (2023); levantamento próprio" onChange={e=>setSourceText(e.target.value)}/></label>
      </div>
      <label className="thematic-brand-toggle">
        <input type="checkbox" checked={includeBranding} onChange={e=>setIncludeBranding(e.target.checked)}/>
        Exibir identificação Amazônika no rodapé (opcional)
      </label>
      {message&&<p role="status">{message}</p>}
      <button type="button" className="thematic-export" disabled={busy||!layers.some(l=>l.role==="property")||(packageId ? selectedPackageLayers.length===0 : !layers.some(l=>l.role==="theme"))}
        onClick={()=>void exportPdf()}><FileDown size={18}/>{busy?"Processando…":"Gerar mapa temático PDF — A3"}</button>
      <p className="thematic-note">O GeoPackage é processado no servidor por recorte espacial; a propriedade é independente. Sugestões automáticas exigem conferência do responsável técnico.</p>
    </div>
  </section>;
}
