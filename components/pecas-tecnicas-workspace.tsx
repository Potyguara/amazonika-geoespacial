"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Download, FileText, Map, X } from "lucide-react";
import { SituationMapPreview, type SituationSnapshot } from "@/components/situation-map-preview";
import { Pa2WitnessMap } from "@/components/pa2-witness-map";
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
  sigma_h_m: number | null;
  confrontant_cns: string;
  confrontant_registration: string;
  height_reference_confirmed: boolean;
  point_role: "BOUNDARY";
  parcel_number: string;
  parcel_name: string;
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
  onRenamePolygon, onRenameVertex, onConfrontant, onAdoptTopconParcels, memorialText,
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
  const [topconBoundary, setTopconBoundary] = useState<TopconBoundaryPoint[]>([]);
  const [topconReview, setTopconReview] = useState<TopconReview | null>(null);
  const [topconReviewBusy, setTopconReviewBusy] = useState(false);
  const [pa2Mode, setPa2Mode] = useState(false);
  const [constructionMethod, setConstructionMethod] = useState<"PA1" | "PA2" | "PT8">("PA2");
  const [constructionDistance, setConstructionDistance] = useState("");
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
    sigma_e_m: number | null; sigma_n_m: number | null; sigma_h_m: number | null;
    warnings: string[]; ready_for_sigef: boolean;
  } | null>(null);
  const [pa2Busy, setPa2Busy] = useState(false);
  const [pa2Error, setPa2Error] = useState("");
  const [verticalModel, setVerticalModel] = useState<"hgeoHNOR2020" | "MAPGEO2015">("hgeoHNOR2020");
  const [verticalFactors, setVerticalFactors] = useState<Record<string, string>>({});
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
          points: topconBoundary.map((point) => ({
            name: point.name,
            latitude: point.latitude,
            longitude: point.longitude,
            ellipsoidal_height_m: point.ellipsoidal_height_m,
            height_reference_confirmed: Boolean(verticalConfirmed[point.name]),
            conversion_factor_m: verticalFactors[point.name] ?? "",
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
    const limit = constructionMethod === "PA2" ? 4 : 2;
    setPa2Witnesses((old) => old.includes(name) ? old.filter((n) => n !== name)
      : old.length >= limit ? [name] : [...old, name]);
  };
  const calculatePa2 = async () => {
    if (!topconPreview || !verticalCalculated ||
        pa2Witnesses.length !== (constructionMethod === "PA2" ? 4 : 2)) return;
    setPa2Busy(true); setPa2Error(""); setPa2Result(null);
    try {
      const witnesses = pa2Witnesses.map((name) => topconPreview.points.find((p) => p.name === name));
      if (witnesses.some((point) => !point)) throw new Error("Marco de apoio não encontrado no relatório.");
      const response = await fetch(`${getApiUrl()}/technical-pieces/topcon/${
        constructionMethod === "PA2" ? "pa2-intersection" : "constructed-vertex"
      }`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          witnesses: witnesses.map((point) => ({
            name: point?.name, easting_m: point?.easting_m, northing_m: point?.northing_m,
          })),
          utm_zone: topconPreview.project.utm_zone,
          hemisphere: topconPreview.project.hemisphere,
          sirgas2000_confirmed: pa2ConfirmedCrs,
          ...(constructionMethod === "PA2" ? {} : {
            method: constructionMethod, distance_m: Number(constructionDistance),
            side: constructionSide,
          }),
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof payload?.detail === "string"
        ? payload.detail : "Não foi possível calcular a interseção PA2.");
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
    if (constructionMethod === "PT8") {
      setPa2Error("PT8 exige vértice do tipo M ou P; a criação automática como V está bloqueada.");
      return;
    }
    const used = new Set([...topconPreview.points.map((p) => p.name),
      ...topconBoundary.map((p) => p.name)]);
    let suffix = 1;
    while (used.has(`V${String(suffix).padStart(3, "0")}`)) suffix++;
    const name = `V${String(suffix).padStart(3, "0")}`;
    const newVertex: TopconBoundaryPoint = {
      ...previous, name,
      northing_m: pa2Result.northing_m, easting_m: pa2Result.easting_m,
      latitude: pa2Result.latitude, longitude: pa2Result.longitude,
      elevation_reported_m: null, ellipsoidal_height_reported_m: null,
      ellipsoidal_height_m: null, sigma_n_m: null, sigma_e_m: null,
      sigma_hz_m: null, sigma_u_m: null,
      sigma_lon_m: null, sigma_lat_m: null, sigma_h_m: null,
      height_reference_confirmed: false,
      sigef_vertex_code: "", sigef_method: constructionMethod, boundary_type: previous.boundary_type,
      confrontant: previous.confrontant, confrontant_cns: previous.confrontant_cns,
      confrontant_registration: previous.confrontant_registration,
      point_role: "BOUNDARY",
    };
    setTopconBoundary((old) => [...old.slice(0, at + 1), newVertex, ...old.slice(at + 1)]);
    setTopconReview(null); setSigefParcelReview(null); setSigefValidatedSignature("");
    setPa2Result(null); setPa2Witnesses([]); setPa2InsertAfter(name);
    setPa2Error("V provisório inserido: informe código SIGEF, h e sigmas com suporte técnico antes de exportar.");
  };
  const updateBoundaryPoint = (index: number, patch: Partial<TopconBoundaryPoint>) => {
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    setVerticalCalculated(null);
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
    setTopconReview(null);
    setVerticalFactors({});
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
                            {topconPreview.points.filter((point) => point.point_role !== "CONTROL")
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
                                          sigma_lon_m: null, sigma_lat_m: null, sigma_h_m: null,
                                          height_reference_confirmed: false,
                                          confrontant_cns: "", confrontant_registration: "",
                                          sigef_method: "", boundary_type: "", confrontant: "" }]
                                        : current.filter((item) => item.name !== point.name));
                                    }} /></td>
                                  <td>{point.name}</td>
                                  <td><input aria-label={`Código SIGEF ${point.name}`} disabled={!selected}
                                    value={selected?.sigef_vertex_code ?? ""}
                                    onChange={(event) => updateBoundaryPoint(index, { sigef_vertex_code: event.target.value })} /></td>
                                  <td><input aria-label={`Parcela do ponto ${point.name}`} disabled={!selected}
                                     value={selected?.parcel_number ?? ""}
                                     onChange={(event) => updateBoundaryPoint(index, { parcel_number: event.target.value })} /></td>
                                   <td><input aria-label={`Denominação da parcela ${point.name}`} disabled={!selected}
                                     value={selected?.parcel_name ?? ""}
                                     onChange={(event) => updateBoundaryPoint(index, { parcel_name: event.target.value })} /></td>
                                   <td><input aria-label={`Altura elipsoidal ${point.name}`} disabled={!selected}
                                    inputMode="decimal" placeholder="Confirmar h"
                                    value={selected?.ellipsoidal_height_m ?? ""}
                                    onChange={(event) => {
                                      const value = event.target.value.trim().replace(",", ".");
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
                        <p><strong>Revisão assistida:</strong> {topconBoundary.filter((p) =>
                          p.sigma_lon_m !== null && p.sigma_lat_m !== null).length}
                          /{topconBoundary.length} vértices com sigmas horizontalmente preenchidos;
                          {topconBoundary.filter((p) => p.height_reference_confirmed).length}
                          /{topconBoundary.length} alturas confirmadas.</p>
                        <p>Os RMS das linhas de base são detectados automaticamente.
                          Para sugerir sigmas individuais, importe no TOPCON o quadro
                          de desvios-padrão dos pontos ajustados (N, E e U) ou a matriz
                          de covariância. A conferência de referencial e a confirmação
                          técnica continuam obrigatórias.</p>
                        <button type="button" className="pecas-secondary"
                          disabled={!topconBoundary.length}
                          onClick={() => {
                            if (!window.confirm("Confirma que você verificou todas as alturas h no referencial SIRGAS2000 e sua época?")) return;
                            setTopconBoundary((old) => old.map((p) => ({ ...p, height_reference_confirmed: true })));
                            setVerticalConfirmed(Object.fromEntries(topconBoundary.map((p) => [p.name, true])));
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
                        <div style={{ overflowX: "auto" }}>
                          <table>
                            <thead><tr><th>Vértice</th><th>σ Longitude (m)</th>
                              <th>σ Latitude (m)</th><th>σ h (m)</th><th>h confirmada</th>
                              <th>CNS confrontante</th><th>Matrícula confrontante</th></tr></thead>
                            <tbody>{topconBoundary.map((point, index) => <tr key={point.name}>
                              <td>{point.sigef_vertex_code || point.name}</td>
                              {(["sigma_lon_m", "sigma_lat_m", "sigma_h_m"] as const)
                                .map((field) => <td key={field}>
                                  <input aria-label={`${field} ${point.name}`} inputMode="decimal"
                                    value={point[field] ?? ""}
                                    onChange={(event) => {
                                      const value = event.target.value.trim().replace(",", ".");
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
                          <p><strong>Conversão concluída. Nenhuma coordenada ou h foi alterada.</strong></p>
                          {verticalCalculated.map((point) => <p key={point.name}>
                            {point.name}: h = {point.ellipsoidal_height_m.toLocaleString("pt-BR")} m;
                            {" "}{verticalModel === "hgeoHNOR2020" ? "HN" : "H"} =
                            {" "}{(point.normal_height_m ?? point.orthometric_height_m)?.toLocaleString("pt-BR")} m
                          </p>)}
                        </div>}
                        <p>Consulte o fator no serviço hgeoHNOR2020 do IBGE e transcreva-o
                          para cada ponto. O sistema ainda não consulta automaticamente esse serviço.</p>
                      </div>
                      <div className="pecas-card" aria-label="Construção assistida de vértices virtuais PA2">
                        <h4>Construção de vértices por geometria analítica — PA1, PA2 ou PT8</h4>
                        <p>Esta etapa sucede a conversão altimétrica. Método PT8 gera
                          vértices M/P conforme a tabela oficial de compatibilidade; PA1/PA2
                          permitem vértice V, sujeito à conferência técnica.</p>
                        {!verticalCalculated && <p className="pecas-warning">
                          Conclua primeiro o cálculo das altitudes normais/ortométricas dos marcos
                          de apoio para habilitar a construção dos vértices.</p>}
                        <p>Se os limites exigirem vértices virtuais, ative o mapa de apoio e indique
                          quatro marcos testemunhos: A1 e A2 definem a primeira reta; B1 e B2
                          definem a segunda. A posição V será calculada na interseção, não por
                          uma escolha visual imprecisa de coordenadas.</p>
                        <label className="pecas-check"><input type="checkbox"
                          disabled={!verticalCalculated} checked={pa2Mode}
                          onChange={(e) => { setPa2Mode(e.target.checked); setPa2Result(null); }} />
                          Preciso construir vértices adicionais</label>
                        {pa2Mode && <label className="pecas-field">
                          <span>Método de posicionamento</span>
                          <select value={constructionMethod} onChange={e => {
                            setConstructionMethod(e.target.value as "PA1" | "PA2" | "PT8");
                            setPa2Witnesses([]); setPa2Result(null); setMapHint(null);
                            setConstructionSide(e.target.value === "PT8" ? "FORWARD" : "LEFT");
                          }}>
                            <option value="PA1">PA1 — Paralela (tipo V)</option>
                            <option value="PA2">PA2 — Interseção de retas (tipo V)</option>
                            <option value="PT8">PT8 — Alinhamento (tipo M/P)</option>
                          </select>
                        </label>}
                        {pa2Mode && <>
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
                            {constructionMethod === "PA2" && <>
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
                              pa2Witnesses.length !== (constructionMethod === "PA2" ? 4 : 2) ||
                              (constructionMethod !== "PA2" &&
                                (!Number.isFinite(Number(constructionDistance)) || constructionDistance === ""))}
                            onClick={() => void calculatePa2()}>
                            {pa2Busy ? "Calculando..." : "Calcular " + constructionMethod}
                          </button>
                          {pa2Result && <div role="status">
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
                              disabled={!pa2ConfirmedCrs || constructionMethod === "PT8" ||
                                !pa2InsertAfter || !Number.isFinite(pa2Result.latitude)}
                              onClick={addProvisionalPa2}>
                              {constructionMethod === "PT8"
                                ? "PT8: requer identificação M/P e revisão específica"
                                : "Adicionar V provisório e renomear na tabela"}
                            </button>
                            <p className="pecas-note">h e sigmas não são estimados sem método altimétrico,
                              matriz de covariância e revisão do responsável técnico.
                              O vértice permanecerá com pendências de exportação.</p>
                          </div>}
                          {pa2Error && <p role="alert" className="pecas-warning">{pa2Error}</p>}
                        </>}
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
            {topconPreview && pa2Mode && Boolean(verticalCalculated)
              ? <div className="pecas-card">
                  <h4>Mapa ampliado — {constructionMethod}</h4>
                  <Pa2WitnessMap points={topconPreview.points} selected={pa2Witnesses}
                    method={constructionMethod} intersection={pa2Result}
                    hint={mapHint} onPositionHint={point => { setMapHint(point); setPa2Result(null); }}
                    onPick={pickPa2Witness} />
                  <button type="button" className="pecas-secondary"
                    onClick={() => { setPa2Witnesses([]); setPa2Result(null); setPa2Error(""); }}>
                    Limpar testemunhos selecionados
                  </button>
                  <p className="pecas-note">Clique nos marcos no mapa e amplie o zoom para
                    conferir o alinhamento. O local clicado não equivale a levantamento de campo,
                    nem fornece altura elipsoidal ou precisão topográfica.</p>
                </div>
              : <SituationMapPreview
                  geometry={displaySituationGeometry}
                  geometryKey={displaySituationKey}
                  saved={previewTopconGeometry ? null : situationSaved}
                  onSave={onSaveSituation}
                  vertexNames={displayVertexNames}
                  showVertices={Boolean(previewTopconGeometry)}
                  previewBasemap={previewTopconGeometry ? "osm" : "satellite"}
                />}
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
