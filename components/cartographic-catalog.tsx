"use client";
import {useEffect,useState} from "react";
import {getApiUrl} from "@/lib/api";

const fields=[
 ["name","Nome da base"],["producer","Órgão produtor"],["distributor","Distribuidor"],["product","Produto / série"],
 ["region","Abrangência"],["scale","Denominador da escala"],["horizontal_crs","Referencial horizontal / EPSG"],
 ["vertical_datum","Datum vertical"],["vertical_kind","Tipo de altitude"],["source_model","Modelo altimétrico original"],
 ["pec","PEC / PEC-PCD"],["resolution","Resolução / GSD"],["format","Formato"],["edition","Edição"],
 ["creation_date","Data de criação"],["metadata_id","ID de metadados"],["reference_sheet","Folha de referência"],
 ["coverage","Extensão geográfica / BBOX"],["url","URL da fonte"],["license","Licença / condições de uso"],
 ["accuracy_reference","Evidência de exatidão"],["vertical_reference","Evidência vertical"],
 ["notes","Observações e limitações"],["report_credit","Texto para relatórios"],["map_credit","Crédito para mapas"]
] as const;
type Field=typeof fields[number][0];
export type CartographicProfile=Record<Field,string>&{id:string;revision:number;builtin:boolean};
const empty=()=>Object.fromEntries(fields.map(([k])=>[k,""])) as Record<Field,string>;

export function CartographicCatalog({onSelect,selectedId}:{onSelect?:(p:CartographicProfile)=>void;selectedId?:string}){
 const [items,setItems]=useState<CartographicProfile[]>([]);
 const [id,setId]=useState(selectedId??"");
 const [editing,setEditing]=useState(false);
 const [editId,setEditId]=useState("");
 const [draft,setDraft]=useState(empty);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 useEffect(()=>{let live=true;fetch(getApiUrl()+"/technical-pieces/cartographic-catalog",{credentials:"include"})
 .then(async r=>{if(!r.ok)throw Error("Catálogo indisponível.");return r.json()})
 .then(data=>{if(live)setItems(data)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false};},[]);
 useEffect(()=>{if(selectedId!==undefined)setId(selectedId)},[selectedId]);
 const current=items.find(p=>p.id===id);
 const begin=(copy?:CartographicProfile)=>{
   setDraft(copy?Object.fromEntries(fields.map(([k])=>[k,copy[k]??""])) as Record<Field,string>:empty());
   setEditId(copy&&!copy.builtin?copy.id:"");setEditing(true);setError("");
 };
 const save=async()=>{
   setBusy(true);setError("");
   try{
     const r=await fetch(getApiUrl()+"/technical-pieces/cartographic-catalog"+(editId?"/"+encodeURIComponent(editId):""),{
       method:editId?"PUT":"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify(draft)});
     const p=await r.json();
     if(!r.ok)throw Error(typeof p.detail==="string"?p.detail:"Confira os campos do cadastro.");
     setItems(old=>[...old.filter(x=>x.id!==p.id),p]);setId(p.id);setEditing(false);
   }catch(e){setError(e instanceof Error?e.message:"Erro ao salvar.");}finally{setBusy(false)}
 };
 return <section className="pecas-card" style={{minWidth:0,whiteSpace:"normal"}}>
   <strong>Catálogo de bases cartográficas</strong>
   <p>Metadados reutilizáveis por conta. A seleção registra a referência; não comprova automaticamente o datum ou PEC do raster.</p>
   <div style={{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center"}}>
   <select aria-label="Selecionar base cartográfica" value={id} onChange={e=>setId(e.target.value)} style={{flex:"1 1 190px",minWidth:0}}>
     <option value="">Selecione uma base</option>{items.map(p=><option key={p.id} value={p.id}>{p.name} · {p.product||"Produto não definido"}</option>)}
   </select>
   <button type="button" className="pecas-secondary" onClick={()=>begin()}>Cadastrar base</button>
   {current&&<button type="button" className="pecas-secondary" onClick={()=>begin(current)}>{current.builtin?"Duplicar referência":"Editar cadastro"}</button>}
   {current&&onSelect&&<button type="button" className="pecas-primary" onClick={()=>onSelect(current)}>Utilizar base na peça</button>}
   </div>
   {current&&!editing&&<details><summary>Metadados e créditos</summary>
     {fields.filter(([k])=>current[k]).map(([k,label])=><p key={k} style={{overflowWrap:"anywhere"}}><strong>{label}:</strong> {current[k]}</p>)}
   </details>}
   {editing&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:10,marginTop:12}}>
     {fields.map(([k,label])=><label key={k} className="pecas-field" style={{minWidth:0}}><span>{label}</span>
       {["notes","report_credit","map_credit","accuracy_reference","vertical_reference","license"].includes(k)?
       <textarea rows={3} value={draft[k]} onChange={e=>setDraft(o=>({...o,[k]:e.target.value}))}/>:
       <input value={draft[k]} onChange={e=>setDraft(o=>({...o,[k]:e.target.value}))}/>}
     </label>)}
     <p style={{gridColumn:"1/-1"}}>Deixe os créditos vazios para gerar automaticamente. Registre somente condições de uso e evidências conhecidas.</p>
     <div style={{display:"flex",gap:8,gridColumn:"1/-1"}}>
       <button type="button" className="pecas-primary" disabled={busy||!draft.name.trim()} onClick={()=>void save()}>{busy?"Salvando…":"Salvar cadastro"}</button>
       <button type="button" className="pecas-secondary" disabled={busy} onClick={()=>setEditing(false)}>Cancelar</button>
     </div>
   </div>}
   {error&&<p role="alert">{error}</p>}
 </section>
}
