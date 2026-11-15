"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Download, FileText, Map, X } from "lucide-react";
import { SituationMapPreview, type SituationSnapshot } from "@/components/situation-map-preview";
import { Pa2WitnessMap } from "@/components/pa2-witness-map";
import { InpeCbersSceneSearch } from "@/components/inpe-cbers-scene-search";
import { getApiUrl } from "@/lib/api";
import { buildPs4Closure } from "@/lib/ps4-closure";

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
  ellipsoidal_height_reported_m?: number | null;
};
export type TopconBoundaryPoint = Omit<TopconPoint, "point_role" | "elevation_reported_m"> & {
  elevation_reported_m: number | null;
  sigef_vertex_code: string;
  sigef_method: string;
  boundary_type: string;
  confrontant: string;
  ellipsoidal_height_m: number | null;
  sigma_lon_m: number | null;
  sigma_lat_m: number | null;
  sigma_reference_confirmed?: boolean;
  sigma_h_m: number | null;
  confrontant_cns: string;
  confrontant_registration: string;
  height_reference_confirmed: boolean;
  point_role: "BOUNDARY";
  parcel_number: string;
  parcel_name: string;
  derived_physical_altitude_m?: number | null;
  derived_physical_model?: "HN" | "H" | null;
  sigma_suggestion_e_m?: number | null;
  sigma_suggestion_n_m?: number | null;
  sigma_suggestion_h_m?: number | null;
  derived_calculation?: Record<string, unknown> | null;
};
type TopconReview = {
  ready_for_ods: boolean;
  errors: string[];
  warnings: string[];
  vertex_count: number;
  area_ha: number | null;
  perimeter_m: number | null;
  geometry: Record<string, unknown> | null;
  parcel_geometries?: Array<{ number: string; name: string; geometry: Record<string, unknown> }>;
};

type TopconPreview = {
  source: "TOPCON_TOOLS";
  filename: string;
  project: Record<string, string | number | null>;
  points: TopconPoint[];
  point_count: number;
  observations?: Array<{ baseline: string; horizontal_rms_m: number; vertical_rms_m: number;
    sigma_x_m: number; sigma_y_m: number; sigma_z_m: number; solution_type: string }>;
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

export type TopconDraft = {
  version: 1;
  preview: TopconPreview | null;
  boundary: TopconBoundaryPoint[];
  vertical_model: "hgeoHNOR2020" | "MAPGEO2015";
  vertical_factors: Record<string, string>;
  vertical_factor_uncertainty?: Record<string, number>;
  vertical_origin: string;
  vertical_confirmed: Record<string, boolean>;
  vertical_calculated: Array<{
    name: string; ellipsoidal_height_m: number;
    normal_height_m?: number; orthometric_height_m?: number;
    conversion_factor_m?: number; eta_m?: number; geoid_undulation_m?: number;
  }> | null;
  municipalities: string;
  situation: string;
  cns: string;
  registration: string;
  stage: number;
  ps4_closure?: { start: string; confirmed: boolean };
  ps4_draft?: Array<{
    name: string; latitude: number; longitude: number; scene_id: string; created_at: string;
  }>;
  construction?: {
    method: "PA1" | "PA2" | "PT8" | "PS4";
    pa2_variant: "SUPPORT_LINE" | "INTERSECTION";
    witnesses: string[];
    distance: string;
    side: "LEFT" | "RIGHT" | "FORWARD" | "BACKWARD";
    crs_confirmed: boolean;
    insert_after: string;
    hint: { longitude: number; latitude: number } | null;
    last_result: Record<string, unknown> | null;
  };
};

const SIGEF_POSITION_METHODS = [
  ["PG1", "Relativo estático"], ["PG2", "Relativo estático-rápido"],
  ["PG3", "Relativo semicinemático"], ["PG4", "Relativo cinemático"],
  ["PG5", "Relativo a partir de códigos"], ["PG6", "RTK convencional / RTPPP"],
  ["PG7", "RTK em rede"], ["PG8", "DGPS"],
  ["PG9", "Posicionamento por Ponto Preciso"], ["PT1", "Poligonação"],
  ["PT2", "Triangulação"], ["PT3", "Trilateração"],
  ["PT4", "Triangulateração"], ["PT5", "Irradiação"],
  ["PT6", "Interseção linear"], ["PT7", "Interseção angular"],
  ["PT8", "Alinhamento"], ["PT9", "Estação livre"],
  ["PA1", "Paralela"], ["PA2", "Interseção de retas"],
  ["PA3", "Projeção técnica"], ["PS1", "Aerofotogrametria"],
  ["PS2", "Radar aerotransportado"], ["PS3", "Laser scanner aerotransportado"],
  ["PS4", "Sensores orbitais"], ["PB1", "Base cartográfica com precisão conhecida"],
  ["PB2", "Base cartográfica sem precisão conhecida"],
] as const;
const SIGEF_BOUNDARY_TYPES = [
  ["LA1", "Cerca"], ["LA2", "Muro"], ["LA3", "Estrada"],
  ["LA4", "Vala"], ["LA5", "Canal"], ["LA6", "Linha ideal"],
  ["LA7", "Limite artificial não tipificado"],
  ["LN1", "Corpo d'água ou curso d'água"],
  ["LN2", "Linha de cumeada"], ["LN3", "Grota"],
  ["LN4", "Crista de encosta"], ["LN5", "Pé de encosta"],
  ["LN6", "Limite natural não tipificado"],
] as const;

function groupTopconParcels(points: TopconBoundaryPoint[], fallback: string) {
  const groups = new globalThis.Map<string, { number: string; name: string; vertices: TopconBoundaryPoint[] }>();
  for (const point of points) {
    const number = point.parcel_number.trim();
    if (!number) throw new Error(`Ponto ${point.name}: informe o número da parcela.`);
    const name = point.parcel_name.trim() || fallback.trim() || `Parcela ${number}`;
    const parcel = groups.get(number);
    if (parcel && parcel.name !== name) {
      throw new Error(`Parcela ${number}: denominações divergentes entre os vértices.`);
    }
    if (parcel) parcel.vertices.push(point);
    else groups.set(number, { number, name, vertices: [point] });
  }
  if (groups.size > 50) throw new Error("Máximo de 50 parcelas por exportação.");
  return [...groups.values()];
}

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
  onAdoptTopconParcels: (parcels: Array<{
    number: string; name: string; vertices: TopconBoundaryPoint[];
  }>) => void;
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
  onSavePiece: (memorialDraft: string, topconDraft: TopconDraft) => Promise<void>;
  loadedTopconDraft?: TopconDraft | null;
  loadedTopconRevision?: number;
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
  onRenamePolygon, onRenameVertex, onConfrontant, onAdoptTopconParcels, memorialText,
  memorialLoading, externalError, onGenerateMemorial, onBuildPdf, onDownloadDocx,
  onExportPolygon, onDownloadSigef, sigefAvailable,
  rtProfile, rtLoading, rtError, onRtChange, onRtReload,
  situationGeometry, situationKey, situationSaved, onSaveSituation,
  elements, onToggleElement, declination, onDeclinationChange,
  surveyDate, onSurveyDateChange,
  onSavePiece, onSaveMemorial, loadedMemorialDraft, loadedPieceId,
  loadedTopconDraft, loadedTopconRevision,
}: Props) {
  const [stage, setStage] = useState(0);
  const [topconPreview, setTopconPreview] = useState<TopconPreview | null>(null);
  const [topconLoading, setTopconLoading] = useState(false);
  const [topconError, setTopconError] = useState("");
  const [topconBoundary, setTopconBoundary] = useState<TopconBoundaryPoint[]>([]);
  const [topconReview, setTopconReview] = useState<TopconReview | null>(null);
  const [topconReviewBusy, setTopconReviewBusy] = useState(false);
  const [pa2Mode, setPa2Mode] = useState(false);
  const [constructionMethod, setConstructionMethod] = useState<"PA1" | "PA2" | "PT8" | "PS4">("PA2");
  const [ps4Draft, setPs4Draft] = useState<NonNullable<TopconDraft["ps4_draft"]>>([]);
  const [ps4Start, setPs4Start] = useState("");
  const [ps4ClosureConfirmed, setPs4ClosureConfirmed] = useState(false);
  const [ps4Status, setPs4Status] = useState<{ kind: "success" | "error" | "info"; message: string }>({
    kind: "info", message: "Etapa 1/3: marque os vértices V no mapa; depois feche o trecho entre dois marcos."
  });
  const [ps4Candidate, setPs4Candidate] = useState<{ longitude: number; latitude: number } | null>(null);
  const [ps4CandidateName, setPs4CandidateName] = useState("");
  const [ps4Notice, setPs4Notice] = useState("");
  const [ps4ConfirmFeature, setPs4ConfirmFeature] = useState(false);
  const PS4_SCENE = "CBERS4A_WPM_PCA_RGB321_20261016_214_113";
  const ps4StartIndex = topconBoundary.findIndex(p => p.name === ps4Start);
  const ps4End = ps4StartIndex < 0 ? "" :
    topconBoundary[(ps4StartIndex + 1) % topconBoundary.length]?.name ?? "";
  const ps4Closure = buildPs4Closure(topconBoundary, ps4Draft, ps4Start, ps4End);
  const ps4Ready = ps4ClosureConfirmed && ps4Closure.valid;
  const ps4PreviewGeometry = ps4Ready ? ps4Closure.geometry : null;
  const ps4PreviewKey = ps4Ready ? JSON.stringify(ps4PreviewGeometry) : "";
  const ps4SuggestedName = () => {
    const code = (rtProfile?.incra_code ?? "").trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    const prefix = code.length >= 3 && code.length <= 6 ? code : "VIRTUAL";
    const existing = [...topconBoundary.map(p => p.sigef_vertex_code || p.name), ...ps4Draft.map(p => p.name)];
    const pattern = new RegExp("^" + prefix + "-V-([0-9]{4})$");
    const taken = new Set(existing.map(value => pattern.exec(value)?.[1]).filter(Boolean).map(Number));
    let number = 1;
    while (taken.has(number)) number++;
    return `${prefix}-V-${String(number).padStart(4, "0")}`;
  };
  const addPs4DraftPoint = () => {
    if (!ps4Candidate || !ps4ConfirmFeature) {
      setPs4Notice("Confirme a identificação visual da feição antes de registrar o ponto provisório.");
      return;
    }
    const name = ps4CandidateName.trim().toUpperCase();
    if (!new RegExp("^[A-Z0-9]{3,12}-V-[0-9]{4}$").test(name)) {
      setPs4Notice("Use o formato CODIGO-V-0001. Confira o código do credenciado no perfil.");
      return;
    }
    if ([...topconBoundary.map(p => p.sigef_vertex_code || p.name), ...ps4Draft.map(p => p.name)]
      .some(value => value.toUpperCase() === name)) {
      setPs4Notice("O código informado já existe neste rascunho.");
      return;
    }
    setPs4ClosureConfirmed(false);
    setPs4Draft(points => [...points, {
      name, longitude: ps4Candidate.longitude, latitude: ps4Candidate.latitude,
      scene_id: PS4_SCENE, created_at: new Date().toISOString(),
    }]);
    setPs4Candidate(null);
    setPs4CandidateName("");
    setPs4ConfirmFeature(false);
    setPs4Notice(`Vértice ${name} registrado como rascunho. Continue marcando a feição e depois confira o fechamento.`);
    setPs4Status({kind:"success", message:`Vértice ${name} registrado. Próximo: marcar outro V ou validar fechamento.`});
  };
  const [pa2Variant, setPa2Variant] = useState<"SUPPORT_LINE" | "INTERSECTION">("SUPPORT_LINE");
  const [constructionDistance, setConstructionDistance] = useState("");
  const [pt8PointConfirmed, setPt8PointConfirmed] = useState(false);
  const [constructionSide, setConstructionSide] = useState<"LEFT" | "RIGHT" | "FORWARD" | "BACKWARD">("LEFT");
  const [mapHint, setMapHint] = useState<{ longitude: number; latitude: number } | null>(null);
  const [pa2Witnesses, setPa2Witnesses] = useState<string[]>([]);
  const [pa2InsertAfter, setPa2InsertAfter] = useState("");
  const [pa2ConfirmedCrs, setPa2ConfirmedCrs] = useState(false);
  const [pa2Result, setPa2Result] = useState<{
    status: string; method: string; vertex_type: string;
    easting_m: number; northing_m: number;
    latitude: number | null; longitude: number | null;
    angle_deg_acute?: number; height_m: number | null;
    physical_altitude_m?: number | null;
    physical_altitude_type?: "HN" | "H" | null;
    fraction?: number;
    distance_a_v_m?: number;
    distance_a_b_m?: number;
    witnesses?: string[];
    sigma_e_m: number | null; sigma_n_m: number | null; sigma_h_m: number | null;
    warnings: string[]; ready_for_sigef: boolean;
  } | null>(null);
  const [pa2Busy, setPa2Busy] = useState(false);
  const [pa2Error, setPa2Error] = useState("");
  const [verticalModel, setVerticalModel] = useState<"hgeoHNOR2020" | "MAPGEO2015">("hgeoHNOR2020");
  const [verticalFactors, setVerticalFactors] = useState<Record<string, string>>({});
  const [verticalFactorUncertainty, setVerticalFactorUncertainty] = useState<Record<string, number>>({});
  const [verticalOrigin, setVerticalOrigin] = useState("IBGE - fator informado manualmente");
  const [verticalConfirmed, setVerticalConfirmed] = useState<Record<string, boolean>>({});
  const [verticalCalculated, setVerticalCalculated] = useState<Array<{
    name: string; ellipsoidal_height_m: number;
    normal_height_m?: number; orthometric_height_m?: number;
    conversion_factor_m?: number; eta_m?: number;
    geoid_undulation_m?: number;
  }> | null>(null);
  const [verticalError, setVerticalError] = useState("");
  const [verticalLoading, setVerticalLoading] = useState(false);
  const [ibgeBatchNotice, setIbgeBatchNotice] = useState("");
  const exportIbgeBatch = () => {
    setIbgeBatchNotice("");
    if (verticalModel !== "hgeoHNOR2020") {
      setIbgeBatchNotice("A exportação é destinada ao hgeoHNOR2020. Selecione esse modelo.");
      return;
    }
    const points = topconBoundary.filter(point =>
      Number.isFinite(point.latitude) && Number.isFinite(point.longitude));
    if (!points.length) {
      setIbgeBatchNotice("Selecione os vértices com latitude e longitude SIRGAS2000.");
      return;
    }
    const lines = points.map(point =>
      `${point.name} ${Number(point.latitude).toFixed(9)} ${Number(point.longitude).toFixed(9)}`);
    downloadBlob(new Blob([lines.join("\n") + "\n"], { type: "text/plain;charset=utf-8" }),
      "amazonika_hgeoHNOR2020_entrada_IBGE.txt");
    setIbgeBatchNotice(`Arquivo para consulta IBGE: ${points.length} ponto(s), ordem ID LAT LON (grau decimal). Confira o referencial SIRGAS2000.`);
  };
  const importIbgeBatch = async (file: File) => {
    setIbgeBatchNotice("");
    try {
      if (file.size > 1_000_000) throw new Error("Arquivo excede 1 MB.");
      const raw = (await file.text()).replace(/^\uFEFF/, "").trim();
      const lines = raw.split(/\r?\n/).map(line => line.trim())
        .filter(line => line && !line.startsWith("#"));
      if (!lines.length) throw new Error("Arquivo de resultados vazio.");
      const norm = (text: string) => text.toUpperCase().normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "").replace(/[^A-Z0-9]/g, "");
      const split = (line: string, delim: string) => (delim === " "
        ? line.trim().split(/\s+/)
        : line.split(delim).map(v => v.trim().replace(/^"|"$/g, "")));
      // Official hgeoHNOR2020 saida.txt: ID LAT LON ETA SIGMA GRADE, no header.
      const first = lines[0];
      const isOfficialTxt = !/[;,]/.test(first)
        && /^\S+\s+[-+]?\d+(?:\.\d+)?\s+[-+]?\d+(?:\.\d+)?\s+[-+]?\d+(?:\.\d+)?\s+[-+]?\d+(?:\.\d+)?\s+\S+/.test(first);
      const delimiter = isOfficialTxt ? " " :
        first.includes(";") ? ";" : first.includes("\t") ? "\t" : ",";
      const header = isOfficialTxt ? [] : split(first, delimiter).map(norm);
      const idIndex = isOfficialTxt ? 0 : header.findIndex(v =>
        ["ID", "PONTO", "NAME", "IDENTIFICACAO"].includes(v));
      const factorIndex = isOfficialTxt ? 3 : header.findIndex(v =>
        ["FATCOR", "ETAM", "ETA", "ONDGEO", "NM"].includes(v));
      const latIndex = isOfficialTxt ? 1 : header.findIndex(v => ["LAT", "LATITUDE"].includes(v));
      const lonIndex = isOfficialTxt ? 2 : header.findIndex(v => ["LON", "LONG", "LONGITUDE"].includes(v));
      const sigmaIndex = isOfficialTxt ? 4 : header.findIndex(v =>
        ["SIGMA", "SIGMAM", "INCERTEZA", "INCERTEZAM"].includes(v));
      const modelIndex = isOfficialTxt ? 5 : header.findIndex(v =>
        ["MODELO", "MODEL", "GRADE"].includes(v));
      if (idIndex < 0 || factorIndex < 0)
        throw new Error("Formato não reconhecido. Use saida.txt oficial ou CSV com ID;FATCOR (ou ID;ETA_M).");
      if (isOfficialTxt && verticalModel !== "hgeoHNOR2020")
        throw new Error("O arquivo oficial é de hgeoHNOR2020, mas o modelo selecionado é diferente.");
      if (!isOfficialTxt && ["ONDGEO", "NM"].includes(header[factorIndex]) !==
        (verticalModel === "MAPGEO2015"))
        throw new Error("O tipo do fator não corresponde ao modelo selecionado.");

      const known = new globalThis.Map(topconBoundary.map(point => [norm(point.name), point]));
      const next: Record<string, string> = {};
      const uncertainties: Record<string, number> = {};
      const warnings: string[] = [];
      for (const [index, line] of lines.entries()) {
        if (!isOfficialTxt && index === 0) continue;
        const values = split(line, delimiter);
        const id = norm(values[idIndex] ?? "");
        const point = known.get(id);
        if (!point) {
          warnings.push(values[idIndex] ?? "sem ID");
          continue;
        }
        if (Object.prototype.hasOwnProperty.call(next, point.name))
          throw new Error("Identificador duplicado no arquivo: " + point.name);
        const factor = Number((values[factorIndex] ?? "").replace(",", "."));
        if (!Number.isFinite(factor) || (values[factorIndex] ?? "") === "")
          throw new Error("Fator η inválido em " + point.name);
        if (latIndex >= 0 && lonIndex >= 0) {
          const latitude = Number((values[latIndex] ?? "").replace(",", "."));
          const longitude = Number((values[lonIndex] ?? "").replace(",", "."));
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude))
            throw new Error("Coordenadas inválidas no arquivo para " + point.name);
          if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude))
            throw new Error("Coordenadas GNSS indisponíveis para conferir " + point.name);
          // ~2 m latitude/longitude guard against attaching a factor from a different location.
          if (Math.abs(latitude - Number(point.latitude)) > 0.00002 ||
              Math.abs(longitude - Number(point.longitude)) > 0.00002)
            throw new Error("Coordenadas do IBGE divergentes do ponto " + point.name +
              ". Confira ordem, época e sistema de referência.");
        }
        if (modelIndex >= 0 && values[modelIndex]) {
          const model = norm(values[modelIndex]);
          if (verticalModel === "hgeoHNOR2020" &&
              !model.includes("HGEOHNOR") && !model.includes("SANTANA") &&
              !model.includes("IMBITUBA"))
            throw new Error("Grade/modelo inesperado no ponto " + point.name);
          if (verticalModel === "MAPGEO2015" && !model.includes("MAPGEO2015"))
            throw new Error("Modelo inesperado no ponto " + point.name);
        }
        if (sigmaIndex >= 0 && values[sigmaIndex]) {
          const sigma = Number(values[sigmaIndex].replace(",", "."));
          if (!Number.isFinite(sigma) || sigma < 0)
            throw new Error("Incerteza de fator inválida no ponto " + point.name);
          uncertainties[point.name] = sigma;
        }
        next[point.name] = String(factor);
      }
      const accepted = Object.keys(next);
      if (!accepted.length)
        throw new Error("Nenhum identificador do arquivo corresponde aos vértices selecionados.");
      const missing = topconBoundary.filter(point =>
        !Object.prototype.hasOwnProperty.call(next, point.name)).map(point => point.name);
      // Commit all factors together; never retain stale values for points missing from this file.
      setVerticalFactors(next);
      setVerticalFactorUncertainty(uncertainties);
      setVerticalOrigin("Arquivo " + file.name + " — " + verticalModel +
        " (resultado declarado; origem e referencial sujeitos a conferência pelo RT)");
      setVerticalCalculated(null);
      setVerticalError("");
      setIbgeBatchNotice("Importação concluída: " + accepted.length +
        " fator(es) preenchido(s) automaticamente." +
        (missing.length ? " Faltam: " + missing.join(", ") + "." : " Todos os pontos encontrados.") +
        (warnings.length ? " IDs não selecionados ignorados: " + warnings.join(", ") + "." : "") +
        " A confirmação de h SIRGAS2000 permanece independente.");
    } catch (err) {
      setIbgeBatchNotice(err instanceof Error ? err.message : "Falha ao interpretar o resultado do IBGE.");
    }
  };
  const calculateVertical = async () => {
    setVerticalLoading(true);
    setVerticalCalculated(null);
    setVerticalError("");
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces/topcon/vertical-conversion`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: verticalModel,
          points: topconBoundary
            .filter((point) => topconPreview?.points.some((original) => original.name === point.name))
            .map((point) => ({
            name: point.name,
            latitude: point.latitude,
            longitude: point.longitude,
            ellipsoidal_height_m: point.ellipsoidal_height_m,
            height_reference_confirmed: Boolean(verticalConfirmed[point.name]),
            conversion_factor_m: verticalFactors[point.name] ?? "",
            factor_uncertainty_m: verticalFactorUncertainty[point.name] ?? null,
            factor_origin: verticalOrigin,
          })),
        }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(
        typeof result?.detail === "string" ? result.detail : "Falha na conversão altimétrica.");
      if (result?.status !== "READY") throw new Error(
        (result?.errors ?? []).join("; ") || "Dados altimétricos incompletos.");
      setVerticalCalculated(result.points);
    } catch (error) {
      setVerticalError(error instanceof Error ? error.message : "Falha na conversão.");
    } finally {
      setVerticalLoading(false);
    }
  };
  const [sigefMunicipalities, setSigefMunicipalities] = useState("");
  const [sigefSituation, setSigefSituation] = useState("Área não Titulada");
  const [sigefCns, setSigefCns] = useState("");
  const [sigefRegistration, setSigefRegistration] = useState("");
  const [sigefParcelReview, setSigefParcelReview] = useState<{
    status: string; errors: string[]; warnings: string[];
    parcels: Array<{ number: string; area_ha: number }>;
  } | null>(null);
  const [sigefParcelBusy, setSigefParcelBusy] = useState(false);
  const [sigefValidatedSignature, setSigefValidatedSignature] = useState("");
  const [reviewedOdsBusy, setReviewedOdsBusy] = useState(false);
  useEffect(() => {
    if (!loadedTopconDraft || loadedTopconDraft.version !== 1) return;
    const d = loadedTopconDraft;
    setTopconPreview(d.preview);
    setTopconBoundary(d.boundary);
    setPs4Draft(d.ps4_draft ?? []);
    setPs4Start(d.ps4_closure?.start ?? "");
    setPs4ClosureConfirmed(Boolean(d.ps4_closure?.confirmed));
    setPs4Candidate(null);
    setVerticalModel(d.vertical_model);
    setVerticalFactors(d.vertical_factors);
    setVerticalFactorUncertainty(d.vertical_factor_uncertainty ?? {});
    setVerticalOrigin(d.vertical_origin);
    setVerticalConfirmed(d.vertical_confirmed);
    setVerticalCalculated(d.vertical_calculated);
    setSigefMunicipalities(d.municipalities);
    setSigefSituation(d.situation);
    setSigefCns(d.cns);
    setSigefRegistration(d.registration);
    setStage(d.stage >= 0 && d.stage <= 4 ? d.stage : 0);
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    setPa2Mode(false);
    setConstructionMethod(d.construction?.method ?? "PA2");
    setPa2Variant(d.construction?.pa2_variant ?? "SUPPORT_LINE");
    setPa2Witnesses(d.construction?.witnesses ?? []);
    setConstructionDistance(d.construction?.distance ?? "");
    setConstructionSide(d.construction?.side ?? "LEFT");
    setPa2ConfirmedCrs(Boolean(d.construction?.crs_confirmed));
    setPa2InsertAfter(d.construction?.insert_after ?? "");
    setMapHint(d.construction?.hint ?? null);
    setPa2Result((d.construction?.last_result ?? null) as typeof pa2Result);
  }, [loadedTopconRevision]);
  const draftForSave = (): TopconDraft => ({
    version: 1, preview: topconPreview, boundary: topconBoundary, ps4_draft: ps4Draft,
    ps4_closure: { start: ps4Start, confirmed: ps4Ready },
    vertical_model: verticalModel, vertical_factors: verticalFactors,
    vertical_factor_uncertainty: verticalFactorUncertainty,
    vertical_origin: verticalOrigin, vertical_confirmed: verticalConfirmed,
    vertical_calculated: verticalCalculated,
    municipalities: sigefMunicipalities, situation: sigefSituation,
    cns: sigefCns, registration: sigefRegistration, stage,
    construction: {
      method: constructionMethod, pa2_variant: pa2Variant,
      witnesses: pa2Witnesses, distance: constructionDistance,
      side: constructionSide, crs_confirmed: pa2ConfirmedCrs,
      insert_after: pa2InsertAfter, hint: mapHint,
      last_result: pa2Result,
    },
  });

  const [reviewedOdsError, setReviewedOdsError] = useState("");
  const [reviewedOdsNotice, setReviewedOdsNotice] = useState("");
  const makeSigefIdentity = () => ({
    holder_name: data.owner, holder_document: data.cpf,
    property_name: data.title, service_nature: "Particular",
    area_nature: "Particular", situation: sigefSituation,
    cns: sigefCns, registration: sigefRegistration,
    municipalities: sigefMunicipalities.split(/[;,]/).map((item) => item.trim()).filter(Boolean),
  });
  const parcelsForOds = () => groupTopconParcels(topconBoundary, data.title);
  const sigefSignature = () => {
    try {
      return JSON.stringify({ identification: makeSigefIdentity(), parcels: parcelsForOds() });
    } catch {
      return "";
    }
  };
  const downloadReviewedOds = async () => {
    if (!topconReview?.ready_for_ods || sigefParcelReview?.status !== "PREVALIDATED") return;
    if (topconBoundary.some(point => !point.sigma_reference_confirmed)) {
      setReviewedOdsError("Confirme os sigmas individuais de todos os vértices antes de gerar ODS.");
      return;
    }
    if (!sigefValidatedSignature || sigefValidatedSignature !== sigefSignature()) {
      setReviewedOdsError("Dados alterados: refaça a pré-validação SIGEF antes da exportação.");
      return;
    }
    setReviewedOdsBusy(true);
    setReviewedOdsError("");
    setReviewedOdsNotice("");
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces/sigef/reviewed-ods`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          identification: makeSigefIdentity(),
          parcels: parcelsForOds(),
          neighbors: [],
        }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(typeof error?.detail === "string"
          ? error.detail : "Não foi possível gerar a ODS revisada.");
      }
      const blob = await response.blob();
      if (blob.size < 100) throw new Error("A planilha gerada está vazia ou incompleta.");
      downloadBlob(blob, `SIGEF-PREVALIDACAO-${fileSlug(data.title)}.ods`);
      setReviewedOdsNotice("ODS gerada para conferência técnica; não certificada pelo SIGEF.");
    } catch (error) {
      setReviewedOdsError(error instanceof Error ? error.message : "Falha no download ODS.");
    } finally {
      setReviewedOdsBusy(false);
    }
  };

  const validateSigefParcel = async () => {
    if (!topconReview?.ready_for_ods || !topconReview.parcel_geometries?.length) return;
    setSigefParcelBusy(true);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    setTopconError("");
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces/sigef/parcels-review`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          identification: makeSigefIdentity(),
          parcels: topconReview.parcel_geometries.map((parcel) => ({
            ...parcel, parcelling_type: "SEM_PARCELAMENTO",
          })),
          neighbors: [],
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(
        typeof payload?.detail === "string" ? payload.detail :
        "A pré-validação cadastral SIGEF não foi concluída.");
      setSigefParcelReview(payload);
      if (payload?.status === "PREVALIDATED") setSigefValidatedSignature(sigefSignature());
    } catch (error) {
      setTopconError(error instanceof Error ? error.message : "Erro na revisão cadastral.");
    } finally {
      setSigefParcelBusy(false);
    }
  };
  const pickPa2Witness = (name: string) => {
    setPa2Result(null);
    setPa2Error("");
    const limit = constructionMethod === "PA2" && pa2Variant === "INTERSECTION" ? 4 : 2;
    setPa2Witnesses((old) => old.includes(name) ? old.filter((n) => n !== name)
      : old.length >= limit ? [name] : [...old, name]);
  };
  const calculatePa2 = async () => {
    if (!topconPreview || !verticalCalculated ||
        pa2Witnesses.length !== (constructionMethod === "PA2" && pa2Variant === "INTERSECTION" ? 4 : 2)) return;
    setPa2Busy(true); setPa2Error(""); setPa2Result(null);
    try {
      const witnesses = pa2Witnesses.map((name) => topconPreview.points.find((p) => p.name === name));
      if (witnesses.some((point) => !point)) throw new Error("Marco de apoio não encontrado no relatório.");
      const response = await fetch(`${getApiUrl()}/technical-pieces/topcon/${
        constructionMethod === "PA2"
          ? (pa2Variant === "SUPPORT_LINE" ? "pa2-support-line" : "pa2-intersection")
          : "constructed-vertex"
      }`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...(constructionMethod === "PA2" && pa2Variant === "SUPPORT_LINE" ? {
            supports: witnesses.map((point) => {
              const physical = verticalCalculated.find((v) => v.name === point?.name);
              const boundary = topconBoundary.find((v) => v.name === point?.name);
              return {
                name: point?.name,
                easting_m: point?.easting_m, northing_m: point?.northing_m,
                physical_altitude_m: verticalModel === "hgeoHNOR2020"
                  ? physical?.normal_height_m : physical?.orthometric_height_m,
                sigma_e_m: boundary?.sigma_lon_m ?? null,
                sigma_n_m: boundary?.sigma_lat_m ?? null,
                sigma_h_m: boundary?.sigma_h_m ?? null,
              };
            }),
            hint_longitude: mapHint?.longitude,
            hint_latitude: mapHint?.latitude,
            altitude_type: verticalModel === "hgeoHNOR2020" ? "HN" : "H",
          } : {
            witnesses: witnesses.map((point) => ({
              name: point?.name, easting_m: point?.easting_m, northing_m: point?.northing_m,
            })),
            ...(constructionMethod === "PA2" ? {} : {
              method: constructionMethod, distance_m: Number(constructionDistance),
              side: constructionSide,
              ...(constructionMethod === "PA1" && mapHint
                ? { hint_longitude: mapHint.longitude, hint_latitude: mapHint.latitude }
                : {}),
            }),
          }),
          utm_zone: topconPreview.project.utm_zone,
          hemisphere: topconPreview.project.hemisphere,
          sirgas2000_confirmed: pa2ConfirmedCrs,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof payload?.detail === "string"
        ? payload.detail : "Não foi possível calcular a interseção PA2.");
      // PA1 e PA2 geométrico: projeção da solução na primeira linha de apoio.
      // A altitude é SEMPRE física (HN/H), nunca a h elipsoidal do TOPCON.
      if (payload && payload.physical_altitude_m == null && witnesses.length >= 2) {
        const a = witnesses[0]!, b = witnesses[1]!;
        const dx = b.easting_m - a.easting_m;
        const dy = b.northing_m - a.northing_m;
        const length2 = dx*dx + dy*dy;
        const t = length2 > 0 ? (
          ((payload.easting_m - a.easting_m)*dx +
           (payload.northing_m - a.northing_m)*dy) / length2
        ) : NaN;
        const pa = verticalCalculated.find(p => p.name === a.name);
        const pb = verticalCalculated.find(p => p.name === b.name);
        const hA = verticalModel === "hgeoHNOR2020" ? pa?.normal_height_m : pa?.orthometric_height_m;
        const hB = verticalModel === "hgeoHNOR2020" ? pb?.normal_height_m : pb?.orthometric_height_m;
        if (Number.isFinite(t) && t >= 0 && t <= 1 &&
            Number.isFinite(hA) && Number.isFinite(hB)) {
          payload.physical_altitude_m = (hA as number) + t*((hB as number)-(hA as number));
          payload.physical_altitude_type = verticalModel === "hgeoHNOR2020" ? "HN" : "H";
          payload.warnings = [...(payload.warnings ?? []),
            "Altitude física interpolada pelo alinhamento dos dois primeiros marcos.",
            "A altura elipsoidal h requer conversão específica no ponto resultante."];
        }
        const ba = topconBoundary.find(p => p.name === a.name);
        const bb = topconBoundary.find(p => p.name === b.name);
        for (const [field, dest] of [
          ["sigma_lon_m", "sigma_e_m"], ["sigma_lat_m", "sigma_n_m"],
          ["sigma_h_m", "sigma_h_m"],
        ] as const) {
          const x = ba?.[field], y = bb?.[field];
          if (x != null && y != null && x >= 0 && y >= 0) {
            payload[dest] = (x+y)/2;
          }
        }
      }
      setPa2Result(payload);
    } catch (error) {
      setPa2Error(error instanceof Error ? error.message : "Falha ao calcular PA2.");
    } finally {
      setPa2Busy(false);
    }
  };
  const addProvisionalPa2 = () => {
    if (!topconPreview || !pa2Result || !Number.isFinite(pa2Result.latitude)
        || !Number.isFinite(pa2Result.longitude)) {
      setPa2Error("Confirme SIRGAS2000 e recalcule antes de inserir o vértice.");
      return;
    }
    const at = topconBoundary.findIndex((p) => p.name === pa2InsertAfter);
    if (at < 0) { setPa2Error("Selecione o segmento de limite onde inserir V."); return; }
    const previous = topconBoundary[at];
    if (constructionMethod === "PT8" && !pt8PointConfirmed) {
      setPa2Error("PT8 requer caracterização do ponto tipo P em campo antes da inserção.");
      return;
    }
    const used = new Set([...topconPreview.points.map((p) => p.name),
      ...topconBoundary.map((p) => p.name)]);
    let suffix = 1;
    const prefix = constructionMethod === "PT8" ? "P" : "V";
    while (used.has(`${prefix}${String(suffix).padStart(3, "0")}`)) suffix++;
    const name = `${prefix}${String(suffix).padStart(3, "0")}`;
    const newVertex: TopconBoundaryPoint = {
      ...previous, name,
      northing_m: pa2Result.northing_m, easting_m: pa2Result.easting_m,
      latitude: pa2Result.latitude, longitude: pa2Result.longitude,
      elevation_reported_m: null, ellipsoidal_height_reported_m: null,
      derived_physical_altitude_m: pa2Result.physical_altitude_m ?? null,
      derived_physical_model: pa2Result.physical_altitude_type ?? null,
      sigma_suggestion_e_m: pa2Result.sigma_e_m,
      sigma_suggestion_n_m: pa2Result.sigma_n_m,
      sigma_suggestion_h_m: pa2Result.sigma_h_m,
      derived_calculation: { ...pa2Result, generated_at: new Date().toISOString() },
      ellipsoidal_height_m: null, sigma_n_m: null, sigma_e_m: null,
      sigma_hz_m: null, sigma_u_m: null,
      sigma_lon_m: null, sigma_lat_m: null, sigma_h_m: null,
      sigma_reference_confirmed: false,
      height_reference_confirmed: false,
      sigef_vertex_code: "", sigef_method: constructionMethod, boundary_type: previous.boundary_type,
      confrontant: previous.confrontant, confrontant_cns: previous.confrontant_cns,
      confrontant_registration: previous.confrontant_registration,
      point_role: "BOUNDARY",
    };
    setTopconBoundary((old) => [...old.slice(0, at + 1), newVertex, ...old.slice(at + 1)]);
    setTopconReview(null); setSigefParcelReview(null); setSigefValidatedSignature("");
    setPa2Result(null); setPa2Witnesses([]); setPa2InsertAfter(name);
    setPa2Error("Ponto provisório inserido: confira identificação, método, h e sigmas antes de exportar.");
  };
  const updateBoundaryPoint = (index: number, patch: Partial<TopconBoundaryPoint>) => {
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    // Mudanças cadastrais, métodos e sigmas não invalidam conversão altimétrica.
    // Somente coordenada, altura ou confirmação do referencial obrigam recalcular.
    if (["latitude", "longitude", "ellipsoidal_height_m", "height_reference_confirmed"]
      .some((field) => field in patch)) {
      setVerticalCalculated(null);
      setPa2Result(null);
    }
    if (["sigma_lon_m", "sigma_lat_m", "sigma_h_m"].some(key => key in patch) &&
        !patch.sigma_reference_confirmed) {
      patch.sigma_reference_confirmed = false;
    }
    setTopconBoundary((current) => current.map((point, i) =>
      i === index ? { ...point, ...patch } : point));
  };
  const moveBoundaryPoint = (index: number, offset: number) => {
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    setTopconBoundary((current) => {
      const dest = index + offset;
      if (dest < 0 || dest >= current.length) return current;
      const next = [...current];
      [next[index], next[dest]] = [next[dest], next[index]];
      return next;
    });
  };
  const validateTopconBoundary = async () => {
    setTopconReviewBusy(true);
    setTopconError("");
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    try {
      const parcels = parcelsForOds();
      if (!parcels.length) throw new Error("Selecione ao menos uma parcela.");
      if (topconBoundary.some(point => !point.sigma_reference_confirmed)) {
        throw new Error("Pendência de pré-validação SIGEF: faltam os sigmas individuais das coordenadas ajustadas (σ Longitude/σ Latitude). O cálculo das altitudes HN está independente e não precisa ser repetido.");
      }
      const reviews: Array<{ number: string; name: string; review: TopconReview }> = [];
      for (const parcel of parcels) {
        const response = await fetch(`${getApiUrl()}/technical-pieces/topcon/perimeter-review`, {
          method: "POST", credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ points: parcel.vertices }),
        });
        const result = await response.json().catch(() => null);
        if (!response.ok) throw new Error(
          typeof result?.detail === "string" ? result.detail : `Falha ao validar parcela ${parcel.number}.`);
        reviews.push({ number: parcel.number, name: parcel.name, review: result as TopconReview });
      }
      const errors = reviews.flatMap(({ number, review }) => review.errors.map((msg) => `Parcela ${number}: ${msg}`));
      const warnings = reviews.flatMap(({ number, review }) => review.warnings.map((msg) => `Parcela ${number}: ${msg}`));
      const ready = errors.length === 0 && reviews.every(({ review }) => review.ready_for_ods && review.geometry);
      setTopconReview({
        ready_for_ods: Boolean(ready), errors, warnings,
        vertex_count: topconBoundary.length,
        area_ha: reviews.reduce((total, { review }) => total + (review.area_ha ?? 0), 0),
        perimeter_m: reviews.reduce((total, { review }) => total + (review.perimeter_m ?? 0), 0),
        geometry: ready ? reviews[0].review.geometry : null,
        parcel_geometries: ready ? reviews.map(({ number, name, review }) => ({
          number, name, geometry: review.geometry as Record<string, unknown>,
        })) : [],
      });
    } catch (error) {
      setTopconError(error instanceof Error ? error.message : "Falha na revisão do perímetro.");
    } finally {
      setTopconReviewBusy(false);
    }
  };
  const importTopcon = async (file: File) => {
    setTopconError("");
    setTopconPreview(null);
    setPa2Mode(false); setPa2Result(null); setPa2Witnesses([]); setMapHint(null);
    setPa2InsertAfter(""); setPa2ConfirmedCrs(false);
    setTopconBoundary([]);
    setPs4Draft([]);
    setPs4Start("");
    setPs4ClosureConfirmed(false);
    setPs4Candidate(null);
    setTopconReview(null);
    setVerticalFactors({});
    setVerticalFactorUncertainty({});
    setVerticalConfirmed({});
    setVerticalCalculated(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
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
  const adoptTopconGeometry = () => {
    setTopconError("");
    try {
      const parcels = parcelsForOds();
      if (!parcels.length) throw new Error("Selecione pelo menos três pontos de limite.");
      if (parcels.some((p) => p.vertices.length < 3)) {
        throw new Error("Cada parcela precisa de pelo menos três vértices.");
      }
      if (!window.confirm(
        "Aplicar os perímetros TOPCON como rascunhos cartográficos na Planta e Memorial? " +
        "A aprovação geométrica e SIGEF permanece pendente e precisará da revisão do RT."
      )) return;
      onAdoptTopconParcels(parcels);
      setStage(1);
    } catch (error) {
      setTopconError(error instanceof Error ? error.message : "Não foi possível transferir a geometria.");
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
  // Prévia cartográfica não substitui geometrias do mapa nem autoriza a ODS.
  // A sequência reflete o ordenamento atual do editor, inclusive erros a corrigir.
  const previewTopconGeometry = (() => {
    const groups = new globalThis.Map<string, Array<[number, number]>>();
    for (const point of topconBoundary) {
      if (!Number.isFinite(point.longitude) || !Number.isFinite(point.latitude)) continue;
      const coordinates = groups.get(point.parcel_number) ?? [];
      coordinates.push([point.longitude as number, point.latitude as number]);
      groups.set(point.parcel_number, coordinates);
    }
    const features = [...groups.entries()].filter(([, coords]) => coords.length >= 3)
      .map(([number, coords]) => ({
        type: "Feature" as const, properties: { parcel_number: number },
        geometry: { type: "Polygon" as const, coordinates: [[...coords, coords[0]]] },
      }));
    return features.length ? { type: "FeatureCollection", features } : null;
  })();
  const displaySituationGeometry = previewTopconGeometry ?? situationGeometry;
  const displaySituationKey = previewTopconGeometry
    ? JSON.stringify(previewTopconGeometry) : situationKey;
  const displayVertexNames = previewTopconGeometry
    ? [...new Set(topconBoundary.map((point) => point.parcel_number))]
      .map((number) => topconBoundary.filter((point) => point.parcel_number === number)
        .map((point) => point.sigef_vertex_code || point.name))
    : chosen.map((polygon) => polygon.vertices);
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
      const message = error instanceof Error ? error.message : "Falha na operação.";
      setActionError(message);
      setPs4Status({ kind: "error", message: "Operação não concluída: " + message });
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
                {topconError && <p className={topconError.startsWith("Pendência de pré-validação SIGEF") ? "pecas-note" : "pecas-warning"} role="status">{topconError}</p>}
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
                    <div className="pecas-card" aria-label="Revisão de perímetro TOPCON">
                      <h4>2. Selecionar, ordenar e validar vértices de divisa</h4>
                      <p>Selecione apenas pontos integrantes do limite, informe os dados técnicos
                        confirmados e organize o percurso horário a partir do vértice mais ao norte.
                        A elevação TOPCON não é interpretada automaticamente como altura SIRGAS2000.
                        Atribua número e denominação aos vértices de cada parcela.</p>
                      <p><strong>Altura do relatório:</strong> o campo "Alt Elip WGS84" é
                        carregado como valor informado e editável. É necessário conferir
                        o referencial SIRGAS2000 e a época das coordenadas antes de
                        confirmar "h" para uso no SIGEF.</p>
                      <p><strong>Método e limite:</strong> selecione os códigos segundo o método
                        efetivamente aplicado e o tipo de divisa constatado em campo;
                        o relatório não identifica automaticamente essas classificações.</p>
                      <div style={{ overflowX: "auto" }}>
                        <table>
                          <thead><tr><th>Selecionar</th><th>Ponto</th><th>Código SIGEF</th>
                            <th>Parcela nº</th><th>Denominação da parcela</th><th>Altura elipsoidal (m)</th><th>Método</th><th>Tipo limite</th>
                            <th>Confrontante seguinte</th><th>Ordem</th></tr></thead>
                          <tbody>
                            {[...topconPreview.points.filter((point) => point.point_role !== "CONTROL"),
                               ...topconBoundary.filter((point) => !topconPreview.points.some((source) => source.name === point.name))]
                               .map((point) => {
                                const index = topconBoundary.findIndex((selected) => selected.name === point.name);
                                const selected = index >= 0 ? topconBoundary[index] : null;
                                return <tr key={point.name}>
                                  <td><input type="checkbox" aria-label={`Incluir ${point.name} no perímetro`}
                                    checked={Boolean(selected)} onChange={(event) => {
                                      setTopconReview(null);
                                      setSigefParcelReview(null);
                                       setSigefValidatedSignature("");
                                      setTopconBoundary((current) => event.target.checked
                                        ? [...current, { ...point, point_role: "BOUNDARY",
                                          sigef_vertex_code: "", parcel_number: "1",
                                           parcel_name: data.title || "Parcela 1",
                                           ellipsoidal_height_m: point.ellipsoidal_height_reported_m ?? null,
                                          sigma_lon_m: point.sigma_e_m ?? null,
                                          sigma_lat_m: point.sigma_n_m ?? null,
                                          sigma_h_m: point.sigma_u_m ?? null,
                                          sigma_reference_confirmed: false,
                                          height_reference_confirmed: false,
                                          confrontant_cns: "", confrontant_registration: "",
                                          sigef_method: "", boundary_type: "", confrontant: "" }]
                                        : current.filter((item) => item.name !== point.name));
                                    }} /></td>
                                  <td>{point.name}
                                     {!topconPreview.points.some((source) => source.name === point.name)
                                       && <small> · calculado</small>}
                                   </td>
                                  <td><input aria-label={`Código SIGEF ${point.name}`} disabled={!selected}
                                    value={selected?.sigef_vertex_code ?? ""}
                                    onChange={(event) => updateBoundaryPoint(index, { sigef_vertex_code: event.target.value })} /></td>
                                  <td><input aria-label={`Parcela do ponto ${point.name}`} disabled={!selected}
                                     value={selected?.parcel_number ?? ""}
                                     onChange={(event) => updateBoundaryPoint(index, { parcel_number: event.target.value })} /></td>
                                   <td><input aria-label={`Denominação da parcela ${point.name}`} disabled={!selected}
                                     value={selected?.parcel_name ?? ""}
                                     onChange={(event) => updateBoundaryPoint(index, { parcel_name: event.target.value })} /></td>
                                   <td><input key={`${point.name}:h:${loadedTopconRevision ?? 0}`}
                                    aria-label={`Altura elipsoidal ${point.name}`} disabled={!selected}
                                    inputMode="decimal" placeholder="Confirmar h"
                                    defaultValue={selected?.ellipsoidal_height_m ?? ""}
                                    onBlur={(event) => {
                                      const value = event.target.value.trim().replace(",", ".");
                                      if (value !== "" && !Number.isFinite(Number(value))) return;
                                      updateBoundaryPoint(index, { ellipsoidal_height_m:
                                        value === "" ? null : Number(value) });
                                    }} /></td>
                                  <td><select aria-label={`Método ${point.name}`} disabled={!selected}
                                    value={selected?.sigef_method ?? ""}
                                    onChange={(event) => updateBoundaryPoint(index, { sigef_method: event.target.value })}>
                                    <option value="">Selecione o método</option>
                                    {SIGEF_POSITION_METHODS.map(([code, label]) => <option key={code} value={code}>
                                      {code} — {label}
                                    </option>)}
                                  </select></td>
                                  <td><select aria-label={`Tipo de limite ${point.name}`} disabled={!selected}
                                    value={selected?.boundary_type ?? ""}
                                    onChange={(event) => updateBoundaryPoint(index, { boundary_type: event.target.value })}>
                                    <option value="">Selecione o limite</option>
                                    {SIGEF_BOUNDARY_TYPES.map(([code, label]) => <option key={code} value={code}>
                                      {code} — {label}
                                    </option>)}
                                  </select></td>
                                  <td><input aria-label={`Confrontante ${point.name}`} disabled={!selected}
                                    value={selected?.confrontant ?? ""}
                                    onChange={(event) => updateBoundaryPoint(index, { confrontant: event.target.value })} /></td>
                                  <td>{selected && <span>
                                    {index + 1} <button type="button" disabled={index === 0}
                                      onClick={() => moveBoundaryPoint(index, -1)}>↑</button>
                                    <button type="button" disabled={index === topconBoundary.length - 1}
                                      onClick={() => moveBoundaryPoint(index, 1)}>↓</button>
                                  </span>}</td>
                                </tr>;
                              })}
                          </tbody>
                        </table>
                      </div>
                      <div className="pecas-card" aria-label="Precisões SIGEF">
                        <h4>Precisões e referências dos confrontantes</h4>
                        <p><strong>Valores individuais:</strong> {topconBoundary.filter(p =>
                          p.sigma_lon_m !== null && p.sigma_lat_m !== null).length}
                          /{topconBoundary.length} vértices com valores disponíveis.
                          {topconBoundary.filter(p => p.sigma_reference_confirmed).length}
                          /{topconBoundary.length} confirmações técnicas registradas.</p>
                        <button type="button" className="pecas-secondary"
                          disabled={!topconBoundary.length}
                          onClick={() => {
                            if (!window.confirm("Confirmo que conferi os desvios padrão individuais extraídos do TOPCON, sua referência e o resultado do ajustamento. Desejo aprovar os valores já preenchidos?")) return;
                            setTopconBoundary(old => old.map(point =>
                              point.sigma_lon_m !== null && point.sigma_lat_m !== null
                                ? { ...point, sigma_reference_confirmed: true } : point
                            ));
                            setTopconReview(null); setSigefParcelReview(null);
                            setSigefValidatedSignature("");
                          }}>Confirmar sigmas individuais preenchidos</button>
                        <p><strong>Revisão assistida:</strong> {topconBoundary.filter((p) =>
                          p.sigma_lon_m !== null && p.sigma_lat_m !== null).length}
                          /{topconBoundary.length} vértices com sigmas horizontalmente preenchidos;
                          {topconBoundary.filter((p) => p.height_reference_confirmed).length}
                          /{topconBoundary.length} alturas confirmadas.</p>
                        <p>Os RMS das linhas de base são detectados automaticamente.
                          A incerteza η importada do IBGE refere-se à conversão vertical e não preenche
                          σ Longitude/σ Latitude. Esta pendência não invalida a conversão HN já concluída.
                          Para sugerir sigmas individuais, importe no TOPCON o quadro
                          de desvios-padrão dos pontos ajustados (N, E e U) ou a matriz
                          de covariância. A conferência de referencial e a confirmação
                          técnica continuam obrigatórias.</p>
                        <button type="button" className="pecas-secondary"
                          disabled={!topconBoundary.length}
                          onClick={() => {
                            if (!window.confirm("Confirma que você verificou todas as alturas h no referencial SIRGAS2000 e sua época?")) return;
                            setTopconBoundary((old) => old.map((p) => ({
                              ...p,
                              height_reference_confirmed: p.ellipsoidal_height_m !== null &&
                                topconPreview?.points.some((source) => source.name === p.name)
                                ? true : p.height_reference_confirmed,
                            })));
                            setVerticalConfirmed(Object.fromEntries(topconBoundary
                              .filter((p) => p.ellipsoidal_height_m !== null &&
                                topconPreview?.points.some((source) => source.name === p.name))
                              .map((p) => [p.name, true])));
                            setTopconReview(null); setSigefParcelReview(null); setSigefValidatedSignature("");
                          }}>
                          Confirmar h de todos após conferência do RT
                        </button>
                        <p><strong>Dados do TOPCON — vetores GNSS:</strong> os RMS horizontal e
                          vertical e σX/Y/Z são apresentados abaixo para conferência.
                          Não equivalem automaticamente aos sigmas das coordenadas ajustadas
                          de cada vértice exigidos pela ODS.</p>
                        {Boolean(topconPreview.observations?.length) && <div style={{ overflowX: "auto" }}>
                          <table>
                            <thead><tr><th>Vetor</th><th>RMS horizontal</th><th>RMS vertical</th>
                              <th>σX</th><th>σY</th><th>σZ</th><th>Solução</th></tr></thead>
                            <tbody>{topconPreview.observations?.map((obs) => <tr key={obs.baseline}>
                              <td>{obs.baseline}</td>
                              <td>{obs.horizontal_rms_m.toLocaleString("pt-BR")} m</td>
                              <td>{obs.vertical_rms_m.toLocaleString("pt-BR")} m</td>
                              <td>{obs.sigma_x_m.toLocaleString("pt-BR")} m</td>
                              <td>{obs.sigma_y_m.toLocaleString("pt-BR")} m</td>
                              <td>{obs.sigma_z_m.toLocaleString("pt-BR")} m</td>
                              <td>{obs.solution_type}</td>
                            </tr>)}</tbody>
                          </table>
                        </div>}
                        <p>O sigma horizontal Topcon não substitui automaticamente as precisões
                          separadas de longitude e latitude exigidas na ODS. Informe os valores
                          confirmados pelo processamento e confirme a referência de h.</p>
                        <details className="pecas-advanced"><summary>Correções individuais de sigmas e confrontantes (avançado)</summary><p>Abra somente quando precisar revisar valores individuais.</p><div style={{ overflowX: "auto" }}>
                          <table>
                            <thead><tr><th>Vértice</th><th>σ Longitude (m)</th>
                              <th>σ Latitude (m)</th><th>σ h (m)</th><th>h confirmada</th>
                              <th>CNS confrontante</th><th>Matrícula confrontante</th></tr></thead>
                            <tbody>{topconBoundary.map((point, index) => <tr key={point.name}>
                              <td>{point.sigef_vertex_code || point.name}
                                {point.derived_physical_altitude_m != null && <p>
                                  {point.derived_physical_model}:{" "}
                                  {point.derived_physical_altitude_m.toLocaleString("pt-BR")} m
                                  <small> (h elipsoidal pendente)</small>
                                </p>}
                                {point.sigma_suggestion_e_m != null &&
                                  point.sigma_suggestion_n_m != null && <div>
                                    <small>Calculados: E={point.sigma_suggestion_e_m.toLocaleString("pt-BR")},
                                      N={point.sigma_suggestion_n_m.toLocaleString("pt-BR")} m</small>
                                    <button type="button" className="pecas-secondary"
                                      onClick={() => {
                                        if (!window.confirm(
                                          "Confirmo que conferi o cálculo e a metodologia dos sigmas " +
                                          "para " + point.name + " e aprovo seu uso no rascunho técnico."
                                        )) return;
                                        updateBoundaryPoint(index, {
                                          sigma_lon_m: point.sigma_suggestion_e_m ?? null,
                                          sigma_lat_m: point.sigma_suggestion_n_m ?? null,
                                          sigma_h_m: point.sigma_suggestion_h_m ?? null,
                                          sigma_reference_confirmed: true,
                                        });
                                      }}>Confirmar sigmas calculados</button>
                                  </div>}
                              </td>
                              {(["sigma_lon_m", "sigma_lat_m", "sigma_h_m"] as const)
                                .map((field) => <td key={field}>
                                  <input key={`${point.name}:${field}:${loadedTopconRevision ?? 0}`}
                                     aria-label={`${field} ${point.name}`} inputMode="decimal"
                                     defaultValue={point[field] ?? ""}
                                     onBlur={(event) => {
                                       const value = event.target.value.trim().replace(",", ".");
                                       if (value !== "" && !Number.isFinite(Number(value))) return;
                                       updateBoundaryPoint(index, {
                                         [field]: value === "" ? null : Number(value),
                                       });
                                     }} />
                                </td>)}
                              <td><input type="checkbox" aria-label={`Confirmar h ${point.name}`}
                                checked={point.height_reference_confirmed}
                                onChange={(event) => {
                                  updateBoundaryPoint(index, {
                                    height_reference_confirmed: event.target.checked,
                                  });
                                  setVerticalConfirmed((old) => ({
                                    ...old, [point.name]: event.target.checked,
                                  }));
                                }} /></td>
                              <td><input aria-label={`CNS confrontante ${point.name}`}
                                value={point.confrontant_cns}
                                onChange={(event) => updateBoundaryPoint(index, {
                                  confrontant_cns: event.target.value,
                                })} /></td>
                              <td><input aria-label={`Matrícula confrontante ${point.name}`}
                                value={point.confrontant_registration}
                                onChange={(event) => updateBoundaryPoint(index, {
                                  confrontant_registration: event.target.value,
                                })} /></td>
                            </tr>)}</tbody>
                          </table>
                        </div>
                         </details>
                      </div>
                       
                      <div className="pecas-card" aria-label="Conversão altimétrica IBGE">
                        <h4>Conversão altimétrica — IBGE</h4>
                        <p>A ODS SIGEF utiliza a altura elipsoidal (h). A altitude normal ou
                          ortométrica é complementar e depende do fator do modelo escolhido.
                          Confirme individualmente que h está referido ao SIRGAS2000.</p>
                        <label className="pecas-field"><span>Modelo do fator</span>
                          <select value={verticalModel} onChange={(event) => {
                            setVerticalModel(event.target.value as "hgeoHNOR2020" | "MAPGEO2015");
                            setVerticalCalculated(null);
                          }}>
                            <option value="hgeoHNOR2020">IBGE hgeoHNOR2020 — altitude normal (HN)</option>
                            <option value="MAPGEO2015">IBGE MAPGEO2015 — altitude ortométrica (H)</option>
                          </select>
                        </label>
                        <label className="pecas-field"><span>Origem dos fatores (protocolo/modelo)</span>
                          <input value={verticalOrigin} onChange={(event) => {
                            setVerticalOrigin(event.target.value); setVerticalCalculated(null);
                          }} />
                        </label>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 12 }}>
                          <button type="button" className="pecas-secondary" onClick={exportIbgeBatch}
                            disabled={topconBoundary.length === 0 || verticalModel !== "hgeoHNOR2020"}>
                            Exportar todos os pontos para o IBGE (.txt)
                          </button>
                          <label className="pecas-field">
                            <span>Importar fatores em lote (.csv / .txt delimitado)</span>
                            <input type="file" accept=".csv,.txt,text/csv,text/plain"
                              aria-label="Selecionar arquivo de fatores IBGE"
                              onChange={event => {
                                const file = event.currentTarget.files?.[0];
                                if (file) void importIbgeBatch(file);
                                event.currentTarget.value = "";
                              }} />
                          </label>
                        </div>
                        {ibgeBatchNotice && <p className="pecas-note" role="status">{ibgeBatchNotice}</p>}
                        <p className="pecas-note">
                          hgeoHNOR2020: no serviço IBGE selecione ID LAT LON (grau decimal). O saida.txt oficial com 6 colunas é reconhecido automaticamente.
                          Importe os resultados com cabeçalho ID;FATCOR;MODELO ou ID;ETA_M.
                          MAPGEO2015: utilize ID;ONDGEO;MODELO. Os valores são vinculados pelo ID, sem alterar h.
                          Os fatores continuam sujeitos à conferência de origem e qualidade pelo RT.
                        </p>
                        <div style={{ overflowX: "auto" }}>
                          <table>
                            <thead><tr><th>Ponto</th><th>h confirmado (m)</th>
                              <th>{verticalModel === "hgeoHNOR2020" ? "Fator η (m)" : "Ondulação N (m)"}</th>
                              <th>h é SIRGAS2000?</th></tr></thead>
                            <tbody>{topconBoundary.map((point) => <tr key={point.name}>
                              <td>{point.name}</td>
                              <td>{point.ellipsoidal_height_m ?? "Não informado"}</td>
                              <td><input aria-label={`Fator altimétrico ${point.name}`}
                                inputMode="decimal" value={verticalFactors[point.name] ?? ""}
                                onChange={(e) => {
                                  setVerticalFactors((old) => ({ ...old, [point.name]: e.target.value }));
                                  setVerticalFactorUncertainty(old => {
                                    const updated = { ...old }; delete updated[point.name]; return updated;
                                  });
                                  setVerticalCalculated(null);
                                }} /></td>
                              <td><input type="checkbox" aria-label={`Confirmar h SIRGAS2000 ${point.name}`}
                                checked={Boolean(verticalConfirmed[point.name])}
                                onChange={(e) => {
                                  setVerticalConfirmed((old) => ({ ...old, [point.name]: e.target.checked }));
                                  setVerticalCalculated(null);
                                }} /></td>
                            </tr>)}</tbody>
                          </table>
                        </div>
                        <button type="button" className="pecas-secondary"
                          disabled={verticalLoading || topconBoundary.length === 0}
                          onClick={() => void calculateVertical()}>
                          {verticalLoading ? "Calculando..." : "Calcular altitudes físicas"}
                        </button>
                        {verticalError && <p className="pecas-warning" role="alert">{verticalError}</p>}
                        {verticalCalculated && <div role="status">
                          <p><strong>Conversão altimétrica concluída. Nenhuma coordenada ou h foi alterada.</strong></p>
                          <p className="pecas-note">A conferência dos sigmas horizontais dos vértices é uma
                            etapa independente para a pré-validação SIGEF.</p>
                          {verticalCalculated.map((point) => <p key={point.name}>
                            {point.name}: h = {point.ellipsoidal_height_m.toLocaleString("pt-BR")} m;
                            {" "}{verticalModel === "hgeoHNOR2020" ? "HN" : "H"} =
                            {" "}{(point.normal_height_m ?? point.orthometric_height_m)?.toLocaleString("pt-BR")} m
                          </p>)}
                        </div>}
                        <p>O Amazonika não calcula η por uma API do IBGE nesta etapa:
                          a exportação e importação em lote preservam os fatores oficiais fornecidos pelo usuário.
                          A interpolação local das grades IBGE dependerá de validação metodológica independente.</p>
                      </div>
                      <div className="pecas-card">
                        <h4>Construção de vértices e ajustes cartográficos</h4>
                        <p>Depois de concluir a conversão de altitudes, abra o
                          espaço de trabalho para criar ou revisar vértices pelo método
                          PA1, PA2 ou PT8, sobre as bases cartográficas disponíveis.</p>
                        <button type="button" className="pecas-primary"
                          disabled={!verticalCalculated}
                          onClick={() => { setPa2Mode(true); setPa2Error(""); }}>
                          Abrir espaço de trabalho cartográfico
                        </button>
                        {!verticalCalculated && <p className="pecas-note">
                          Conclua primeiro a conversão altimétrica dos marcos de apoio.
                        </p>}
                      </div>
                      <button type="button" className="pecas-primary"
                        disabled={topconReviewBusy || topconBoundary.length < 3}
                        onClick={() => void validateTopconBoundary()}>
                        {topconReviewBusy ? "Validando perímetro..." : "Validar perímetro TOPCON"}
                      </button>
                      {topconReview && <div role="status">
                        <p><strong>{topconReview.ready_for_ods
                          ? "Pré-validação aprovada" : "Pré-validação com pendências"}</strong>
                          {" · "}{topconReview.vertex_count} vértices
                          {" · "}{topconReview.area_ha?.toLocaleString("pt-BR") ?? "—"} ha
                          {" · "}{topconReview.perimeter_m?.toLocaleString("pt-BR") ?? "—"} m</p>
                        {topconReview.errors.map((message, index) =>
                          <p key={index} className="pecas-warning" role="alert">{message}</p>)}
                        {topconReview.warnings.map((message, index) =>
                          <p key={index} className="pecas-note">{message}</p>)}
                        {topconReview.ready_for_ods && topconReview.geometry && (
                          <div className="pecas-card" aria-label="Revisão preliminar de identificação SIGEF">
                            <h4>3. Identificação e situação jurídica — pré-validação SIGEF</h4>
                            <p>Preencha os dados do titular e imóvel nos campos gerais acima.
                              Informe aqui os municípios e a situação jurídica para testar todas as parcelas.
                              Não é gerado ODS e não é efetuada consulta de vizinhos nesta etapa.</p>
                            <label className="pecas-field"><span>Municípios (separados por ponto e vírgula)</span>
                              <input value={sigefMunicipalities} placeholder="Macapá-AP; Santana-AP"
                                onChange={(e) => { setSigefMunicipalities(e.target.value); setSigefParcelReview(null); }} />
                            </label>
                            <label className="pecas-field"><span>Situação jurídica</span>
                              <select value={sigefSituation}
                                onChange={(e) => { setSigefSituation(e.target.value); setSigefParcelReview(null); }}>
                                <option>Imóvel Registrado</option>
                                <option>Área Titulada não Registrada</option>
                                <option>Área não Titulada</option>
                              </select>
                            </label>
                            {sigefSituation === "Imóvel Registrado" && <div>
                              <label className="pecas-field"><span>CNS cartório</span>
                                <input value={sigefCns} onChange={(e) => { setSigefCns(e.target.value); setSigefParcelReview(null); }} />
                              </label>
                              <label className="pecas-field"><span>Matrícula / transcrição</span>
                                <input value={sigefRegistration} onChange={(e) => { setSigefRegistration(e.target.value); setSigefParcelReview(null); }} />
                              </label>
                            </div>}
                            <button type="button" className="pecas-primary" disabled={sigefParcelBusy}
                              onClick={() => void validateSigefParcel()}>
                              {sigefParcelBusy ? "Validando identificação..." : "Pré-validar identificação e parcela"}
                            </button>
                            {sigefParcelReview && <div role="status">
                              <p><strong>{sigefParcelReview.status === "PREVALIDATED"
                                ? "Pré-validação cadastral sem erros locais"
                                : "Pendências cadastrais detectadas"}</strong></p>
                              {sigefParcelReview.parcels.map((p) => <p key={p.number}>
                                Parcela {p.number}: {p.area_ha.toLocaleString("pt-BR")} ha</p>)}
                              {sigefParcelReview.errors.map((msg, i) =>
                                <p key={i} className="pecas-warning" role="alert">{msg}</p>)}
                              {sigefParcelReview.warnings.map((msg, i) =>
                                <p key={i} className="pecas-note">{msg}</p>)}
                              <p>A ausência de base confrontante não comprova inexistência de sobreposição.
                                Nenhum campo da ODS é inferido ou preenchido automaticamente aqui.</p>
                              {sigefParcelReview.status === "PREVALIDATED" && <div>
                                <button type="button" className="pecas-primary"
                                  disabled={reviewedOdsBusy || !sigefValidatedSignature || sigefValidatedSignature !== sigefSignature()}
                                  onClick={() => void downloadReviewedOds()}>
                                  {reviewedOdsBusy ? "Gerando ODS..." : "Gerar ODS SIGEF revisada"}
                                </button>
                                {reviewedOdsError && <p className="pecas-warning" role="alert">{reviewedOdsError}</p>}
                                {reviewedOdsNotice && <p role="status">{reviewedOdsNotice}</p>}
                                <p>ODS para conferência técnica. A validação oficial do SIGEF
                                  e a verificação com parcelas certificadas continuam necessárias.</p>
                              </div>}
                            </div>}
                          </div>
                        )}
                        <button type="button" className="pecas-primary"
                          disabled={!topconBoundary.length}
                          onClick={adoptTopconGeometry}>
                          Aplicar poligonal ao mapa e avançar para Planta/Memorial (rascunho)
                        </button>
                        <p className="pecas-note">A transferência exige pelo menos três vértices
                          por parcela. Ela cria polígonos editáveis apenas após sua confirmação,
                          sem declarar que o processamento está apto ao SIGEF.</p>
                        <p>Este teste não gera ODS certificável nem modifica a geometria salva.
                          A próxima etapa será vincular o perímetro revisado ao modelo SIGEF, à planta e ao memorial.</p>
                      </div>}
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
              <InpeCbersSceneSearch geometry={displaySituationGeometry} geometryKey={displaySituationKey} />
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
                  geometry={displaySituationGeometry}
                  geometryKey={displaySituationKey}
                  saved={previewTopconGeometry ? null : situationSaved}
                  onSave={onSaveSituation}
                  vertexNames={displayVertexNames}
                  showVertices={Boolean(previewTopconGeometry)}
                  previewBasemap={previewTopconGeometry ? "osm" : "satellite"}
                  ps4Draft={ps4Draft}
                  ps4ClosureGeometry={ps4PreviewGeometry}
                 />
                 {ps4Draft.length > 0 && <div className="pecas-card" aria-label="Resumo de restituição PS4 provisória">
                   <h4>Restituição PS4 — pontos provisórios</h4>
                   <p role="status" className="pecas-note">{ps4Ready
                     ? "Prévia do perímetro fechada: segmento orbital integrado visualmente entre " +
                       (topconBoundary.find(p=>p.name===ps4Start)?.sigef_vertex_code || ps4Start) + " e " +
                       (topconBoundary.find(p=>p.name===ps4End)?.sigef_vertex_code || ps4End) +
                       ". Ainda não liberado para a planta oficial, memorial ou ODS."
                     : "Trecho orbital aberto: use Fechar prévia da poligonal no espaço PS4 antes de preparar a planta."}</p>
                   <p>{ps4Draft.length} ponto(s) restituído(s) visualmente. O traçado aparece em vermelho no mapa
                     de situação. Estes pontos não substituem automaticamente os vértices oficiais nem são enviados
                     ao SIGEF enquanto não houver validação da acurácia orbital e revisão do RT.</p>
                   {ps4Ready && <div className="pecas-card" aria-label="Sequência consolidada da poligonal PS4">
                     <h4>Prévia consolidada · marcos M e vértices V na ordem do perímetro</h4>
                     <p>O último ponto é ligado automaticamente ao primeiro para fechar a prévia.
                       Altitudes normais dos M são calculadas pelo IBGE quando disponíveis;
                       os pontos V permanecem sem altitude ou precisão certificável.</p>
                     <div style={{ overflowX: "auto" }}>
                       <table className="pecas-table">
                         <thead><tr><th>Ordem</th><th>Código</th><th>Tipo</th><th>Latitude</th>
                           <th>Longitude</th><th>HN (m)</th><th>Origem / Status</th></tr></thead>
                         <tbody>{ps4Closure.names.map((name, index) => {
                           const m = topconBoundary.find(p => p.name === name);
                           const v = ps4Draft.find(p => p.name === name);
                           const h = m ? verticalCalculated?.find(p => p.name === m.name)?.normal_height_m : null;
                           const lon = m?.longitude ?? v?.longitude;
                           const lat = m?.latitude ?? v?.latitude;
                           return <tr key={name + index}>
                             <td>{index + 1}</td>
                             <td>{m?.sigef_vertex_code || name}</td>
                             <td>{m ? "M (GNSS)" : "V (PS4)"}</td>
                             <td>{typeof lat === "number" ? lat.toFixed(8) : "—"}</td>
                             <td>{typeof lon === "number" ? lon.toFixed(8) : "—"}</td>
                             <td>{typeof h === "number" ? h.toFixed(3) : "Pendente"}</td>
                             <td>{m ? "Levantamento GNSS / revisar sigmas" : "CBERS-4A / provisório"}</td>
                           </tr>;
                         })}</tbody>
                       </table>
                     </div>
                     <button type="button" className="pecas-secondary" onClick={() => {
                       if (!ps4PreviewGeometry) return;
                       const feature = {
                         type: "Feature",
                         properties: {
                           status: "PREVIA_NAO_CERTIFICAVEL",
                           method: "PS4",
                           scene: PS4_SCENE,
                           vertices_in_order: ps4Closure.names,
                           disclaimer: "Restituição visual preliminar. Não é planta certificada ou ODS SIGEF.",
                         },
                         geometry: ps4PreviewGeometry,
                       };
                       downloadBlob(new Blob([JSON.stringify({
                         type: "FeatureCollection", features: [feature],
                       }, null, 2)], {type:"application/geo+json"}),
                         "amazonika_previa_ps4_nao_certificavel.geojson");
                       setSavedPieceNotice("GeoJSON de conferência gerado. Não utilizar como SIGEF.");
                     }}>
                       Baixar GeoJSON da prévia para conferência
                     </button>
                   </div>}
                   <div style={{ overflowX: "auto" }}>
                     <table className="pecas-table"><thead><tr>
                       <th>Vértice</th><th>Latitude</th><th>Longitude</th><th>Cena</th>
                     </tr></thead><tbody>{ps4Draft.map(point => <tr key={point.name}>
                       <td>{point.name}</td>
                       <td>{point.latitude.toFixed(8)}</td>
                       <td>{point.longitude.toFixed(8)}</td>
                       <td>{point.scene_id}</td>
                     </tr>)}</tbody></table>
                   </div>
                 </div>}
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
                    await onSavePiece(editableMemorial, draftForSave());
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
              await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
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
      {topconPreview && pa2Mode && (Boolean(verticalCalculated) || constructionMethod === "PS4") && (
        <div role="dialog" aria-modal="true" aria-label="Espaço de trabalho cartográfico"
          style={{ position: "fixed", inset: 10, zIndex: 100000, background: "#f7faf8",
            border: "1px solid #99b9ae", borderRadius: 14, display: "flex",
            flexDirection: "column", padding: 16, boxShadow: "0 10px 50px #0005" }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center",
            justifyContent: "space-between", marginBottom: 12 }}>
            <div>
              <strong>Espaço de trabalho — Construção de vértices</strong>
              <p style={{ margin: 0, fontSize: 12 }}>Planta de apoio · PA1 Paralela · PA2 Interseção · PT8 Alinhamento · PS4 Sensores orbitais</p>
            </div>
            <button type="button" className="pecas-secondary"
              disabled={actionBusy}
              onClick={() => {
                if (constructionMethod === "PS4" && !ps4Ready) {
                  setPs4Status({kind:"error",message:ps4Closure.valid
                    ? "Ainda falta confirmar o segmento e o fechamento da prévia PS4 (etapa 2)."
                    : "Não é possível concluir: " + ps4Closure.message +
                      " Use Salvar rascunho sem fechar, ou complete a etapa 2."});
                  return;
                }
                void runAction(async () => {
                  setPs4Status({kind:"info",message:"Salvando peça e traçado no servidor..."});
                  await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
                  setPa2Mode(false);
                  setSavedPieceNotice(constructionMethod === "PS4"
                    ? "Prévia PS4 fechada e rascunho salvo — pendente de acurácia orbital"
                    : "Construção salva e prévia atualizada");
                });
              }}>{actionBusy ? "Salvando..." : "Concluir, salvar e voltar à peça"}</button>
            {constructionMethod === "PS4" && <button type="button" className="pecas-secondary"
              disabled={actionBusy}
              onClick={() => void runAction(async () => {
                setPs4Status({kind:"info",message:"Salvando rascunho PS4 sem fechamento..."});
                await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
                setPa2Mode(false);
                setSavedPieceNotice("Rascunho PS4 salvo sem fechamento; complete antes da planta");
              })}>Salvar rascunho sem fechar</button>}
          </div>
          {(actionError || actionBusy) && <div role={actionError ? "alert" : "status"}
            aria-live="polite" style={{ marginBottom: 8, padding: "10px 12px",
              borderRadius: 8, background: actionError ? "#fff1ed" : "#e8f3ed",
              color: actionError ? "#932a1c" : "#12513b", fontWeight: 600 }}>
            {actionError ? "Não foi possível concluir: " + actionError : "Processando e salvando..."}
          </div>}
          <div role="toolbar" aria-label="Métodos de construção e ferramentas cartográficas"
            style={{ display: "flex", alignItems: "center", gap: 8,
              flexWrap: "wrap", paddingBottom: 12, borderBottom: "1px solid #b8cfc5",
              marginBottom: 12 }}>
            {(["PA1", "PA2", "PT8", "PS4"] as const).map(method => <button
              key={method} type="button"
              className={constructionMethod === method ? "pecas-primary" : "pecas-secondary"}
              onClick={() => {
                setConstructionMethod(method);
                setPs4Status({kind:"info",message: method === "PS4"
                  ? "Método PS4 ativado. Etapa 1: clique sobre a feição na imagem CBERS-4A."
                  : `Método ${method} selecionado. Confira o procedimento e as entradas exigidas.`});
                setPa2Witnesses([]); setPa2Result(null); setMapHint(null);
                setConstructionSide(method === "PT8" ? "FORWARD" : "LEFT");
              }}>
              {method} — {method === "PA1" ? "Paralela"
                : method === "PA2" ? "Interseção/apoio"
                : method === "PS4" ? "Sensores orbitais" : "Alinhamento"}
            </button>)}
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
              Outros métodos:
              <select defaultValue="" aria-label="Métodos dependentes de fontes georreferenciadas">
                <option value="">Selecione uma fonte</option>
                <option value="PS1" disabled>PS1 — Aerofotogrametria (requer projeto fotogramétrico)</option>
                <option value="PS2" disabled>PS2 — Radar aerotransportado (requer validação)</option>

                <option value="PB1" disabled>PB1 — Base cartográfica com precisão conhecida</option>
                <option value="PB2" disabled>PB2 — Base cartográfica sem precisão conhecida</option>
              </select>
            </label>
            <details>
              <summary>Tutorial do método</summary>
              {constructionMethod === "PA1" ? <p>Selecione A e B, informe o
                afastamento perpendicular medido, escolha o lado e indique no mapa
                a posição aproximada. O cálculo projeta o clique na paralela.</p>
                : constructionMethod === "PA2" ? <p>Selecione o procedimento:
                  linha de apoio (dois marcos e clique projetado) ou interseção
                  geométrica (dois alinhamentos). O resultado precisa de revisão.</p>
                : constructionMethod === "PS4"
                ? <p>Ative a cena CBERS-4A no mapa, clique sucessivamente ao longo da feição natural,
                  confirme cada ponto e atribua código V. Sem RMS da ortorretificação, os pontos
                  permanecem como rascunho, fora da ODS e da certificação.</p>
                : <p>Selecione dois marcos e informe a distância medida a partir
                  do primeiro, observando a direção. PT8 é aplicável a tipo M/P,
                  não a V automaticamente.</p>}
            </details>
          </div>
          <div style={{ flex: 1, minHeight: 0, display: "grid",
            gridTemplateColumns: "minmax(325px, 37%) minmax(0, 1fr)", gap: 12 }}>
            <div style={{ overflowY: "auto", minHeight: 0, paddingRight: 8 }}>
                      <div className="pecas-card" aria-label="Construção assistida de vértices virtuais PA2">
                        <h4>Construção de vértices — PA1, PA2, PT8 e PS4</h4>
                        <p>PA1, PA2 e PT8 exigem conversão altimétrica prévia. Método PT8 gera
                          vértices M/P conforme a tabela oficial de compatibilidade; PA1/PA2
                          permitem vértice V, sujeito à conferência técnica.</p>
                        {!verticalCalculated && constructionMethod !== "PS4" && <p className="pecas-warning">
                          Conclua primeiro o cálculo das altitudes normais/ortométricas dos marcos
                          de apoio para habilitar a construção dos vértices.</p>}
                        <p>Após calcular as altitudes físicas, selecione o método adequado.
                          PA1 usa dois marcos, distância perpendicular e lado; PA2 utiliza
                          quatro marcos em duas retas; PT8 usa dois marcos e distância
                          medida a partir do primeiro. O mapa permite escolher visualmente
                          um local, mas o cálculo mantém as restrições geométricas do método. PS4 é independente da conversão altimétrica para criar rascunhos, mas exige acurácia comprovada para exportação.</p>
                        <label className="pecas-check"><input type="checkbox"
                          checked={pa2Mode}
                          onChange={(e) => { setPa2Mode(e.target.checked); setPa2Result(null); }} />
                          Preciso construir vértices adicionais</label>
                        {pa2Mode && <label className="pecas-field">
                          <span>Método de posicionamento</span>
                          <select value={constructionMethod} onChange={e => {
                            setConstructionMethod(e.target.value as "PA1" | "PA2" | "PT8" | "PS4");
                            setPa2Witnesses([]); setPa2Result(null); setMapHint(null);
                            setConstructionSide(e.target.value === "PT8" ? "FORWARD" : "LEFT");
                          }}>
                            <option value="PA1">PA1 — Paralela (tipo V)</option>
                            <option value="PA2">PA2 — Vértice virtual (tipo V)</option>
                            <option value="PT8">PT8 — Alinhamento (tipo M/P)</option>
                            <option value="PS4">PS4 — Sensores orbitais (tipo V, pré-restituição)</option>
                          </select>
                        </label>}
                        {pa2Mode && constructionMethod === "PS4" && <section aria-label="Restituição orbital PS4">
                          <h4>PS4 — Delimitação de feição natural na imagem</h4>
                          <p>Marque pontos sucessivos nas margens do curso d'água visível na imagem.
                            A trilha é apenas um rascunho técnico; nenhum ponto será tratado como certificado,
                            nem transferido automaticamente para ODS ou memorial.</p>
                          <p className="pecas-warning">O PS4 depende da cena ortorretificada, relatório RMS,
                            feição identificável, precisão absoluta compatível com o limite e revisão do RT.
                            Não utilize em cerca, vértices M ou mudança de confrontação.</p>
                          <p><strong>Cena em edição:</strong> CBERS-4A WPM 16/10/2026 (cobertura de teste).</p>
                          <div style={{ border: "1px solid #b8cfc5", borderRadius: 10, padding: 12,
                            background: "#f6faf8", display: "grid", gap: 9 }}>
                            <strong>Fluxo guiado PS4 — 3 etapas</strong>
                            <div aria-label="Andamento da restituição PS4" style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                              <span style={{ fontWeight: 700 }}>1. Marcar V {ps4Draft.length >= 2 ? "✓" : "•"}</span>
                              <span>→</span>
                              <span style={{ fontWeight: 700 }}>2. Fechar perímetro {ps4Ready ? "✓" : "•"}</span>
                              <span>→</span>
                              <span style={{ fontWeight: 700 }}>3. Salvar e revisar</span>
                            </div>
                            <p style={{ margin: 0 }}>{ps4Draft.length < 2
                              ? "Clique na imagem para adicionar pelo menos dois vértices V na sequência da feição."
                              : !ps4Ready
                                ? "Os pontos V já estão ligados. Selecione agora o segmento entre dois marcos para fechar a prévia do imóvel."
                                : "Prévia fechada em azul: confira a geometria, salve o rascunho e retorne à peça."}</p>
                            <div role={ps4Status.kind === "error" ? "alert" : "status"}
                              aria-live="polite" style={{ borderRadius: 8, padding: "9px 11px",
                                background: ps4Status.kind === "error" ? "#fff1ed" : "#e8f3ed",
                                color: ps4Status.kind === "error" ? "#942d19" : "#12513b" }}>
                              {ps4Status.message}
                            </div>
                            <strong>Vértices V provisórios: {ps4Draft.length}</strong>
                            {ps4Draft.length > 0 && <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
                              <button type="button" className="pecas-secondary"
                                onClick={() => {
                                  const last = ps4Draft[ps4Draft.length - 1];
                                  setPs4Draft(old => old.slice(0,-1));
                                  setPs4ClosureConfirmed(false);
                                  setPs4Status({kind:"info",message:`Último vértice ${last.name} desfeito. A prévia de fechamento precisa ser confirmada novamente.`});
                                }}>Desfazer último V</button>
                              <button type="button" className="pecas-secondary"
                                onClick={() => {
                                  if (!window.confirm("Remover todos os pontos V deste rascunho PS4?")) return;
                                  setPs4Draft([]);
                                  setPs4ClosureConfirmed(false);
                                  setPs4Candidate(null);
                                  setPs4Status({kind:"info",message:"Rascunho PS4 limpo. Marque o primeiro vértice na imagem."});
                                }}>Limpar traçado V</button>
                            </div>}
                          </div>
                          <div className="pecas-card" style={{ marginTop: 12 }} aria-label="Fechar prévia da poligonal">
                            <h4>Etapa 2 · Fechar prévia da poligonal</h4>
                            <p>O imóvel já tem os marcos de divisa. Selecione qual <strong>segmento entre marcos consecutivos</strong>
                              deve ser substituído pela sequência V. O sistema conecta o primeiro e último V aos respectivos
                              marcos, conserva os demais limites e fecha a poligonal para revisão, sem alterar o perímetro oficial.</p>
                            <label className="pecas-field"><span>Segmento natural a substituir (início → fim)</span>
                              <select aria-label="Segmento entre marcos para PS4"
                                value={ps4Start} onChange={e => {
                                  setPs4Start(e.target.value);
                                  setPs4ClosureConfirmed(false);
                                  setPs4Status({kind:"info",message:"Segmento selecionado. Confira se os pontos V seguem do marco inicial ao final antes de confirmar."});
                                }}>
                                <option value="">Selecione o segmento...</option>
                                {topconBoundary.map((p,i) => {
                                  const end = topconBoundary[(i+1)%topconBoundary.length];
                                  return <option key={p.name} value={p.name}>
                                    {p.sigef_vertex_code || p.name} → {end.sigef_vertex_code || end.name}
                                  </option>;
                                })}
                              </select>
                            </label>
                            <p className="pecas-note">Ordem adotada: {ps4Start
                              ? (topconBoundary.find(p=>p.name===ps4Start)?.sigef_vertex_code || ps4Start) +
                                " → " + ps4Draft.map(p=>p.name).join(" → ") + " → " +
                                (topconBoundary.find(p=>p.name===ps4End)?.sigef_vertex_code || ps4End)
                              : "nenhum segmento selecionado"}</p>
                            {ps4Start && <p className={ps4Closure.valid ? "pecas-note" : "pecas-warning"}
                              role={ps4Closure.valid ? "status" : "alert"}>{ps4Closure.message}</p>}
                            <label className="pecas-check"><input type="checkbox"
                              disabled={!ps4Closure.valid}
                              checked={ps4ClosureConfirmed && ps4Closure.valid}
                              onChange={e => {
                                setPs4ClosureConfirmed(e.target.checked);
                                setPs4Status(e.target.checked
                                  ? {kind:"success",message:"Prévia de poligonal fechada! Confira o contorno azul no mapa. Ainda pendente de validação técnica PS4."}
                                  : {kind:"info",message:"Prévia de fechamento desmarcada. Selecione o segmento e confirme."});
                              }}/>
                              Confirmo a sequência dos V e a ligação com esses dois marcos (somente prévia).
                            </label>
                            <button type="button" className="pecas-primary" disabled={!ps4Ready}
                              onClick={() => setPs4Status({kind:"success",message:
                                "Fechamento revisado geometricamente. Próximo: Concluir, salvar e voltar à peça; depois revisar a planta provisória."})}>
                              Verificar prévia fechada
                            </button>
                            <p className="pecas-note">Contorno azul tracejado = poligonal proposta, não certificada.
                              A precisão PS4 e os dados oficiais do perímetro ainda dependem de revisão do RT.</p>
                          </div>
                          {ps4Candidate && <div className="pecas-card" role="group" aria-label="Nomear vértice PS4">
                            <p>Posição clicada: {ps4Candidate.latitude.toFixed(8)}°, {ps4Candidate.longitude.toFixed(8)}°.</p>
                            <label className="pecas-field"><span>Código do novo vértice V</span>
                              <input value={ps4CandidateName} onChange={e => setPs4CandidateName(e.target.value)}
                                aria-label="Código do novo vértice PS4" />
                            </label>
                            <p className="pecas-note">Numeração sugerida somente dentro desta peça.
                              A reserva de códigos por usuário credenciado ainda depende de serviço transacional.</p>
                            <label className="pecas-check"><input type="checkbox"
                              checked={ps4ConfirmFeature} onChange={e => setPs4ConfirmFeature(e.target.checked)} />
                              Confirmo que identifiquei visualmente a feição natural nesta cena.
                            </label>
                            <button type="button" className="pecas-primary" onClick={addPs4DraftPoint}>
                              Adicionar V ao rascunho
                            </button>
                            <button type="button" className="pecas-secondary" onClick={() => {
                              setPs4Candidate(null);
                              setPs4Status({kind:"info",message:"Ponto candidato cancelado. Nenhum vértice foi criado."});
                            }}>
                              Cancelar ponto
                            </button>
                          </div>}
                          {ps4Notice && <p role="status" className="pecas-note">{ps4Notice}</p>}
                          {ps4Draft.length > 0 && <div style={{ overflowX: "auto" }}>
                            <table><thead><tr><th>Código</th><th>Latitude</th><th>Longitude</th><th>Ação</th></tr></thead>
                              <tbody>{ps4Draft.map((point, index) => <tr key={point.name}>
                                <td>{point.name}</td><td>{point.latitude.toFixed(8)}</td>
                                <td>{point.longitude.toFixed(8)}</td>
                                <td><button type="button" className="pecas-secondary"
                                  onClick={() => {
                                    setPs4Draft(old => old.filter((_, i) => i !== index));
                                    setPs4ClosureConfirmed(false);
                                    setPs4Status({kind:"info",message:`Vértice ${point.name} removido. Confira e feche novamente a poligonal.`});
                                  }}>
                                  Remover
                                </button></td>
                              </tr>)}</tbody>
                            </table>
                          </div>}
                          <p>Use “Salvar peça” para guardar o traçado no rascunho associado ao usuário autenticado.
                            A atribuição definitiva de código SIGEF dependerá de validação e unicidade.</p>
                        </section>}
                        {pa2Mode && constructionMethod !== "PS4" && <>
                          {constructionMethod === "PA2" && <label className="pecas-field">
                            <span>Procedimento de construção PA2</span>
                            <select value={pa2Variant} onChange={(event) => {
                              setPa2Variant(event.target.value as typeof pa2Variant);
                              setPa2Witnesses([]); setPa2Result(null); setMapHint(null);
                            }}>
                              <option value="SUPPORT_LINE">Linha de apoio entre dois marcos + clique projetado</option>
                              <option value="INTERSECTION">Interseção geométrica de duas retas (quatro marcos)</option>
                            </select>
                          </label>}
                          <p>No mapa à direita, selecione os marcos diretamente posicionados.
                            O clique no terreno é um indicador visual de posição e nunca
                            substitui a distância ou o afastamento medido em campo.</p>
                          {constructionMethod !== "PA2" && <>
                            <label className="pecas-field"><span>
                              {constructionMethod === "PA1" ? "Afastamento perpendicular medido (m)"
                                : "Distância medida a partir do primeiro marco (m)"}
                            </span>
                              <input type="number" min="0" step="any"
                                value={constructionDistance}
                                onChange={e => { setConstructionDistance(e.target.value); setPa2Result(null); }} />
                            </label>
                            <label className="pecas-field"><span>Direção geométrica</span>
                              <select value={constructionSide} onChange={e => {
                                setConstructionSide(e.target.value as typeof constructionSide);
                                setPa2Result(null);
                              }}>
                                {constructionMethod === "PA1" ? <>
                                  <option value="LEFT">Esquerda de A → B</option>
                                  <option value="RIGHT">Direita de A → B</option>
                                </> : <>
                                  <option value="FORWARD">No sentido A → B</option>
                                  <option value="BACKWARD">No sentido contrário</option>
                                </>}
                              </select>
                            </label>
                            {mapHint && <p>Posição aproximada clicada: {mapHint.latitude.toFixed(7)}°,
                              {" "}{mapHint.longitude.toFixed(7)}°. Informe a distância medida,
                              pois o clique não define coordenada para certificação.</p>}
                          </>}
                          <p><strong>Alinhamento A:</strong> {pa2Witnesses[0] || "—"}
                            {" → "}{pa2Witnesses[1] || "—"}
                            {constructionMethod === "PA2" && pa2Variant === "INTERSECTION" && <>
                              {" · "}<strong>Alinhamento B:</strong> {pa2Witnesses[2] || "—"}
                              {" → "}{pa2Witnesses[3] || "—"}
                            </>}</p>
                          <label className="pecas-check">
                            <input type="checkbox" checked={pa2ConfirmedCrs}
                              onChange={(e) => { setPa2ConfirmedCrs(e.target.checked); setPa2Result(null); }} />
                            Confirmo que os marcos estão no mesmo referencial SIRGAS2000,
                            na zona e hemisfério indicados pelo processamento.
                          </label>
                          <button type="button" className="pecas-primary"
                            disabled={pa2Busy || !verticalCalculated ||
                              pa2Witnesses.length !== (constructionMethod === "PA2" && pa2Variant === "INTERSECTION" ? 4 : 2) ||
                              (constructionMethod === "PA2" && pa2Variant === "SUPPORT_LINE" && !mapHint) ||
                              (constructionMethod !== "PA2" &&
                                (!Number.isFinite(Number(constructionDistance)) || constructionDistance === ""))}
                            onClick={() => void calculatePa2()}>
                            {pa2Busy ? "Calculando..." : "Calcular " + constructionMethod}
                          </button>
                          {constructionMethod === "PT8" && <label className="pecas-check">
                            <input type="checkbox" checked={pt8PointConfirmed}
                              onChange={event => setPt8PointConfirmed(event.target.checked)} />
                            Confirmo em campo a caracterização do ponto como vértice do tipo P
                            (PT8 não pode gerar um vértice do tipo V).
                          </label>}
                          {pa2Result && <div role="status">
                            {pa2Result.physical_altitude_m != null && <p>
                              <strong>Altitude física interpolada:</strong>{" "}
                              {pa2Result.physical_altitude_m.toLocaleString("pt-BR",
                                { minimumFractionDigits: 2, maximumFractionDigits: 4 })} m
                              {" "}({pa2Result.physical_altitude_type}).
                              A altura elipsoidal h será determinada separadamente.
                            </p>}
                            {pa2Result.sigma_e_m != null && pa2Result.sigma_n_m != null
                              ? <p>Sigmas sugeridos pelos marcos: σE =
                                  {pa2Result.sigma_e_m.toLocaleString("pt-BR")} m,
                                  σN = {pa2Result.sigma_n_m.toLocaleString("pt-BR")} m.
                                  Sujeitos a conferência da metodologia e do RT.</p>
                              : <p className="pecas-note">
                                  Os marcos de apoio não possuem sigmas individuais suficientes
                                  para calcular as sugestões. Reimporte os desvios-padrão de
                                  coordenadas ajustadas do TOPCON.</p>}

                            <p><strong>{pa2Result.vertex_type} preliminar:</strong> E {pa2Result.easting_m.toLocaleString("pt-BR", {maximumFractionDigits:4})} m
                              {" · "}N {pa2Result.northing_m.toLocaleString("pt-BR", {maximumFractionDigits:4})} m
                              {pa2Result.angle_deg_acute != null &&
                                <>{" · "}Ângulo agudo {pa2Result.angle_deg_acute.toLocaleString("pt-BR")}°</>}</p>
                            {pa2Result.warnings.map((warning, i) => <p key={i} className="pecas-note">{warning}</p>)}
                            <label className="pecas-field">
                              <span>Inserir V após qual vértice de limite?</span>
                              <select value={pa2InsertAfter} onChange={(event) => setPa2InsertAfter(event.target.value)}>
                                <option value="">Selecione o segmento do perímetro</option>
                                {topconBoundary.map((point) => <option key={point.name} value={point.name}>
                                  Após {point.name} — parcela {point.parcel_number}
                                </option>)}
                              </select>
                            </label>
                            <button type="button" className="pecas-secondary"
                              disabled={!pa2ConfirmedCrs || (constructionMethod === "PT8" && !pt8PointConfirmed) ||
                                !pa2InsertAfter || !Number.isFinite(pa2Result.latitude)}
                              onClick={addProvisionalPa2}>
                              {constructionMethod === "PT8"
                                ? "Adicionar P provisório e renomear na tabela"
                                : "Adicionar V provisório e renomear na tabela"}
                            </button>
                            <p className="pecas-note">h e sigmas não são estimados sem método altimétrico,
                              matriz de covariância e revisão do responsável técnico.
                              O vértice permanecerá com pendências de exportação.
                              O resultado físico e as sugestões de precisão serão mantidos no rascunho.</p>
                          </div>}
                          {pa2Error && <p role="alert" className="pecas-warning">{pa2Error}</p>}
                        </>}
                      </div>


            </div>
            <div style={{ overflow: "auto", minHeight: 0 }}>
              <div className="pecas-card">
                  <h4>Mapa ampliado — {constructionMethod}</h4>
                  <Pa2WitnessMap
                    polygonGeometry={displaySituationGeometry}
                    polygonKey={displaySituationKey}
                    points={[...topconPreview.points.map(point => ({
                      ...point,
                      label: topconBoundary.find(p => p.name === point.name)?.sigef_vertex_code || point.name,
                    })),
                      ...topconBoundary.filter(point =>
                        !topconPreview.points.some(p => p.name === point.name))
                        .map(point => ({
                          name: point.name,
                          label: point.sigef_vertex_code || point.name,
                          longitude: point.longitude, latitude: point.latitude,
                          virtual: true,
                        }))]}
                    selected={pa2Witnesses}
                    method={constructionMethod}
                    ps4Points={ps4Draft}
                    ps4Candidate={ps4Candidate}
                    ps4ClosureGeometry={ps4PreviewGeometry}
                    onPs4Click={point => {
                      setPs4Candidate(point);
                      setPs4CandidateName(ps4SuggestedName());
                      setPs4ConfirmFeature(false);
                      setPs4Notice("");
                      setPs4Status({ kind: "info", message: "Ponto localizado na imagem. Confirme a feição e o nome antes de adicionar V." });
                    }}
                    supportLineMode={constructionMethod === "PA2" && pa2Variant === "SUPPORT_LINE"}
                    intersection={pa2Result}
                    hint={mapHint} onPositionHint={point => {
                      setMapHint(point); setPa2Result(null);
                      const a = topconPreview.points.find(p => p.name === pa2Witnesses[0]);
                      const b = topconPreview.points.find(p => p.name === pa2Witnesses[1]);
                      if (constructionMethod !== "PA2" && a && b && Number.isFinite(a.longitude)
                          && Number.isFinite(a.latitude) && Number.isFinite(b.longitude)
                          && Number.isFinite(b.latitude)) {
                        const cosine = Math.cos((a.latitude as number) * Math.PI / 180);
                        const dx = ((b.longitude as number) - (a.longitude as number)) * cosine;
                        const dy = (b.latitude as number) - (a.latitude as number);
                        const px = (point.longitude - (a.longitude as number)) * cosine;
                        const py = point.latitude - (a.latitude as number);
                        if (constructionMethod === "PA1") {
                          setConstructionSide(dx * py - dy * px >= 0 ? "LEFT" : "RIGHT");
                        } else setConstructionSide(dx * px + dy * py >= 0 ? "FORWARD" : "BACKWARD");
                      }
                    }}
                    onPick={name => {
                      if (!topconPreview.points.some(point => point.name === name)) {
                        setPa2Error("Selecione como testemunhos os marcos diretamente posicionados no TOPCON.");
                        return;
                      }
                      pickPa2Witness(name);
                    }} />
                  {constructionMethod !== "PS4" ? <>
                    <button type="button" className="pecas-secondary"
                      onClick={() => { setPa2Witnesses([]); setPa2Result(null); setPa2Error(""); }}>
                      Limpar testemunhos selecionados
                    </button>
                    <p className="pecas-note">Clique nos marcos no mapa e amplie o zoom para
                      conferir o alinhamento. O local clicado não equivale a levantamento de campo,
                      nem fornece altura elipsoidal ou precisão topográfica.</p>
                  </> : <p className="pecas-note">
                    Os pontos PS4 são registros provisórios de restituição visual,
                    sem h ou desvio-padrão homologado. Salve a peça para guardar este traçado.
                  </p>}
                </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
