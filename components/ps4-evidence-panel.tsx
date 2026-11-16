"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type Vertex = { name: string; longitude: number; latitude: number };
type UploadedAsset = {
  kind: "raster" | "report"; sha256: string; size_bytes: number;
  metadata?: { width?: number; height?: number; crs_wkt?: string;
    wgs84_extent?: { type: string; coordinates: number[][][] } };
};
type Evidence = {
  scene_id: string; report_scene_id: string;
  raster_sha256: string; report_sha256: string;
  orthorectification_rms_m: number;
  horizontal_positional_precision_m: number;
  gsd_m: number; scene_crs: string; feature_identifiable: boolean;
};
type Submission = {
  needs_additional_vertices: boolean; evidence: Evidence | null;
  vertices: Array<{ vertex_id: string; longitude: number; latitude: number;
    limit_type: "natural"; feature_type: "natural_feature" }>;
};
type Ps4Record = {
  submission?: Submission;
  assets?: Partial<Record<"raster" | "report", UploadedAsset>>;
  validation?: { status: string; blockers: string[]; message?: string };
  approval?: { approved_at: string; rt_name: string; art: string };
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
  pieceId, sceneId, vertices, rmsFromWorkspace, onApprovalChange, onRasterChange, onReportChange, onEnsurePieceSaved, onSceneChange,
}: {
  pieceId: string | null | undefined;
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
  const [reportScene, setReportScene] = useState("");
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
  }, [pieceId]);

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
      },
      vertices: vertices.map(p => ({
        vertex_id: p.name, longitude: p.longitude, latitude: p.latitude,
        limit_type: "natural" as const,
        feature_type: "natural_feature" as const,
      })),
    };
  };

  const save = () => void operation(async () => {
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
      <h4>PS4 — Imagem orbital e comprovação documental</h4>
      <p className="pecas-note">Somente GeoTIFF ortorretificado e relatório PDF correspondente.
        A verificação de hash e metadados não substitui o exame da acurácia pelo RT.</p>
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
        onClick={save}>Salvar e validar evidências PS4</button>
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
