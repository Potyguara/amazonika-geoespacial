"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type Vertex = { name: string; longitude: number; latitude: number };
type UploadedAsset = {
  kind: "raster" | "report"; sha256: string; size_bytes: number;
  metadata?: { width?: number; height?: number; crs_wkt?: string; crs_authority?: string | null;
    wgs84_extent?: { type: string; coordinates: number[][][] } };
};
type Evidence = {
  scene_id: string; report_scene_id: string;
  raster_sha256: string; report_sha256: string;
  orthorectification_rms_m: number;
  horizontal_positional_precision_m: number;
  gsd_m: number; scene_crs: string; feature_identifiable: boolean;
  validation_mode?: "LEGACY" | "DOCUMENTAL";
  report_page?: number | null;
  accuracy_source?: "RMS_ORTHORECTIFICATION" | "EXTERNAL_ACCURACY_REPORT" | null;
  report_metric_reference?: string | null;
};
type Submission = {
  needs_additional_vertices: boolean; evidence: Evidence | null;
  vertices: Array<{ vertex_id: string; longitude: number; latitude: number;
    limit_type: "natural"; feature_type: "natural_feature" }>;
};
type Ps4Record = {
  submission?: Submission;
  import_job_id?: string | null;
  assets?: Partial<Record<"raster" | "report", UploadedAsset>>;
  validation?: { status: string; blockers: string[]; message?: string };
  approval?: { approved_at: string; rt_name: string; art: string };
  source_provenance?: { provider: string; item_id: string; source_type: string;
    requires_rt_review: boolean; requires_orthorectification_report: boolean;
    technical_xml?: {
      status: string; asset_key?: string; sha256?: string; bytes?: number;
      candidate_field_names?: string[];
    } };
};
const reviewLabels = [
  ["report_scene_correspondence_checked", "O PDF identifica a mesma cena da ortoimagem"],
  ["orthorectification_rms_checked", "Conferi o RMS no relatório de ortorretificação"],
  ["positional_accuracy_checked", "Avaliei a precisão horizontal para o limite natural"],
  ["feature_identification_checked", "A feição natural está inequivocamente identificável"],
  ["source_resolution_checked", "Conferi resolução, origem e referencial da imagem"],
  ["technical_responsibility_accepted", "Assumo a responsabilidade técnica pela conferência"],
] as const;

type CheckKey = (typeof reviewLabels)[number][0];
const emptyChecks = () => Object.fromEntries(
  reviewLabels.map(([name]) => [name, false])
) as Record<CheckKey, boolean>;

export function Ps4EvidencePanel({
  pieceId, sceneId, vertices, rmsFromWorkspace, onApprovalChange, onRasterChange, onReportChange, onEnsurePieceSaved, onSceneChange, refreshRevision = 0,
}: {
  pieceId: string | null | undefined;
  refreshRevision?: number;
  onApprovalChange?: (approved: boolean) => void;
  onRasterChange?: (asset: UploadedAsset | null) => void;
  onReportChange?: (present: boolean) => void;
  onEnsurePieceSaved?: () => Promise<string>;
  onSceneChange?: (sceneId: string) => void;
  sceneId: string;
  vertices: Vertex[];
  rmsFromWorkspace: number | null;
}) {
  const [record, setRecord] = useState<Ps4Record>({});
  const [inpeJobStatus, setInpeJobStatus] = useState<{status:string;message:string}|null>(null);
  const [reportScene, setReportScene] = useState("");
  const [reportPage, setReportPage] = useState("");
  const [accuracySource, setAccuracySource] = useState<"RMS_ORTHORECTIFICATION" | "EXTERNAL_ACCURACY_REPORT">("RMS_ORTHORECTIFICATION");
  const [metricReference, setMetricReference] = useState("");
  const [precision, setPrecision] = useState("");
  const [gsd, setGsd] = useState("");
  const [crs, setCrs] = useState("");
  const [featureConfirmed, setFeatureConfirmed] = useState(false);
  const [checks, setChecks] = useState(emptyChecks);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let active = true;
    setRecord({});
    setNotice("");
    setDirty(false);
    setChecks(emptyChecks());
    if (!pieceId) return;
    void (async () => {
      try {
        const response = await fetch(
          `${getApiUrl()}/technical-pieces/${pieceId}/ps4`,
          { credentials: "include" },
        );
        if (!response.ok) throw new Error("Não foi possível recuperar as evidências PS4.");
        const saved: Ps4Record = await response.json();
        if (!active) return;
        setRecord(saved);
        const ev = saved.submission?.evidence;
        if (ev) {
          setReportScene(ev.report_scene_id);
          setReportPage(ev.report_page ? String(ev.report_page) : "");
          setAccuracySource(ev.accuracy_source ?? "RMS_ORTHORECTIFICATION");
          setMetricReference(ev.report_metric_reference ?? "");
          setPrecision(String(ev.horizontal_positional_precision_m));
          setGsd(String(ev.gsd_m));
          setCrs(ev.scene_crs);
          setFeatureConfirmed(ev.feature_identifiable);
        }
      } catch (error) {
        if (active) setNotice(error instanceof Error ? error.message : "Erro ao consultar PS4.");
      }
    })();
    return () => { active = false; };
  }, [pieceId, refreshRevision]);

  useEffect(() => {
    if (!pieceId || !record.import_job_id) return;
    let alive = true;
    let finished = false;
    const jobId = record.import_job_id;
    const check = async () => {
      if (finished || !alive) return;
      try {
        const response = await fetch(
          `${getApiUrl()}/technical-pieces/${pieceId}/ps4/inpe/jobs/${jobId}`,
          {credentials:"include",cache:"no-store"},
        );
        if (!response.ok) return;
        const payload = await response.json();
        if (!alive) return;
        const current = payload?.job;
        if (!current) return;
        setInpeJobStatus({status:String(current.status),message:String(current.message||"")});
        if (["READY", "FAILED", "CANCELLED"].includes(current.status)) {
          finished = true;
          if (current.status === "READY") {
            const restored = await fetch(
              `${getApiUrl()}/technical-pieces/${pieceId}/ps4`,
              {credentials:"include",cache:"no-store"},
            );
            if (restored.ok && alive) {
              const updated: Ps4Record = await restored.json();
              if (!alive) return;
              setRecord(updated);
              if (updated.assets?.raster?.metadata?.crs_authority) {
                setCrs(updated.assets.raster.metadata.crs_authority);
              }
            }
          }
        }
      } catch {
        // Falha de rede temporária: próxima consulta tenta novamente.
      }
    };
    void check();
    const interval = window.setInterval(() => void check(), 4000);
    return () => {alive=false;window.clearInterval(interval);};
  }, [pieceId, record.import_job_id]);

  const operation = async (callback: () => Promise<void>) => {
    if (!pieceId) { setNotice("Salve a peça técnica antes de anexar evidências."); return; }
    setBusy(true); setNotice("");
    try { await callback(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Falha no processamento PS4."); }
    finally { setBusy(false); }
  };

  const upload = (kind: "raster" | "report", file: File) => void operation(async () => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(
      `${getApiUrl()}/technical-pieces/${pieceId}/ps4/files/${kind}`,
      { method: "POST", body: form, credentials: "include" },
    );
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(
      typeof body?.detail === "string" ? body.detail : "Upload PS4 rejeitado."
    );
    setRecord(body.ps4);
    if (kind === "raster" && body.asset?.metadata?.crs_authority) {
      setCrs(body.asset.metadata.crs_authority);
    }
    setDirty(true);
    setChecks(emptyChecks());
    setNotice(kind === "raster"
      ? "GeoTIFF recebido, georreferenciamento inspecionado e hash registrado."
      : "Relatório PDF recebido e hash registrado. Conteúdo ainda depende da revisão técnica.");
  });

  const makeSubmission = (): Submission => {
    if (!record.assets?.raster || !record.assets?.report)
      throw new Error("Anexe a imagem GeoTIFF e o relatório PDF da ortorretificação.");
    const number = (s: string) => s.trim() === "" ? NaN : Number(s);
    const p = number(precision), g = number(gsd);
    if (!Number.isFinite(p) || p < 0 || !Number.isFinite(g) || g <= 0)
      throw new Error("Informe valores válidos para precisão horizontal e GSD.");
    if (rmsFromWorkspace === null || !Number.isFinite(rmsFromWorkspace) ||
        rmsFromWorkspace < 0)
      throw new Error("Informe o RMS documental da ortorretificação na seção anterior.");
    if (!reportScene.trim() || !crs.trim())
      throw new Error("Informe a cena identificada no relatório e o SRC.");
    const page = Number(reportPage);
    if (!Number.isSafeInteger(page) || page < 1 || !metricReference.trim())
      throw new Error("Informe a página e a seção/tabela do relatório que demonstram a precisão da cena.");
    if (vertices.length < 1)
      throw new Error("Ainda não existem vértices V para vincular à cena.");
    return {
      needs_additional_vertices: true,
      evidence: {
        scene_id: sceneId,
        report_scene_id: reportScene.trim(),
        raster_sha256: record.assets.raster.sha256,
        report_sha256: record.assets.report.sha256,
        orthorectification_rms_m: rmsFromWorkspace,
        horizontal_positional_precision_m: p,
        gsd_m: g,
        scene_crs: crs.trim(),
        feature_identifiable: featureConfirmed,
        validation_mode: "DOCUMENTAL",
        report_page: page,
        accuracy_source: accuracySource,
        report_metric_reference: metricReference.trim(),
      },
      vertices: vertices.map(p => ({
        vertex_id: p.name, longitude: p.longitude, latitude: p.latitude,
        limit_type: "natural" as const,
        feature_type: "natural_feature" as const,
      })),
    };
  };

  const save = () => void operation(async () => {
    // Guardar rascunhos de V sem simular evidências de precisão inexistentes.
    // Só o PUT PS4 validado exige o PDF, o RMS e a conferência do RT.
    if (!record.assets?.raster || !record.assets?.report) {
      if (!onEnsurePieceSaved) {
        throw new Error("Salve a peça técnica para guardar os vértices V provisórios.");
      }
      await onEnsurePieceSaved();
      setNotice("Vértices provisórios salvos no rascunho da peça. " +
        "Para validação PS4, anexe GeoTIFF, relatório PDF e comprove a precisão com revisão do RT.");
      return;
    }
    const submission = makeSubmission();
    const response = await fetch(
      `${getApiUrl()}/technical-pieces/${pieceId}/ps4`,
      {
        method: "PUT", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(submission),
      },
    );
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.detail ?? "Falha ao salvar evidências PS4.");
    setRecord(body.ps4);
    setDirty(false);
    setChecks(emptyChecks());
    setNotice("Evidências persistidas. Confira as pendências antes da aprovação do RT.");
  });

  const approve = () => void operation(async () => {
    if (!allChecks) throw new Error("Confira individualmente os seis requisitos técnicos.");
    const response = await fetch(
      `${getApiUrl()}/technical-pieces/${pieceId}/ps4/approve`,
      {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(checks),
      },
    );
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      throw new Error(
        typeof detail === "string" ? detail :
        detail?.blockers?.join(" ") ?? "A aprovação foi recusada."
      );
    }
    setRecord(body.ps4);
    setNotice("Revisão do RT registrada com identificação e trilha de auditoria.");
  });

  const reportKey = record.assets?.report?.sha256 ?? "";
  useEffect(() => {
    onReportChange?.(Boolean(reportKey));
    // Stable parent state callback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pieceId, reportKey]);
  const rasterAsset = record.assets?.raster ?? null;
  const rasterKey = rasterAsset?.sha256 ?? "";
  useEffect(() => {
    onRasterChange?.(rasterAsset);
    // Ref remains owned by parent; notify only when actual raster changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pieceId, rasterKey]);
  const saved = record.submission;
  const currentMatches = Boolean(
    saved?.needs_additional_vertices &&
    saved.evidence?.scene_id === sceneId &&
    saved.vertices.length === vertices.length &&
    vertices.every((point, index) => (
      saved.vertices[index]?.vertex_id === point.name &&
      saved.vertices[index]?.longitude === point.longitude &&
      saved.vertices[index]?.latitude === point.latitude
    )) &&
    saved.evidence?.orthorectification_rms_m === rmsFromWorkspace &&
    saved.evidence?.report_scene_id === reportScene.trim() &&
    saved.evidence?.horizontal_positional_precision_m === Number(precision) &&
    saved.evidence?.gsd_m === Number(gsd) &&
    saved.evidence?.scene_crs === crs.trim() &&
    saved.evidence?.feature_identifiable === featureConfirmed &&
    saved.evidence?.validation_mode === "DOCUMENTAL" &&
    saved.evidence?.report_page === Number(reportPage) &&
    saved.evidence?.accuracy_source === accuracySource &&
    saved.evidence?.report_metric_reference === metricReference.trim() &&
    saved.evidence?.raster_sha256 === record.assets?.raster?.sha256 &&
    saved.evidence?.report_sha256 === record.assets?.report?.sha256
  );
  const allChecks = reviewLabels.every(([key]) => checks[key]);
  const status = dirty || !currentMatches
    ? "ALTERADO — SALVE NOVAMENTE"
    : record.validation?.status ?? "PENDENTE";
  const canApprove = !dirty && currentMatches &&
    status === "REVIEW_REQUIRED" && allChecks;
  useEffect(() => {
    onApprovalChange?.(status === "APPROVED_BY_RT");
    // Reavaliar apenas quando a aprovação efetivamente muda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);
  return (
    <section className="pecas-card" aria-label="Evidências oficiais PS4"
      style={{ display: "grid", gap: 12, marginTop: 16 }}>
      <h4>PS4 — Validação documental da cena (sem pontos GNSS próprios)</h4>
      <div className="geo96-next-step" role="status">
        <strong>Modalidade DOCUMENTAL — pontos próprios opcionais</strong>
        <p>Utiliza o GeoTIFF já vinculado à peça e o relatório técnico da mesma cena.
          Não exige pontos GNSS de checagem próprios, mas exige RMS/avaliação de
          acurácia rastreável no documento e conferência do responsável técnico.
          XML STAC e GSD não constituem prova de precisão.</p>
      </div>
      <p className="pecas-note">A conferência documental exige identificar página, fonte e seção da métrica de precisão.
        O preenchimento não comprova por si só o conteúdo do PDF. É possível desenhar e salvar vértices V provisórios antes de anexar
        GeoTIFF e relatório PDF. Esses documentos, a precisão absoluta demonstrada e a revisão
        do RT continuam obrigatórios para VALIDAR PS4. Hash e GSD não comprovam acurácia.</p>
      {inpeJobStatus && <p role="status" className="pecas-note">
        Recorte INPE: {inpeJobStatus.status} · {inpeJobStatus.message}
      </p>}
      {record.source_provenance && <p className="pecas-note" role="status">
        Fonte: {record.source_provenance.provider} ·
        Cena: {record.source_provenance.item_id} ·
        Recorte georreferenciado importado automaticamente do catálogo STAC.
        O recorte NÃO comprova RMS, precisão absoluta ou aptidão PS4.
        O relatório técnico e a conferência do RT continuam obrigatórios.
      </p>}
      {record.source_provenance?.technical_xml?.status === "ARCHIVED_UNVERIFIED" && (
        <div className="pecas-note">
          <p>Metadados técnicos XML oficiais do INPE arquivados com SHA-256.
          Documento de origem, não comprovante automático de precisão absoluta.</p>
          {Boolean(record.source_provenance.technical_xml.candidate_field_names?.length) && (
            <p>Campos para conferência do RT: {
              record.source_provenance.technical_xml.candidate_field_names?.join(", ")
            }.</p>
          )}
          <button type="button" className="pecas-secondary" disabled={!pieceId || busy}
            onClick={() => void operation(async () => {
              const response = await fetch(
                `${getApiUrl()}/technical-pieces/${pieceId}/ps4/inpe/metadata.xml`,
                { credentials: "include", cache: "no-store" },
              );
              if (!response.ok) throw new Error("XML oficial não disponível.");
              const blob = await response.blob();
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement("a");
              anchor.href = url; anchor.download = "CBERS_INPE_metadados.xml";
              document.body.append(anchor); anchor.click(); anchor.remove();
              window.setTimeout(() => URL.revokeObjectURL(url), 1500);
            })}>
            Baixar metadados XML oficiais
          </button>
        </div>
      )}
      {!pieceId && <div className="pecas-warning" role="status">
        <p>Salve a peça técnica sem sair desta tela para habilitar os anexos.</p>
        <button type="button" className="pecas-primary"
          disabled={busy || !onEnsurePieceSaved}
          onClick={() => void (async () => {
            if (!onEnsurePieceSaved) return;
            setBusy(true); setNotice("");
            try {
              await onEnsurePieceSaved();
              setNotice("Peça salva no servidor. Importe o GeoTIFF e o relatório PDF.");
            } catch (error) {
              setNotice(error instanceof Error ? error.message : "Falha ao salvar a peça.");
            } finally { setBusy(false); }
          })()}>
          Salvar peça e continuar no PS4
        </button>
      </div>}
      <label className="pecas-field">
        <span>Imagem orbital ortorretificada (GeoTIFF, até 256 MB)</span>
        <input type="file" accept=".tif,.tiff,image/tiff"
          disabled={!pieceId || busy}
          onChange={e => {
            const file = e.currentTarget.files?.[0];
            if (file) upload("raster", file);
            e.currentTarget.value = "";
          }} />
      </label>
      {record.assets?.raster && <p className="pecas-note">
        GeoTIFF registrado · {record.assets.raster.size_bytes.toLocaleString("pt-BR")} bytes ·
        {record.assets.raster.metadata?.width} × {record.assets.raster.metadata?.height} pixels ·
        SHA-256: {record.assets.raster.sha256.slice(0, 16)}…
      </p>}
      <label className="pecas-field">
        <span>Relatório de ortorretificação da mesma cena (PDF, até 25 MB)</span>
        <input type="file" accept=".pdf,application/pdf"
          disabled={!pieceId || busy}
          onChange={e => {
            const file = e.currentTarget.files?.[0];
            if (file) upload("report", file);
            e.currentTarget.value = "";
          }} />
      </label>
      {record.assets?.report && <p className="pecas-note">
        PDF registrado · SHA-256: {record.assets.report.sha256.slice(0, 16)}…
      </p>}
      <label className="pecas-field"><span>Identificador da cena conforme o relatório</span>
        <input value={reportScene} onChange={e => {
          setReportScene(e.target.value); setDirty(true);
        }} placeholder="Identificador que consta efetivamente no PDF" />
        <button type="button" className="pecas-secondary"
          disabled={busy || !reportScene.trim() || reportScene.trim() === sceneId}
          onClick={() => onSceneChange?.(reportScene.trim())}>
          Vincular esta cena à ortoimagem e ao mapa
        </button>
        {reportScene.trim() !== sceneId && <small role="status">
          A cena do mapa ainda é {sceneId}. Vincule a identificação do relatório
          antes de criar ou validar os vértices.
        </small>}
      </label>
      <label className="pecas-field"><span>Página do PDF que comprova a métrica</span>
        <input type="number" min="1" step="1" value={reportPage}
          placeholder="Ex.: 12"
          onChange={e => {setReportPage(e.target.value);setDirty(true);}} />
      </label>
      <label className="pecas-field"><span>Origem da precisão declarada</span>
        <select value={accuracySource}
          onChange={e => {setAccuracySource(e.target.value as typeof accuracySource);setDirty(true);}}>
          <option value="RMS_ORTHORECTIFICATION">RMS do processo de ortorretificação</option>
          <option value="EXTERNAL_ACCURACY_REPORT">Avaliação externa independente documentada</option>
        </select>
      </label>
      <label className="pecas-field"><span>Tabela / seção exata do documento</span>
        <input value={metricReference}
          placeholder="Ex.: Tabela 4 — RMS horizontal, cena ..."
          onChange={e => {setMetricReference(e.target.value);setDirty(true);}} />
      </label>
      <label className="pecas-field"><span>Precisão posicional horizontal avaliada (m)</span>
        <input type="number" min="0" step="0.001" value={precision}
          onChange={e => { setPrecision(e.target.value); setDirty(true); }} /></label>
      <label className="pecas-field"><span>GSD da ortoimagem (m/pixel)</span>
        <input type="number" min="0" step="0.01" value={gsd}
          onChange={e => { setGsd(e.target.value); setDirty(true); }} /></label>
      <label className="pecas-field"><span>SRC declarado (ex.: EPSG:31982)</span>
        <input value={crs} onChange={e => { setCrs(e.target.value); setDirty(true); }} /></label>
      <label className="pecas-check">
        <input type="checkbox" checked={featureConfirmed}
          onChange={e => { setFeatureConfirmed(e.target.checked); setDirty(true); }}/>
        Confirmo que os V representam feição natural inequívoca, não cerca ou mudança de confrontação
      </label>
      <p className="pecas-note">
        Vértices vinculados: {vertices.length} · Cena selecionada: {sceneId} ·
        RMS informado na seção anterior: {rmsFromWorkspace ?? "não informado"} m.
      </p>
      <button type="button" className="pecas-primary" disabled={!pieceId || busy}
        onClick={save}>{!record.assets?.raster || !record.assets?.report
          ? "Salvar rascunho V (validação pendente)" : "Salvar e validar evidências PS4"}</button>
      <div role="status" className={status === "APPROVED_BY_RT" ? "geo96-next-step" : "pecas-note"}>
        <strong>Resultado: {status}</strong>
        <p>{record.validation?.message ?? "Aguardando importação e validação."}</p>
        {record.validation?.blockers?.map((item, index) => (
          <p key={index}>• {item}</p>
        ))}
      </div>
      {status === "REVIEW_REQUIRED" && <>
        <h4>Conferência e aprovação do responsável técnico</h4>
        {reviewLabels.map(([key, label]) => <label className="pecas-check" key={key}>
          <input type="checkbox" checked={checks[key]} onChange={e =>
            setChecks(old => ({ ...old, [key]: e.target.checked }))} />
          {label}
        </label>)}
        <button type="button" className="pecas-primary" disabled={!canApprove || busy}
          onClick={approve}>Registrar conferência do RT e concluir PS4</button>
      </>}
      {record.approval && status === "APPROVED_BY_RT" && <p className="geo96-next-step">
        Responsável: {record.approval.rt_name} · ART: {record.approval.art} ·
        Revisão registrada em {new Date(record.approval.approved_at).toLocaleString("pt-BR")}.
      </p>}
      {notice && <p role="status" className="pecas-note">{notice}</p>}
    </section>
  );
}
