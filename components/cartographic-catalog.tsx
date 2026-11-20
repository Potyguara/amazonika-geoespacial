"use client";
import {useEffect,useState} from "react";
import {getApiUrl} from "@/lib/api";

const groups=[
 {title:"Identificação e procedência",fields:[["name","Nome da base"],["producer","Órgão produtor"],["distributor","Distribuidor"],["product","Produto / série"],["region","Abrangência"],["url","URL da fonte"]]},
 {title:"Cartografia e referenciais",fields:[["scale","Escala — denominador"],["horizontal_crs","Referencial horizontal / EPSG"],["vertical_datum","Datum vertical do produto"],["vertical_kind","Tipo de altitude do raster"],["source_model","Modelo de conversão altimétrica — se conhecido"],["pec","PEC / PEC-PCD declarado"],["resolution","Resolução / GSD"],["format","Formato"],["reference_sheet","Folha genérica ou MI/INOM"]]},
 {title:"Histórico e metadados",fields:[["edition","Edição"],["creation_date","Data de criação"],["metadata_id","ID de metadados"],["coverage","Extensão geográfica / BBOX"],["license","Licença / condições de uso"]]},
 {title:"Qualidade, observações e créditos",fields:[["accuracy_reference","Referência documental de exatidão"],["vertical_reference","Referência documental vertical"],["notes","Observações e limitações"],["report_credit","Texto para relatórios"],["map_credit","Crédito para mapas"]]}
] as const;
type Field=(typeof groups)[number]["fields"][number][0];
const fields=(groups as ReadonlyArray<{title:string;fields:ReadonlyArray<readonly [Field,string]>}>).flatMap(g=>g.fields);
export type CartographicProfile=Record<Field,string>&{id:string;revision:number;builtin:boolean};
const empty=()=>Object.fromEntries(fields.map(([k])=>[k,""])) as Record<Field,string>;
const multiline=new Set<Field>(["notes","report_credit","map_credit","accuracy_reference","vertical_reference","license","coverage"]);

export function CartographicCatalog({onSelect,selectedId}:{onSelect?:(p:CartographicProfile)=>void;selectedId?:string}){
 const [items,setItems]=useState<CartographicProfile[]>([]);
 const [id,setId]=useState(selectedId??"");
 const [editing,setEditing]=useState(false);
 const [editId,setEditId]=useState("");
 const [draft,setDraft]=useState(empty);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 useEffect(()=>{let live=true;fetch(getApiUrl()+"/technical-pieces/cartographic-catalog",{credentials:"include"})
 .then(async r=>{if(!r.ok)throw Error("Catálogo indisponível.");return r.json()})
 .then(data=>{if(live)setItems(data)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false};},[]);
 useEffect(()=>{if(selectedId!==undefined)setId(selectedId)},[selectedId]);
 const template=items.find(p=>p.builtin);
 const registered=items.filter(p=>!p.builtin);
 const current=registered.find(p=>p.id===id);
 const begin=(copy?:CartographicProfile)=>{
   setDraft(copy?Object.fromEntries(fields.map(([k])=>[k,copy[k]??""])) as Record<Field,string>:empty());
   setEditId(copy&&!copy.builtin?copy.id:"");setEditing(true);setError("");setNotice("");
 };
 const save=async()=>{
   setBusy(true);setError("");setNotice("");
   try{
     const r=await fetch(getApiUrl()+"/technical-pieces/cartographic-catalog"+(editId?"/"+encodeURIComponent(editId):""),{
       method:editId?"PUT":"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify(draft)});
     const p=await r.json();
     if(!r.ok)throw Error(typeof p.detail==="string"?p.detail:"Confira os campos do cadastro.");
     setItems(old=>[...old.filter(x=>x.id!==p.id),p]);setId(p.id);setEditing(false);setNotice("Cadastro salvo.");
   }catch(e){setError(e instanceof Error?e.message:"Erro ao salvar.");}finally{setBusy(false)}
 };
 const remove=async()=>{
   if(!current||current.builtin||busy)return;
   if(!window.confirm('Excluir o cadastro "'+current.name+'"? Esta exclusão não altera as peças técnicas já salvas.'))return;
   setBusy(true);setError("");setNotice("");
   try{
     const response=await fetch(getApiUrl()+"/technical-pieces/cartographic-catalog/"+encodeURIComponent(current.id),{method:"DELETE",credentials:"include"});
     const result=await response.json();
     if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Não foi possível excluir.");
     setItems(old=>old.filter(p=>p.id!==current.id));setId("");setEditing(false);
     setNotice("Cadastro excluído. Dados já incorporados às peças permanecem preservados.");
   }catch(e){setError(e instanceof Error?e.message:"Falha ao excluir.");}finally{setBusy(false)}
 };
 return <section className="pecas-card" style={{minWidth:0,whiteSpace:"normal",maxWidth:"100%",padding:16}}>
   <div style={{display:"flex",alignItems:"baseline",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
     <div><strong style={{fontSize:16}}>Bases cartográficas</strong><p style={{margin:"3px 0 10px",fontSize:12}}>Cadastre uma vez e reutilize os metadados e créditos em cada peça.</p></div>
     <button type="button" className="pecas-secondary" disabled={busy} onClick={()=>begin()}>+ Nova base</button>
   </div>
   <label className="pecas-field" style={{minWidth:0,marginBottom:8}}>
     <span>Base disponível</span>
     <select aria-label="Selecionar base cartográfica" value={current?.id??""} onChange={e=>{const next=items.find(p=>p.id===e.target.value);setId(e.target.value);setEditing(false);setError("");if(next&&onSelect){onSelect(next);setNotice("Base aplicada à peça; parâmetros técnicos específicos do raster continuam sujeitos à verificação.");}}} style={{width:"100%",maxWidth:"100%",minWidth:0,textOverflow:"ellipsis"}}>
       <option value="">Selecione uma base</option>
       {registered.map(p=><option key={p.id} value={p.id}>{p.name} · {p.product||"Produto não definido"}</option>)}
     </select>
   </label>
   {!registered.length&&!editing&&<p style={{fontSize:12}}>Nenhuma base particular cadastrada. Crie uma base ou utilize o modelo do Amapá.</p>}
   {current&&!editing&&<div style={{border:"1px solid #d4e3db",borderRadius:10,padding:12,background:"#f7faf8"}}>
     <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:8,flexWrap:"wrap"}}>
       <div style={{minWidth:0,flex:"1 1 230px"}}>
         <strong>{current.name}</strong>
         <p style={{margin:"4px 0",fontSize:12}}>{[current.producer,current.scale?(current.scale.includes(":")?current.scale:"1:"+Number(current.scale).toLocaleString("pt-BR")):"",current.horizontal_crs].filter(Boolean).join(" · ")}</p>
         <small>{current.builtin?"Referência geral do sistema":"Cadastro particular"} · Revisão {current.revision}</small>
       </div>
       <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
         
         {!current.builtin&&<button type="button" className="pecas-secondary" disabled={busy} onClick={()=>begin(current)}>Editar</button>}
         {!current.builtin&&<button type="button" className="pecas-secondary" disabled={busy} style={{color:"#ae4035"}} onClick={()=>void remove()}>Excluir</button>}
       </div>
     </div>
     <details style={{marginTop:10}}><summary style={{cursor:"pointer",fontWeight:600}}>Ver metadados e textos automáticos</summary>
       <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:"5px 16px",paddingTop:8}}>
         {fields.filter(([k])=>current[k]).map(([k,label])=><p key={k} style={{margin:"5px 0",overflowWrap:"anywhere",fontSize:12}}><strong>{label}:</strong> {current[k]}</p>)}
       </div>
     </details>
   </div>}
   {editing&&<div style={{borderTop:"1px solid #d4e3db",marginTop:12,paddingTop:10}}>
     <h4 style={{margin:"0 0 10px"}}>{editId?"Editar base cadastrada":"Cadastrar base"}</h4>
     {!editId&&template&&<button type="button" className="pecas-secondary" disabled={busy} onClick={()=>begin(template)}>Preencher com modelo do Amapá</button>}
     {groups.map((group,i)=><details key={group.title} open={i===0} style={{marginBottom:8,border:"1px solid #d4e3db",borderRadius:8,padding:"9px 12px"}}>
       <summary style={{cursor:"pointer",fontWeight:600}}>{group.title}</summary>
       <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))",gap:10,marginTop:10}}>
         {group.fields.map(([k,label])=><label key={k} className="pecas-field" style={{minWidth:0}}>
           <span>{label}</span>
           {multiline.has(k)?<textarea rows={3} value={draft[k]} onChange={e=>setDraft(o=>({...o,[k]:e.target.value}))}/>:
             <input value={draft[k]} onChange={e=>setDraft(o=>({...o,[k]:e.target.value}))}/>}
         </label>)}
       </div>
     </details>)}
     <p style={{fontSize:12}}>Créditos vazios serão gerados automaticamente. Uma referência cadastrada não equivale a comprovação de precisão para certificação.</p>
     <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
       <button type="button" className="pecas-primary" disabled={busy||!draft.name.trim()} onClick={()=>void save()}>{busy?"Salvando…":"Salvar cadastro"}</button>
       <button type="button" className="pecas-secondary" disabled={busy} onClick={()=>setEditing(false)}>Cancelar</button>
     </div>
   </div>}
   {notice&&<p role="status" style={{fontSize:12,color:"#185e4a",marginBottom:0}}>{notice}</p>}
   {error&&<p role="alert" style={{color:"#ae4035"}}>{error}</p>}
 </section>;
}
