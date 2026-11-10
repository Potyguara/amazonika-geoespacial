"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Download, FileText, Map, X } from "lucide-react";
import { SituationMapPreview, type SituationSnapshot } from "@/components/situation-map-preview";
import { getApiUrl } from "@/lib/api";

export type ProfessionalDocumentProfile = {
  full_name: string;
  rg: string;
  cpf: string;
  profession: string;
  specialization: string;
  crea: string;
  visto: string;
  incra_code: string;
  art: string;
};

export const PLANT_OPTIONS = [
  ["title", "Título e identificação da planta"],
  ["grid", "Grade UTM georreferenciada"],
  ["north", "Seta do norte / orientação"],
  ["scale_text", "Escala numérica (1:...)"],
  ["scale_bar", "Escala gráfica"],
  ["vertex_labels", "Rótulos dos vértices"],
  ["azimuths", "Azimutes dos segmentos"],
  ["distances", "Distâncias dos segmentos"],
  ["confrontants", "Rótulos de confrontantes"],
  ["coordinates", "Quadro de coordenadas"],
  ["situation", "Planta de situação"],
  ["technical_stamp", "Carimbo do responsável técnico"],
  ["magnetic_declination", "Declinação magnética (WMM2025 automática ou manual)"],
] as const;
export type PlantElementKey = (typeof PLANT_OPTIONS)[number][0];
export type PlantElementFlags = Record<PlantElementKey, boolean>;
export const DEFAULT_PLANT_ELEMENTS: PlantElementFlags = {
  title: true, grid: true, north: true, scale_text: true,
  scale_bar: false, vertex_labels: true, azimuths: true,
  distances: true, confrontants: true, coordinates: true,
  situation: true, technical_stamp: true, magnetic_declination: true,
};

export type PecasPolygon = {
  id: string;
  name: string;
  vertices: string[];
  confrontants: string[];
  altitudes: string[];
  vertexDetails?: Array<Record<string, unknown>>;
  areaHa: number;
  perimeterM: number;
};

export type PecasData = {
  title: string;
  plantHeading: string;
  memorialHeading: string;
  owner: string;
  rg: string;
  cpf: string;
  address: string;
  croqui: boolean;
  format: "A4" | "A3" | "A2" | "A1" | "A0";
  orientation: "paisagem" | "retrato";
  layoutTemplate: "lateral" | "inferior" | "classic_lateral" | "cartographic_frame" | "modern_lateral";
  scale: string;
  customScale: string;
};

type TopconPoint = {
  name: string;
  northing_m: number;
  easting_m: number;
  elevation_reported_m: number;
  latitude: number | null;
  longitude: number | null;
  sigma_n_m: number | null;
  sigma_e_m: number | null;
  sigma_hz_m: number | null;
  sigma_u_m: number | null;
  point_role: "CONTROL" | "UNCLASSIFIED";
};
type TopconPreview = {
  source: "TOPCON_TOOLS";
  filename: string;
  project: Record<string, string | number | null>;
  points: TopconPoint[];
  point_count: number;
  solution: Array<{
    baseline: string; distance_m: number; solution_type: string;
    orbit: string; pdop: number; hdop: number; vdop: number;
  }>;
  sessions: Array<{
    point: string; started_at_reported: string; ended_at_reported: string;
    duration: string; method: string; antenna: string; interval_ms: string;
  }>;
  checks: { errors: string[]; warnings: string[] };
  ready_for_sigef: false;
};

type Props = {
  open: boolean;
  onClose: () => void;
  data: PecasData;
  onDataChange: (key: keyof PecasData, value: string | boolean) => void;
  polygons: PecasPolygon[];
  importedMetadata?: Record<string, string> | null;
  selectedIds: string[];
  rasterKey: string;
  onSelect: (id: string, checked: boolean) => void;
  onRenamePolygon: (id: string, name: string) => void;
  onRenameVertex: (id: string, index: number, name: string) => void;
  onConfrontant: (id: string, index: number, value: string) => void;
  memorialText: string;
  memorialLoading: boolean;
  externalError?: string | null;
  onGenerateMemorial: () => Promise<void>;
  onBuildPdf: () => Promise<Blob>;
  onDownloadDocx: () => Promise<void>;
  onExportPolygon: (id: string, format: "txt" | "kml" | "shp") => Promise<void>;
  onDownloadSigef: () => Promise<void>;
  sigefAvailable: boolean;
  rtProfile: ProfessionalDocumentProfile | null;
  rtLoading: boolean;
  rtError: string;
  onRtChange: (key: keyof ProfessionalDocumentProfile, value: string) => void;
  onRtReload: () => void;
  situationGeometry: Record<string, unknown>;
  situationKey: string;
  situationSaved: SituationSnapshot | null;
  onSaveSituation: (snapshot: SituationSnapshot) => void;
  elements: PlantElementFlags;
  onToggleElement: (key: PlantElementKey, checked: boolean) => void;
  declination: string;
  onDeclinationChange: (value: string) => void;
  surveyDate: string;
  onSurveyDateChange: (value: string) => void;
  onSavePiece: (memorialDraft: string) => Promise<void>;
  onSaveMemorial: (text: string | null) => void;
  loadedMemorialDraft?: string | null;
  loadedPieceId?: string | null;
};

const stages = ["Dados do imóvel", "Áreas e vértices", "Memorial", "Planta", "Exportar"];

const fileSlug = (value: string) => value.trim().replace(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 80) || "imovel";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 3000);
}

export function PecasTecnicasWorkspace({
  open, onClose, data, onDataChange, polygons, importedMetadata, selectedIds, rasterKey, onSelect,
  onRenamePolygon, onRenameVertex, onConfrontant, memorialText,
  memorialLoading, externalError, onGenerateMemorial, onBuildPdf, onDownloadDocx,
  onExportPolygon, onDownloadSigef, sigefAvailable,
  rtProfile, rtLoading, rtError, onRtChange, onRtReload,
  situationGeometry, situationKey, situationSaved, onSaveSituation,
  elements, onToggleElement, declination, onDeclinationChange,
  surveyDate, onSurveyDateChange,
  onSavePiece, onSaveMemorial, loadedMemorialDraft, loadedPieceId,
}: Props) {
  const [stage, setStage] = useState(0);
  const [topconPreview, setTopconPreview] = useState<TopconPreview | null>(null);
  const [topconLoading, setTopconLoading] = useState(false);
  const [topconError, setTopconError] = useState("");
  const importTopcon = async (file: File) => {
    setTopconError("");
    setTopconPreview(null);
    setTopconLoading(true);
    try {
      const payload = new FormData();
      payload.append("file", file);
      const response = await fetch(`${getApiUrl()}/technical-pieces/import-topcon`, {
        method: "POST", credentials: "include", body: payload,
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(typeof result?.detail === "string"
          ? result.detail : "Relatório TOPCON não pôde ser interpretado.");
      }
      setTopconPreview(result as TopconPreview);
    } catch (error) {
      setTopconError(error instanceof Error ? error.message : "Falha ao ler relatório TOPCON.");
    } finally {
      setTopconLoading(false);
    }
  };
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [editableMemorial, setEditableMemorial] = useState("");
  const [memorialSaved, setMemorialSaved] = useState(false);
  const [memorialDirty, setMemorialDirty] = useState(false);
  const memorialSavingRef = useRef(false);
  const [savedPieceNotice, setSavedPieceNotice] = useState("");
  useEffect(() => {
    if (!loadedPieceId || loadedMemorialDraft == null) return;
    setEditableMemorial(loadedMemorialDraft);
    setMemorialDirty(true);
    setMemorialSaved(true);
    setStage(0);
    setPdfBlob(null);
    setPdfUrl(null);
    lastPdfKey.current = "";
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, [loadedPieceId, loadedMemorialDraft]);
  const lastPdfKey = useRef("");
  const urlRef = useRef<string | null>(null);
  const memorialCallbackRef = useRef(onGenerateMemorial);
  const pdfCallbackRef = useRef(onBuildPdf);
  memorialCallbackRef.current = onGenerateMemorial;
  pdfCallbackRef.current = onBuildPdf;

  const chosen = polygons.filter((polygon) => selectedIds.includes(polygon.id));
  const commonKey = JSON.stringify({
    selected: selectedIds,
    polygons: chosen,
    title: data.title, plantHeading: data.plantHeading,
    memorialHeading: data.memorialHeading, owner: data.owner,
    rg: data.rg, cpf: data.cpf, address: data.address, croqui: data.croqui, rtProfile,
  });
  const pdfKey = JSON.stringify({
    commonKey, format: data.format, orientation: data.orientation,
    scale: data.scale, customScale: data.customScale, layoutTemplate: data.layoutTemplate, rasterKey, elements, declination, surveyDate, situationKey, situationToken: situationSaved?.token, memorialRevision: memorialSaved ? editableMemorial : null,
  });
  const pdfReady = Boolean(pdfBlob && lastPdfKey.current === pdfKey);

  // Nenhuma mudança de configuração, etapa ou geometria dispara geração.
  // A referência da revisão é capturada antes da chamada e conferida ao fim.
  const handleGeneratePlantAndMemorial = async () => {
    if (!chosen.length || pdfBusy) return;
    const requestedKey = pdfKey;
    setPdfBusy(true);
    setPdfError("");
    try {
      const blob = await pdfCallbackRef.current();
      const url = URL.createObjectURL(blob);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = url;
      setPdfBlob(blob);
      setPdfUrl(url);
      lastPdfKey.current = requestedKey;
    } catch (error) {
      setPdfError(error instanceof Error
        ? error.message : "Falha ao gerar planta e memorial.");
    } finally {
      setPdfBusy(false);
    }
  };

  useEffect(() => () => {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
  }, []);

  useEffect(() => {
    // O texto automático nunca substitui uma revisão salva pelo usuário.
    if (memorialDirty || memorialSaved || memorialSavingRef.current) return;
    setEditableMemorial(memorialText);
  }, [memorialText, memorialDirty, memorialSaved]);

  if (!open) return null;

  const field = (label: string, key: keyof PecasData, placeholder = "") => (
    <label className="pecas-field" key={key}>
      <span>{label}</span>
      <input value={String(data[key])} placeholder={placeholder}
        onChange={(event) => onDataChange(key, event.target.value)} />
    </label>
  );

  const runAction = async (fn: () => Promise<void>) => {
    setActionError("");
    setActionBusy(true);
    try {
      await fn();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Falha na exportação.");
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <section className="pecas-workspace" aria-label="Elaboração de peças técnicas">
      <header className="pecas-header">
        <div>
          <small>AMAZÔNIKA GEOESPACIAL</small>
          <h2>Elaboração de peças técnicas</h2>
          <p>Planta georreferenciada e memorial descritivo — uma única área de trabalho.</p>
        </div>
        <button className="pecas-return" type="button" onClick={onClose}>
          <X size={17} /> Voltar ao mapa
        </button>
      </header>
      <nav className="pecas-stepper" aria-label="Etapas de elaboração">
        {stages.map((name, index) => (
          <button type="button" key={name} aria-current={index === stage ? "step" : undefined}
            className={index === stage ? "active" : index < stage ? "done" : ""}
            onClick={() => setStage(index)}
            disabled={(index > 1 && selectedIds.length === 0) || (index === 4 && !pdfReady)}
          >
            <span className="pecas-step-number">{index < stage ? <Check size={14} /> : index + 1}</span>
            {name}
          </button>
        ))}
      </nav>
      <main className="pecas-main">
        {stage === 0 && (
          <div className="pecas-data-layout">
            <div className="pecas-card">
              <h3>1. Identificação do imóvel</h3>
              <p>As informações abaixo compõem a planta e o memorial. As correções do responsável técnico valem somente para esta peça.</p>
              <div className="pecas-card" aria-label="Pré-validação do processamento TOPCON Tools">
                <h4>Importar processamento GNSS — TOPCON Tools</h4>
                <p>Arquivo HTML/HTM, XLSX ou PDF textual. Extração preliminar dos pontos e das precisões; a importação não converte automaticamente estações de controle em vértices SIGEF.</p>
                <input
                  type="file"
                  accept=".html,.htm,.xlsx,.pdf"
                  aria-label="Selecionar relatório TOPCON Tools"
                  disabled={topconLoading}
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    if (file) void importTopcon(file);
                    event.currentTarget.value = "";
                  }}
                />
                {topconLoading && <p role="status">Interpretando relatório de processamento...</p>}
                {topconError && <p className="pecas-warning" role="alert">{topconError}</p>}
                {topconPreview && (
                  <div>
                    <p><strong>{topconPreview.point_count} pontos extraídos</strong> de {topconPreview.filename}.
                      Referencial: {topconPreview.project.datum || "não identificado"};
                      projeção: {topconPreview.project.projection || "não identificada"}.</p>
                    <p><strong>Pré-validação:</strong> {topconPreview.checks.errors.length} erro(s)
                      e {topconPreview.checks.warnings.length} ressalva(s).
                      A geração ODS dependerá da classificação dos vértices,
                      confrontações, altura elipsoidal e revisão pelo responsável técnico.</p>
                    {topconPreview.checks.errors.map((message, index) => (
                      <p key={index} className="pecas-warning" role="alert">{message}</p>
                    ))}
                    {topconPreview.checks.warnings.map((message, index) => (
                      <p key={index} className="pecas-note">{message}</p>
                    ))}
                    <div style={{ overflowX: "auto" }}>
                      <table>
                        <thead><tr><th>Ponto TOPCON</th><th>N (m)</th><th>E (m)</th>
                          <th>Elevação informada (m)</th><th>σ horizontal (m)</th><th>Função</th></tr></thead>
                        <tbody>
                          {topconPreview.points.map((point) => (
                            <tr key={point.name}>
                              <td>{point.name}</td>
                              <td>{point.northing_m.toLocaleString("pt-BR", { maximumFractionDigits: 3 })}</td>
                              <td>{point.easting_m.toLocaleString("pt-BR", { maximumFractionDigits: 3 })}</td>
                              <td>{point.elevation_reported_m.toLocaleString("pt-BR", { maximumFractionDigits: 3 })}</td>
                              <td>{point.sigma_hz_m?.toLocaleString("pt-BR", { maximumFractionDigits: 3 }) ?? "—"}</td>
                              <td>{point.point_role === "CONTROL" ? "Controle" : "A classificar"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {topconPreview.solution.length > 0 && (
                      <details>
                        <summary>Vetores e qualidade GNSS ({topconPreview.solution.length})</summary>
                        <div style={{ overflowX: "auto" }}>
                          <table><thead><tr>
                            <th>Linha-base</th><th>Distância (m)</th><th>Solução</th><th>Órbita</th>
                            <th>PDOP</th><th>HDOP</th><th>VDOP</th>
                          </tr></thead><tbody>
                            {topconPreview.solution.map((v) => (
                              <tr key={v.baseline}><td>{v.baseline}</td>
                                <td>{v.distance_m.toLocaleString("pt-BR", { maximumFractionDigits: 3 })}</td>
                                <td>{v.solution_type}</td><td>{v.orbit}</td>
                                <td>{v.pdop.toLocaleString("pt-BR")}</td>
                                <td>{v.hdop.toLocaleString("pt-BR")}</td>
                                <td>{v.vdop.toLocaleString("pt-BR")}</td>
                              </tr>
                            ))}
                          </tbody></table>
                        </div>
                      </details>
                    )}
                    {topconPreview.sessions.length > 0 && (
                      <details>
                        <summary>Sessões de levantamento ({topconPreview.sessions.length})</summary>
                        <div style={{ overflowX: "auto" }}>
                          <table><thead><tr>
                            <th>Ponto</th><th>Início informado</th><th>Fim informado</th>
                            <th>Duração</th><th>Método</th><th>Antena</th>
                          </tr></thead><tbody>
                            {topconPreview.sessions.map((v) => (
                              <tr key={v.point}><td>{v.point}</td>
                                <td>{v.started_at_reported}</td><td>{v.ended_at_reported}</td>
                                <td>{v.duration}</td><td>{v.method}</td><td>{v.antenna}</td>
                              </tr>
                            ))}
                          </tbody></table>
                        </div>
                      </details>
                    )}
                    <p className="pecas-note">Pré-visualização de processamento: nenhum ponto foi incluído no perímetro e nenhum documento oficial foi gerado.</p>
                  </div>
                )}
              </div>
              {importedMetadata?.source === "SIGEF_ODS" && (
                <div className="pecas-card" aria-label="Dados preservados da planilha SIGEF">
                  <h4>Identificação SIGEF importada</h4>
                  <dl>
                    {([["Situação jurídica", "legal_status"], ["Natureza da área", "area_nature"], ["Natureza do serviço", "service_nature"], ["Tipo de pessoa", "person_type"], ["Município", "municipality"], ["SNCR/INCRA", "sncr"], ["Cartório/CNS", "cns"], ["Matrícula", "registration"], ["Sistema geodésico", "reference_system"]] as const).map(([label, key]) => (
                      <div key={key}><dt>{label}</dt><dd>{importedMetadata[key] || "Não informado na planilha"}</dd></div>
                    ))}
                  </dl>
                </div>
              )}
              <div className="pecas-form-grid">
                {field("Denominação do imóvel ou lote", "title", "Ex.: Fazenda Boa Vista")}
                {field("Nome completo do detentor / posseiro", "owner")}
                {field("RG do detentor", "rg")}
                {field("CPF do detentor", "cpf")}
                {field("Localização / endereço do imóvel", "address")}
                {field("Título da planta", "plantHeading")}
                {field("Título do memorial", "memorialHeading")}
              </div>
              <label className="pecas-check">
                <input type="checkbox" checked={data.croqui} onChange={(e) => onDataChange("croqui", e.target.checked)} />
                Inserir ressalva opcional de croqui nos documentos
              </label>
              <div className="pecas-rt-heading">
                <h3>Responsável técnico</h3>
                <button className="pecas-secondary" type="button" onClick={onRtReload}
                  disabled={rtLoading}>Recarregar cadastro</button>
              </div>
              <p>Pré-preenchido do perfil profissional. Alterações não atualizam o cadastro original.</p>
              {rtLoading && <p>Consultando cadastro do RT…</p>}
              {rtError && <p className="pecas-warning" role="alert">{rtError}</p>}
              {rtProfile && (
                <div className="pecas-form-grid">
                  {([
                    ["full_name", "Nome completo"],
                    ["profession", "Título profissional"],
                    ["specialization", "Especialização"],
                    ["crea", "CREA / CAU"],
                    ["visto", "Visto"],
                    ["incra_code", "Credenciamento INCRA"],
                    ["art", "ART específica da peça"],
                    ["rg", "RG do RT"],
                    ["cpf", "CPF do RT"],
                  ] as const).map(([key, label]) => (
                    <label className="pecas-field" key={key}>
                      <span>{label}</span>
                      <input value={rtProfile[key]} onChange={(e) => onRtChange(key, e.target.value)} />
                    </label>
                  ))}
                </div>
              )}
            </div>
            <SituationMapPreview
              geometry={situationGeometry}
              geometryKey={situationKey}
              saved={situationSaved}
              onSave={onSaveSituation}
              vertexNames={chosen.map((polygon) => polygon.vertices)}
            />
          </div>
        )}

        {stage === 1 && (
          <div className="pecas-data-layout">
            <div className="pecas-card">
            <h3>2. Áreas, vértices e confrontações</h3>
            <p>Selecione as parcelas que comporão as peças. Os polígonos continuam sendo os mesmos do mapa, sem cópias ou alteração automática da geometria.</p>
            {polygons.map((polygon) => (
              <article className="pecas-polygon" key={polygon.id}>
                <div className="pecas-polygon-top">
                  <label className="pecas-check">
                    <input type="checkbox" checked={selectedIds.includes(polygon.id)}
                      onChange={(e) => onSelect(polygon.id, e.target.checked)} />
                    Incluir
                  </label>
                  <input aria-label="Denominação da área" value={polygon.name}
                    onChange={(e) => onRenamePolygon(polygon.id, e.target.value)} />
                  <span>{polygon.areaHa.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ha · {polygon.perimeterM.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m</span>
                </div>
                {selectedIds.includes(polygon.id) && (
                  <div className="pecas-table-wrap">
                    <table className="pecas-table">
                      <thead><tr><th>#</th><th>Nome do vértice</th><th>Confrontante do segmento</th><th>Altitude elipsoidal (m)</th><th>Método</th><th>Tipo limite</th></tr></thead>
                      <tbody>
                        {polygon.vertices.map((name, index) => (
                          <tr key={index}>
                            <td>{index + 1}</td>
                            <td><input aria-label={`Nome do vértice ${index + 1}`}
                              value={name} onChange={(e) => onRenameVertex(polygon.id, index, e.target.value)} /></td>
                            <td><input aria-label={`Confrontante do segmento ${index + 1}`}
                              value={polygon.confrontants[index] ?? ""}
                              onChange={(e) => onConfrontant(polygon.id, index, e.target.value)} /></td>
                            <td>{polygon.altitudes[index] ?? "—"}</td>
                            <td>{String(polygon.vertexDetails?.[index]?.positioning_method ?? "—")}</td>
                            <td>{String(polygon.vertexDetails?.[index]?.boundary_type ?? "—")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </article>
            ))}
            {!polygons.length && <p className="pecas-warning">Não há polígono no mapa. Volte ao mapa para desenhar ou importar uma área.</p>}
            </div>
            <SituationMapPreview geometry={situationGeometry} geometryKey={situationKey}
              saved={situationSaved} onSave={onSaveSituation}
              showVertices vertexNames={chosen.map((polygon) => polygon.vertices)} />
          </div>
        )}

        {stage === 2 && (
          <div className="pecas-card pecas-large">
            <h3>3. Memorial descritivo</h3>
            <p>Edite o texto livremente. “Salvar alterações” grava a revisão no servidor e a aplica às exportações PDF e DOCX.</p>
            {memorialLoading && <p className="pecas-busy">Gerando memorial…</p>}
            <textarea className="pecas-memorial" value={editableMemorial}
              onChange={(event) => { setEditableMemorial(event.target.value); setMemorialDirty(true); setMemorialSaved(false); }}
              aria-label="Memorial descritivo editável" />
            <div className="pecas-situation-actions">
              <button type="button" className="pecas-primary"
                onClick={() => void runAction(async () => {
                  memorialSavingRef.current = true;
                  try {
                    await onSavePiece(editableMemorial);
                    onSaveMemorial(editableMemorial);
                    setMemorialDirty(false);
                    setMemorialSaved(true);
                    setSavedPieceNotice("Memorial salvo no servidor");
                  } finally {
                    memorialSavingRef.current = false;
                  }
                })}
                disabled={!editableMemorial.trim() || actionBusy}> {actionBusy ? "Salvando…" : "Salvar alterações do memorial"}</button>
              <button type="button" className="pecas-secondary"
                onClick={() => { onSaveMemorial(null); setMemorialDirty(false); setEditableMemorial(memorialText); setMemorialSaved(false); }}>Restaurar texto automático</button>
              <button type="button" className="pecas-secondary" disabled={memorialLoading}
                onClick={() => { onSaveMemorial(null); setMemorialDirty(false); void onGenerateMemorial(); }}>Regenerar memorial</button>
            </div>
            {memorialSaved && <p role="status">Memorial revisado salvo no servidor e aplicado às próximas exportações PDF e DOCX.</p>}
          </div>
        )}

        {stage === 3 && (
          <div className="pecas-card pecas-large">
            <h3>4. Planta georreferenciada — pré-visualização real</h3>
            <p>A visualização abaixo apresenta o PDF produzido pelo serviço oficial do sistema, e não uma imagem de exemplo. A planta de situação utiliza a captura do mapa atual.</p>
            <div className="pecas-print-grid">
              <label className="pecas-field"><span>Modelo da prancha</span>
                <select value={data.layoutTemplate} onChange={(event) => onDataChange("layoutTemplate", event.target.value)}>
                  <option value="classic_lateral">Profissional A — clássico lateral (A0–A4)</option>
                  <option value="cartographic_frame">Profissional B — moldura cartográfica (A0–A4)</option>
                  <option value="modern_lateral">Profissional C — moderno com quadro lateral (A0–A4)</option>
                </select>
              </label>
              <label className="pecas-field"><span>Formato da folha</span>
                <select value={data.format} onChange={(e) => onDataChange("format", e.target.value)}>
                  {(["A4", "A3", "A2", "A1", "A0"] as const).map((v) => <option key={v}>{v}</option>)}
                </select>
              </label>
              <label className="pecas-field"><span>Orientação</span>
                <select value={data.orientation} onChange={(e) => onDataChange("orientation", e.target.value)}>
                  <option value="retrato">Retrato</option>
                  <option value="paisagem">Paisagem</option>
                </select>
              </label>
              <label className="pecas-field"><span>Escala nominal</span>
                <select value={data.scale} onChange={(e) => onDataChange("scale", e.target.value)}>
                  <option value="auto">Automática</option>
                  {["500", "1000", "1500", "2000", "2500", "5000", "10000", "25000", "50000"].map(
                    (v) => <option key={v} value={v}>1:{Number(v).toLocaleString("pt-BR")}</option>
                  )}
                  <option value="custom">Outra escala</option>
                </select>
              </label>
              {data.scale === "custom" && <label className="pecas-field"><span>Denominador 1:</span>
                <input type="number" min={50} max={1000000} value={data.customScale}
                  onChange={(e) => onDataChange("customScale", e.target.value)} />
              </label>}
            </div>
            {["classic_lateral", "cartographic_frame", "modern_lateral"].includes(data.layoutTemplate) && <p className="pecas-note">Modelos profissionais: folhas A0, A1, A2, A3 e A4; retrato ou paisagem. Fonte e quadro técnico ajustados para composição de engenharia.</p>}
            {data.layoutTemplate === "inferior" && <p className="pecas-note">No modelo inferior, o quadro utiliza toda a largura da folha; quando houver muitos vértices, os demais seguem em folhas de continuação para manter a leitura.</p>}
            <details className="pecas-advanced">
              <summary>Configurações avançadas dos elementos da planta</summary>
              <p>Configure os elementos e clique em Gerar Planta + Memorial para atualizar o PDF.</p>
              <div className="pecas-options-grid">
                {PLANT_OPTIONS.map(([key, label]) => (
                  <label className="pecas-check" key={key}>
                    <input type="checkbox" checked={elements[key]}
                      onChange={(event) => onToggleElement(key, event.target.checked)} />
                    {label}
                  </label>
                ))}
              </div>
              <label className="pecas-field">
                <span>Data do levantamento (opcional)</span>
                <input type="date" value={surveyDate} onChange={(event) => onSurveyDateChange(event.target.value)} />
                <small>Sem preenchimento: usa a data de elaboração da planta. O cálculo WMM2025 cobre 2025 a 2029.</small>
              </label>
              {elements.magnetic_declination && (
                <label className="pecas-field">
                  <span>Declinação magnética manual (graus decimais com sinal; opcional)</span>
                  <input type="number" min={-30} max={30} step="0.01"
                    value={declination} onChange={(event) => onDeclinationChange(event.target.value)} />
                  <small>Se ficar vazio, o sistema calcula pelo modelo WMM2025 no vértice mais ao norte, usando a data de referência.</small>
                </label>
              )}
              <button type="button" className="pecas-secondary"
                onClick={() => PLANT_OPTIONS.forEach(([key]) => onToggleElement(key, DEFAULT_PLANT_ELEMENTS[key]))}>
                Restaurar elementos padrão
              </button>
            </details>
            <div className="pecas-situation-actions">
              <button type="button" className="pecas-primary"
                disabled={pdfBusy || !chosen.length}
                onClick={() => void handleGeneratePlantAndMemorial()}>
                {pdfBusy ? "Gerando Planta + Memorial…" : "Gerar Planta + Memorial"}
              </button>
            </div>
            {!pdfReady && !pdfBusy && <p className="pecas-note" role="status">Documento ainda não gerado ou configurações alteradas. Clique em Gerar Planta + Memorial para atualizar a pré-visualização.</p>}
            {pdfBusy && <p className="pecas-busy">Gerando a planta e o memorial…</p>}
            {pdfError && <p role="alert" className="pecas-warning">{pdfError}</p>}
            {pdfReady && pdfUrl && !pdfBusy && (
              <iframe className="pecas-pdf-frame" title="Pré-visualização da planta e memorial"
                src={pdfUrl} />
            )}
          </div>
        )}

        {stage === 4 && (
          <div className="pecas-card">
            <h3>5. Conferência e exportação</h3>
            <p>Documentos gerados pelos serviços existentes. As exportações vetoriais são feitas individualmente por polígono.</p>
            <div className="pecas-export-grid">
              <button disabled={!pdfReady || actionBusy} onClick={() => { if (pdfReady && pdfBlob) downloadBlob(pdfBlob, `${fileSlug(data.title)}-planta-memorial.pdf`); }}>
                <Download size={17} /> Planta + Memorial (PDF)
              </button>
              <button disabled={actionBusy} onClick={() => void runAction(onDownloadDocx)}>
                <FileText size={17} /> Memorial descritivo (DOCX)
              </button>
              <button disabled={!sigefAvailable || actionBusy} onClick={() => void runAction(onDownloadSigef)}>
                <Download size={17} /> SIGEF — simulação (ODS)
              </button>
            </div>
            {!sigefAvailable && <p className="pecas-note">A exportação ODS SIGEF exige uma análise espacial registrada e a permissão correspondente. Conclua a análise no módulo existente para habilitá-la.</p>}
            <h4>Exportações vetoriais por área</h4>
            {chosen.map((polygon) => (
              <div className="pecas-vector-row" key={polygon.id}>
                <strong>{polygon.name}</strong>
                {(["txt", "kml", "shp"] as const).map((format) => (
                  <button key={format} disabled={actionBusy}
                    onClick={() => void runAction(() => onExportPolygon(polygon.id, format))}>
                    {format === "shp" ? "Shapefile ZIP" : format.toUpperCase()}
                  </button>
                ))}
              </div>
            ))}
            {(actionError || externalError) && <p className="pecas-warning" role="alert">{actionError || externalError}</p>}
            {!pdfReady && <p className="pecas-note">O PDF precisa ser conferido novamente na etapa Planta antes da exportação.</p>}
          </div>
        )}
      </main>
      {(actionError || (externalError && stage !== 4)) && (
        <p role="alert" className="pecas-warning pecas-workspace-alert">
          {actionError || externalError}
        </p>
      )}
      <footer className="pecas-footer">
        <span>{selectedIds.length} polígono(s) selecionado(s) · Etapa {stage + 1} de 5 {savedPieceNotice && "· " + savedPieceNotice}</span>
        <div>
          <button className="pecas-secondary" type="button" disabled={actionBusy}
            onClick={() => void runAction(async () => {
              onSaveMemorial(editableMemorial.trim() ? editableMemorial : null);
              await onSavePiece(editableMemorial.trim() ? editableMemorial : "");
              setSavedPieceNotice("Rascunho salvo no servidor");
            })}>Salvar peça</button>
          <button className="pecas-secondary" type="button" onClick={() => stage === 0 ? onClose() : setStage(stage - 1)}>
            <ArrowLeft size={16} /> {stage === 0 ? "Mapa" : "Voltar"}
          </button>
          {stage < 4 && <button className="pecas-primary" type="button"
            disabled={selectedIds.length === 0 || (stage === 3 && (!pdfReady || pdfBusy))}
            onClick={() => setStage(stage + 1)}>
            Avançar <ArrowRight size={16} />
          </button>}
          {stage === 4 && <button className="pecas-primary" type="button" onClick={onClose}>
            <Map size={16} /> Concluir e voltar ao mapa
          </button>}
        </div>
      </footer>
    </section>
  );
}
