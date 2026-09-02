"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { getApiUrl } from "@/lib/api";
import { Archive, CheckCircle2, Clock3, Database, FileArchive, HardDriveUpload, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";

const API_URL = getApiUrl();

type Source = { id:string; slug:string; name:string; institution:string; kind:string; is_official:boolean; update_frequency:string|null };
export type SourceVersion = { id:string; source_id:string; reference_date:string|null; imported_at:string|null; feature_count:number; status:string; is_current:boolean; original_filename:string|null; checksum:string|null; error_message:string|null };

interface SigefModuleProps {
  onVersionChanged?: (version: SourceVersion) => void;
}

function formatDate(value: string | null) {
  if (!value) return "Sem data";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function SigefModule({ onVersionChanged }: SigefModuleProps) {
  const [sources, setSources] = useState<Source[]>([]);
  const [versions, setVersions] = useState<SourceVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [activating, setActivating] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [referenceDate, setReferenceDate] = useState(new Date().toISOString().slice(0,10));
  const [layerName, setLayerName] = useState("");
  const [message, setMessage] = useState<{kind:"success"|"error";text:string}|null>(null);

  const sigefSource = useMemo(() => sources.find((source) => source.slug === "sigef-interno"), [sources]);
  const officialSource = useMemo(() => sources.find((source) => source.slug === "incra-fundiario"), [sources]);
  const currentVersion = useMemo(() => versions.find((version) => version.is_current) ?? null, [versions]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const sourceResponse = await fetch(`${API_URL}/sources`);
      if (!sourceResponse.ok) throw new Error("Não foi possível consultar as fontes cadastradas.");
      const loadedSources: Source[] = await sourceResponse.json();
      setSources(loadedSources);
      const sigef = loadedSources.find((source) => source.slug === "sigef-interno");
      if (!sigef) throw new Error("A fonte SIGEF interno não está cadastrada. Execute a carga inicial do catálogo.");
      const versionResponse = await fetch(`${API_URL}/sources/${sigef.id}/versions`);
      if (!versionResponse.ok) throw new Error("Não foi possível consultar o histórico do SIGEF.");
      setVersions(await versionResponse.json());
    } catch (error) {
      setMessage({kind:"error",text:error instanceof Error?error.message:"Falha ao carregar o módulo SIGEF."});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!sigefSource || !file) return;
    setUploading(true); setMessage(null);
    const data = new FormData();
    data.append("file",file);
    data.append("reference_date",referenceDate);
    if (layerName.trim()) data.append("layer_name",layerName.trim());
    try {
      const response = await fetch(`${API_URL}/sources/${sigefSource.id}/imports/geopackage`,{method:"POST",body:data});
      const body = await response.json().catch(()=>null);
      if (!response.ok) throw new Error(body?.detail??"Falha ao importar o GeoPackage.");
      setMessage({kind:"success",text:`Carga concluída: ${formatNumber(body.feature_count)} parcelas importadas e ativadas.`});
      setFile(null); setLayerName("");
      onVersionChanged?.(body);
      await load();
    } catch (error) {
      setMessage({kind:"error",text:error instanceof Error?error.message:"Falha inesperada durante a importação."});
    } finally {
      setUploading(false);
    }
  };

  const activate = async (version: SourceVersion) => {
    if (!sigefSource || version.is_current) return;
    setActivating(version.id); setMessage(null);
    try {
      const response=await fetch(`${API_URL}/sources/${sigefSource.id}/versions/${version.id}/activate`,{method:"POST"});
      const body=await response.json().catch(()=>null);
      if (!response.ok) throw new Error(body?.detail??"Não foi possível ativar esta versão.");
      setMessage({kind:"success",text:`A carga de ${formatDate(version.reference_date)} voltou a ser a versão ativa.`});
      onVersionChanged?.(body);
      await load();
    } catch(error) {
      setMessage({kind:"error",text:error instanceof Error?error.message:"Falha ao ativar a versão."});
    } finally { setActivating(null); }
  };

  return <section className="sigef-module">
    <div className="sigef-hero">
      <div><p className="eyebrow">GESTÃO DO ACERVO INTERNO</p><h2>Módulo SIGEF</h2><p>Controle mensal das parcelas utilizadas nas consultas de sobreposição, com histórico e rastreabilidade das cargas.</p></div>
      <Button className="sigef-refresh" onClick={()=>void load()} disabled={loading}><RefreshCw size={16} className={loading?"spin":""}/> Atualizar</Button>
    </div>

    <div className="sigef-summary">
      <article><span className="status-icon blue"><Database size={19}/></span><div><small>VERSÃO ATIVA</small><strong>{currentVersion?formatDate(currentVersion.reference_date):"Sem carga"}</strong></div></article>
      <article><span className="status-icon green"><FileArchive size={19}/></span><div><small>PARCELAS ATIVAS</small><strong>{currentVersion?formatNumber(currentVersion.feature_count):"0"}</strong></div></article>
      <article><span className="status-icon amber"><Archive size={19}/></span><div><small>VERSÕES ARMAZENADAS</small><strong>{formatNumber(versions.length)}</strong></div></article>
      <article><span className="status-icon green"><ShieldCheck size={19}/></span><div><small>USO NAS ANÁLISES</small><strong>{currentVersion?"Habilitado":"Aguardando carga"}</strong></div></article>
    </div>

    {message&&<div className={`sigef-message ${message.kind}`}>{message.kind==="success"?<CheckCircle2 size={18}/>:<TriangleAlert size={18}/>}<span>{message.text}</span></div>}

    <div className="sigef-grid">
      <form className="sigef-upload-card" onSubmit={upload}>
        <div className="sigef-card-title"><span><HardDriveUpload size={20}/></span><div><small>NOVA ATUALIZAÇÃO</small><h3>Importar GeoPackage mensal</h3></div></div>
        <p>O arquivo será validado, convertido para SIRGAS 2000 e somente substituirá a versão atual após a conclusão integral da importação.</p>
        <label className="sigef-file-drop"><HardDriveUpload size={25}/><strong>{file?file.name:"Selecionar arquivo .gpkg"}</strong><small>{file?`${(file.size/1024/1024).toFixed(2)} MB`:"GeoPackage contendo as parcelas do SIGEF"}</small><input type="file" accept=".gpkg,application/geopackage+sqlite3" onChange={(event)=>setFile(event.target.files?.[0]??null)}/></label>
        <div className="sigef-form-row"><label><span>Data de referência *</span><input type="date" required value={referenceDate} onChange={(event)=>setReferenceDate(event.target.value)}/></label><label><span>Nome da camada</span><input placeholder="Automático" value={layerName} onChange={(event)=>setLayerName(event.target.value)}/></label></div>
        <Button className="sigef-upload-button" type="submit" disabled={!file||!sigefSource||uploading}>{uploading?<><RefreshCw size={16} className="spin"/> Importando parcelas…</>:<><HardDriveUpload size={16}/> Importar e ativar versão</>}</Button>
      </form>

      <aside className="sigef-official-card">
        <div className="sigef-card-title"><span><ShieldCheck size={20}/></span><div><small>CAMADA SEPARADA</small><h3>INCRA Fundiário oficial</h3></div></div>
        <div className="official-source-state"><i/><div><strong>{officialSource?"Fonte cadastrada":"Fonte não cadastrada"}</strong><small>{officialSource?`${officialSource.institution} · ${officialSource.update_frequency??"Conforme publicação"}`:"Execute a carga inicial do catálogo"}</small></div></div>
        <p>Esta camada permanece independente da base SIGEF mensal. Quando houver uma publicação oficial disponível, ela poderá ser atualizada sem alterar o histórico interno.</p>
        <ul><li>Identificação visual própria no mapa</li><li>Participação independente nas análises</li><li>Metadados e referência da publicação oficial</li></ul>
      </aside>
    </div>

    <div className="sigef-history-card">
      <div className="sigef-history-heading"><div><small>RASTREABILIDADE</small><h3>Histórico de versões</h3></div><span>{versions.length} carga{versions.length===1?"":"s"}</span></div>
      {loading?<div className="sigef-empty"><RefreshCw size={20} className="spin"/> Consultando histórico…</div>:versions.length===0?<div className="sigef-empty"><Clock3 size={21}/> Nenhuma carga mensal realizada.</div>:<div className="sigef-table-wrap"><table><thead><tr><th>Referência</th><th>Arquivo</th><th>Importação</th><th>Feições</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{versions.map((version)=><tr key={version.id}><td><strong>{formatDate(version.reference_date)}</strong></td><td title={version.original_filename??""}>{version.original_filename??"—"}</td><td>{formatDateTime(version.imported_at)}</td><td>{formatNumber(version.feature_count)}</td><td><span className={`version-status ${version.status.toLowerCase()} ${version.is_current?"current":""}`}>{version.is_current?"ATIVA":version.status==="READY"?"ARQUIVADA":version.status}</span></td><td>{version.status==="READY"&&!version.is_current?<button className="activate-version" onClick={()=>void activate(version)} disabled={activating===version.id}>{activating===version.id?"Ativando…":"Tornar ativa"}</button>:<span className="no-action">—</span>}</td></tr>)}</tbody></table></div>}
    </div>
  </section>;
}
