"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Download, FileText, Map, X } from "lucide-react";
import { SituationMapPreview, type SituationSnapshot } from "@/components/situation-map-preview";
import { Pa2WitnessMap } from "@/components/pa2-witness-map";
import { InpeCbersSceneSearch } from "@/components/inpe-cbers-scene-search";
import { Ps4EvidencePanel } from "@/components/ps4-evidence-panel";
import { Ps4RasterDiagnosticCard } from "@/components/ps4-raster-diagnostic-card";
import { Ps4CheckpointAnalysis } from "@/components/ps4-checkpoint-analysis";
import { Pb1SheetLookup } from "@/components/pb1-sheet-lookup";
import { getApiUrl } from "@/lib/api";
import { buildPs4Closure } from "@/lib/ps4-closure";
import { lonLatToSirgasUtm } from "@/lib/utm-sirgas-preview";
import { estimatePs4NormalAltitudes } from "@/lib/ps4-normal-altitude-preview";
import { evaluatePs4Controls, type Ps4Quality, type Ps4Control } from "@/lib/ps4-quality";
import { OfficialOverlapCheck } from "@/components/official-overlap-check";

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
  coordinates?: Array<[number,number]>;
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
  boundary_detail?: string;
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
  ready_for_geometry?: boolean;
  ready_for_ods: boolean;
  missing_sigmas?: string[];
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

type Pb1Source = {sheet:string;product:string;accuracy_reference:string;vertical_datum:string;
  scale?:string;pec?:string;vertical_kind?:string;source_model?:string;vertical_reference?:string};
const PB1_SCALE_OPTIONS=["10000","25000","50000","100000","Outra"];
const PB1_PEC_OPTIONS=["PEC A","PEC B","PEC C","PEC-PCD A","PEC-PCD B","PEC-PCD C","PEC-PCD D","Outra"];
const PB1_DATUM_OPTIONS=["Santana — AP","Imbituba — SC","GRS80 — SIRGAS 2000 (elipsoidal)","Referência local","Outro"];
const PB1_MODEL_OPTIONS=["MAPGEO2010","MAPGEO2015","hgeoHNOR2020","EGM96","EGM2008","NONE","Outro"];
const PB1_KIND_OPTIONS=[["NORMAL","Altitude normal (HN)"],["ORTHOMETRIC","Altitude ortométrica (H)"],["ELLIPSOIDAL","Altitude geométrica (h)"],["OTHER","Outra referência"]];
const PB1_PEC_MM:Record<string,[number,number]>={"PEC A":[0.5,0.3],"PEC B":[0.8,0.5],"PEC C":[1,0.6]};

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
  area_nature?:string;
  sncr?:string;
  stage: number;
  ps4_closure?: { start: string; confirmed: boolean; signature?: string };
  ps4_selected_scene?: string;
  construction_skipped?: boolean;
  construction_requested?: boolean;
  ps4_ortho_report?: {scene_id:string;reference:string;rms_m:number|null;reviewed_by_rt:boolean};
  official_overlap?: {signature:string;status:string;complete:boolean;count:number};
  ps4_quality?: Ps4Quality & {source:string;filename:string;scene_id:string};
  pb1_draft?: Array<{name:string;latitude:number;longitude:number;source_elevation_m:number|null;raster_sha256:string;created_at:string}>;
  pb1_closure?: {start:string;confirmed:boolean;signature?:string};
  pb1_source?: Pb1Source;
  ps4_draft?: Array<{
    name: string; latitude: number; longitude: number; scene_id: string; created_at: string;
  }>;
  construction?: {
    method: "PA1" | "PA2" | "PT8" | "PS4" | "PB1";
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

// Rótulos operacionais — a ODS recebe somente o código oficial do INCRA.
// São descrições do elemento físico, NÃO novos códigos SIGEF.
const BOUNDARY_DETAILS: Record<string, readonly string[]> = {
  LA3:["Estrada","Rodovia","Estrada vicinal","Ramal","Travessão","Rua","Avenida"],
  LA5:["Canal"],
  LA4:["Vala"],
  LA7:["Ferrovia","Linha de transmissão","Aceiro","Outro elemento artificial"],
  LN1:["Rio","Igarapé","Córrego","Lago","Ressaca","Corpo d'água"],
  LN6:["Nascente","Outro elemento natural"],
};

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
  onLegalMetadataChange: (values: Record<string,string>) => void;
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
  onSavePiece: (memorialDraft: string, topconDraft: TopconDraft) => Promise<string>;
  loadedTopconDraft?: TopconDraft | null;
  loadedTopconRevision?: number;
  onSaveMemorial: (text: string | null) => void;
  loadedMemorialDraft?: string | null;
  loadedPieceId?: string | null;
};

const stages = ["Dados do imóvel", "Áreas e vértices", "Memorial", "Planta", "Exportar"];
const premiumSteps = [
  { title: "Importação GNSS", detail: "Pontos e precisões TOPCON", stage: 0, target: "geo96-import" },
  { title: "Vértices do divisor", detail: "Seleção e ordenamento", stage: 0, target: "geo96-vertices" },
  { title: "Conversão altimétrica", detail: "Resultado oficial do IBGE", stage: 0, target: "geo96-altimetry" },
  { title: "Construção de vértices", detail: "PB1 base oficial ou PS4 orbital", stage: 0, target: "geo96-ps4" },
  { title: "Sobreposições SIGEF", detail: "SIGEF Mensais e Brasil", stage: 0, target: "geo97-overlaps" },
  { title: "Áreas e vértices", detail: "Parcela M–V consolidada", stage: 1, target: "" },
  { title: "Memorial", detail: "Conferência dos segmentos", stage: 2, target: "" },
  { title: "Planta", detail: "Prévia e elementos", stage: 3, target: "" },
  { title: "Identificação jurídica", detail: "Titular, matrícula e situação", stage: 4, target: "geo97-legal" },
  { title: "Revisão e exportação", detail: "Documentos preliminares", stage: 4, target: "geo97-export" },
] as const;


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
  open, onClose, data, onDataChange, onLegalMetadataChange, polygons, importedMetadata, selectedIds, rasterKey, onSelect,
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
  const [premiumStep, setPremiumStep] = useState(0);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [workflowNotice, setWorkflowNotice] = useState("");
  const jumpToWorkflow = (index: number) => {
    setShowAllTasks(false);
    if (index >= 5 && index <= 7 && selectedIds.length === 0) {
      setPremiumStep(ps4Ready ? 3 : 1);
      setStage(0);
      setWorkflowNotice(ps4Ready
        ? "Antes de gerar áreas, memorial ou planta, aplique a geometria M–V à parcela preliminar."
        : "Selecione e ordene os marcos GNSS; para o trecho natural, conclua PB1 ou PS4 e aplique a parcela preliminar.");
      return;
    }
    const item = premiumSteps[index];
    setPremiumStep(index);
    setStage(item.stage);
    if (index === 3) {
      if (topconBoundary.length < 2) {
        setWorkflowNotice("Para iniciar PB1 ou PS4, importe e selecione pelo menos dois marcos GNSS do divisor.");
        return;
      }
      setPa2Mode(false);
      setWorkflowNotice("Escolha se o perímetro necessita de vértices adicionais.");
      return;
    }
    setWorkflowNotice("Etapa selecionada: " + item.title + ". Confira os dados antes de continuar.");
    window.setTimeout(() => {
      if (item.target) {
        const target = document.getElementById(item.target);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        else setWorkflowNotice("Esta seção aparece após importar o levantamento GNSS correspondente.");
      }
    }, 50);
  };

  const [topconPreview, setTopconPreview] = useState<TopconPreview | null>(null);
  const [topconLoading, setTopconLoading] = useState(false);
  const [topconError, setTopconError] = useState("");
  const [topconBoundary, setTopconBoundary] = useState<TopconBoundaryPoint[]>([]);
  const [topconReview, setTopconReview] = useState<TopconReview | null>(null);
  const [topconReviewBusy, setTopconReviewBusy] = useState(false);
  const [topconReviewFeedback, setTopconReviewFeedback] = useState<{status:"info"|"error"|"success";message:string}|null>(null);
  const [pa2Mode, setPa2Mode] = useState(false);
  const [constructionSkipped,setConstructionSkipped] = useState(false);
  const [constructionRequested,setConstructionRequested] = useState(false);
  const [constructionMethod, setConstructionMethod] = useState<"PA1" | "PA2" | "PT8" | "PS4" | "PB1">("PS4");
  const [ps4Draft, setPs4Draft] = useState<NonNullable<TopconDraft["ps4_draft"]>>([]);
  const [pb1IbgeOutput,setPb1IbgeOutput]=useState("");
  const [pb1IbgeFilename,setPb1IbgeFilename]=useState("");
  const [pb1Technical,setPb1Technical]=useState({vertical_kind:"",vertical_datum:"",vertical_reference:"",accuracy_reference:"",sigma_e_m:"",sigma_n_m:"",source_sigma_m:"",limit_category:"",factor_reference:"",factors:""});
  const [pb1TechnicalResult,setPb1TechnicalResult]=useState<{points:Array<{vertex_id:string;source_value_m:number;h_ellipsoidal_m:number;sigma_h_m:number|null}>;horizontal_sigma_m:number;limit_m:number;meets_numeric_threshold:boolean}|null>(null);
  const [pb1Draft,setPb1Draft] = useState<NonNullable<TopconDraft["pb1_draft"]>>([]);
  const [pb1Start,setPb1Start] = useState("");
  const [pb1ClosureConfirmed,setPb1ClosureConfirmed] = useState(false);
  const [pb1ConfirmedSignature,setPb1ConfirmedSignature] = useState("");
  const [pb1Candidate,setPb1Candidate] = useState<{longitude:number;latitude:number}|null>(null);
  const [pb1Notice,setPb1Notice] = useState("");
  const [pb1Busy,setPb1Busy] = useState(false);
  const [pb1Diagnostic,setPb1Diagnostic]=useState<{rows:Array<{name:string;h_gnss_m:number|null;hn_ibge_m:number|null;mdt_m:number|null;residual_hn_m:number|null;error?:string}>;vs_hn:{count:number;mean_m:number;rmse_m:number;sample_std_m:number|null;max_abs_m:number}|null;vs_h:{count:number;mean_m:number;rmse_m:number;sample_std_m:number|null;max_abs_m:number}|null}|null>(null);
  const runPb1Diagnostic=async()=>{
    setPb1Busy(true);setPb1Diagnostic(null);setPb1Notice("");
    try{
      const id=await onSavePiece(editableMemorial.trim(),draftForSave());
      const res=await fetch(getApiUrl()+"/technical-pieces/"+id+"/pb1/diagnostic",{credentials:"include",cache:"no-store"});
      const body=await res.json();
      if(!res.ok)throw new Error(typeof body.detail==="string"?body.detail:"Diagnóstico indisponível.");
      setPb1Diagnostic(body);
    }catch(e){setPb1Notice(e instanceof Error?e.message:"Falha no diagnóstico.");}
    finally{setPb1Busy(false);}
  };

  const [pb1PieceId,setPb1PieceId] = useState<string|null>(null);
  const [pb1Assets,setPb1Assets] = useState<Record<string,{
    sha256:string;size_bytes:number;kind:string;metadata?:{width?:number;height?:number;bands?:Array<{type?:string}>;
      wgs84_extent?:{type:string;coordinates:number[][][]};
      crs_authority?:string|null; vertical_crs_name?:string|null;
      embedded_source_tags?:Record<string,string>};
  }>>({});
  const [pb1Source,setPb1Source] = useState<Pb1Source>({sheet:"",product:"",accuracy_reference:"",vertical_datum:""});
  const [ps4SceneId,setPs4SceneId] = useState("CBERS4A_WPM_PCA_RGB321_20261016_214_113");
  const [ps4Armed,setPs4Armed] = useState(false);
  const [ps4ApprovalConfirmed, setPs4ApprovalConfirmed] = useState(false);
  const [ps4ReportAttached, setPs4ReportAttached] = useState(false);
  const [ps4ImportRevision, setPs4ImportRevision] = useState(0);
  const [ps4RasterAsset, setPs4RasterAsset] = useState<{
    kind: "raster" | "report"; sha256: string; size_bytes: number;
    metadata?: { width?: number; height?: number; crs_wkt?: string;
      wgs84_extent?: { type: string; coordinates: number[][][] } };
  } | null>(null);
  const [ps4OrthoReport,setPs4OrthoReport] = useState<NonNullable<TopconDraft["ps4_ortho_report"]>>({
    scene_id:"",reference:"",rms_m:null,reviewed_by_rt:false,
  });
  const [officialOverlap, setOfficialOverlap] = useState<TopconDraft["official_overlap"]>(undefined);
  const [ps4Quality, setPs4Quality] = useState<TopconDraft["ps4_quality"]>(undefined);
  const [ps4QualitySource, setPs4QualitySource] = useState("");
  const [ps4QualityError, setPs4QualityError] = useState("");
  const [ps4Start, setPs4Start] = useState("");
  const [ps4ClosureConfirmed, setPs4ClosureConfirmed] = useState(false);
  const [ps4ConfirmedSignature, setPs4ConfirmedSignature] = useState("");
  const [ps4Status, setPs4Status] = useState<{ kind: "success" | "error" | "info"; message: string }>({
    kind: "info", message: "Etapa 1/3: marque os vértices V no mapa; depois feche o trecho entre dois marcos."
  });
  const [ps4Candidate, setPs4Candidate] = useState<{ longitude: number; latitude: number } | null>(null);
  const [ps4CheckCapture,setPs4CheckCapture] = useState(false);
  const [ps4CheckPoint,setPs4CheckPoint] = useState<{longitude:number;latitude:number}|null>(null);
  const [ps4CandidateName, setPs4CandidateName] = useState("");
  const [ps4Notice, setPs4Notice] = useState("");
  const [ps4ConfirmFeature, setPs4ConfirmFeature] = useState(false);
  const PS4_SCENE = ps4SceneId;
  const ps4StartIndex = topconBoundary.findIndex(p => p.name === ps4Start);
  const ps4End = ps4StartIndex < 0 ? "" :
    topconBoundary[(ps4StartIndex + 1) % topconBoundary.length]?.name ?? "";
  const ps4Closure = buildPs4Closure(topconBoundary, ps4Draft, ps4Start, ps4End);
  const ps4Signature = JSON.stringify({
    start: ps4Start,
    boundary: topconBoundary.map(p => [p.name, p.sigef_vertex_code, p.longitude, p.latitude]),
    draft: ps4Draft.map(p => [p.name, p.longitude, p.latitude, p.scene_id]),
  });
  const ps4Ready = ps4ClosureConfirmed && ps4ConfirmedSignature === ps4Signature && ps4Closure.valid;
  const ps4PreviewGeometry = ps4Ready ? ps4Closure.geometry : null;
  const pb1StartIndex=topconBoundary.findIndex(p=>p.name===pb1Start);
  const pb1End=pb1StartIndex<0?"":topconBoundary[(pb1StartIndex+1)%topconBoundary.length]?.name??"";
  const pb1Closure=buildPs4Closure(topconBoundary,pb1Draft,pb1Start,pb1End);
  const pb1Signature=JSON.stringify({
    start:pb1Start,boundary:topconBoundary.map(p=>[p.name,p.longitude,p.latitude]),
    draft:pb1Draft.map(p=>[p.name,p.longitude,p.latitude,p.source_elevation_m,p.raster_sha256]),
  });
  const pb1Ready=pb1Closure.valid && pb1ClosureConfirmed && pb1Signature===pb1ConfirmedSignature;
  const pb1Raster=pb1Assets.pb1_color;
  const pb1Dtm=pb1Assets.pb1_dtm;
  useEffect(()=>{
    if(!loadedPieceId)return;
    setPb1PieceId(loadedPieceId);
    setPb1TechnicalResult(null);setPb1Diagnostic(null);
    setPb1IbgeOutput("");setPb1IbgeFilename("");
    setPb1Technical({vertical_kind:"",vertical_datum:"",vertical_reference:"",accuracy_reference:"",sigma_e_m:"",sigma_n_m:"",source_sigma_m:"",limit_category:"",factor_reference:"",factors:""});
    let active=true;
    fetch(getApiUrl()+"/technical-pieces/"+loadedPieceId+"/pb1/technical-preview",
      {credentials:"include",cache:"no-store"})
      .then(r=>{if(!r.ok)throw new Error("Não foi possível recuperar a prévia PB1.");return r.json();})
      .then(body=>{
        if(!active||!body?.preview)return;
        const p=body.preview;
        setPb1TechnicalResult(p);
        const inputs=p.inputs??{};
        setPb1Technical({
          vertical_kind:String(inputs.vertical_kind??""),vertical_datum:String(inputs.vertical_datum??""),
          vertical_reference:String(inputs.vertical_reference??""),accuracy_reference:String(inputs.accuracy_reference??""),
          sigma_e_m:String(inputs.sigma_e_m??""),sigma_n_m:String(inputs.sigma_n_m??""),
          source_sigma_m:String(inputs.source_sigma_m??""),limit_category:String(inputs.limit_category??""),
          factor_reference:String(inputs.factor_reference??""),
          factors:Object.entries(inputs.factors??{}).map(([id,values])=>id+";"+(Array.isArray(values)?values.join(";"):"")).join("\n")
        });
      })
      .catch(e=>{if(active)setPb1Notice(String(e.message??e));});
    fetch(`${getApiUrl()}/technical-pieces/${loadedPieceId}/pb1/assets`,
      {credentials:"include",cache:"no-store"})
      .then(r=>r.ok?r.json():null)
      .then(body=>{if(active&&body?.assets)setPb1Assets(body.assets);})
      .catch(()=>undefined);
    return ()=>{active=false;};
  },[loadedPieceId]);

  // A folha deve ser identificada antes da restituição quando a parcela já está desenhada.
  const pb1SelectedParcel = polygons.find(p =>
    selectedIds.includes(p.id) && (p.coordinates?.length ?? 0) >= 3
  );
  const pb1LookupGeometry: Record<string, unknown> | null = pb1SelectedParcel?.coordinates
    ? {type:"Polygon", coordinates:[[
        ...pb1SelectedParcel.coordinates,
        pb1SelectedParcel.coordinates[0],
      ]]}
    : ps4Closure.valid ? (ps4Closure.geometry ?? null) : null;

  const calculatePb1Technical=async()=>{
    setPb1Busy(true);setPb1TechnicalResult(null);setPb1Notice("");
    try{
      const t=pb1Technical;
      if(pb1Source.source_model && pb1Source.source_model!=="Outro"){
        const expected:Record<string,string>={NORMAL:"hgeoHNOR2020",ORTHOMETRIC:"MAPGEO2015",ELLIPSOIDAL:"NONE"};
        if(expected[t.vertical_kind] && pb1Source.source_model!==expected[t.vertical_kind])
          throw new Error("O modelo original declarado ("+pb1Source.source_model+") difere do modelo de conversão disponível. Verifique a compatibilidade documental; a conversão direta não está habilitada.");
      }

      if(!t.vertical_kind||!t.limit_category||[t.sigma_e_m,t.sigma_n_m,t.source_sigma_m].some(v=>!v.trim()))throw new Error("Preencha o tipo vertical, categoria do limite e sigmas documentados.");
      const factors:Record<string,number[]>={};
      for(const line of (pb1IbgeOutput&&t.vertical_kind==="NORMAL"?"":t.factors).trim().split(/\r?\n/).filter(Boolean)){
        const [id,eta,sigma,...extra]=line.trim().split(/[;\s]+/);
        if(!id||!eta||!sigma||extra.length||factors[id])throw new Error("Fatores: uma linha por V, código;fator;sigma.");
        const values=[eta,sigma].map(v=>Number(v.replace(",",".")));
        if(values.some(v=>!Number.isFinite(v)))throw new Error("Fator inválido: "+id);
        factors[id]=values;
      }
      const id=await onSavePiece(editableMemorial.trim(),draftForSave());
      const res=await fetch(getApiUrl()+"/technical-pieces/"+id+"/pb1/technical-preview",{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({...t,factors,ibge_output:t.vertical_kind==="NORMAL"?pb1IbgeOutput:"",sigma_e_m:Number(t.sigma_e_m.replace(",",".")),sigma_n_m:Number(t.sigma_n_m.replace(",",".")),source_sigma_m:Number(t.source_sigma_m.replace(",","."))})
      });
      const body=await res.json();
      if(!res.ok)throw new Error(typeof body.detail==="string"?body.detail:"Dados técnicos inválidos.");
      setPb1TechnicalResult(body);
      setPb1Notice("Prévia calculada e salva no servidor. Não constitui aprovação RT.");
    }catch(e){setPb1Notice(e instanceof Error?e.message:"Falha no cálculo PB1.");}
    finally{setPb1Busy(false);}
  };
  const pb1Upload=async(kind:"pb1_color"|"pb1_dtm",file:File)=>{
    setPb1Busy(true);setPb1Notice("");
    try{
      const id=await onSavePiece(editableMemorial.trim(),draftForSave());
      setPb1PieceId(id);
      const form=new FormData();form.append("file",file);
      const res=await fetch(`${getApiUrl()}/technical-pieces/${id}/pb1/files/${kind}`,
        {method:"POST",credentials:"include",body:form});
      const body=await res.json().catch(()=>null);
      if(!res.ok)throw new Error(typeof body?.detail==="string"?body.detail:"Falha no upload PB1");
      setPb1Assets(old=>({...old,[kind]:body.asset}));
      if(kind==="pb1_color" && pb1Raster?.sha256!==body.asset.sha256){
        setPb1Draft([]);setPb1ClosureConfirmed(false);setPb1ConfirmedSignature("");
      }
      if(kind==="pb1_dtm" && pb1Dtm?.sha256!==body.asset.sha256){
        setPb1Draft(old=>old.map(p=>({...p,source_elevation_m:null})));
        setPb1ClosureConfirmed(false);
      }
      setPb1Notice(`${kind==="pb1_color"?"ORIXP RGB":"MDT numérico"} vinculado à peça. A aprovação PB1 permanece pendente.`);
    }catch(err){setPb1Notice(err instanceof Error?err.message:"Erro no upload PB1");}
    finally{setPb1Busy(false);}
  };
  const pb1AddPoint=async()=>{
    if(!pb1Candidate||!pb1Raster||!pb1PieceId)return;
    setPb1Busy(true);setPb1Notice("");
    try{
      const prefix=(rtProfile?.incra_code??"").trim().toUpperCase().replace(/[^A-Z0-9]/g,"");
      const code=prefix.length>=3&&prefix.length<=6?prefix:"VIRTUAL";
      const taken=new Set([...topconBoundary.map(p=>p.sigef_vertex_code||p.name),
        ...ps4Draft.map(p=>p.name),...pb1Draft.map(p=>p.name)].map(v=>v.toUpperCase()));
      let i=1;while(taken.has(`${code}-V-${String(i).padStart(4,"0")}`))i++;
      const name=`${code}-V-${String(i).padStart(4,"0")}`;
      let elevation:number|null=null;
      if(pb1Dtm){
        const res=await fetch(`${getApiUrl()}/technical-pieces/${pb1PieceId}/pb1/dtm/sample`,
          {method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
           body:JSON.stringify(pb1Candidate)});
        const body=await res.json().catch(()=>null);
        if(!res.ok)throw new Error(typeof body?.detail==="string"?body.detail:"MDT não amostrado");
        elevation=Number(body.source_elevation_m);
        if(!Number.isFinite(elevation))throw new Error("Valor MDT inválido");
      }
      setPb1Draft(old=>[...old,{name,...pb1Candidate,source_elevation_m:elevation,
        raster_sha256:pb1Raster.sha256,
        created_at:new Date().toISOString()}]);
      setPb1ClosureConfirmed(false);
      setPb1Candidate(null);
      setPb1Notice(`Vértice ${name} criado por PB1. Altitude original: ${elevation??"MDT pendente"}; h elipsoidal não calculada.`);
    }catch(err){setPb1Notice(err instanceof Error?err.message:"Falha na captura PB1");}
    finally{setPb1Busy(false);}
  };
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
  const [areaNature,setAreaNature] = useState("");
  const [sncr,setSncr] = useState("");
  const [sigefParcelReview, setSigefParcelReview] = useState<{
    status: string; errors: string[]; warnings: string[];
    parcels: Array<{ number: string; area_ha: number }>;
  } | null>(null);
  const [sigefParcelBusy, setSigefParcelBusy] = useState(false);
  const [sigefValidatedSignature, setSigefValidatedSignature] = useState("");
  const [reviewedOdsBusy, setReviewedOdsBusy] = useState(false);
  const [workingOdsBusy,setWorkingOdsBusy] = useState(false);
  const [workingOdsError,setWorkingOdsError] = useState("");
  const downloadWorkingSigefOds = async () => {
    setWorkingOdsBusy(true);setWorkingOdsError("");
    try {
      const parcels=polygons.filter(p=>selectedIds.includes(p.id)).map((parcel,index)=>{
        if(!parcel.coordinates || parcel.coordinates.length!==parcel.vertices.length)
          throw new Error("Coordenadas da parcela "+parcel.name+" indisponíveis. Salve a parcela antes da exportação.");
        return {
          name:parcel.name,number:String(index+1),
          vertices:parcel.vertices.map((name,i)=>{
            const details=parcel.vertexDetails?.[i]??{};
            const coord=parcel.coordinates![i];
            const height=details.height_reference_confirmed===true ?
              parcel.altitudes[i]?.trim() : "";
            return {
              sigef_vertex_code:name,
              longitude:coord[0],latitude:coord[1],
              ellipsoidal_height_m:height?Number(height.replace(",",".")):null,
              sigma_lon_m:typeof details.sigma_lon_m==="number"?details.sigma_lon_m:null,
              sigma_lat_m:typeof details.sigma_lat_m==="number"?details.sigma_lat_m:null,
              sigma_h_m:typeof details.sigma_h_m==="number"?details.sigma_h_m:null,
              sigef_method:typeof details.sigef_method==="string"?details.sigef_method:"",
              boundary_type:typeof details.boundary_type==="string"?details.boundary_type:"",
              confrontant:parcel.confrontants[i]??"",
              confrontant_cns:typeof details.confrontant_cns==="string"?details.confrontant_cns:"",
              confrontant_registration:typeof details.confrontant_registration==="string"?details.confrontant_registration:"",
            };
          }),
        };
      });
      if(!parcels.length)throw new Error("Selecione uma parcela antes de baixar a ODS de trabalho.");
      const response=await fetch(getApiUrl()+"/technical-pieces/sigef/rascunho-ods",{
        method:"POST",credentials:"include",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({identification:makeSigefIdentity(),parcels}),
      });
      if(!response.ok){
        const info=await response.json().catch(()=>null);
        throw new Error(typeof info?.detail==="string"?info.detail:"Falha na ODS de trabalho (HTTP "+response.status+").");
      }
      downloadBlob(await response.blob(),"RASCUNHO_INCOMPLETO_NAO_SUBMETER_SIGEF.ods");
    }catch(e){setWorkingOdsError(e instanceof Error?e.message:"Falha na ODS de trabalho.");}
    finally{setWorkingOdsBusy(false);}
  };
  const [blankOdsBusy,setBlankOdsBusy] = useState(false);
  const [blankOdsError,setBlankOdsError] = useState("");
  const downloadBlankSigefOds = async () => {
    setBlankOdsBusy(true);setBlankOdsError("");
    try {
      const response=await fetch(getApiUrl()+"/technical-pieces/sigef/modelo-ods",{
        credentials:"include",cache:"no-store",
      });
      if(!response.ok)throw new Error("Modelo SIGEF indisponível (HTTP "+response.status+").");
      const blob=await response.blob();
      downloadBlob(blob,"MODELO_SIGEF_EM_BRANCO.ods");
    }catch(e){setBlankOdsError(e instanceof Error?e.message:"Falha no download do modelo ODS.");}
    finally{setBlankOdsBusy(false);}
  };

  useEffect(() => {
    if (!loadedTopconDraft || loadedTopconDraft.version !== 1) return;
    const d = loadedTopconDraft;
    setTopconPreview(d.preview);
    setTopconBoundary(d.boundary);
    setPs4Draft(d.ps4_draft ?? []);
    setPb1Draft(d.pb1_draft ?? []);
    setPb1Start(d.pb1_closure?.start ?? "");
    setPb1ClosureConfirmed(Boolean(d.pb1_closure?.confirmed));
    setPb1ConfirmedSignature(d.pb1_closure?.signature ?? "");
    setPb1Source(d.pb1_source ?? {sheet:"",product:"",accuracy_reference:"",vertical_datum:""});
    const existingAdditional=Boolean(d.pb1_draft?.length||d.ps4_draft?.length||d.boundary?.some(p=>Boolean(p.derived_calculation)));
    setConstructionSkipped(Boolean(d.construction_skipped)&&!existingAdditional);
    setConstructionRequested(existingAdditional||d.construction_requested===true&&!d.construction_skipped);
    setPs4SceneId(d.ps4_selected_scene || d.ps4_draft?.[0]?.scene_id ||
      "CBERS4A_WPM_PCA_RGB321_20261016_214_113");
    setPs4Armed(Boolean(d.ps4_draft?.length));
    setPs4OrthoReport(d.ps4_ortho_report??{scene_id:"",reference:"",rms_m:null,reviewed_by_rt:false});
    setOfficialOverlap(d.official_overlap);
    setPs4Quality(d.ps4_quality);
    setPs4QualitySource(d.ps4_quality?.source ?? "");
    setPs4Start(d.ps4_closure?.start ?? "");
    setPs4ClosureConfirmed(Boolean(d.ps4_closure?.confirmed));
    setPs4ConfirmedSignature(d.ps4_closure?.signature ?? "");
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
    setAreaNature(d.area_nature??"");setSncr(d.sncr??"");
    setStage(d.stage >= 0 && d.stage <= 4 ? d.stage : 0);
    setPremiumStep(d.stage>0?[0,5,6,7,9][d.stage]:d.ps4_closure?.confirmed?3:0);
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    setPa2Mode(false);
    setConstructionMethod(d.construction?.method === "PT8" ? "PT8" :
      d.construction?.method === "PB1" ? "PB1" : "PS4");
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
    pb1_draft: pb1Draft, pb1_source: pb1Source,
    pb1_closure: {start:pb1Start,confirmed:pb1Ready,signature:pb1Ready?pb1ConfirmedSignature:""},
    ps4_selected_scene: ps4SceneId,
    construction_skipped: constructionSkipped,
    construction_requested: constructionRequested,
    ps4_ortho_report: ps4OrthoReport,
    official_overlap:overlapCurrent?officialOverlap:undefined,
    ps4_quality:ps4Quality,
    ps4_closure: { start: ps4Start, confirmed: ps4Ready,
      signature: ps4Ready ? ps4ConfirmedSignature : "" },
    vertical_model: verticalModel, vertical_factors: verticalFactors,
    vertical_factor_uncertainty: verticalFactorUncertainty,
    vertical_origin: verticalOrigin, vertical_confirmed: verticalConfirmed,
    vertical_calculated: verticalCalculated,
    municipalities: sigefMunicipalities, situation: sigefSituation,
    cns: sigefCns, registration: sigefRegistration,
    area_nature:areaNature, sncr, stage,
    construction: {
      method: constructionMethod, pa2_variant: pa2Variant,
      witnesses: pa2Witnesses, distance: constructionDistance,
      side: constructionSide, crs_confirmed: pa2ConfirmedCrs,
      insert_after: pa2InsertAfter, hint: mapHint,
      last_result: pa2Result,
    },
  });

  const hasAdditionalVertices = pb1Draft.length>0 || ps4Draft.length>0 ||
    topconBoundary.some(p=>Boolean(p.derived_calculation)) ||
    polygons.some(p=>p.vertexDetails?.some(d=>["PB1","PS4","PA1","PA2","PT8"].includes(String(d.sigef_method??""))));
  const openAdditionalVertices = () => {
    setConstructionSkipped(false);setConstructionRequested(true);
    if(pb1Draft.length) setConstructionMethod("PB1");
    else if(ps4Draft.length || !verticalCalculated) setConstructionMethod("PS4");
    setPa2Mode(true);setPa2Error("");
    setWorkflowNotice("Escolha o método no espaço de trabalho cartográfico.");
  };
  const skipAdditionalVertices = async () => {
    // Do not discard an existing draft or adopted geometry through a checkbox.
    if(hasAdditionalVertices){
      setActionError("Existem vértices adicionais registrados. Revise ou remova-os explicitamente antes de dispensar a construção.");
      return;
    }
    setActionBusy(true); setActionError("");
    try {
      await onSavePiece(editableMemorial.trim(), {...draftForSave(), construction_skipped:true, construction_requested:false});
      setConstructionSkipped(true);setConstructionRequested(false);setPa2Mode(false);
      setSavedPieceNotice("Sem vértices adicionais: decisão salva.");
      setWorkflowNotice("Construção adicional dispensada para todos os métodos.");
    } catch(e) {setActionError(e instanceof Error?e.message:"Falha ao salvar a decisão.");}
    finally{setActionBusy(false);}
  };
  const [reviewedOdsError, setReviewedOdsError] = useState("");
  const [reviewedOdsNotice, setReviewedOdsNotice] = useState("");
  const makeSigefIdentity = () => ({
    holder_name: data.owner, holder_document: data.cpf,
    property_name: data.title, service_nature: "Particular",
    area_nature: areaNature || "Particular", sncr, situation: sigefSituation,
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
    if (ps4SigefIncomplete) {
      setReviewedOdsError("ODS preenchida bloqueada: os vértices PS4 exigem acurácia horizontal aprovada, h elipsoidal confirmada e sigmas individuais.");
      return;
    }
    // Original adjusted-point precisions from TOPCON are retained. Manual adjustment
    // and a second confirmation click are optional; mandatory SIGEF columns are not.
    const incomplete = topconBoundary.filter(point =>
      ![point.sigma_lon_m, point.sigma_lat_m, point.sigma_h_m]
        .every(value => typeof value === "number" && Number.isFinite(value) && value > 0));
    if (incomplete.length) {
      setReviewedOdsError("Não é possível produzir a ODS: faltam σ Longitude, σ Latitude ou σ h para " +
        incomplete.map(point => point.sigef_vertex_code || point.name).join(", ") +
        ". Importe o Point Summary com as precisões individuais ajustadas; nenhum valor será inventado.");
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
  const [sigmaImportFeedback, setSigmaImportFeedback] = useState("");
  const importAdjustedSigmas = async (file: File) => {
    setSigmaImportFeedback("");
    try {
      if (file.size > 1024 * 1024) throw new Error("O arquivo não pode exceder 1 MB.");
      const lines = (await file.text()).replace(/^\uFEFF/, "").split(/\r?\n/)
        .map(v => v.trim()).filter(v => v && !v.startsWith("#"));
      if (lines.length < 2) throw new Error("Use CSV com cabeçalho e pelo menos um ponto ajustado.");
      const delim = lines[0].includes(";") ? ";" : lines[0].includes("\t") ? "\t" : ",";
      const fields = (s: string) => s.split(delim).map(v => v.trim().replace(/^"|"$/g,""));
      const normalize = (s: string) => s.toUpperCase().normalize("NFD")
        .replace(/[\u0300-\u036f]/g,"").replace(/[^A-Z0-9]/g,"");
      const header = fields(lines[0]).map(normalize);
      const col = (aliases: string[]) => header.findIndex(x => aliases.includes(x));
      const idCol = col(["ID","PONTO","VERTICE","CODIGO","NAME"]);
      const eCol = col(["SIGMAE","SIGMAEM","SIGMAESTE","SIGMALONGITUDE","SIGMALON"]);
      const nCol = col(["SIGMAN","SIGMANM","SIGMANORTE","SIGMALATITUDE","SIGMALAT"]);
      const hCol = col(["SIGMAH","SIGMAHM","SIGMAALTURA"]);
      if ([idCol,eCol,nCol].some(i => i < 0)) throw new Error(
        "Cabeçalho esperado: ID;SIGMA_E;SIGMA_N;SIGMA_H (metros). " +
        "Utilize as precisões dos pontos ajustados, não RMS das linhas de base.");
      const parseValue = (text: string, label: string) => {
        const value = Number(text.replace(",","."));
        if (!text || !Number.isFinite(value) || value < 0 || value > 100)
          throw new Error("Valor de precisão inválido em "+label);
        return value;
      };
      const lookup = new globalThis.Map<string, TopconBoundaryPoint>();
      for(const p of topconBoundary) {
        lookup.set(normalize(p.name),p);
        if(p.sigef_vertex_code)lookup.set(normalize(p.sigef_vertex_code),p);
      }
      const changes = new globalThis.Map<string,{e:number;n:number;h:number|null}>();
      for(const line of lines.slice(1)){
        const cells=fields(line), id=cells[idCol] || "";
        const point=lookup.get(normalize(id));
        if(!point)throw new Error("Ponto não encontrado na peça: "+id);
        if(changes.has(point.name))throw new Error("Ponto duplicado no arquivo: "+id);
        changes.set(point.name,{
          e:parseValue(cells[eCol] || "",id+" σE"),
          n:parseValue(cells[nCol] || "",id+" σN"),
          h:hCol>=0 && cells[hCol] ? parseValue(cells[hCol],id+" σh") : null,
        });
      }
      const unmatched=topconBoundary.filter(p=>!changes.has(p.name));
      if(unmatched.length)throw new Error("Arquivo incompleto: faltam "+unmatched
        .map(p=>p.sigef_vertex_code||p.name).join(", ")+". Nada foi alterado.");
      setTopconBoundary(old=>old.map(p=>{
        const row=changes.get(p.name);
        if(!row)return p;
        return {...p,sigma_lon_m:row.e,sigma_lat_m:row.n,
          sigma_h_m:row.h??p.sigma_h_m,sigma_reference_confirmed:false};
      }));
      setTopconReview(null);setSigefParcelReview(null);setSigefValidatedSignature("");
      setSigmaImportFeedback(changes.size+" precisões individuais importadas de "+file.name+
        ". Confira a origem do processamento e use 'Confirmar sigmas individuais preenchidos'.");
    } catch(error) {
      setSigmaImportFeedback("Importação não concluída: "+
        (error instanceof Error?error.message:"arquivo inválido"));
    }
  };
  const validateTopconBoundary = async () => {
    setTopconReviewBusy(true);
    setTopconReviewFeedback({ status:"info", message:"Conferindo os marcos GNSS, os sigmas e as parcelas TOPCON..." });
    setTopconError("");
    setTopconReview(null);
    setSigefParcelReview(null);
    setSigefValidatedSignature("");
    try {
      const parcels = parcelsForOds();
      if (!parcels.length) throw new Error("Nenhuma parcela TOPCON válida foi formada. Confira os marcos de limite, sua ordem e a identificação de parcela.");
      // A pré-validação geométrica não exige edição manual de sigmas.
      // A ODS segue sujeita às verificações completas do serviço específico.
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
      const ready = errors.length === 0 && reviews.every(({ review }) =>
        (review.ready_for_geometry ?? review.ready_for_ods) && review.geometry);
      setTopconReviewFeedback({
        status: ready ? "success" : "error",
        message: ready
          ? "Geometria TOPCON conferida. Sigmas individuais continuam facultativos nesta etapa; ODS exige verificação separada. Não inclui os V PS4."
          : "Pré-validação TOPCON executada com " + errors.length + " pendência(s). Leia os detalhes abaixo.",
      });
      setTopconReview({
        ready_for_geometry: Boolean(ready),
        ready_for_ods: Boolean(ready && reviews.every(({review})=>review.ready_for_ods)),
        missing_sigmas: reviews.flatMap(({review})=>review.missing_sigmas??[]),
        errors, warnings,
        vertex_count: topconBoundary.length,
        area_ha: reviews.reduce((total, { review }) => total + (review.area_ha ?? 0), 0),
        perimeter_m: reviews.reduce((total, { review }) => total + (review.perimeter_m ?? 0), 0),
        geometry: ready ? reviews[0].review.geometry : null,
        parcel_geometries: ready ? reviews.map(({ number, name, review }) => ({
          number, name, geometry: review.geometry as Record<string, unknown>,
        })) : [],
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha na revisão do perímetro.";
      setTopconError(message);
      setTopconReviewFeedback({status:"error",message});
    } finally {
      setTopconReviewBusy(false);
    }
  };
  const importTopcon = async (file: File) => {
    setTopconError("");
    setTopconPreview(null);
    setPa2Mode(false); setConstructionSkipped(false);setConstructionRequested(false);
    setPa2Result(null); setPa2Witnesses([]); setMapHint(null);
    setPa2InsertAfter(""); setPa2ConfirmedCrs(false);
    setTopconBoundary([]);
    setPs4Draft([]);
    setPb1Draft([]);setPb1ClosureConfirmed(false);setPb1ConfirmedSignature("");
    setPb1Candidate(null);
    setPs4Armed(false);
    setPs4OrthoReport({scene_id:"",reference:"",rms_m:null,reviewed_by_rt:false});
    setOfficialOverlap(undefined);
    setPs4Quality(undefined);
    setPs4QualitySource("");
    setPs4Start("");
    setPs4ClosureConfirmed(false);
    setPs4ConfirmedSignature("");
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
  const downloadPb1Report=async()=>{
    setActionBusy(true);setActionError("");
    try{
      const id=await onSavePiece(editableMemorial.trim(),draftForSave());
      const res=await fetch(getApiUrl()+"/technical-pieces/"+id+"/pb1/report.pdf",{credentials:"include",cache:"no-store"});
      if(!res.ok){const body=await res.json();throw new Error(typeof body.detail==="string"?body.detail:"Relatório PB1 indisponível.");}
      const blob=await res.blob();const url=URL.createObjectURL(blob);
      const link=document.createElement("a");link.href=url;link.download="RELATORIO_TECNICO_PB1.pdf";link.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),30000);
      setSavedPieceNotice("Relatório técnico preliminar PB1 gerado.");
    }catch(e){setActionError(e instanceof Error?e.message:"Falha no relatório PB1.");}
    finally{setActionBusy(false);}
  };
  const adoptPb1WorkingParcel=(finish=false)=>{
    setTopconError("");setWorkflowNotice("");
    try{
      if(!(finish?pb1Closure.valid:pb1Ready)||!pb1Closure.geometry||!pb1Raster)
        throw new Error("Feche o perímetro PB1 e confirme o ORIXP vinculado.");
      if(new Set(topconBoundary.map(p=>p.parcel_number)).size!==1)
        throw new Error("Trabalhe em uma única parcela de cada vez.");

      const initial=topconBoundary[pb1StartIndex];
      if(!initial||initial.longitude===null||initial.latitude===null)
        throw new Error("Marco inicial PB1 inválido.");
      const zone=lonLatToSirgasUtm(initial.longitude,initial.latitude);
      const newVertices:TopconBoundaryPoint[]=pb1Draft.map(v=>{
        const utm=lonLatToSirgasUtm(v.longitude,v.latitude);
        if(utm.zone!==zone.zone||utm.hemisphere!==zone.hemisphere)
          throw new Error("Vértice PB1 em zona UTM diferente: "+v.name);
        return {
          ...initial,name:v.name,sigef_vertex_code:v.name,point_role:"BOUNDARY" as const,
          longitude:v.longitude,latitude:v.latitude,
          easting_m:utm.easting_m,northing_m:utm.northing_m,
          elevation_reported_m:null,ellipsoidal_height_reported_m:null,ellipsoidal_height_m:null,
          sigma_e_m:null,sigma_n_m:null,sigma_u_m:null,sigma_hz_m:null,
          sigma_lon_m:null,sigma_lat_m:null,sigma_h_m:null,
          sigma_reference_confirmed:false,height_reference_confirmed:false,
          sigma_suggestion_e_m:null,sigma_suggestion_n_m:null,sigma_suggestion_h_m:null,
          derived_physical_altitude_m:null,derived_physical_model:null,
          sigef_method:"PB1",boundary_type:"LN1",
          derived_calculation:{
            method:"PB1",status:"PRELIMINAR",accuracy_verified:false,
            official_sheet:pb1Source.sheet,product:pb1Source.product,
            accuracy_document:pb1Source.accuracy_reference,
            raster_sha256:v.raster_sha256,dtm_sha256:pb1Dtm?.sha256??null,
            source_elevation_m:v.source_elevation_m,
            source_vertical_datum:pb1Source.vertical_datum||"NAO_VERIFICADO",
            altitude_source:"MDT_ORIGINAL_NAO_CONVERTIDO",
            note:"MDT sem h confirmada. Sigma horizontal/vertical não atribuído; PB1 não liberado à ODS.",
          },
        };
      });
      const vertices=[...topconBoundary.slice(0,pb1StartIndex+1),...newVertices,
        ...topconBoundary.slice(pb1StartIndex+1)];
      if(vertices.length!==pb1Closure.names.length||
         vertices.some((v,i)=>v.name!==pb1Closure.names[i]))
        throw new Error("Sequência diferente da poligonal confirmada. Refazer fechamento PB1.");
      if(finish){setPb1ConfirmedSignature(pb1Signature);setPb1ClosureConfirmed(true);}
      onAdoptTopconParcels([{number:initial.parcel_number,
        name:initial.parcel_name||data.title||"Parcela preliminar",vertices}]);
      onDataChange("plantHeading","PLANTA PRELIMINAR PB1 — NÃO CERTIFICADA");
      onDataChange("memorialHeading","MEMORIAL PRELIMINAR PB1 — NÃO CERTIFICADO");
      setEditableMemorial("");setMemorialSaved(false);setMemorialDirty(false);
      setPdfBlob(null);setPdfUrl(null);lastPdfKey.current="";
      setPa2Mode(false);setStage(1);setPremiumStep(5);
      setSavedPieceNotice("Parcela PB1 preliminar aplicada com "+newVertices.length+" vértices V.");
    }catch(error){
      setTopconError(error instanceof Error?error.message:"Não foi possível aplicar PB1.");
    }
  };
  const importPs4AccuracyControls = async (file:File) => {
    setPs4QualityError("");
    setPs4Quality(undefined);
    try{
      if(file.size>1024*1024)throw new Error("O arquivo de pontos excede 1 MB.");
      if(!ps4QualitySource.trim() || ps4QualitySource.trim().length<8)
        throw new Error("Informe a origem independente dos pontos GNSS antes da importação.");
      const raw=(await file.text()).replace(/^\uFEFF/,"");
      const lines=raw.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
      if(lines.length<2)throw new Error("CSV sem pontos de controle.");
      const hdr=lines[0].split(";").map(s=>s.trim().toUpperCase().replace(/[^A-Z0-9_]/g,""));
      const expected=["ID","LON_IMAGEM","LAT_IMAGEM","LON_CONTROLE","LAT_CONTROLE"];
      if(expected.some((name,index)=>hdr[index]!==name))
        throw new Error("Cabeçalho esperado: ID;LON_IMAGEM;LAT_IMAGEM;LON_CONTROLE;LAT_CONTROLE.");
      const rows:Ps4Control[]=lines.slice(1).map((line,index)=>{
        const fields=line.split(";").map(v=>v.trim());
        if(fields.length<5)throw new Error("Linha "+(index+2)+" incompleta.");
        const num=(t:string)=>{
          const x=Number(t.replace(",","."));
          if(!t||!Number.isFinite(x))throw new Error("Coordenada não numérica na linha "+(index+2));
          return x;
        };
        return {id:fields[0],image_lon:num(fields[1]),image_lat:num(fields[2]),
          reference_lon:num(fields[3]),reference_lat:num(fields[4])};
      });
      const evaluated=evaluatePs4Controls(rows);
      setPs4Quality({...evaluated,source:ps4QualitySource.trim(),filename:file.name,scene_id:PS4_SCENE});
      setPs4Status({kind:"info",message:"Diagnóstico de acurácia calculado. O RT deve conferir distribuição, independência e documentação da ortorretificação."});
    }catch(e){
      setPs4QualityError(e instanceof Error?e.message:"Falha na avaliação PS4.");
    }
  };

  const adoptPs4WorkingParcel = () => {
    setTopconError("");
    setWorkflowNotice("");
    try {
      if (!ps4Ready || !ps4Closure.geometry)
        throw new Error("Confirme primeiro a sequência e o fechamento da poligonal PS4.");
      const numbers = new Set(topconBoundary.map(p => p.parcel_number));
      if (numbers.size !== 1)
        throw new Error("A incorporação PS4 é feita uma parcela de cada vez. Separe as parcelas antes de continuar.");
      if (!topconBoundary.every(p => p.height_reference_confirmed))
        setWorkflowNotice("Existem alturas GNSS sem confirmação do referencial. A planta permanecerá preliminar.");
      const initial = topconBoundary[ps4StartIndex];
      if (!initial || initial.longitude == null || initial.latitude == null)
        throw new Error("Marco inicial da restituição PS4 inválido.");
      const utmZone = lonLatToSirgasUtm(initial.longitude,initial.latitude);
      const final = topconBoundary[(ps4StartIndex+1)%topconBoundary.length];
      if(!final||final.longitude===null||final.latitude===null)
        throw new Error("Marco final PS4 inválido.");
      const confirmedNormal = (name:string) =>
        verticalModel==="hgeoHNOR2020" ?
          (verticalCalculated?.find(p=>p.name===name)?.normal_height_m??null) : null;
      const virtualHN = estimatePs4NormalAltitudes(
        {longitude:initial.longitude,latitude:initial.latitude,
          normal_height_m:confirmedNormal(initial.name)},
        ps4Draft,
        {longitude:final.longitude,latitude:final.latitude,
          normal_height_m:confirmedNormal(final.name)},
      );
      const vertices: TopconBoundaryPoint[] = [
        ...topconBoundary.slice(0,ps4StartIndex+1).map(p=>({
          ...p,
          derived_physical_altitude_m: confirmedNormal(p.name) ?? p.derived_physical_altitude_m ?? null,
          derived_physical_model: confirmedNormal(p.name) !== null ? ("HN" as const) : p.derived_physical_model,
        })),
        ...ps4Draft.map((point,pointIndex)=>{
          const utm = lonLatToSirgasUtm(point.longitude,point.latitude);
          if (utm.zone !== utmZone.zone || utm.hemisphere !== utmZone.hemisphere)
            throw new Error("O vértice "+point.name+" não está na zona UTM do marco. Revise a cena.");
          return {
            ...initial,
            name: point.name, sigef_vertex_code: point.name, point_role:"BOUNDARY" as const,
            longitude:point.longitude, latitude:point.latitude,
            easting_m:utm.easting_m,northing_m:utm.northing_m,
            elevation_reported_m:null,ellipsoidal_height_reported_m:null,ellipsoidal_height_m:null,
            sigma_e_m:null,sigma_n_m:null,sigma_u_m:null,sigma_hz_m:null,
            sigma_lon_m:null,sigma_lat_m:null,sigma_h_m:null,
            sigma_reference_confirmed:false,height_reference_confirmed:false,
            sigma_suggestion_e_m:null,sigma_suggestion_n_m:null,sigma_suggestion_h_m:null,
            derived_physical_altitude_m:virtualHN[pointIndex],
            derived_physical_model:virtualHN[pointIndex]===null?null:("HN" as const),
            sigef_method:"PS4",boundary_type:"LN1",
            derived_calculation:{method:"PS4",scene_id:point.scene_id,
              status:ps4ApprovalConfirmed?"ACURACIA_HORIZONTAL_CONFERIDA_RT":"PRELIMINAR",
              accuracy_verified:ps4ApprovalConfirmed,
              altitude_source:virtualHN[pointIndex]===null?"AUSENTE":"INTERPOLACAO_HN_M_V_M",
              altitude_quality:"INDICATIVA_NAO_MEDIDA",
              note:"Posicionamento orbital visual sem h medida. HN estimada somente por interpolação entre os dois M, não válida para SIGEF"},
          };
        }),
        ...topconBoundary.slice(ps4StartIndex+1).map(p=>({
          ...p,
          derived_physical_altitude_m: confirmedNormal(p.name) ?? p.derived_physical_altitude_m ?? null,
          derived_physical_model: confirmedNormal(p.name) !== null ? ("HN" as const) : p.derived_physical_model,
        })),
      ];
      if(vertices.length !== ps4Closure.names.length ||
         vertices.some((p,i) => p.name !== ps4Closure.names[i]))
        throw new Error("A ordem dos vértices mudou. Feche a prévia novamente.");
      if(!window.confirm("Aplicar a poligonal de "+vertices.length+
         " vértices à PARCELA PRELIMINAR para elaborar planta e memorial?\n"+
         "Os pontos V só terão acurácia horizontal confirmada quando houver revisão do RT; a altura permanece pendente.\n"+
         "Isto não libera a ODS nem constitui certificação SIGEF."))return;
      onAdoptTopconParcels([{
        number:initial.parcel_number,
        name:initial.parcel_name || data.title || "Parcela preliminar",
        vertices,
      }]);
      onDataChange("plantHeading","PLANTA PRELIMINAR — NÃO CERTIFICADA");
      onDataChange("memorialHeading","MEMORIAL PRELIMINAR — NÃO CERTIFICADO");
      setEditableMemorial("");
      setMemorialSaved(false);
      setMemorialDirty(false);
      setPdfBlob(null);setPdfUrl(null);lastPdfKey.current="";
      setStage(1);setPremiumStep(5);
      setSavedPieceNotice("Parcela preliminar M–V transferida: "+vertices.length+
        " vértices. Regere memorial e planta; SIGEF permanece pendente.");
      setWorkflowNotice("Parcela M–V aplicada ao mapa. Confira áreas e vértices, depois regere o memorial.");
    }catch(error){
      setTopconError(error instanceof Error?error.message:"Não foi possível aplicar os V.");
      setWorkflowNotice("Falha ao aplicar poligonal M–V. Revise o fechamento e os marcos selecionados.");
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
      onAdoptTopconParcels(parcels.map(parcel=>({
        ...parcel,
        vertices:parcel.vertices.map(point=>{
          const normal=verticalModel==="hgeoHNOR2020"
            ? verticalCalculated?.find(row=>row.name===point.name)?.normal_height_m
            : undefined;
          return {
            ...point,
            derived_physical_altitude_m:
              normal!==undefined && Number.isFinite(normal) ? normal : point.derived_physical_altitude_m??null,
            derived_physical_model:
              normal!==undefined && Number.isFinite(normal) ? ("HN" as const) : point.derived_physical_model??null,
          };
        }),
      })));
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
  const [actionFeedback, setActionFeedback] = useState("");
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
  const hasProvisionalPs4Parcel = chosen.some(p =>
    p.vertexDetails?.some(d => d.preliminary_ps4 === true && d.accuracy_verified !== true));
  const ps4SigefIncomplete = topconBoundary.some(point => point.sigef_method === "PS4" && (
    point.derived_calculation?.accuracy_verified !== true ||
    point.height_reference_confirmed !== true ||
    point.ellipsoidal_height_m === null ||
    ![point.sigma_lon_m, point.sigma_lat_m, point.sigma_h_m]
      .every(value => typeof value === "number" && Number.isFinite(value) && value > 0)
  ));
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
  // Parcela já selecionada no mapa é a fonte de verdade da Planta e do Memorial.
  // A prévia TOPCON/PS4 só assume o enquadramento quando ainda não há parcela aplicada.
  const displaySituationGeometry = chosen.length ? situationGeometry :
    ps4PreviewGeometry ? { type:"FeatureCollection",features:[
      {type:"Feature",properties:{status:"PRELIMINAR_PS4"},geometry:ps4PreviewGeometry},
    ]} : (previewTopconGeometry ?? situationGeometry);
  const displaySituationKey = chosen.length ? situationKey :
    JSON.stringify(displaySituationGeometry);
  // SIGEF compara a parcela selecionada, independente de haver vertices V.
  // Se nenhuma parcela foi selecionada, somente uma poligonal de previa
  // inequivoca pode ser analisada; nunca supor ausencia de sobreposicao.
  const overlapGeometry = (() => {
    const selected = chosen.filter(p => p.coordinates && p.coordinates.length >= 3);
    if (chosen.length === 1 && selected.length === 1) {
      const coords = selected[0].coordinates!;
      const ring = [...coords];
      if (ring[0][0] !== ring[ring.length - 1][0] ||
          ring[0][1] !== ring[ring.length - 1][1]) ring.push(ring[0]);
      return { type: "Polygon" as const, coordinates: [ring] };
    }
    if (chosen.length > 1) return null;
    if (ps4Ready) return ps4Closure.geometry;
    if (previewTopconGeometry?.features.length === 1) {
      return previewTopconGeometry.features[0].geometry;
    }
    return null;
  })();
  const overlapSignature = JSON.stringify(overlapGeometry);
  const overlapCurrent = officialOverlap?.signature === overlapSignature;

  const displayVertexNames = chosen.length
    ? chosen.map(polygon => polygon.vertices)
    : ps4Ready ? [ps4Closure.names.map(name =>
      topconBoundary.find(p=>p.name===name)?.sigef_vertex_code || name)]
    : previewTopconGeometry
      ? [...new Set(topconBoundary.map(point => point.parcel_number))]
        .map(number => topconBoundary.filter(point => point.parcel_number === number)
          .map(point => point.sigef_vertex_code || point.name))
      : [];
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
  const verifiedProgress = [
    Boolean(topconPreview),
    topconBoundary.length>=3,
    Boolean(verticalCalculated?.length),
    Boolean(pb1Ready || ps4Ready || constructionSkipped),
    Boolean(overlapCurrent && officialOverlap?.complete && officialOverlap?.count===0),
    selectedIds.length>0,
    Boolean(memorialText || editableMemorial),
    Boolean(pdfReady),
    Boolean(sigefParcelReview?.status==="PREVALIDATED"),
  ].filter(Boolean).length;
  const progressPercent = Math.round(verifiedProgress / 9 * 100);

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
    setActionFeedback("Executando ação...");
    setActionBusy(true);
    try {
      await fn();
      setActionFeedback("Ação concluída. Confira as informações atualizadas.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Falha na operação.";
      setActionFeedback("");
      setActionError(message);
      setPs4Status({ kind: "error", message: "Operação não concluída: " + message });
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <section className="pecas-workspace" aria-label="Elaboração de peças técnicas">
      <header className="pecas-header geo96-header">
        <div>
          <small>AMAZÔNIKA GEOESPACIAL · PEÇAS TÉCNICAS</small>
          <h2>{data.title || "Imóvel em elaboração"}</h2>
          <p>Planta georreferenciada e memorial descritivo · Rascunho técnico do usuário autenticado</p>
        </div>
        <button className="pecas-return" type="button" onClick={onClose}>
          <X size={17} /> Voltar ao mapa
        </button>
      </header>
      <div className="geo96-shell">
        <aside className="geo96-sidebar" aria-label="Progresso e navegação da peça">
          <div className="geo96-sidebar-brand"><span className="geo96-logo">A</span>
            <span><strong>AMAZÔNIKA</strong><small>GEOESPACIAL</small></span>
          </div>
          <div className="geo96-progress">
            <div className="geo96-progress-head"><strong>PROGRESSO DO PROJETO</strong>
              <span>{progressPercent}%</span></div>
            <div className="geo96-progress-track"><span style={{width: progressPercent + "%"}} /></div>
            <p>Passo {premiumStep + 1} de {premiumSteps.length} · {verifiedProgress}/9 marcos de progresso concluídos</p>
          </div>
          <nav className="geo96-sidebar-nav" aria-label="Etapas do projeto">
            {premiumSteps.map((item, index) => (
              <button type="button" key={item.title} onClick={() => jumpToWorkflow(index)}
                aria-current={premiumStep === index ? "step" : undefined}
                className={premiumStep === index ? "current" : index < premiumStep ? "completed" : ""}>
                <span className="geo96-step-index">{index < premiumStep ? <Check size={13}/> : index + 1}</span>
                <span><strong>{item.title}</strong><small>{item.detail}</small></span>
              </button>
            ))}
          </nav>
          <p className="geo96-sidebar-foot">Os dados originais GNSS são preservados. As etapas PS4
            permanecem preliminares até revisão do responsável técnico.</p>
        </aside>
        <div className="geo96-content">
      {(actionError || (actionFeedback && !pa2Mode)) && <div
        role={actionError ? "alert" : "status"} aria-live="polite"
        style={{ padding: "10px 16px", borderRadius: 8, margin: "8px 20px",
          background: actionError ? "#fff1ed" : "#e8f3ed",
          color: actionError ? "#942d19" : "#12513b", fontWeight: 600 }}>
        {actionError || actionFeedback}
        <button type="button" aria-label="Dispensar mensagem" onClick={() => {
          setActionFeedback(""); setActionError("");
        }} style={{ marginLeft: 12 }}>Fechar</button>
      </div>}
      <nav className="pecas-stepper" aria-label="Etapas de elaboração">
        {stages.map((name, index) => (
          <button type="button" key={name} aria-current={index === stage ? "step" : undefined}
            className={index === stage ? "active" : index < stage ? "done" : ""}
            onClick={() => jumpToWorkflow(([0,5,6,7,9] as const)[index])}
            disabled={(index > 1 && selectedIds.length === 0) || (index === 4 && !pdfReady)}
          >
            <span className="pecas-step-number">{index < stage ? <Check size={14} /> : index + 1}</span>
            {name}
          </button>
        ))}
      </nav>
      <main className="pecas-main" id="geo96-main">
        {showAllTasks && stage===0 && <button type="button" className="pecas-secondary"
          style={{marginBottom:12}} onClick={()=>setShowAllTasks(false)}>
          Voltar ao fluxo guiado · mostrar somente a etapa atual
        </button>}
        {workflowNotice && <div className="geo96-workflow-feedback" role="status">
          <Check size={16}/><span>{workflowNotice}</span>
          <button type="button" onClick={() => setWorkflowNotice("")} aria-label="Fechar orientação">×</button>
        </div>}
        {stage === 0 && !showAllTasks && premiumStep === 4 && <OfficialOverlapCheck
          key={overlapSignature}
          geometry={overlapGeometry}
          vertices={ps4Draft}
          onReport={result=>setOfficialOverlap({...result,signature:overlapSignature})}
          onNext={() => jumpToWorkflow(5)}
          onOpenMap={() => {
            setWorkflowNotice("Abra as camadas auxiliares no mapa principal e retorne à peça para continuar a análise.");
            onClose();
          }} />}
        {stage === 0 && !showAllTasks && premiumStep !== 4 && (
          <div className="pecas-data-layout geo97-focus-layout">
            <div className="pecas-card geo96-main-card geo97-focused-card">
              <div className="geo96-section-heading">
                <small>PASSO {premiumStep+1} DE {premiumSteps.length} · FLUXO GUIADO</small>
                <h3>{premiumSteps[premiumStep]?.title}</h3>
                <p>{premiumSteps[premiumStep]?.detail}. As demais tarefas ficam ocultas
                  para manter o foco. Os dados da peça continuam preservados.</p>
              </div>
              {premiumStep===0 && <>
                <h4>Importar processamento GNSS — TOPCON Tools</h4>
                <label className="pecas-field"><span>Relatório TOPCON (HTML, XLSX ou PDF textual)</span>
                  <input type="file" accept=".html,.htm,.xlsx,.pdf"
                    disabled={topconLoading} onChange={event=>{
                      const file=event.currentTarget.files?.[0];
                      if(file)void importTopcon(file);
                      event.currentTarget.value="";
                    }}/></label>
                {topconLoading&&<p role="status">Lendo e interpretando o levantamento…</p>}
                {topconError&&<p role="alert" className="pecas-warning">{topconError}</p>}
                {topconPreview&&<div className="geo96-next-step" role="status">
                  {topconPreview.point_count} pontos identificados no arquivo {topconPreview.filename}.
                  {topconBoundary.length} marcos de limite selecionados.
                </div>}
              </>}
              {premiumStep===1 && <>
                <h4>Vértices GNSS que compõem o imóvel</h4>
                <p>Escolha os marcos e confirme sua ordem. Os códigos SIGEF não alteram
                  os identificadores originais do processamento TOPCON.</p>
                {!topconPreview&&<p className="pecas-warning" role="status">
                  Ainda não há processamento TOPCON. Volte ao passo 1.</p>}
                {topconPreview&&<div className="pecas-table-wrap"><table className="pecas-table">
                  <thead><tr><th>Incluir</th><th>Ordem</th><th>Ponto TOPCON</th>
                    <th>Código SIGEF</th><th>Precisão GNSS</th><th>Reordenar</th></tr></thead>
                  <tbody>{topconPreview.points.filter(p=>p.point_role!=="CONTROL")
                    .map(p=>{
                      const i=topconBoundary.findIndex(item=>item.name===p.name);
                      const selected=i>=0?topconBoundary[i]:null;
                      return <tr key={p.name}>
                        <td><input aria-label={"Selecionar "+p.name} type="checkbox"
                          checked={Boolean(selected)} onChange={e=>{
                            setTopconReview(null);setSigefParcelReview(null);
                            setSigefValidatedSignature("");
                            setTopconBoundary(current=>e.target.checked?
                              [...current,{...p,point_role:"BOUNDARY" as const,
                                sigef_vertex_code:"",parcel_number:"1",
                                parcel_name:data.title||"Parcela 1",
                                ellipsoidal_height_m:p.ellipsoidal_height_reported_m??null,
                                sigma_lon_m:p.sigma_e_m??null,sigma_lat_m:p.sigma_n_m??null,
                                sigma_h_m:p.sigma_u_m??null,sigma_reference_confirmed:false,
                                height_reference_confirmed:false,confrontant_cns:"",
                                confrontant_registration:"",sigef_method:"",
                                boundary_type:"",confrontant:""}]:
                              current.filter(item=>item.name!==p.name));
                          }}/></td>
                        <td>{selected?i+1:"—"}</td>
                        <td><strong>{p.name}</strong></td>
                        <td>{selected?<input aria-label={"Código SIGEF "+p.name}
                          value={selected.sigef_vertex_code} onChange={e=>
                            setTopconBoundary(old=>old.map(item=>item.name===p.name?
                              {...item,sigef_vertex_code:e.target.value}:item))}/>:"—"}</td>
                        <td>{p.sigma_hz_m!=null?p.sigma_hz_m.toFixed(3)+" m":"Não fornecida"}</td>
                        <td>{selected&&<span className="geo97-order-actions">
                          <button type="button" aria-label={"Subir "+p.name}
                            disabled={i===0} onClick={()=>setTopconBoundary(old=>{
                              const next=[...old];[next[i-1],next[i]]=[next[i],next[i-1]];return next;
                            })}>↑</button>
                          <button type="button" aria-label={"Descer "+p.name}
                            disabled={i===topconBoundary.length-1} onClick={()=>setTopconBoundary(old=>{
                              const next=[...old];[next[i+1],next[i]]=[next[i],next[i+1]];return next;
                            })}>↓</button></span>}</td>
                      </tr>;
                    })}</tbody></table></div>}
                <p className="geo96-next-step">{topconBoundary.length} marcos na sequência.
                  A pré-validação SIGEF e a edição manual de sigmas são procedimentos
                  separados desta seleção.</p>
              </>}
              {premiumStep===2 && <>
                <h4>Altitudes normais — IBGE hgeoHNOR2020</h4>
                <p>Importe o arquivo <code>saida.txt</code> do IBGE.
                  Os fatores η são aplicados aos marcos M sem alterar h original.</p>
                <label className="pecas-field"><span>Modelo de conversão</span>
                  <select value={verticalModel} onChange={e=>
                    setVerticalModel(e.target.value as "hgeoHNOR2020"|"MAPGEO2015")}>
                    <option value="hgeoHNOR2020">hgeoHNOR2020 · altitude normal</option>
                    <option value="MAPGEO2015">MAPGEO2015 · altitude ortométrica</option>
                  </select></label>
                <label className="pecas-field"><span>Arquivo de resultados do IBGE (.txt, .csv)</span>
                  <input type="file" accept=".txt,.csv" onChange={e=>{
                    const file=e.currentTarget.files?.[0];
                    if(file)void importIbgeBatch(file);
                    e.currentTarget.value="";
                  }}/></label>
                {ibgeBatchNotice&&<p role="status" className="geo96-next-step">{ibgeBatchNotice}</p>}
                {verticalError&&<p role="alert" className="pecas-warning">{verticalError}</p>}
                <div className="pecas-table-wrap"><table className="pecas-table">
                  <thead><tr><th>Marco</th><th>h (m)</th><th>Fator η (m)</th><th>HN (m)</th></tr></thead>
                  <tbody>{topconBoundary.map(p=>{
                    const result=verticalCalculated?.find(x=>x.name===p.name);
                    return <tr key={p.name}><td>{p.sigef_vertex_code||p.name}</td>
                      <td>{p.ellipsoidal_height_m?.toFixed(3)??"—"}</td>
                      <td>{verticalFactors[p.name]??"—"}</td>
                      <td>{result?.normal_height_m?.toFixed(3)??"Pendente"}</td>
                    </tr>;
                  })}</tbody></table></div>
                <button type="button" className="pecas-primary" disabled={verticalLoading}
                  onClick={()=>void calculateVertical()}>
                  {verticalLoading?"Calculando…":"Calcular altitudes normais"}
                </button>
                <p className="pecas-note">A altitude dos V por PS4 exige fonte adicional
                  tecnicamente apropriada; não será estimada como se fosse GNSS.</p>
              </>}
              {premiumStep===3 && <>
                <h4>Construção de vértices adicionais</h4>
                <p>Se os marcos GNSS já definem todo o perímetro, dispense esta etapa. Caso contrário, abra o editor e escolha o método de posicionamento adequado.</p>
                <label className="pecas-check">
                  <input type="checkbox" checked={constructionRequested||hasAdditionalVertices} disabled={actionBusy||!topconPreview||topconBoundary.length<2}
                    onChange={e=>{if(e.target.checked)openAdditionalVertices();else void skipAdditionalVertices();}}/>
                  Preciso construir vértices adicionais (facultativo)
                </label>
                <p className="pecas-note">{constructionSkipped?"Dispensado — prossiga com os vértices existentes.":constructionRequested||hasAdditionalVertices?"Construção habilitada — escolha o método no editor.":"Sem seleção — confirme a dispensa ou marque para construir."}</p>
                {!constructionSkipped&&!constructionRequested&&!hasAdditionalVertices&&<button type="button" className="pecas-secondary" disabled={actionBusy} onClick={()=>void skipAdditionalVertices()}>Continuar sem vértices adicionais</button>}
                {actionError&&<p role="alert" className="pecas-warning">{actionError}</p>}
                {(constructionRequested||hasAdditionalVertices)&&<button type="button" className="pecas-primary"
                  disabled={!topconPreview||topconBoundary.length<2||actionBusy}
                  onClick={openAdditionalVertices}>Abrir espaço de trabalho de vértices</button>}
                {pb1Draft.length>0&&<button type="button" className="pecas-secondary" disabled={actionBusy} onClick={()=>void downloadPb1Report()}>Baixar relatório técnico PB1 (PDF)</button>}
                {pb1Ready&&<div className="geo97-adopt-banner" role="status">
                  <strong>PB1: traçado fechado com {pb1Draft.length} vértices V preliminares.</strong>
                  <p>É possível aplicar à planta preliminar; exatidão da base e altitude elipsoidal ainda pendentes.</p>
                  <button type="button" className="pecas-primary" onClick={()=>adoptPb1WorkingParcel()}>
                    Aplicar geometria PB1 à parcela preliminar
                  </button>
                </div>}
                {ps4Ready&&<div className="geo97-adopt-banner" role="status">
                  <strong>Poligonal fechada com {ps4Closure.names.length} vértices.</strong>
                  <p>A prévia e o PDF de cinco marcos são diferentes até aplicar
                    o novo perímetro à parcela de trabalho.</p>
                  <button type="button" className="pecas-primary"
                    onClick={adoptPs4WorkingParcel}>
                    Aplicar geometria M–V à parcela preliminar
                  </button>
                </div>}

              </>}
              <div className="geo97-flow-actions">
                <button type="button" className="pecas-secondary"
                  onClick={()=>setShowAllTasks(true)}>Abrir edição avançada desta peça</button>
                <button type="button" className="pecas-primary"
                  onClick={()=>jumpToWorkflow(Math.min(4,premiumStep+1))}>
                  {premiumStep===3?"Ir para sobreposições SIGEF":"Continuar para o próximo passo"} →
                </button>
              </div>
            </div>
            <div className="geo97-map-aside">
              <SituationMapPreview
                geometry={displaySituationGeometry}
                geometryKey={displaySituationKey}
                saved={chosen.length?situationSaved:null}
                onSave={onSaveSituation}
                vertexNames={displayVertexNames}
                showVertices={Boolean(previewTopconGeometry || chosen.length)}
                previewBasemap={previewTopconGeometry?"osm":"satellite"}
                ps4Draft={ps4Draft}
                ps4ClosureGeometry={ps4PreviewGeometry}
              />
            </div>
          </div>
        )}
        {stage === 0 && showAllTasks && (
          <div className="pecas-data-layout">
            <div className="pecas-card geo96-main-card">
              <div className="geo96-section-heading">
                <small>ETAPA {premiumStep + 1} · IMÓVEL</small>
                <h3>{premiumSteps[premiumStep].stage === 0
                  ? premiumSteps[premiumStep].title : "Dados do imóvel"}</h3>
                <p>Selecione o próximo procedimento na navegação à esquerda. O sistema mantém
                  os resultados GNSS originais e fornece feedback em cada etapa.</p>
              </div>
              <div className="geo96-task-strip" aria-label="Atalhos do processamento">
                {premiumSteps.slice(0,5).map((item,index) => (
                  <button type="button" key={item.title} onClick={() => jumpToWorkflow(index)}
                    className={premiumStep===index ? "current" : ""}>
                    <span>{index+1}</span>{item.title}
                  </button>
                ))}
              </div>
              <div className="geo96-next-step" role="status">
                <strong>Próxima ação recomendada:</strong> {topconBoundary.length === 0
                  ? "Importe o processamento GNSS para iniciar a peça."
                  : !ps4Ready && ps4Draft.length
                    ? "Abra Construção PS4, confira o segmento M–V–M e feche a prévia."
                    : ps4Ready
                      ? "Prévia PS4 fechada: confira a tabela consolidada e salve a peça."
                      : "Confira os vértices importados; ajustes de sigmas são facultativos para a prévia."}
              </div>
              <div id="geo96-import" className="pecas-card geo96-task-card" aria-label="Pré-validação do processamento TOPCON Tools">
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
                    <div id="geo96-vertices" className="pecas-card geo96-task-card" aria-label="Revisão de perímetro TOPCON">
                      <div className="geo96-task-eyebrow">02 · SELEÇÃO DOS VÉRTICES</div>
                      <h4>Vértices do divisor</h4>
                      <p className="geo96-helper">Revise os códigos SIGEF, escolha os marcos integrantes
                        do perímetro e ajuste a sequência antes de prosseguir. As coordenadas
                        importadas não são sobrescritas por esta visualização.</p>
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
                                    onChange={(event) => updateBoundaryPoint(index, {
                                      boundary_type: event.target.value,
                                      boundary_detail: "",
                                    })}>
                                    <option value="">Selecione o limite</option>
                                    {SIGEF_BOUNDARY_TYPES.map(([code, label]) => <option key={code} value={code}>
                                      {code} — {label}
                                    </option>)}
                                  </select>
                                    {selected && BOUNDARY_DETAILS[selected.boundary_type]?.length && <label style={{display:"block",marginTop:4}}>
                                      <span style={{fontSize:11}}>Descrição da feição</span>
                                      <select aria-label={`Detalhe do limite ${point.name}`}
                                        value={selected.boundary_detail||""}
                                        onChange={event=>updateBoundaryPoint(index,{
                                          boundary_detail:event.target.value
                                        })}>
                                        <option value="">Especificar…</option>
                                        {BOUNDARY_DETAILS[selected.boundary_type].map(detail=>
                                          <option key={detail} value={detail}>{detail}</option>)}
                                      </select>
                                    </label>}
                                  </td>
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
                      <div id="geo96-sigmas" className="pecas-card geo96-task-card" aria-label="Precisões SIGEF">
                        <h4>Precisões e confrontantes · conferência opcional</h4>
                        <p className="geo96-sigma-principle" role="note">
                          <Check size={16}/> O sistema preserva os valores efetivamente extraídos do TOPCON.
                          Os campos de σ Longitude e σ Latitude permanecem facultativos durante a elaboração
                          preliminar. A exportação SIGEF exige os dados técnicos previstos pelo seu esquema,
                          sem atribuir valores inexistentes nem confundir RMS de vetores com σ de coordenadas.
                        </p>
                        <details className="geo96-optional-section">
                          <summary>Ajustes avançados de sigmas e referências · opcional</summary>
                        <p className="pecas-note">As precisões individuais σE/σN são necessárias à pré-validação
                          oficial, mas <strong>não são exigidas para desenhar, fechar e salvar a poligonal preliminar PS4</strong>.
                          Não preencha valores estimados nem reaproveite os RMS das linhas de base.</p>
                        <label className="pecas-field"><span>Importar precisões de todos os pontos ajustados (CSV)</span>
                          <input type="file" accept=".csv,.txt,text/csv,text/plain"
                            onChange={e=>{
                              const file=e.currentTarget.files?.[0];
                              if(file)void importAdjustedSigmas(file);
                              e.currentTarget.value="";
                            }}/>
                        </label>
                        <p className="pecas-note">Formato: ID;SIGMA_E;SIGMA_N;SIGMA_H (metros).
                          Aceita o nome TOPCON ou código SIGEF. Valores importados precisam ser conferidos pelo RT.
                          Sem relatório de ajustamento individual, mantenha esta etapa pendente.</p>
                        {sigmaImportFeedback && <p role="status" className="pecas-note">{sigmaImportFeedback}</p>}
                        <p><strong>Valores individuais:</strong> {topconBoundary.filter(p =>
                          p.sigma_lon_m !== null && p.sigma_lat_m !== null).length}
                          /{topconBoundary.length} vértices com valores disponíveis.
                          {topconBoundary.filter(p => p.sigma_reference_confirmed).length}
                          /{topconBoundary.length} confirmações técnicas registradas.</p>
                        <button type="button" className="pecas-secondary"
                          disabled={!topconBoundary.length}
                          onClick={() => {
                            if (!window.confirm("Confirmo que conferi os desvios padrão individuais extraídos do TOPCON, sua referência e o resultado do ajustamento. Desejo aprovar os valores já preenchidos?")) return;
                            const valid=(v:number|null|undefined):v is number=>typeof v==="number"&&Number.isFinite(v)&&v>0;
                            const first=(...values:Array<number|null|undefined>)=>values.find(valid)??null;
                            const next=topconBoundary.map(point=>{
                              const source=topconPreview?.points.find(p=>p.name===point.name);
                              const lon=first(point.sigma_lon_m,point.sigma_e_m,source?.sigma_e_m);
                              const lat=first(point.sigma_lat_m,point.sigma_n_m,source?.sigma_n_m);
                              const alt=first(point.sigma_h_m,point.sigma_u_m,source?.sigma_u_m);
                              return {...point,sigma_lon_m:lon,sigma_lat_m:lat,sigma_h_m:alt,
                                sigma_reference_confirmed:lon!==null&&lat!==null&&alt!==null};
                            });
                            setTopconBoundary(next);
                            const confirmed=next.filter(p=>p.sigma_reference_confirmed).length;
                            setSigmaImportFeedback(confirmed+" de "+next.length+
                              " vértices com os três sigmas preenchidos e confirmados na tabela avançada. "+
                              (confirmed<next.length?"Os valores ausentes precisam do relatório de pontos ajustados; RMS de linha de base não será usado como substituto.":""));
                            setTopconReview(null); setSigefParcelReview(null);
                            setSigefValidatedSignature("");
                          }}>Confirmar sigmas individuais preenchidos</button>
                        <p className="pecas-note" role="status">A ação confirma apenas valores
                          já presentes. Para preencher automaticamente os campos avançados,
                          importe o quadro de pontos ajustados do TOPCON; quando não existem
                          sigmas individuais, os campos permanecem vazios e facultativos.
                          A validação geométrica não depende desta ação.</p>
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
                        <details className="pecas-advanced"><summary>Correções individuais de sigmas e confrontantes (avançado · totalmente facultativo)</summary><p>Abra somente quando precisar revisar valores individuais.</p><div style={{ overflowX: "auto" }}>
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
                                  <input key={`${point.name}:${field}`}
                                     aria-label={`${field} ${point.name}`} inputMode="decimal"
                                     value={point[field] ?? ""}
                                     onChange={(event) => {
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
                        </details>
                      </div>
                       
                      <div id="geo96-altimetry" className="pecas-card geo96-task-card" aria-label="Conversão altimétrica IBGE">
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
                          disabled={topconBoundary.length < 2}
                          onClick={() => {
                            if (!verticalCalculated) setConstructionMethod("PS4");
                            openAdditionalVertices();
                            setWorkflowNotice("Espaço de trabalho aberto. O PS4 pode criar rascunhos sem altitude calculada.");
                          }}>
                          Abrir espaço de trabalho cartográfico
                        </button>
                        {!verticalCalculated && <p className="pecas-note">
                          Para PA1, PA2 e PT8, conclua a conversão altimétrica dos marcos de apoio.
                        </p>}
                      </div>
                      <div className="pecas-card" aria-label="Validação do perímetro TOPCON" style={{marginTop:12}}>
                        <h4>Validação técnica dos marcos GNSS (TOPCON)</h4>
                        <button type="button" className="pecas-secondary"
                          onClick={()=>{
                            const target=document.getElementById("ps4-preliminary-review");
                            if(!target){setTopconReviewFeedback({status:"error",
                              message:"Ainda não há poligonal PS4 fechada. Volte ao espaço de trabalho, selecione o segmento e confirme a prévia."});return;}
                            target.scrollIntoView({behavior:"smooth",block:"center"});
                            setTopconReviewFeedback({status:"info",message:
                              "Você está revisando a poligonal PS4 preliminar. Sigmas não são exigidos nesta etapa."});
                          }}>
                          Ir para poligonal PS4 preliminar (sem informar sigmas)
                        </button>
                        <p className="pecas-note"><strong>Não é necessário clicar nesta validação para concluir
                          a prévia PS4.</strong> Os 0/5 sigmas representam uma pendência documental para SIGEF,
                          não um erro de importação ou cálculo das altitudes.</p>
                        <p className="pecas-note">Esta ação confere somente os marcos GNSS do levantamento.
                          O fechamento PS4 em azul é uma prévia independente e NÃO é enviado como geometria certificada.</p>
                        <p className="pecas-note">Marcos disponíveis: {topconBoundary.length} ·
                          Precisões por eixo disponíveis: {topconBoundary.filter(point =>
                          [point.sigma_lon_m, point.sigma_lat_m, point.sigma_h_m]
                            .every(value => typeof value === "number" && Number.isFinite(value) && value > 0)).length}/{topconBoundary.length} ·
                          PS4: {ps4Ready ? "fechamento preliminar confirmado" : "fechamento pendente"}.</p>
                        <button type="button" className="pecas-primary"
                          disabled={topconReviewBusy || topconBoundary.length < 3}
                          onClick={() => void validateTopconBoundary()}>
                          {topconReviewBusy ? "Validando, aguarde..." : "Pré-validar perímetro TOPCON para SIGEF"}
                        </button>
                        {topconBoundary.length < 3 &&
                          <p role="status" className="pecas-warning">Importe pelo menos três marcos de limite para habilitar a validação.</p>}
                        {topconReviewFeedback && <div aria-live="assertive"
                          role={topconReviewFeedback.status === "error" ? "alert" : "status"}
                          style={{marginTop:10,padding:12,borderRadius:8,
                            background: topconReviewFeedback.status==="error"?"#fff1ed":"#e8f3ed",
                            color:topconReviewFeedback.status==="error"?"#962d1b":"#14563b"}}>
                          <strong>{topconReviewFeedback.status==="error"?"Validação não concluída":
                            topconReviewFeedback.status==="success"?"Validação concluída":"Processando"}</strong>
                          <p style={{margin:"6px 0 0"}}>{topconReviewFeedback.message}</p>
                          {topconReviewFeedback.status==="error" && <p style={{margin:"6px 0 0"}}>
                            Próximo passo: revise as precisões individuais dos marcos na seção
                            “Correções individuais de sigmas e confrontantes”. O resultado HN do IBGE continua válido.
                          </p>}
                        </div>}
                      </div>
                      {topconReview && <div role="status">
                        <p><strong>{topconReview.ready_for_geometry
                          ? "Geometria aprovada · ODS sujeita a requisitos adicionais"
                          : "Pré-validação geométrica com pendências"}</strong>
                          {" · "}{topconReview.vertex_count} vértices
                          {" · "}{topconReview.area_ha?.toLocaleString("pt-BR") ?? "—"} ha
                          {" · "}{topconReview.perimeter_m?.toLocaleString("pt-BR") ?? "—"} m</p>
                        {topconReview.errors.map((message, index) =>
                          <p key={index} className="pecas-warning" role="alert">{message}</p>)}
                        {topconReview.warnings.map((message, index) =>
                          <p key={index} className="pecas-note">{message}</p>)}
                        <p className="pecas-note">A identificação e a situação jurídica foram transferidas para a revisão final.</p>
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
<SituationMapPreview
                  geometry={displaySituationGeometry}
                  geometryKey={displaySituationKey}
                  saved={chosen.length ? situationSaved : null}
                  onSave={onSaveSituation}
                  vertexNames={displayVertexNames}
                  showVertices={Boolean(previewTopconGeometry || chosen.length)}
                  previewBasemap={previewTopconGeometry || chosen.length ? "osm" : "satellite"}
                  ps4Draft={ps4Draft}
                  ps4ClosureGeometry={ps4PreviewGeometry}
                 />
                 {ps4Draft.length > 0 && <div id="geo96-ps4" className="pecas-card geo96-task-card" aria-label="Resumo de restituição PS4 provisória">
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
                     <h4 id="ps4-preliminary-review">Prévia consolidada · marcos M e vértices V na ordem do perímetro</h4>
                     <div className="geo97-adopt-banner" role="status">
                       <strong>Próximo passo: aplicar os {ps4Closure.names.length} vértices à parcela de trabalho.</strong>
                       <p>Atualmente a tabela e o mapa mostram apenas a prévia PS4.
                         A planta e o memorial antigos continuam com a geometria de cinco marcos
                         até confirmar esta transferência.</p>
                       <button type="button" className="pecas-primary"
                         onClick={adoptPs4WorkingParcel}>
                         Aplicar geometria M–V na parcela preliminar
                       </button>
                       <small>A ação substitui a parcela TOPCON anterior na área de trabalho,
                         preservando o levantamento GNSS; os V continuam pendentes de acurácia e altitude.</small>
                     </div>
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
                      <thead><tr><th>#</th><th>Nome do vértice</th><th>Confrontante do segmento</th><th>Altitude geométrica h (m)</th><th>Altitude normal HN (m)</th><th>Método</th><th>Tipo limite</th></tr></thead>
                      <tbody>
                        {polygon.vertices.map((name, index) => (
                          <tr key={index}>
                            <td>{index + 1}</td>
                            <td><input aria-label={`Nome do vértice ${index + 1}`}
                              value={name} onChange={(e) => onRenameVertex(polygon.id, index, e.target.value)} /></td>
                            <td><input aria-label={`Confrontante do segmento ${index + 1}`}
                              value={polygon.confrontants[index] ?? ""}
                              onChange={(e) => onConfrontant(polygon.id, index, e.target.value)} /></td>
                            <td>{polygon.altitudes[index] || "—"}</td>
                            <td>{String(polygon.vertexDetails?.[index]?.normal_altitude_m ?? "—")}</td>
                            <td>{String(polygon.vertexDetails?.[index]?.positioning_method ?? polygon.vertexDetails?.[index]?.sigef_method ?? "—")}</td>
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
            {premiumStep === 8 && <>
              {topconPreview && (
                          <div className="pecas-card" id="geo97-legal" aria-label="Revisão final de identificação SIGEF">
                            <h4>9. Identificação e situação jurídica — revisão final SIGEF</h4>
                            <p>Preencha os dados do titular e imóvel nos campos gerais acima.
                              Informe aqui os municípios e a situação jurídica para testar todas as parcelas.
                              Não é gerado ODS e não é efetuada consulta de vizinhos nesta etapa.</p>
                            <label className="pecas-field"><span>Municípios (separados por ponto e vírgula)</span>
                              <input value={sigefMunicipalities} placeholder="Macapá-AP; Santana-AP"
                                onChange={(e) => { setSigefMunicipalities(e.target.value); setSigefParcelReview(null); }} />
                            </label>
                            <label className="pecas-field"><span>Situação jurídica</span>
                              <select value={sigefSituation}
                                onChange={(e) => {
                                  setSigefSituation(e.target.value);setSigefParcelReview(null);
                                  onLegalMetadataChange({legal_status:e.target.value});
                                  setPdfBlob(null);setPdfUrl(null);
                                }}>
                                <option>Imóvel Registrado</option>
                                <option>Área Titulada não Registrada</option>
                                <option>Área não Titulada</option>
                              </select>
                            </label>
                            <label className="pecas-field"><span>Natureza da área</span>
                              <select value={areaNature} onChange={e=>{
                                setAreaNature(e.target.value);onLegalMetadataChange({area_nature:e.target.value});
                                setPdfBlob(null);setPdfUrl(null);
                              }}>
                                <option value="">Selecione a natureza</option>
                                <option value="Particular">Particular</option>
                                <option value="Pública">Pública</option>
                              </select>
                            </label>
                            <label className="pecas-field"><span>Código SNCR / INCRA</span>
                              <input value={sncr} onChange={e=>{
                                setSncr(e.target.value);onLegalMetadataChange({sncr:e.target.value});
                                setPdfBlob(null);setPdfUrl(null);
                              }}/>
                            </label>
                            {sigefSituation === "Imóvel Registrado" && <div>
                              <label className="pecas-field"><span>CNS cartório</span>
                                <input value={sigefCns} onChange={(e) => { setSigefCns(e.target.value); setSigefParcelReview(null);onLegalMetadataChange({cns:e.target.value});setPdfBlob(null);setPdfUrl(null); }} />
                              </label>
                              <label className="pecas-field"><span>Matrícula / transcrição</span>
                                <input value={sigefRegistration} onChange={(e) => { setSigefRegistration(e.target.value); setSigefParcelReview(null);onLegalMetadataChange({registration:e.target.value});setPdfBlob(null);setPdfUrl(null); }} />
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
                                  disabled={reviewedOdsBusy || ps4SigefIncomplete || !sigefValidatedSignature || sigefValidatedSignature !== sigefSignature()}
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
              {!topconPreview && <div className="pecas-warning" role="status">
                Importe o levantamento TOPCON antes de revisar a identificação jurídica.
              </div>}
            </>}
            {premiumStep !== 8 && <div id="geo97-export">
            <h3>5. Conferência e exportação</h3>
            <p>Documentos gerados pelos serviços existentes. As exportações vetoriais são feitas individualmente por polígono.</p>
            <div className="pecas-export-grid">
              <button disabled={!pdfReady || actionBusy} onClick={() => { if (pdfReady && pdfBlob) downloadBlob(pdfBlob, `${fileSlug(data.title)}-planta-memorial.pdf`); }}>
                <Download size={17} /> Planta + Memorial (PDF)
              </button>
              <button disabled={actionBusy} onClick={() => void runAction(onDownloadDocx)}>
                <FileText size={17} /> Memorial descritivo (DOCX)
              </button>
              <button type="button" disabled={workingOdsBusy}
                onClick={() => void downloadWorkingSigefOds()}>
                <Download size={17}/>
                {workingOdsBusy?"Gerando ODS...":"ODS de trabalho M + V (não submetível)"}
              </button>
              <button type="button" disabled={blankOdsBusy}
                onClick={() => void downloadBlankSigefOds()}>
                <Download size={17} />
                {blankOdsBusy?"Baixando modelo...":"Baixar modelo SIGEF (ODS em branco)"}
              </button>
              <button disabled={!sigefAvailable || actionBusy || hasProvisionalPs4Parcel || ps4SigefIncomplete}
                onClick={() => void runAction(onDownloadSigef)}>
                <Download size={17} /> ODS preenchida · somente dados validados
              </button>
            </div>
            {workingOdsError && <p role="alert" className="pecas-warning">{workingOdsError}</p>}
            {blankOdsError && <p role="alert" className="pecas-warning">{blankOdsError}</p>}
            <p className="pecas-note">O modelo em branco pode ser baixado a qualquer momento.
              A planilha preenchida depende de dados reais, incluindo h, coordenadas e precisão; HN estimada não substitui h SIGEF.</p>
            {!sigefAvailable && <p className="pecas-note">A exportação ODS SIGEF exige uma análise espacial registrada e a permissão correspondente. Conclua a análise no módulo existente para habilitá-la.</p>}
            {ps4SigefIncomplete && <p className="pecas-warning" role="status">
              Os vértices PS4 ainda não têm todos os atributos exigidos para a ODS preenchida:
              acurácia horizontal revisada, altura elipsoidal h e sigmas individuais.
              A ODS de trabalho e os documentos preliminares continuam disponíveis.
            </p>}
            {hasProvisionalPs4Parcel && <p className="pecas-warning" role="status">
              Esta parcela contém vértices V restituídos por PS4 sem acurácia certificável.
              A ODS SIGEF permanece bloqueada. A planta e o memorial PRELIMINARES podem ser gerados.
            </p>}
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
            </div>}
          </div>
        )}
      </main>
      {(actionError || (externalError && stage !== 4)) && (
        <p role="alert" className="pecas-warning pecas-workspace-alert">
          {actionError || externalError}
        </p>
      )}
      <footer className="pecas-footer">
        <span>{ps4Ready ? "Prévia PS4 fechada · " : ""}{selectedIds.length} parcela(s) oficial(is) selecionada(s) ·
          Passo {premiumStep + 1}/{premiumSteps.length} {savedPieceNotice && "· " + savedPieceNotice}</span>
        <div>
          <button className="pecas-secondary" type="button" disabled={actionBusy}
            onClick={() => void runAction(async () => {
              onSaveMemorial(editableMemorial.trim() ? editableMemorial : null);
              await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
              setSavedPieceNotice("Rascunho salvo no servidor");
            })}>Salvar peça</button>
          <button className="pecas-secondary" type="button" onClick={() => stage === 0 ? onClose() : jumpToWorkflow(([0,0,5,6,7] as const)[stage])}>
            <ArrowLeft size={16} /> {stage === 0 ? "Mapa" : "Voltar"}
          </button>
          {stage < 4 && <button className="pecas-primary" type="button"
            disabled={selectedIds.length === 0 || (stage === 3 && (!pdfReady || pdfBusy))}
            onClick={() => {
              if(stage===0)jumpToWorkflow(5);
              else jumpToWorkflow(([0,6,7,8,9] as const)[stage]);
            }}>
            Avançar <ArrowRight size={16} />
          </button>}
          {stage === 4 && <button className="pecas-primary" type="button" onClick={onClose}>
            <Map size={16} /> Concluir e voltar ao mapa
          </button>}
        </div>
      </footer>
      {topconPreview && pa2Mode && (Boolean(verticalCalculated) || constructionMethod === "PS4" || constructionMethod === "PB1") && (
        <div role="dialog" aria-modal="true" aria-label="Espaço de trabalho cartográfico" className={constructionMethod === "PS4" || constructionMethod === "PB1" ? "ps4-redesigned-dialog" : undefined}
          style={{ position: "fixed", inset: 10, zIndex: 100000, background: "#f7faf8",
            border: "1px solid #99b9ae", borderRadius: 14, display: "flex",
            flexDirection: "column", padding: 16, boxShadow: "0 10px 50px #0005" }}>
          <div style={{ display: "flex", gap: 16, alignItems: "center",
            justifyContent: "space-between", marginBottom: 12 }}>
            <div>
              <strong>Espaço de trabalho — Construção de vértices</strong>
              <p style={{ margin: 0, fontSize: 12 }}>Planta de apoio · PA1 Paralela · PA2 Interseção · PT8 Alinhamento · PS4 Sensores orbitais · PB1 Base oficial</p>
            </div>
            <button type="button" className="pecas-secondary"
              disabled={actionBusy}
              onClick={() => {
                if ((constructionMethod === "PS4" && !ps4Ready) || (constructionMethod === "PB1" && !pb1Ready)) {
                  setPs4Status({kind:"error",message:(constructionMethod === "PB1" ? pb1Closure : ps4Closure).valid
                    ? "Ainda falta confirmar o segmento e o fechamento da prévia (etapa 2)."
                    : "Não é possível concluir: " + (constructionMethod === "PB1" ? pb1Closure : ps4Closure).message +
                      " Use Salvar rascunho sem fechar, ou complete a etapa 2."});
                  return;
                }
                // Fechar a geometria M–V–M preliminar não certifica PS4.
                // Documentos, precisão e RT continuam bloqueando a validação
                // oficial em evaluate_verified_ps4 e exportação ODS SIGEF.
                void runAction(async () => {
                  setPs4Status({kind:"info",message:"Salvando peça e traçado no servidor..."});
                  await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
                  setPa2Mode(false);
                  setSavedPieceNotice(constructionMethod === "PB1"
                    ? "Traçado PB1 preliminar salvo — precisão e datum vertical pendentes"
                    : constructionMethod === "PS4"
                    ? "Prévia PS4 fechada e rascunho salvo — pendente de acurácia orbital"
                    : "Construção salva e prévia atualizada");
                });
              }}>{actionBusy ? "Salvando..." : (constructionMethod === "PS4" || constructionMethod === "PB1")
                ? "Concluir traçado PRELIMINAR e voltar à peça"
                : "Concluir, salvar e voltar à peça"}</button>
            {(constructionMethod === "PS4" || constructionMethod === "PB1") && <button type="button" className="pecas-secondary"
              disabled={actionBusy}
              onClick={() => void runAction(async () => {
                setPs4Status({kind:"info",message:"Salvando rascunho cartográfico sem fechamento..."});
                await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
                setPa2Mode(false);
                setSavedPieceNotice("Rascunho cartográfico salvo sem fechamento; complete antes da planta");
              })}>Salvar rascunho sem fechar</button>}
          </div>
          {(actionError || actionBusy) && <div role={actionError ? "alert" : "status"}
            aria-live="polite" style={{ marginBottom: 8, padding: "10px 12px",
              borderRadius: 8, background: actionError ? "#fff1ed" : "#e8f3ed",
              color: actionError ? "#932a1c" : "#12513b", fontWeight: 600 }}>
            {actionError ? "Não foi possível concluir: " + actionError : "Processando e salvando..."}
          </div>}
          
<style>{`
.ps4-navigation {background:#05392e;color:#fff;border-radius:12px;display:flex;flex-direction:column;overflow-y:auto;min-height:0;padding:18px 12px;gap:24px;}
.ps4-brand-lockup {display:flex;align-items:center;gap:8px;padding:0 4px;}
.ps4-brand-mark {display:grid;place-items:center;width:31px;height:31px;min-width:31px;border-radius:8px;background:#43aa80;font-size:19px;font-weight:900;color:#064332;}
.ps4-brand-lockup strong {font-size:13px;letter-spacing:.035em;display:block;}
.ps4-brand-lockup small {font-size:9px;letter-spacing:.2em;color:#a2d6bf;display:block;margin-top:2px;}
.ps4-navigation-label {font-size:10px;letter-spacing:.12em;color:#a2cfbd;font-weight:750;padding:0 6px;}
.ps4-navigation-steps {padding:0;margin:0;list-style:none;display:grid;gap:6px;}
.ps4-navigation-steps li {display:flex;gap:8px;padding:10px 7px;align-items:center;border-radius:9px;color:#bbd8cd;}
.ps4-navigation-steps li>span {border:1px solid #3c7863;border-radius:100%;min-width:25px;height:25px;display:grid;place-items:center;font-size:10px;}
.ps4-navigation-steps strong {font-size:11px;display:block;color:inherit;line-height:1.3;}
.ps4-navigation-steps small {display:block;font-size:9px;margin-top:2px;color:#9dc5b5;}
.ps4-navigation-steps .ps4-navigation-active {background:#165540;color:white;}
.ps4-navigation-steps .ps4-navigation-active>span {border:0;background:#e1f4e7;color:#0b4e38;font-weight:900;}
.ps4-navigation-foot {margin-top:auto;border-top:1px solid #326a55;padding:14px 6px 0;display:grid;gap:5px;font-size:12px;}
.ps4-navigation-foot small {color:#a9d2bd;font-size:10px;}
.ps4-navigation-foot .ps4-sidebar-warning {color:#ffb6bc;}
@media(max-width:1180px) {.ps4-navigation {display:none;} .ps4-redesigned-dialog .ps4-main-grid {grid-template-columns:minmax(360px, 1fr) minmax(320px, 1fr)!important;}}
@media(max-width:800px) {.ps4-redesigned-dialog .ps4-main-grid {grid-template-columns:minmax(0,1fr)!important;}}
.ps4-redesigned-dialog .ps4-flow-scroll > .pecas-card > label.pecas-field {display:none;}
.ps4-redesigned-dialog .ps4-flow-scroll > .pecas-card > section > h4 {display:none;}
.ps4-redesigned-dialog .ps4-flow-scroll > .pecas-card > section {display:grid;gap:7px;}
.ps4-redesigned-dialog .ps4-main-grid {gap:12px!important;}
.ps4-redesigned-dialog .ps4-flow-summary {padding:12px 14px;}
.ps4-redesigned-dialog .ps4-flow-card {margin:7px 0;}
.ps4-redesigned-dialog .ps4-redesign-intro {padding:13px 15px;}
.ps4-redesigned-dialog .ps4-alert-red {padding:11px 14px;}
.ps4-redesigned-dialog .ps4-flow-scroll {padding-bottom:18px;}
.ps4-redesigned-dialog .ps4-map-column {overflow:auto;min-width:0;}
.ps4-redesigned-dialog .ps4-map-column > .pecas-card {padding:12px;min-height:calc(100% - 6px);}
.ps4-redesigned-dialog .ps4-map-column > .pecas-card > h4 {margin:0 0 8px;}
.ps4-redesigned-dialog { --ps4-dark:#073b2f; --ps4-danger:#b4232d; --ps4-soft:#fff1f1; --ps4-line:#d9e3dc; background:#f4f8f5!important; }
.ps4-redesigned-dialog .ps4-flow-scroll > .pecas-card { border:0; background:transparent; box-shadow:none; padding:0; }
.ps4-redesigned-dialog .ps4-flow-scroll > .pecas-card > h4, .ps4-redesigned-dialog .ps4-flow-scroll > .pecas-card > p { display:none; }
.ps4-redesign-intro { display:flex; justify-content:space-between; gap:12px; align-items:center; background:#fff; border:1px solid var(--ps4-line); border-radius:13px; padding:18px; margin-bottom:10px; }
.ps4-eyebrow { color:#257b61; font-size:10px; font-weight:800; letter-spacing:.14em; }
.ps4-redesign-intro h4 { font-size:21px; color:#123d32; margin:2px 0; }
.ps4-redesign-intro p {font-size:12px; color:#687a72; margin:0;}
.ps4-state-pills {display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;}
.ps4-pill {font-size:11px;font-weight:700;background:#edf1ed;color:#5c6e63;border-radius:999px;padding:6px 10px;white-space:nowrap;}
.ps4-pill--ok {background:#e2f5e9;color:#17633b;}
.ps4-pill--danger {background:#ffe9ea;color:#a31f2b;}
.ps4-alert-red {padding:14px 16px;background:#fff0f1;border-left:4px solid #c42733;border-radius:9px;margin-bottom:12px;color:#8e222c;}
.ps4-alert-red strong {font-size:13px;} .ps4-alert-red p {font-size:12px;margin:5px 0 0;}
.ps4-flow-card {border:1px solid var(--ps4-line);border-radius:13px;background:#fff;margin:10px 0;overflow:hidden;}
.ps4-flow-card--danger {border-color:#f0b6bb;}
.ps4-flow-summary {display:flex;align-items:center;gap:11px;padding:15px;cursor:pointer;list-style:none;user-select:none;}
.ps4-flow-summary::-webkit-details-marker {display:none;}
.ps4-flow-summary:hover {background:#f5faf7;}
.ps4-flow-card[open] .ps4-step-caret {transform:rotate(180deg);}
.ps4-flow-summary:focus-visible {outline:3px solid #168a69;outline-offset:-3px;}
.ps4-step-no {border-radius:50%;background:#e8f1eb;color:#14503c;width:29px;height:29px;min-width:29px;display:grid;place-items:center;font-size:13px;font-weight:800;}
.ps4-flow-card--danger .ps4-step-no {background:#cc2a35;color:white;}
.ps4-step-heading {display:flex;flex-direction:column;gap:3px;flex:1;min-width:0;}
.ps4-step-heading strong {font-size:14px;color:#183b2f;}
.ps4-step-heading small {font-size:11px;color:#718178;}
.ps4-step-state {font-size:11px;color:#2c7652;background:#e5f5eb;border-radius:999px;padding:5px 9px;white-space:nowrap;}
.ps4-flow-card--danger .ps4-step-state {background:#ffe9eb;color:#b4232d;}
.ps4-step-caret {color:#718178;font-size:20px;transition:transform .15s ease;}


.ps4-v-panel {min-width:0;border:1px solid #dbe6de;border-radius:12px;padding:12px;background:#fafffc;display:grid;gap:10px;}
.ps4-v-panel-head {display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.ps4-v-panel-head strong {font-size:13px;color:#173d2f;}
.ps4-v-count {background:#e4f4e9;color:#17633e;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:800;}
.ps4-v-actions {display:flex;gap:8px;flex-wrap:wrap;}
.ps4-v-actions button {font-size:12px;padding:8px 12px;min-height:36px;}
.ps4-v-table-wrap {width:100%;min-width:0;overflow-x:auto;border:1px solid #dce7e0;border-radius:10px;background:#fff;}
.ps4-v-table {width:100%;border-collapse:collapse;table-layout:auto;font-size:12px;}
.ps4-v-table th {background:#eff7f2;color:#345847;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.04em;padding:11px 12px;white-space:nowrap;}
.ps4-v-table td {padding:11px 12px;color:#173a2c;border-top:1px solid #e7eee9;vertical-align:middle;white-space:nowrap;}
.ps4-v-table tbody tr:nth-child(even) {background:#fbfdfb;}
.ps4-v-table tbody tr:hover {background:#f1f8f3;}
.ps4-v-code {font-weight:750;color:#16533b;font-variant-numeric:tabular-nums;}
.ps4-v-coord {font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-variant-numeric:tabular-nums;letter-spacing:-.025em;}
.ps4-v-row-action {border:1px solid #f0c9cc;background:#fff6f6;color:#a02c35;border-radius:8px;padding:7px 10px;cursor:pointer;font-weight:650;font-size:11px;}
.ps4-v-row-action:hover {background:#fde6e8;}
.ps4-v-row-action:focus-visible {outline:3px solid #ad343d;outline-offset:2px;}
.ps4-v-help {font-size:11px;color:#687b70;margin:0;line-height:1.5;}
.ps4-flow-body {border-top:1px solid #edf1ee;padding:14px 15px 17px;display:grid;gap:8px;}
.ps4-flow-body .geo97-cbers-panel {border-radius:9px;}
.ps4-analysis-note {background:#fff2f2;color:#96343b;border-left:3px solid #c62734;border-radius:8px;padding:12px;font-size:12px;}
.ps4-analysis-note p {margin:5px 0 0;}
.ps4-documentary-toggle {border:1px solid #e0e6e1;border-radius:10px;padding:10px;}
.ps4-documentary-toggle > summary {cursor:pointer;font-size:12px;font-weight:750;color:#315d4d;}
.ps4-redesigned-dialog .pecas-warning {border-left:3px solid #c42733!important;background:#fff0f0!important;color:#98232c!important;}
@media(max-width:1050px) {.ps4-redesigned-dialog {inset:4px!important;padding:9px!important;}  .ps4-redesign-intro {flex-wrap:wrap;} }
@media(prefers-reduced-motion:reduce) {.ps4-step-caret {transition:none;}}
`}</style>
          <div role="toolbar" aria-label="Métodos de construção e ferramentas cartográficas"
            style={{ display: "flex", alignItems: "center", gap: 8,
              flexWrap: "wrap", paddingBottom: 12, borderBottom: "1px solid #b8cfc5",
              marginBottom: 12 }}>
            {(["PA1", "PA2", "PT8", "PS4", "PB1"] as const).map(method => <button
              key={method} type="button"
              disabled={method === "PA1" || method === "PA2"}
              title={method === "PA1" || method === "PA2"
                ? "Vértices V nesta versão utilizam somente PS4 com relatório" : undefined}
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
                : method === "PS4" ? "Sensores orbitais" : method === "PB1" ? "Base cartográfica oficial" : "Alinhamento"}
            </button>)}
            <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
              Outros métodos:
              <select value={constructionMethod==="PB1"?"PB1":""}
                aria-label="Métodos dependentes de fontes georreferenciadas"
                onChange={e=>{if(e.target.value==="PB1")setConstructionMethod("PB1");}}>
                <option value="">Selecione uma fonte</option>
                <option value="PS1" disabled>PS1 — Aerofotogrametria (requer projeto fotogramétrico)</option>
                <option value="PS2" disabled>PS2 — Radar aerotransportado (requer validação)</option>

                <option value="PB1">PB1 — Base cartográfica oficial (ORIXP + MDT)</option>
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
                : constructionMethod === "PB1"
                ? <p>Importe a ortoimagem oficial ORIXP e o MDT da folha, digitalize somente sobre o RGB e obtenha as cotas originais no MDT. ODS depende de precisão e datum vertical validados.</p>
                : constructionMethod === "PS4"
                ? <p>Ative a cena CBERS-4A no mapa, clique sucessivamente ao longo da feição natural,
                  confirme cada ponto e atribua código V. Sem RMS da ortorretificação, os pontos
                  permanecem como rascunho, fora da ODS e da certificação.</p>
                : <p>Selecione dois marcos e informe a distância medida a partir
                  do primeiro, observando a direção. PT8 é aplicável a tipo M/P,
                  não a V automaticamente.</p>}
            </details>
          </div>
          <div className={constructionMethod === "PS4" || constructionMethod === "PB1" ? "ps4-main-grid" : undefined} style={{ flex: 1, minHeight: 0, display: "grid",
            gridTemplateColumns: constructionMethod === "PS4" || constructionMethod === "PB1" ? "minmax(390px, 42%) minmax(0, 1fr)" : "minmax(325px, 37%) minmax(0, 1fr)", gap: 12 }}>
            
            <div className={constructionMethod === "PS4" || constructionMethod === "PB1" ? "ps4-flow-scroll" : undefined} style={{ overflowY: "auto", minHeight: 0, paddingRight: 8 }}>
                      <div className="pecas-card" aria-label="Construção assistida de vértices virtuais PA2">
                        <h4>Construção de vértices — PA1, PA2, PT8 e PS4</h4>
                        <p>PA1, PA2 e PT8 exigem conversão altimétrica prévia. Método PT8 gera
                          vértices M/P conforme a tabela oficial de compatibilidade; PA1/PA2
                          permitem vértice V, sujeito à conferência técnica.</p>
                        {!verticalCalculated && constructionMethod !== "PS4" && constructionMethod !== "PB1" && <p className="pecas-warning">
                          Conclua primeiro o cálculo das altitudes normais/ortométricas dos marcos
                          de apoio para habilitar a construção dos vértices.</p>}
                        <p>Após calcular as altitudes físicas, selecione o método adequado.
                          PA1 usa dois marcos, distância perpendicular e lado; PA2 utiliza
                          quatro marcos em duas retas; PT8 usa dois marcos e distância
                          medida a partir do primeiro. O mapa permite escolher visualmente
                          um local, mas o cálculo mantém as restrições geométricas do método. PS4 é independente da conversão altimétrica para criar rascunhos, mas exige acurácia comprovada para exportação.</p>
                        <label className="pecas-check"><input type="checkbox"
                          checked={constructionRequested||hasAdditionalVertices}
                          onChange={(e) => {
                            setPa2Result(null);
                            if (!e.target.checked) {
                              void skipAdditionalVertices();
                            } else {
                              setConstructionSkipped(false);
                              setPa2Mode(true);
                            }
                          }} />
                          Preciso construir vértices adicionais</label>
                        {pa2Mode && <label className="pecas-field">
                          <span>Método de posicionamento</span>
                          <select value={constructionMethod} onChange={e => {
                            setConstructionMethod(e.target.value as "PA1" | "PA2" | "PT8" | "PS4" | "PB1");
                            setPa2Witnesses([]); setPa2Result(null); setMapHint(null);
                            setConstructionSide(e.target.value === "PT8" ? "FORWARD" : "LEFT");
                          }}>
                            <option value="PA1" disabled>PA1 — Não disponível nesta versão</option>
                            <option value="PA2" disabled>PA2 — Não disponível nesta versão</option>
                            <option value="PT8">PT8 — Alinhamento (tipo M/P)</option>
                            <option value="PS4">PS4 — Sensores orbitais (tipo V, pré-restituição)</option>
                            <option value="PB1">PB1 — Base cartográfica com precisão conhecida</option>
                          </select>
                        </label>}
                        {pa2Mode && constructionMethod === "PB1" && <section aria-label="Vetorização PB1 base cartográfica oficial" style={{display:"grid",gap:12}}>
                          <div className="ps4-redesign-intro">
                            <div><small className="ps4-eyebrow">PB1 · BASE CARTOGRÁFICA COM PRECISÃO CONHECIDA</small>
                              <h4>Vetorização na base oficial</h4>
                              <p style={{margin:0}}>Fonte ORIXP RGB para posição; MDT numérico para cota original. Independente do PS4.</p>
                            </div>
                            <span className="ps4-step-state">Rascunho técnico</span>
                          </div>
                          <details className="ps4-flow-card">
                            <summary className="ps4-flow-summary"><span className="ps4-step-no">1</span>
                              <span className="ps4-step-heading"><strong>Carregar recortes oficiais</strong>
                                <small>Mosaico previamente montado em SIG e recortado; até 256 MiB por arquivo</small></span>
                              <span className="ps4-step-caret">⌄</span></summary>
                            <div className="ps4-flow-body">
                              <label className="pecas-field"><span>MDT Color / ORIXP · mosaico RGB recortado (GeoTIFF)</span>
                                <input type="file" accept=".tif,.tiff" disabled={pb1Busy} onChange={e=>{
                                  const file=e.target.files?.[0];if(file)void pb1Upload("pb1_color",file);
                                  e.target.value="";
                                }}/></label>
                              <div className="pecas-note">{pb1Raster
                                ?`RGB vinculado: ${pb1Raster.metadata?.width??"?"} × ${pb1Raster.metadata?.height??"?"} · SHA ${pb1Raster.sha256.slice(0,16)}…`
                                :"Nenhum ORIXP anexado; cliques PB1 permanecem bloqueados."}</div>
                              <label className="pecas-field"><span>MDT cinza · mosaico numérico recortado (GeoTIFF)</span>
                                <input type="file" accept=".tif,.tiff" disabled={pb1Busy} onChange={e=>{
                                  const file=e.target.files?.[0];if(file)void pb1Upload("pb1_dtm",file);
                                  e.target.value="";
                                }}/></label>
                              <div className="pecas-note">{pb1Dtm
                                ?`MDT vinculado: ${pb1Dtm.metadata?.width??"?"} × ${pb1Dtm.metadata?.height??"?"} · SHA ${pb1Dtm.sha256.slice(0,16)}…`
                                :"Sem MDT: é possível visualizar a fonte, mas a cota original dos V ficará pendente."}</div>
                              <p className="pecas-note">O sistema não exige que o nome do arquivo corresponda
                                ao código INOM/MI. A localização é verificada pelas coordenadas reais do GeoTIFF,
                                e não pelo nome da folha.</p>
                              {pb1Busy&&<p role="status">Processando o produto georreferenciado…</p>}
                            </div>
                          </details>
                          <details className="ps4-flow-card" open>
                            <summary className="ps4-flow-summary"><span className="ps4-step-no">2</span>
                              <span className="ps4-step-heading"><strong>Digitalizar os vértices V</strong>
                                <small>Clique somente sobre o recorte ORIXP oficial</small></span>
                              <span className="ps4-step-state">{pb1Draft.length} V</span><span className="ps4-step-caret">⌄</span>
                            </summary>
                            <div className="ps4-flow-body">
                              {!pb1Raster&&<p className="ps4-analysis-note">Importe o ORIXP RGB para habilitar a vetorização PB1.</p>}
                              {pb1Candidate&&<div className="pecas-card">
                                <strong>Ponto selecionado na fonte oficial</strong>
                                <p>Latitude {pb1Candidate.latitude.toFixed(8)}° · longitude {pb1Candidate.longitude.toFixed(8)}°</p>
                                <button type="button" className="pecas-primary" disabled={pb1Busy}
                                  onClick={()=>void pb1AddPoint()}>Confirmar V PB1 e amostrar MDT</button>
                                <button type="button" className="pecas-secondary" onClick={()=>setPb1Candidate(null)}>Cancelar</button>
                              </div>}
                              <div className="ps4-v-table-wrap"><table className="ps4-v-table">
                                <thead><tr><th>Ordem</th><th>Vértice</th><th>Latitude</th><th>Longitude</th><th>Cota MDT original (m)</th><th>Ação</th></tr></thead>
                                <tbody>{pb1Draft.map((v,i)=><tr key={v.name}>
                                  <td>{i+1}</td><td className="ps4-v-code">{v.name}</td>
                                  <td className="ps4-v-coord">{v.latitude.toFixed(8)}</td>
                                  <td className="ps4-v-coord">{v.longitude.toFixed(8)}</td>
                                  <td>{v.source_elevation_m===null?"Pendente":v.source_elevation_m.toFixed(3)}</td>
                                  <td><button className="ps4-v-row-action" type="button" onClick={()=>{
                                    setPb1Draft(old=>old.filter((_,j)=>i!==j));setPb1ClosureConfirmed(false);
                                  }}>Remover</button></td>
                                </tr>)}</tbody>
                              </table></div>
                              <p className="pecas-note">A cota é o valor original do MDT, não a altitude elipsoidal h.
                                Sem verificação do datum vertical e modelo de conversão, h e sigma-h permanecem pendentes.</p>
                            </div>
                          </details>
                          <details className="ps4-flow-card" open>
                            <summary className="ps4-flow-summary"><span className="ps4-step-no">3</span>
                              <span className="ps4-step-heading"><strong>Fechar perímetro M–V–M</strong>
                                <small>O fechamento preliminar não certifica a precisão</small></span>
                              <span className="ps4-step-state">{pb1Ready?"Fechado":"Pendente"}</span><span className="ps4-step-caret">⌄</span>
                            </summary>
                            <div className="ps4-flow-body">
                              <label className="pecas-field"><span>Marco GNSS inicial do segmento substituído</span>
                                <select value={pb1Start} onChange={e=>{setPb1Start(e.target.value);setPb1ClosureConfirmed(false);}}>
                                  <option value="">Selecione o marco inicial</option>
                                  {topconBoundary.map(v=><option key={v.name} value={v.name}>{v.name}</option>)}
                                </select>
                              </label>
                              <p className="pecas-note">Marco final consecutivo: <strong>{pb1End||"—"}</strong></p>
                              <p role="status">{pb1Closure.message.replace(/PS4/g,"PB1")}</p>
                              <button type="button" className="pecas-primary" disabled={!pb1Closure.valid||!pb1Raster||actionBusy}
                                onClick={()=>adoptPb1WorkingParcel(true)}>Concluir construção e aplicar à parcela</button>
                              <p className="pecas-note">Pendências de precisão e altimetria não impedem a peça preliminar; a ODS definitiva permanece bloqueada.</p>
                            </div>
                          </details>
                          <details className="ps4-flow-card">
                            <summary className="ps4-flow-summary"><span className="ps4-step-no">i</span>
                              <span className="ps4-step-heading"><strong>Dados técnicos da base (avançado)</strong>
                                <small>Origem cartográfica e precisão documentada</small></span>
                              <span className="ps4-step-caret">⌄</span></summary>
                            <div className="ps4-flow-body">
                              <Pb1SheetLookup geometry={pb1LookupGeometry} autoLookup
                                onSheetsFound={sheets=>{
                                  const intersecting=sheets.filter(row=>row.area_overlap);
                                  const list=(intersecting.length?intersecting:sheets)
                                    .map(row=>row.inom+(row.mi?" · MI "+row.mi:"")).join("; ");
                                  if(list)setPb1Source(old=>({...old,sheet:list}));
                                }}/>
                              <label className="pecas-field"><span>Folhas INOM / MI cobertas pelo mosaico (uma ou mais)</span>
                                <input value={pb1Source.sheet} placeholder="Ex.: 0244-1-NE; 0244-1-NO"
                                  onChange={e=>setPb1Source(o=>({...o,sheet:e.target.value}))}/></label>
                              <p className="pecas-note">As folhas são preenchidas pelo botão “Identificar folhas da parcela”.
                                O código INOM/MI não depende do nome dos dois TIFFs.</p>
                              <label className="pecas-field"><span>Fonte e edição do produto oficial (independe do nome do arquivo)</span>
                                <input value={pb1Source.product} placeholder="Ex.: Exército/GEA · base cartográfica 1:25.000 · ORIXP 2,5 m"
                                  onChange={e=>setPb1Source(o=>({...o,product:e.target.value}))}/></label>
                              <label className="pecas-field"><span>Escala original do produto</span><select value={pb1Source.scale??""} onChange={e=>{setPb1Source(o=>({...o,scale:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Não identificada</option>{PB1_SCALE_OPTIONS.map(v=><option key={v} value={v}>{v==="Outra"?v:"1:"+Number(v).toLocaleString("pt-BR")}</option>)}</select></label>
                              <label className="pecas-field"><span>Classificação planimétrica declarada</span><select value={pb1Source.pec??""} onChange={e=>{setPb1Source(o=>({...o,pec:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Não comprovada</option>{PB1_PEC_OPTIONS.map(v=><option key={v}>{v}</option>)}</select></label>
                              {pb1Source.pec&&PB1_PEC_MM[pb1Source.pec]&&Number(pb1Source.scale)>0&&<p className="pecas-note">Referência normativa PEC tradicional: PEC {(PB1_PEC_MM[pb1Source.pec][0]*Number(pb1Source.scale)/1000).toLocaleString("pt-BR")} m; erro-padrão {(PB1_PEC_MM[pb1Source.pec][1]*Number(pb1Source.scale)/1000).toLocaleString("pt-BR")} m. Não são sigmas medidos dos vértices.</p>}
                              <label className="pecas-field"><span>Documento comprobatório da exatidão planimétrica</span>
                                <input value={pb1Source.accuracy_reference} placeholder="Informe documento e classe efetivamente comprovados"
                                  onChange={e=>{setPb1Source(o=>({...o,accuracy_reference:e.target.value}));setPb1TechnicalResult(null);}}/></label>
                              <div className="pecas-note">
                                <strong>Referencial horizontal identificado:</strong> {pb1Dtm?.metadata?.crs_authority
                                  ||pb1Raster?.metadata?.crs_authority||"Não identificado"}.
                                <strong> Referencial vertical:</strong> {pb1Dtm?.metadata?.vertical_crs_name
                                  ||"não declarado no GeoTIFF — confirmar com a documentação oficial"}.
                                SIRGAS 2000 / UTM define coordenadas horizontais e não comprova
                                por si só se as elevações são normais, ortométricas ou elipsoidais.
                              </div>
                              <label className="pecas-field"><span>Tipo de altitude original do MDT</span><select value={pb1Source.vertical_kind??""} onChange={e=>{setPb1Source(o=>({...o,vertical_kind:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Não identificado</option>{PB1_KIND_OPTIONS.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
                              <label className="pecas-field"><span>Datum vertical declarado</span><select value={PB1_DATUM_OPTIONS.includes(pb1Source.vertical_datum)?pb1Source.vertical_datum:pb1Source.vertical_datum?"custom":""} onChange={e=>{setPb1Source(o=>({...o,vertical_datum:e.target.value==="custom"?o.vertical_datum:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Não identificado</option>{PB1_DATUM_OPTIONS.map(v=><option key={v}>{v}</option>)}<option value="custom">Personalizado / anteriormente informado</option></select></label>
                              <label className="pecas-field"><span>Referencial vertical informado (editável; não confundir com UTM)</span>
                                <input value={pb1Source.vertical_datum} placeholder="Não presumir HN, H ou h sem metadados"
                                  onChange={e=>{setPb1Source(o=>({...o,vertical_datum:e.target.value}));setPb1TechnicalResult(null);}}/></label>
                              <label className="pecas-field"><span>Modelo altimétrico original da fonte</span><select value={pb1Source.source_model??""} onChange={e=>{setPb1Source(o=>({...o,source_model:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Não identificado</option>{PB1_MODEL_OPTIONS.map(v=><option key={v} value={v}>{v==="NONE"?"Não se aplica (altura elipsoidal)":v}</option>)}</select></label>
                              <label className="pecas-field"><span>Documento comprobatório do referencial vertical</span><input value={pb1Source.vertical_reference??""} onChange={e=>{setPb1Source(o=>({...o,vertical_reference:e.target.value}));setPb1TechnicalResult(null);}} placeholder="Ficha técnica ou metadados"/></label>
                              <p className="pecas-note">As escolhas são declarações de origem, não aprovação de exatidão. O modelo original pode diferir do modelo de conversão atual.</p>
                              {pb1Raster?.metadata?.embedded_source_tags &&
                                Object.keys(pb1Raster.metadata.embedded_source_tags).length>0 &&
                                <p className="pecas-note"><strong>Metadados de origem extraídos do RGB:</strong>{" "}
                                  {Object.values(pb1Raster.metadata.embedded_source_tags).join(" · ")}
                                  <button type="button" className="pecas-secondary" style={{marginLeft:8}}
                                    onClick={()=>setPb1Source(old=>({...old,product:
                                      Object.values(pb1Raster.metadata!.embedded_source_tags!).join(" · ")}))}>
                                    Usar descrição do TIFF
                                  </button>
                                </p>}
                              <p className="pecas-note">O nome do TIFF pode ser livre, inclusive o da folha predominante.
                                Informe todas as folhas abrangidas pela área e mantenha os créditos e metadados
                                da base original. Envie o mosaico já montado e recortado no SIG em GeoTIFF
                                com SRC incorporado; arquivos .tfw isolados não definem o datum.
                                Esses campos descrevem a fonte; não constituem validação automática.
                                O responsável técnico deverá conferir a escala, a exatidão e a compatibilidade com o limite.</p>
                            </div>
                          </details>
                          <details className="ps4-flow-card" id="pb1-technical-step">
                            <summary className="ps4-flow-summary"><span className="ps4-step-no">i</span><span className="ps4-step-heading"><strong>Precisão e altimetria (avançado)</strong><small>MDT original, fatores individuais e revisão técnica</small></span></summary>
                            <div className="ps4-flow-body">
                              <div className="pecas-note">
                                <strong>Diagnóstico altimétrico local — MDT × GNSS</strong>
                                <p>Compara cotas do raster com h confirmada e HN disponível dos marcos. Não identifica automaticamente o datum.</p>
                                <button type="button" className="pecas-secondary" disabled={pb1Busy||!pb1Dtm} onClick={()=>void runPb1Diagnostic()}>Comparar MDT com marcos GNSS</button>
                                {pb1Diagnostic&&<>
                                  <div className="ps4-v-table-wrap"><table className="ps4-v-table"><thead><tr><th>Marco</th><th>h GNSS</th><th>HN IBGE</th><th>MDT</th><th>MDT − HN</th></tr></thead><tbody>{pb1Diagnostic.rows.map(r=><tr key={r.name}><td>{r.name}</td><td>{r.h_gnss_m?.toFixed(3)??"—"}</td><td>{r.hn_ibge_m?.toFixed(3)??"—"}</td><td>{r.mdt_m?.toFixed(3)??r.error??"—"}</td><td>{r.residual_hn_m?.toFixed(3)??"—"}</td></tr>)}</tbody></table></div>
                                  {([["h",pb1Diagnostic.vs_h],["HN",pb1Diagnostic.vs_hn]] as const).map(([label,m])=>m&&<p key={label}>MDT − {label}: n={m.count} · média {m.mean_m.toFixed(3)} m · RMSE {m.rmse_m.toFixed(3)} m · desvio-padrão {m.sample_std_m?.toFixed(3)??"—"} m · máximo absoluto {m.max_abs_m.toFixed(3)} m.</p>)}
                                  <p>Diagnóstico exploratório. Confirme a documentação, a altura do marco sobre o terreno e a independência dos controles.</p>
                                </>}
                              </div>
                              <button type="button" className="pecas-secondary" onClick={()=>{
                                const k=pb1Source.vertical_kind??"";
                                setPb1Technical(o=>({...o,vertical_kind:["NORMAL","ORTHOMETRIC","ELLIPSOIDAL"].includes(k)?k:"",
                                  vertical_datum:pb1Source.vertical_datum,vertical_reference:pb1Source.vertical_reference??"",
                                  accuracy_reference:pb1Source.accuracy_reference}));
                                setPb1TechnicalResult(null);setPb1IbgeOutput("");setPb1IbgeFilename("");
                              }}>Preencher dados da etapa 1</button>
                              {pb1Source.source_model&&<p className="pecas-note">Modelo original declarado: {pb1Source.source_model}. Confira a compatibilidade antes de converter. Modelos distintos não são intercambiáveis.</p>}
                              <label className="pecas-field"><span>Tipo de altura do MDT</span><select value={pb1Technical.vertical_kind} onChange={e=>{setPb1Technical(o=>({...o,vertical_kind:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Selecione conforme documentação</option><option value="NORMAL">Normal · hgeoHNOR2020</option><option value="ORTHOMETRIC">Ortométrica · MAPGEO2015 (se compatível)</option><option value="ELLIPSOIDAL">Elipsoidal SIRGAS2000</option></select></label>
                              <label className="pecas-field"><span>Categoria do limite</span><select value={pb1Technical.limit_category} onChange={e=>{setPb1Technical(o=>({...o,limit_category:e.target.value}));setPb1TechnicalResult(null);}}><option value="">Selecione</option><option value="NATURAL">Natural · 3 m</option><option value="INACCESSIBLE">Inacessível · 7,50 m</option><option value="ARTIFICIAL">Artificial · 0,50 m (somente conferência numérica)</option></select></label>
                              {([["vertical_datum","Datum vertical"],["vertical_reference","Documento do datum vertical"],["accuracy_reference","Documento de exatidão da base"],["sigma_e_m","Sigma E (m)"],["sigma_n_m","Sigma N (m)"],["source_sigma_m","Sigma da elevação MDT (m)"],["factor_reference","Origem dos fatores de conversão"]] as const).map(([key,label])=><label key={key} className="pecas-field"><span>{label}</span><input value={pb1Technical[key]} onChange={e=>{setPb1Technical(o=>({...o,[key]:e.target.value}));setPb1TechnicalResult(null);}}/></label>)}
                              {pb1Technical.vertical_kind==="NORMAL"&&<label className="pecas-field">
                                <span>Retorno do IBGE hgeoHNOR2020 (saida.txt)</span>
                                <input type="file" accept=".txt,text/plain" onChange={async e=>{
                                  const file=e.target.files?.[0];if(!file)return;
                                  setPb1IbgeOutput("");setPb1IbgeFilename("");setPb1TechnicalResult(null);
                                  try{
                                    if(file.size>1000000)throw new Error("Arquivo excede 1 MB.");
                                    setPb1IbgeOutput(await file.text());setPb1IbgeFilename(file.name);
                                    setPb1Technical(o=>({...o,factor_reference:"IBGE hgeoHNOR2020 · "+file.name}));
                                    setPb1Notice("Arquivo carregado. IDs, coordenadas e fatores serão conferidos no cálculo.");
                                  }catch(err){setPb1Notice(err instanceof Error?err.message:"Falha ao ler arquivo.");}
                                }}/>
                                {pb1IbgeFilename&&<span>{pb1IbgeFilename} <button type="button" onClick={()=>{setPb1IbgeOutput("");setPb1IbgeFilename("");setPb1TechnicalResult(null);}}>Remover</button></span>}
                              </label>}
                              {pb1Technical.vertical_kind!=="ELLIPSOIDAL"&&<label className="pecas-field"><span>Fatores individuais (código; fator assinado em m; sigma em m)</span><textarea rows={5} value={pb1Technical.factors} onChange={e=>{setPb1Technical(o=>({...o,factors:e.target.value}));setPb1TechnicalResult(null);}}/></label>}
                              <button type="button" className="pecas-secondary" disabled={!pb1Draft.length} onClick={()=>{
                                const blob=new Blob([pb1Draft.map(p=>p.name+" "+p.latitude.toFixed(8)+" "+p.longitude.toFixed(8)).join("\n")+"\n"],{type:"text/plain"});
                                const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download="PB1_vertices_IBGE.txt";link.click();URL.revokeObjectURL(url);
                              }}>Exportar ID LAT LON dos V para IBGE</button>
                              {!pb1Ready&&<p className="pecas-note">Confirme o fechamento geométrico na etapa 4 para habilitar o cálculo.</p>}
                              {!pb1Dtm&&<p className="pecas-note">Vincule o MDT numérico na etapa 2.</p>}
                              <button type="button" className="pecas-primary" disabled={pb1Busy||!pb1Ready||!pb1Draft.length||!pb1Dtm} onClick={()=>void calculatePb1Technical()}>Calcular prévia técnica PB1</button>
                              {pb1TechnicalResult&&<div className="pecas-note"><strong>Precisão horizontal resultante: {pb1TechnicalResult.horizontal_sigma_m.toFixed(3)} m</strong><p>{pb1TechnicalResult.meets_numeric_threshold?"Dentro do limiar numérico declarado":"Excede o limiar numérico declarado"} · {pb1TechnicalResult.limit_m} m. Sem aprovação automática.</p><div className="ps4-v-table-wrap"><table className="ps4-v-table"><thead><tr><th>V</th><th>Cota original</th><th>h (m)</th><th>σh (m)</th></tr></thead><tbody>{pb1TechnicalResult.points.map(p=><tr key={p.vertex_id}><td>{p.vertex_id}</td><td>{p.source_value_m.toFixed(3)}</td><td>{p.h_ellipsoidal_m.toFixed(3)}</td><td>{p.sigma_h_m?.toFixed(3)??"—"}</td></tr>)}</tbody></table></div></div>}
                              <p className="pecas-note">Prévia salva no servidor, sem substituir coordenadas oficiais. A documentação e a compatibilidade do método ainda exigem revisão RT.</p>
                            </div>
                          </details>
                          {pb1Notice&&<div role="status" className="pecas-note">{pb1Notice}</div>}
                        </section>}
                        {pa2Mode && constructionMethod === "PS4" && <section aria-label="Restituição orbital PS4">
                          <h4>PS4 — Delimitação de feição natural na imagem</h4>
                          
                          <div className="ps4-redesign-intro">
                            <div><span className="ps4-eyebrow">PS4 · FLUXO EM CINCO ETAPAS</span>
                              <h4>Sensores orbitais</h4>
                              <p>Construa a geometria de forma independente. A aferição posicional é uma etapa técnica posterior.</p></div>
                            <div className="ps4-state-pills">
                              <span className={ps4Ready ? "ps4-pill ps4-pill--ok" : "ps4-pill"}>{ps4Ready ? "Traçado fechado" : "Traçado em edição"}</span>
                              <span className={ps4ApprovalConfirmed ? "ps4-pill ps4-pill--ok" : "ps4-pill ps4-pill--danger"}>{ps4ApprovalConfirmed ? "RT aprovou PS4" : "Acurácia pendente"}</span>
                            </div>
                          </div>
                          {!ps4ApprovalConfirmed && <div className="ps4-alert-red" role="alert">
                            <strong>PS4 ainda é preliminar</strong>
                            <p>A restituição na imagem não comprova precisão horizontal. A avaliação da imagem e a conferência do RT são independentes do fechamento geométrico. A ODS oficial permanece sujeita aos controles técnicos.</p>
                          </div>}

                          <details className={"ps4-flow-card ps4-flow-card--normal"} open>
                            <summary className="ps4-flow-summary">
                              <span className="ps4-step-no">1</span>
                              <span className="ps4-step-heading"><strong>Escolher cena orbital</strong><small>Selecionar ou reutilizar o recorte CBERS-4A</small></span>
                              <span className="ps4-step-state">{ps4RasterAsset ? "Recorte pronto" : "Selecionar cena"}</span>
                              <span className="ps4-step-caret" aria-hidden="true">⌄</span>
                              
                            </summary>
                            <div className="ps4-flow-body">
                              <details className="geo97-cbers-panel" open>
                            <summary>INPE · CBERS-4A WPM — cenas, thumbnails e enquadramento automático</summary>
                            {ps4RasterAsset && <div className="geo96-next-step" role="status">
                              <strong>RECORTE JÁ EXISTENTE NESTA PEÇA — não é necessário importar novamente.</strong>
                              <p>GeoTIFF armazenado: {ps4RasterAsset.metadata?.width ?? "?"} ×
                                {ps4RasterAsset.metadata?.height ?? "?"} pixels ·
                                {(ps4RasterAsset.size_bytes/1024/1024).toFixed(2)} MB ·
                                SHA-256 {ps4RasterAsset.sha256.slice(0,16)}…</p>
                              <p>Você pode utilizar o recorte atual para marcar vértices V provisórios.
                                Para substituí-lo, selecione outra imagem, confirme a operação e aguarde
                                a importação completa. O raster anterior permanece preservado se a nova
                                importação falhar. A certificação exige relatório e aprovação RT.</p>
                            </div>}
                            <p className="pecas-note">Escolha a imagem com base no enquadramento do imóvel.
                              As cenas RGB disponíveis são carregadas no mapa após a seleção.
                              A coleção L4 oferece metadados/miniaturas; sua composição multibanda
                              ainda depende de um renderizador específico.</p>
                            <InpeCbersSceneSearch geometry={displaySituationGeometry}
                              geometryKey={displaySituationKey}
                              selectedScene={ps4SceneId}
                              onPrepareScene={async (scene, collection, bounds) => {
                                if (ps4RasterAsset && !window.confirm(
                                  "Já existe um recorte salvo nesta peça. Deseja solicitar outro? " +
                                  "O anterior será excluído SOMENTE após o novo arquivo ser recebido e vinculado com sucesso. " +
                                  "Os vértices PS4 anteriores deverão ser novamente conferidos."
                                )) throw new Error("Importação cancelada; recorte existente preservado.");
                                if (scene !== ps4SceneId && ps4Draft.length &&
                                  !window.confirm("Importar outra cena removerá os vértices V anteriores. Confirma?")) {
                                  throw new Error("Troca de cena cancelada.");
                                }
                                // Não apagar os V atuais ANTES de a substituição ser validada.
                                // A API rejeita recortes duplicados ou concorrentes (409).
                                const id = await onSavePiece(editableMemorial.trim(), draftForSave());
                                const response = await fetch(
                                  `${getApiUrl()}/technical-pieces/${id}/ps4/inpe/prepare`,
                                  {
                                    method:"POST",credentials:"include",
                                    headers:{"Content-Type":"application/json"},
                                    body:JSON.stringify({
                                      item_id:scene,
                                      collection,
                                      bbox:[bounds.west,bounds.south,bounds.east,bounds.north],
                                    }),
                                  },
                                );
                                const result = await response.json().catch(() => null);
                                if (!response.ok) {
                                  const reason = result?.detail;
                                  throw new Error(typeof reason === "string"
                                    ? reason : "Recorte CBERS não foi gerado.");
                                }
                                const jobId = String(result?.job?.id ?? "");
                                if (!jobId) throw new Error("O servidor não retornou o identificador do recorte CBERS.");
                                setPs4Status({kind:"info",message:"Recorte CBERS enfileirado. Aguardando o worker GDAL..."});
                                let completed = false;
                                for (let attempt = 0; attempt < 96; attempt += 1) {
                                  await new Promise(resolve => window.setTimeout(resolve, 2500));
                                  const check = await fetch(
                                    `${getApiUrl()}/technical-pieces/${id}/ps4/inpe/jobs/${jobId}`,
                                    {credentials:"include",cache:"no-store"},
                                  );
                                  const outcome = await check.json().catch(() => null);
                                  if (!check.ok) throw new Error(
                                    typeof outcome?.detail === "string" ? outcome.detail :
                                    "Não foi possível consultar o andamento do recorte."
                                  );
                                  const status = String(outcome?.job?.status ?? "");
                                  if (status === "READY") { completed = true; break; }
                                  if (status === "FAILED" || status === "CANCELLED") {
                                    throw new Error(String(outcome?.job?.message || "Importação CBERS não concluída."));
                                  }
                                  if (attempt % 4 === 0) {
                                    setPs4Status({kind:"info",message:
                                      String(outcome?.job?.message || "Preparando recorte orbital...")});
                                  }
                                }
                                if (!completed) throw new Error(
                                  "O recorte continua no servidor. Reabra a peça para consultar o resultado."
                                );
                                setPs4Draft([]);
                                setPs4ClosureConfirmed(false);
                                setPs4ConfirmedSignature("");
                                setPs4Quality(undefined);
                                setOfficialOverlap(undefined);
                                setPs4Candidate(null);
                                setPs4ApprovalConfirmed(false);
                                setPs4OrthoReport({
                                  scene_id:scene,reference:"",rms_m:null,reviewed_by_rt:false,
                                });
                                setPs4SceneId(scene);
                                setPs4Armed(true);
                                setPs4ImportRevision(value=>value+1);
                                setPs4Status({kind:"info",message:
                                  "Recorte CBERS da cena "+scene+
                                  " importado. Falta conferir o relatório e a acurácia absoluta pelo RT."});
                              }}
                              onSelectScene={scene=>{
                                if (scene!==ps4SceneId && ps4Draft.length>0 &&
                                  !window.confirm("Trocar de cena remove os pontos V deste rascunho para evitar misturar imagens. Deseja continuar?"))return;
                                if(scene!==ps4SceneId){
                                  setPs4Draft([]);setPs4ClosureConfirmed(false);
                                  setPs4ConfirmedSignature("");setPs4Candidate(null);
                                  setPs4Quality(undefined);setOfficialOverlap(undefined);
                                }
                                setPs4SceneId(scene);setPs4Armed(true);
                                if(scene!==ps4OrthoReport.scene_id)
                                  setPs4OrthoReport({scene_id:scene,reference:"",rms_m:null,reviewed_by_rt:false});
                                setPs4Status({kind:"success",message:
                                  "Cena "+scene+" ativada para vetorização. Os pontos V serão vinculados a esta cena."});
                              }}/>
                            <div className="geo96-next-step" role="status">
                              Cena no mapa: <strong>{ps4SceneId}</strong>.
                              {ps4Armed?" Vetorização habilitada.":" Selecione a cena acima antes de criar novos V."}
                            </div>
                            {!ps4Armed&&<button type="button" className="pecas-primary"
                              onClick={()=>{setPs4Armed(true);setPs4Status({
                                kind:"info",message:"Cena atual confirmada. Clique no mapa para criar V."});
                              }}>Usar cena atual para iniciar vetorização</button>}
                          </details>
                          
                            </div>
                          </details>

                          <details className={"ps4-flow-card ps4-flow-card--normal"} open>
                            <summary className="ps4-flow-summary">
                              <span className="ps4-step-no">2</span>
                              <span className="ps4-step-heading"><strong>Marcar vértices V</strong><small>Digitalização sobre a feição natural da cena</small></span>
                              <span className="ps4-step-state">{ps4Draft.length + " V"}</span>
                              <span className="ps4-step-caret" aria-hidden="true">⌄</span>
                              
                            </summary>
                            <div className="ps4-flow-body">
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
                            <div className="ps4-v-panel-head"><strong>Vértices V provisórios</strong><span className="ps4-v-count">{ps4Draft.length} vértice(s)</span></div>
                            {ps4Draft.length > 0 && <div className="ps4-v-actions">
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
                          <div className="ps4-v-panel">
                            <div className="ps4-v-panel-head"><strong>Vértices digitalizados</strong><span className="ps4-v-count">{ps4Draft.length} V</span></div>
                            {ps4Draft.length > 0 ? <div className="ps4-v-table-wrap">
                            <table className="ps4-v-table" aria-label="Vértices V provisórios"><thead><tr><th scope="col">Ordem</th><th scope="col">Código provisório</th><th scope="col">Latitude (°)</th><th scope="col">Longitude (°)</th><th scope="col">Ação</th></tr></thead>
                              <tbody>{ps4Draft.map((point, index) => <tr key={point.name}>
                                <td>{String(index+1).padStart(2,"0")}</td>
                                <td><span className="ps4-v-code">{point.name}</span></td>
                                <td className="ps4-v-coord">{point.latitude.toFixed(8)}</td>
                                <td className="ps4-v-coord">{point.longitude.toFixed(8)}</td>
                                <td><button type="button" className="ps4-v-row-action" aria-label={"Remover vértice " + point.name}
                                  onClick={() => {
                                    setPs4Draft(old => old.filter((_, i) => i !== index));
                                    setPs4ClosureConfirmed(false);
                                    setPs4Status({kind:"info",message:`Vértice ${point.name} removido. Confira e feche novamente a poligonal.`});
                                  }}>
                                  Remover
                                </button></td>
                              </tr>)}</tbody>
                            </table>
                          </div> : <p className="ps4-v-help">Nenhum vértice V criado. Marque uma feição no mapa para começar.</p>}
                            <p className="ps4-v-help">Use “Salvar peça” para guardar o traçado. A atribuição definitiva do código SIGEF depende de validação e unicidade.</p>
                          </div>

                            </div>
                          </details>

                          <details className={"ps4-flow-card ps4-flow-card--normal"}>
                            <summary className="ps4-flow-summary">
                              <span className="ps4-step-no">3</span>
                              <span className="ps4-step-heading"><strong>Fechar poligonal M–V–M</strong><small>Substituição de um segmento entre marcos GNSS</small></span>
                              <span className="ps4-step-state">{ps4Ready ? "Consistente" : "Pendente"}</span>
                              <span className="ps4-step-caret" aria-hidden="true">⌄</span>
                              
                            </summary>
                            <div className="ps4-flow-body">
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
                                setPs4ConfirmedSignature(e.target.checked ? ps4Signature : "");
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
                          
                            </div>
                          </details>

                          <details className={"ps4-flow-card ps4-flow-card--danger"}>
                            <summary className="ps4-flow-summary">
                              <span className="ps4-step-no">4</span>
                              <span className="ps4-step-heading"><strong>Avaliação de acurácia</strong><small>Separada da restituição; não impede salvar rascunho</small></span>
                              <span className="ps4-step-state">{ps4ApprovalConfirmed ? "Conferida pelo RT" : "Pendente"}</span>
                              <span className="ps4-step-caret" aria-hidden="true">⌄</span>
                              
                            </summary>
                            <div className="ps4-flow-body">
                              <Ps4RasterDiagnosticCard pieceId={loadedPieceId}
                              rasterSha256={ps4RasterAsset?.sha256 ?? null}
                              vertices={ps4Draft} sceneId={ps4SceneId} />
                            <Ps4CheckpointAnalysis pieceId={loadedPieceId}
                              sceneId={ps4SceneId}
                              rasterSha256={ps4RasterAsset?.sha256 ?? null}
                              marks={topconBoundary.filter(p=>p.name.includes("-M-") || p.name.startsWith("M")).map(p=>({
                                name: p.name, longitude: p.longitude, latitude: p.latitude,
                              }))}
                              lastImageClick={ps4CheckPoint}
                              capturing={ps4CheckCapture}
                              onCapture={enabled=>{setPs4CheckCapture(enabled);setPs4CheckPoint(null);}} />
                            <div className="ps4-analysis-note" role="status">
                              <strong>Processamento próprio ativo · análise visual e geométrica</strong>
                              <p>O sistema calcula indicadores de contraste, textura e cobertura sobre o GeoTIFF real. Esses indicadores ajudam a avaliar o material, mas não fornecem acurácia absoluta. RMS/EMQ posicional e sigmas permanecem pendentes.</p>
                            </div><details className="geo97-cbers-panel">
                            <summary>Via complementar · relatório ou pontos independentes (opcional)</summary>
                            <div className="geo97-ortho-rms">
                              <h4>Via principal · RMS do relatório de ortorretificação (INCRA 3.4.2)</h4>
                              <p className="pecas-note">Pontos GNSS independentes são facultativos.
                                O credenciado deve verificar o relatório de ortorretificação da imagem
                                efetivamente selecionada e a identificabilidade do limite.</p>
                              <label className="pecas-field"><span>Identificador do relatório / fornecedor / data</span>
                                <input value={ps4OrthoReport.reference}
                                  placeholder="Referência verificável do relatório de ortorretificação"
                                  onChange={e=>setPs4OrthoReport(p=>({...p,scene_id:ps4SceneId,
                                    reference:e.target.value,reviewed_by_rt:false}))}/></label>
                              <label className="pecas-field"><span>RMS horizontal absoluto declarado (m)</span>
                                <input inputMode="decimal" type="number" step="0.001" min="0"
                                  value={ps4OrthoReport.rms_m??""}
                                  onChange={e=>setPs4OrthoReport(p=>({...p,scene_id:ps4SceneId,
                                    rms_m:e.target.value===""?null:Number(e.target.value),
                                    reviewed_by_rt:false}))}/></label>
                              <label className="pecas-check">
                                <input type="checkbox" checked={ps4OrthoReport.reviewed_by_rt}
                                  disabled={ps4OrthoReport.scene_id!==ps4SceneId ||
                                    !ps4OrthoReport.reference.trim() ||
                                    ps4OrthoReport.rms_m===null || !Number.isFinite(ps4OrthoReport.rms_m) ||
                                    ps4OrthoReport.rms_m<0}
                                  onChange={e=>setPs4OrthoReport(p=>({...p,reviewed_by_rt:e.target.checked}))}/>
                                RT conferiu a origem, a cena correspondente, o RMS e a feição natural
                              </label>
                              <p className="pecas-note" role="status">
                                {ps4OrthoReport.scene_id===ps4SceneId && ps4OrthoReport.reviewed_by_rt
                                  ? ps4OrthoReport.rms_m!==null && ps4OrthoReport.rms_m<=3
                                    ? "RMS informado dentro de 3 m e revisão RT registrada; confirmar demais requisitos técnicos antes de qualquer certificação."
                                    : "RMS informado superior a 3 m. Não atende à referência horizontal de limite natural."
                                  : "RMS posicional absoluto ainda não conferido para esta cena. PS4 permanece preliminar."}
                              </p>
                            </div>
                            <h4>Via complementar · pontos GNSS independentes (opcional)</h4>
                            <p className="pecas-note">A ortorretificação L4 e o GSD de 2 m NÃO
                              comprovam precisão absoluta de até 3 m. Utilize pontos independentes,
                              bem distribuídos, com coordenadas observadas na imagem e GNSS de referência.</p>
                            <label className="pecas-field"><span>Origem do levantamento independente / relatório</span>
                              <input value={ps4QualitySource} placeholder="Ex.: Relatório GNSS de controle nº..., data e RT"
                                onChange={e=>{setPs4QualitySource(e.target.value);setPs4Quality(undefined);}}/>
                            </label>
                            <label className="pecas-field"><span>CSV de pontos de checagem da cena (graus decimais)</span>
                              <input type="file" accept=".csv,.txt" onChange={e=>{
                                const file=e.currentTarget.files?.[0];
                                if(file)void importPs4AccuracyControls(file);
                                e.currentTarget.value="";
                              }}/></label>
                            <p className="pecas-note">Colunas: ID;LON_IMAGEM;LAT_IMAGEM;LON_CONTROLE;LAT_CONTROLE.
                              Critério INTERNO de triagem: ao menos 20 pontos distribuídos
                              em quatro quadrantes, RMSE e percentil 90 até 3 m.
                              Isso não substitui avaliação de acurácia pelo RT nem confirma norma SIGEF.</p>
                            {ps4QualityError&&<p className="pecas-warning" role="alert">{ps4QualityError}</p>}
                            {ps4Quality&&<div className="geo96-next-step" role="status">
                              <strong>Diagnóstico: {ps4Quality.status==="INSUFICIENTE"?
                                "Amostragem insuficiente":"Exige revisão do responsável técnico"}</strong>
                              <p>Controles: {ps4Quality.checkpoints} · quadrantes: {ps4Quality.quadrant_count}/4 ·
                                RMSE horizontal: {ps4Quality.rmse_m.toFixed(3)} m ·
                                P90: {ps4Quality.p90_m.toFixed(3)} m ·
                                máximo: {ps4Quality.max_m.toFixed(3)} m.</p>
                              <p>{ps4Quality.preliminary_criterion_met?
                                "Triagem interna atendida. Ainda falta a validação técnica documentada.":
                                "Triagem não atendida. Não utilizar a cena como fonte de precisão comprovada."}</p>
                            </div>}
                          </details>
                          <details className="ps4-documentary-toggle"><summary>Via documental legada · anexar relatório (opcional nesta fase de estudo)</summary><Ps4EvidencePanel
                            pieceId={loadedPieceId}
                            refreshRevision={ps4ImportRevision}
                            sceneId={ps4SceneId}
                            vertices={ps4Draft}
                            rmsFromWorkspace={ps4OrthoReport.rms_m}
                            onApprovalChange={setPs4ApprovalConfirmed}
                            onRasterChange={setPs4RasterAsset}
                            onReportChange={setPs4ReportAttached}
                            onEnsurePieceSaved={() => onSavePiece(
                              editableMemorial.trim(), draftForSave()
                            )}
                            onSceneChange={scene => {
                              if (scene !== ps4SceneId && ps4Draft.length &&
                                !window.confirm(
                                  "Trocar a cena invalida os vértices V associados à anterior. Deseja removê-los?"
                                )) return;
                              if (scene !== ps4SceneId) {
                                setPs4Draft([]); setPs4ClosureConfirmed(false);
                                setPs4ConfirmedSignature(""); setPs4Candidate(null);
                                setPs4ApprovalConfirmed(false); setOfficialOverlap(undefined);
                              }
                              setPs4SceneId(scene);
                              setPs4Armed(true);
                              setPs4Status({kind:"info", message:
                                "Cena do relatório vinculada ao mapa: " + scene +
                                ". Salve a peça antes de solicitar a aprovação."});
                            }}
                          />
                          <p>Marque pontos sucessivos na imagem INPE carregada ou no recorte privado.
                            O GeoTIFF manual e o relatório PDF NÃO são pré-requisitos para DESENHAR
                            os pontos V como rascunho. Para validar tecnicamente o PS4, os documentos,
                            a precisão absoluta e a conferência do RT continuam obrigatórios.
                            A prévia é PRELIMINAR e não substitui a validação SIGEF.</p>
                          <div className={ps4Ready?"geo96-next-step":"pecas-note"} role="status">
                            <strong>{ps4Ready
                              ? "Construção PS4 concluída: traçado M–V–M fechado e pronto para peça preliminar."
                              : "Construção PS4 em andamento: selecione cena, vetorize e confirme fechamento."}</strong>
                            <p>A conclusão da vetorização não é uma certificação SIGEF.
                              O PDF preliminar pode ser gerado mesmo sem laudo RMS, sempre com indicação
                              explícita das limitações. A ODS preenchida para SIGEF só poderá ser
                              liberada após validar os requisitos técnicos separadamente.</p>
                          </div>
                          <div className={ps4OrthoReport.reviewed_by_rt &&
                            ps4OrthoReport.scene_id===ps4SceneId &&
                            ps4OrthoReport.rms_m!==null &&
                            ps4OrthoReport.rms_m<=3?"geo96-next-step":"pecas-note"}
                            role="status">
                            {ps4OrthoReport.reviewed_by_rt &&
                              ps4OrthoReport.scene_id===ps4SceneId &&
                              ps4OrthoReport.rms_m!==null &&
                              ps4OrthoReport.rms_m<=3
                              ? "RMS documental informado e conferido pelo RT. A aceitação técnica exige revisão da documentação, da cena e do limite natural."
                              : "Comprovação de acurácia pendente somente para uso técnico certificável: relatório de ortorretificação e revisão RT. A construção preliminar continua disponível."}
                          </div>
                          <p><strong>Cena em edição:</strong> {ps4SceneId} ·
                            {ps4Armed?" vetorização habilitada":" escolha a cena antes de clicar"}.</p>
                          </details>
                            </div>
                          </details>

                          <details className={"ps4-flow-card ps4-flow-card--normal"}>
                            <summary className="ps4-flow-summary">
                              <span className="ps4-step-no">5</span>
                              <span className="ps4-step-heading"><strong>Salvar e revisar</strong><small>Persistir os vértices provisórios e retornar à peça</small></span>
                              <span className="ps4-step-state">{ps4Ready ? "Pronto para salvar" : "Rascunho"}</span>
                              <span className="ps4-step-caret" aria-hidden="true">⌄</span>
                              
                            </summary>
                            <div className="ps4-flow-body">
                              <p>O arquivo da peça guarda os V provisórios sem confundi-los com posicionamento certificável. O processamento da cena e a conferência RT serão executados separadamente.</p>
                              <button type="button" className="pecas-primary" disabled={actionBusy}
                                onClick={() => void runAction(async () => {
                                  await onSavePiece(editableMemorial.trim() ? editableMemorial : "", draftForSave());
                                  setSavedPieceNotice("Vértices V provisórios salvos. Acurácia PS4 ainda pendente.");
                                })}>{actionBusy ? "Salvando..." : "Salvar rascunho dos vértices V"}</button>
                            </div>
                          </details>
                        </section>}
                        {pa2Mode && constructionMethod !== "PS4" && constructionMethod !== "PB1" && <>
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
            <div className={constructionMethod === "PS4" || constructionMethod === "PB1" ? "ps4-map-column" : undefined} style={{ overflow: "auto", minHeight: 0 }}>
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
                    pb1Raster={constructionMethod==="PB1" && pb1Raster && pb1PieceId
                      ?{pieceId:pb1PieceId,sha256:pb1Raster.sha256,
                        footprint:pb1Raster.metadata?.wgs84_extent}:null}
                    pb1Dtm={constructionMethod==="PB1" && pb1Dtm && pb1PieceId
                      ?{pieceId:pb1PieceId,sha256:pb1Dtm.sha256,
                        footprint:pb1Dtm.metadata?.wgs84_extent}:null}
                    ps4SceneId={ps4SceneId}
                    ps4ReportAttached={ps4ReportAttached}
                    ps4Raster={loadedPieceId && ps4RasterAsset?.kind === "raster"
                      ? {pieceId:loadedPieceId, sha256:ps4RasterAsset.sha256,
                         footprint:ps4RasterAsset.metadata?.wgs84_extent}
                      : null}
                    ps4Points={constructionMethod==="PB1"?pb1Draft:ps4Draft}
                    ps4Candidate={constructionMethod==="PB1"?pb1Candidate:ps4Candidate}
                    ps4CheckCapture={constructionMethod==="PB1"?false:ps4CheckCapture}
                    ps4ClosureGeometry={constructionMethod==="PB1"?(pb1Ready?pb1Closure.geometry:null):ps4PreviewGeometry}
                    onPs4Click={point => {
                       if(constructionMethod==="PB1"){
                         if(!pb1Raster){setPb1Notice("Importe o ORIXP georreferenciado antes de capturar V.");return;}
                         setPb1Candidate(point);
                         setPb1Notice("Ponto capturado no ORIXP. Confirme a inclusão e a amostragem MDT na coluna esquerda.");
                         return;
                       }
                       if (ps4CheckCapture) {
                         setPs4CheckPoint(point);setPs4CheckCapture(false);
                         setPs4Status({kind:"info",message:"Ponto de imagem capturado para confronto GNSS. Confirme a feição na etapa 4."});
                         return;
                       }
                      if(!ps4Armed){
                        setPs4Status({kind:"error",message:"Selecione uma cena INPE e clique em iniciar vetorização antes de marcar V."});
                        return;
                      }
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
                  {constructionMethod !== "PS4" && constructionMethod !== "PB1" ? <>
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
        </div>
      </div>
    </section>
  );
}
