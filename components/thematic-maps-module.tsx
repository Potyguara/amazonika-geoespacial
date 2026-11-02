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
  const [savedPackages,setSavedPackages] = useState<{package_id:string;name:string;layers:{name:string}[];size_bytes:number}[]>([]);
  const [packageId,setPackageId] = useState("");
  const [packageLayers,setPackageLayers] = useState<string[]>([]);
  const [selectedPackageLayers,setSelectedPackageLayers] = useState<string[]>([]);
  const [includeBranding,setIncludeBranding] = useState(false);
  const [styleMode,setStyleMode] = useState("minimalista");
  const [gridMode,setGridMode] = useState("border");
  const [propertyMode,setPropertyMode] = useState("outline");
  const [contextMode,setContextMode] = useState("balanced");
  const [mapScale,setMapScale] = useState("auto");
  const [design,setDesign] = useState<{layer:string;class_field:string|null;color:string;reason:string}[]>([]);
  const [availableFields,setAvailableFields] = useState<Record<string,string[]>>({});
  const [classFields,setClassFields] = useState<Record<string,string>>({});
  const [classPreviews,setClassPreviews] = useState<Record<string,{value:string;count:number}[]>>({});
  const [classColors,setClassColors] = useState<Record<string,string>>({});
  const [aiUsed,setAiUsed] = useState(false);
  const [aiTokens,setAiTokens] = useState<number|null>(null);
  const [previewUrl,setPreviewUrl] = useState<string|null>(null);
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  useEffect(() => {
    void fetch(`${API}/thematic-maps/templates`,{credentials:"include"})
      .then(r=>r.json()).then(setTemplates).catch(()=>setMessage("Falha ao carregar modelos."));
  },[]);
  const loadPackages=async()=>{
    try {
      const r=await fetch(`${API}/thematic-maps/packages`,{credentials:"include"});
      if(r.ok)setSavedPackages(await r.json());
    }catch { /* biblioteca offline */ }
  };
  useEffect(()=>{void loadPackages();},[]);
  const loadFields=async(id:string)=>{
    const response=await fetch(API+"/thematic-maps/package/"+encodeURIComponent(id)+"/fields",{credentials:"include"});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Falha ao consultar atributos.");
    setAvailableFields(Object.fromEntries((body.layers as {name:string;fields:{name:string}[]}[])
      .map(layer=>[layer.name,layer.fields.map(field=>field.name)])));
  };
  const loadClasses=async(id:string,layer:string,field:string)=>{
    if(!field){setClassPreviews(prev=>({...prev,[layer]:[]}));return;}
    try{
      const query=new URLSearchParams({layer,field});
      const response=await fetch(API+"/thematic-maps/package/"+encodeURIComponent(id)+"/classes?"+query,{credentials:"include"});
      const body=await response.json();
      if(!response.ok)throw new Error(body.detail||"Falha ao consultar classes.");
      setClassPreviews(prev=>({...prev,[layer]:body.classes}));
    }catch(err){setMessage(err instanceof Error?err.message:"Erro nas classes.");}
  };
  const selectClassField=(layer:string,field:string)=>{
    setClassFields(old=>({...old,[layer]:field}));
    setClassPreviews(old=>({...old,[layer]:[]}));
    if(packageId)void loadClasses(packageId,layer,field);
  };
  const usePackage=(item:{package_id:string;layers:{name:string}[]})=>{
    const names=item.layers.map(layer=>layer.name);
    setPackageId(item.package_id);setPackageLayers(names);setSelectedPackageLayers(names);setDesign([]);
    setClassFields({});setClassPreviews({});setClassColors({});setAvailableFields({});
    void loadFields(item.package_id).catch(err=>setMessage(err instanceof Error?err.message:"Falha nos atributos."));
    setMessage("Base carregada da biblioteca. Selecione as camadas e gere seu mapa.");
  };
  const importPackage=async(file:File)=>{
    setBusy(true);setMessage("");
    try {
      const data=new FormData();data.append("file",file);
      const r=await fetch(`${API}/thematic-maps/package`,{method:"POST",credentials:"include",body:data});
      const payload=await r.json();
      if(!r.ok)throw new Error(payload.detail||"Falha no pacote GeoPackage.");
      setPackageId(payload.package_id);setDesign([]);
      setClassFields({});setClassPreviews({});setClassColors({});setAvailableFields({});
      await loadFields(payload.package_id);
      setPackageLayers(payload.layers.map((layer:{name:string})=>layer.name));
      setSelectedPackageLayers(payload.layers.map((layer:{name:string})=>layer.name));
      setMessage(`Pacote gravado na biblioteca: ${payload.layers.length} camadas.`);
      await loadPackages();
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
  const proposeDesign=async()=>{
    if(!packageId||!selectedPackageLayers.length)return;
    setBusy(true);setMessage("");
    try {
      const r=await fetch(`${API}/thematic-maps/package/design`,{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({package_id:packageId,template,selected_layers:selectedPackageLayers})
      });
      const result=await r.json();
      if(!r.ok)throw new Error(result.detail||"Erro na proposta cartográfica.");
      setDesign(result.design);
      setClassFields(Object.fromEntries((result.design as {layer:string;class_field:string|null}[])
        .filter(item=>item.class_field).map(item=>[item.layer,item.class_field as string])));
      for(const item of result.design as {layer:string;class_field:string|null}[]){
        if(item.class_field)void loadClasses(packageId,item.layer,item.class_field);
      }
      setAvailableFields(Object.fromEntries((result.metadata as {name:string;fields:{field:string}[]}[])
        .map(layer=>[layer.name,layer.fields.map(f=>f.field)])));
      setAiUsed(Boolean(result.ai_used));
      setAiTokens(result.usage?.total_tokens??null);
      setMessage(result.ai_used?"IA analisou os atributos disponíveis. Revise as sugestões abaixo.":"Regras locais aplicadas: IA não respondeu. Revise as sugestões.");
    }catch(err){setMessage(err instanceof Error?err.message:"Falha na IA.");}
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
  const exportPdf=async(preview=false)=>{
    setBusy(true);setMessage("");
    try{
      const property=layers.find(l=>l.role==="property");
      const endpoint=packageId ? "package/pdf" : "pdf";
      const style={mode:styleMode,grid:gridMode,property:propertyMode,context:contextMode,
        scale:mapScale==="auto"?null:Number(mapScale)};
      const body=packageId ? {
        package_id:packageId,property_geometry:property?.geometry,title,subtitle,style,
        selected_layers:selectedPackageLayers,include_branding:includeBranding,source_text:sourceText,
        class_fields:Object.fromEntries(Object.entries(classFields).filter(([,field])=>Boolean(field))),
        class_colors:classColors,
        layer_colors:Object.fromEntries(design.map(d=>[d.layer,d.color]))
      } : {title,subtitle,style,source_text:sourceText,include_branding:includeBranding,
        layers:layers.map(({features,...layer})=>layer)};
      const r=await fetch(`${API}/thematic-maps/${endpoint}`,{method:"POST",credentials:"include",
        headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      if(!r.ok){const e=await r.json().catch(()=>null);throw new Error(e?.detail||"Não foi possível emitir PDF.");}
      const url=URL.createObjectURL(await r.blob());
      if(preview){
        setPreviewUrl(previous=>{if(previous)URL.revokeObjectURL(previous);return url;});
      } else {
        const a=document.createElement("a");a.href=url;a.download="mapa-tematico.pdf";a.click();
        window.setTimeout(()=>URL.revokeObjectURL(url),30000);
      }
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
      <h3>3. Biblioteca de bases temáticas</h3>
      <p>Selecione uma base já armazenada no servidor ou importe um GeoPackage novo. Não será necessário reenviar a mesma base em cada mapa.</p>
      <select className="thematic-saved-select" value={packageId}
        onChange={e=>{const item=savedPackages.find(p=>p.package_id===e.target.value);if(item)usePackage(item);}}>
        <option value="">Selecionar base existente...</option>
        {savedPackages.map(p=><option key={p.package_id} value={p.package_id}>
          {p.name} — {(p.size_bytes/1000000).toFixed(1)} MB · {p.layers.length} camadas
        </option>)}
      </select>
      <h3>Importar novo pacote temático (.gpkg)</h3>
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
      {packageId&&selectedPackageLayers.length>0&&<div className="thematic-design-review">
        <h3>Classificação por atributos do GeoPackage</h3>
        <p>Selecione um campo para consultar as categorias. As quantidades são de feições, não hectares.</p>
        {selectedPackageLayers.map(layer=><div key={layer}>
          <strong>{layer}</strong>
          <label>Campo de classificação
            <select value={classFields[layer]||""} onChange={e=>selectClassField(layer,e.target.value)}>
              <option value="">Classificação automática</option>
              {(availableFields[layer]||[]).map(field=><option value={field} key={field}>{field}</option>)}
            </select>
          </label>
          {(classPreviews[layer]||[]).map((item,index)=>{
            const key=layer+": "+item.value;
            return <div key={key} className="thematic-layer-row">
              <input type="color" aria-label={"Cor da classe "+item.value}
                value={classColors[key]||COLORS[index%COLORS.length]}
                onChange={e=>setClassColors(old=>({...old,[key]:e.target.value}))}/>
              <span>{item.value}</span><small>{item.count} feições</small>
            </div>;
          })}
        </div>)}
      </div>}
      <h3>4. Assistente cartográfico de IA</h3>
      <p>A IA analisa nomes, amostras de atributos e tipos geométricos, sem enviar coordenadas. A aplicação das sugestões depende da sua revisão.</p>
      <button type="button" className="thematic-ai-button" disabled={busy||!packageId||selectedPackageLayers.length===0}
        onClick={()=>void proposeDesign()}>Analisar camadas e sugerir simbologia com IA</button>
      {design.length>0&&<div className="thematic-design-review">
        <p>{aiUsed?"Sugestões geradas pela IA":"Sugestões geradas por regras locais"}{aiTokens!==null?` · ${aiTokens} tokens`:""} — edite antes de gerar.</p>
        {design.map(item=><div className="thematic-layer-row" key={item.layer}>
          <strong>{item.layer}</strong>
          <label>Cor <input type="color" value={item.color} onChange={e=>setDesign(old=>old.map(x=>x.layer===item.layer?{...x,color:e.target.value}:x))}/></label>
          <label>Classificação <select value={item.class_field||""} onChange={e=>{selectClassField(item.layer,e.target.value);setDesign(old=>old.map(x=>x.layer===item.layer?{...x,class_field:e.target.value||null}:x));}}>
            <option value="">Automática</option>
            {(availableFields[item.layer]||[]).map(field=><option key={field} value={field}>{field}</option>)}
          </select></label>
          <small>{item.reason}</small>
        </div>)}
      </div>}
      <h3>5. Estilo e enquadramento do mapa</h3>
      <div className="thematic-style-grid">
        <label>Perfil visual
          <select value={styleMode} onChange={e=>{setStyleMode(e.target.value);setGridMode(e.target.value==="minimalista"?"border":e.target.value==="tecnico"?"subtle":"full");}}>
            <option value="minimalista">Minimalista</option>
            <option value="tecnico">Técnico</option>
            <option value="analitico">Analítico</option>
          </select>
        </label>
        <label>Propriedade
          <select value={propertyMode} onChange={e=>setPropertyMode(e.target.value)}>
            <option value="outline">Vazada — somente contorno</option>
            <option value="transparent">Translúcida</option>
            <option value="fill">Preenchida</option>
          </select>
        </label>
        <label>Grade georreferenciada
          <select value={gridMode} onChange={e=>setGridMode(e.target.value)}>
            <option value="border">Coordenadas apenas nas bordas</option>
            <option value="subtle">Grade discreta</option>
            <option value="full">Grade completa</option>
            <option value="off">Ocultar grade e coordenadas</option>
          </select>
        </label>
        <label>Enquadramento
          <select value={contextMode} onChange={e=>setContextMode(e.target.value)}>
            <option value="close">Foco na propriedade</option>
            <option value="balanced">Equilibrado</option>
            <option value="regional">Contexto regional</option>
          </select>
        </label>
        <label>Escala para impressão A3
          <select value={mapScale} onChange={e=>setMapScale(e.target.value)}>
            <option value="auto">Automática — escala padronizada</option>
            {[2500,5000,10000,25000,50000,100000,250000,500000,1000000].map(n=><option key={n} value={String(n)}>1:{n.toLocaleString("pt-BR")}</option>)}
          </select>
        </label>
      </div>
      <h3>6. Composição cartográfica</h3>
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
      <div className="thematic-export-actions">
        <button type="button" className="thematic-export" disabled={busy||!layers.some(l=>l.role==="property")||(packageId ? selectedPackageLayers.length===0 : !layers.some(l=>l.role==="theme"))}
          onClick={()=>void exportPdf(true)}>Visualizar prévia A3</button>
        <button type="button" className="thematic-export" disabled={busy||!layers.some(l=>l.role==="property")||(packageId ? selectedPackageLayers.length===0 : !layers.some(l=>l.role==="theme"))}
          onClick={()=>void exportPdf(false)}><FileDown size={18}/>{busy?"Processando…":"Baixar mapa temático PDF"}</button>
      </div>
      {previewUrl&&<div className="thematic-pdf-preview">
        <div><strong>Pré-visualização da prancha A3</strong>
          <button type="button" onClick={()=>{URL.revokeObjectURL(previewUrl);setPreviewUrl(null);}}>Fechar prévia</button>
        </div>
        <iframe title="Pré-visualização do mapa temático" src={previewUrl}/>
      </div>}
      <p className="thematic-note">O GeoPackage é processado no servidor por recorte espacial; a propriedade é independente. Sugestões automáticas exigem conferência do responsável técnico.</p>
    </div>
  </section>;
}
