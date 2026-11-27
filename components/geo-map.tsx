"use client";

import { useEffect, useRef, useState } from "react";
import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import MVT from "ol/format/MVT";
import KML from "ol/format/KML";
import Draw from "ol/interaction/Draw";
import Modify from "ol/interaction/Modify";
import Snap from "ol/interaction/Snap";
import Map from "ol/Map";
import MapBrowserEvent from "ol/MapBrowserEvent";
import LineString from "ol/geom/LineString";
import MultiPolygon from "ol/geom/MultiPolygon";
import Point from "ol/geom/Point";
import Polygon from "ol/geom/Polygon";
import ImageLayer from "ol/layer/Image";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorTileLayer from "ol/layer/VectorTile";
import { fromLonLat, toLonLat } from "ol/proj";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import ImageWMS from "ol/source/ImageWMS";
import VectorSource from "ol/source/Vector";
import VectorTileSource from "ol/source/VectorTile";
import { Fill, Stroke, Style, Circle as CircleStyle, Text as TextStyle } from "ol/style";
import View from "ol/View";
import { getArea, getLength } from "ol/sphere";
import { getApiUrl } from "@/lib/api";
import { trackedFetch } from "@/components/app-feedback";
import { LayerAttributeSearch, type LayerSearchResult } from "@/components/layer-attribute-search";
import { PecasTecnicasWorkspace, DEFAULT_PLANT_ELEMENTS, type PecasData, type PlantElementFlags, type PlantElementKey, type ProfessionalDocumentProfile, type TopconBoundaryPoint, type TopconDraft } from "@/components/pecas-tecnicas-workspace";
import type { SituationSnapshot } from "@/components/situation-map-preview";
import type { TechnicalPieceSnapshot } from "@/components/technical-pieces-module";
import { parseManualCoordinates, type ManualCoordinateMode } from "@/lib/geospatial-tools";
import {
  ArrowLeft,
  Crosshair,
  Eraser,
  FileUp,
  Info,
  MapPin,
  Magnet,
  Layers3,
  Download,
  ListPlus,
  Trash2,
  Pencil,
  Pentagon,
  Ruler,
  Satellite,
  Sparkles,
  X,
} from "lucide-react";

type DrawKind = "Point" | "Polygon" | null;

interface GeoMapProps {
  onGeometryChange: (geometry: Record<string, unknown> | null) => void;
  hideAdvancedTools?: boolean;
  focusRequest?: { sourceId: string; nonce: number } | null;
  incraUf: string;
  resetNonce?: number;
  analysisId?: string | null;
  analysisPanelOpen?: boolean;
  restorePiece?: { id: string; snapshot: TechnicalPieceSnapshot; nonce: number } | null;
  onPieceSaved?: () => void;
  startTopconNonce?: number;
  layers: Array<{
    id?: string;
    slug?: string;
    name: string;
    color: string;
    enabled: boolean;
    featureCount?: number;
    source?: string;
    wmsEnabled?: boolean;
    wmsTheme?: string;
    wmsFixedLayer?: string;
    wmsAvailableUfs?: string[];
  }>;
}

const subjectStyle = new Style({
  fill: new Fill({ color: "rgba(27, 126, 85, 0.18)" }),
  stroke: new Stroke({ color: "#0d6847", width: 3 }),
  image: new CircleStyle({
    radius: 8,
    fill: new Fill({ color: "#e44f5f" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});

// Parcelas escolhidas para download (qualquer base).
const downloadParcelStyle = new Style({
  fill: new Fill({ color: "rgba(255, 128, 0, 0.22)" }),
  stroke: new Stroke({ color: "#ff8000", width: 3, lineDash: [8, 4] }),
});

type DownloadParcel = {
  id: string;
  name: string;
  layer: string;
  properties: Record<string, string>;
  visible: boolean;
};

const officialStyleCache = new globalThis.Map<string, Style>();
const selectedOfficialStyle = new Style({
  fill: new Fill({ color: "rgba(255, 193, 7, 0.35)" }),
  stroke: new Stroke({ color: "#ff9f1c", width: 4 }),
  image: new CircleStyle({
    radius: 7,
    fill: new Fill({ color: "#ff9f1c" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});

// Destaque universal da ferramenta Identificar.
// Duas passadas de estilo garantem contraste sobre qualquer camada/base.
const identifyHighlightStyles = [
  // halo branco: separa a seleção de qualquer simbologia existente
  new Style({
    fill: new Fill({ color: "rgba(255, 159, 28, 0.10)" }),
    stroke: new Stroke({ color: "rgba(255,255,255,0.98)", width: 10 }),
    image: new CircleStyle({
      radius: 12,
      fill: new Fill({ color: "rgba(255,255,255,0.98)" }),
      stroke: new Stroke({ color: "rgba(23,63,50,0.35)", width: 2 }),
    }),
  }),
  // corpo laranja: seleção propriamente dita
  new Style({
    fill: new Fill({ color: "rgba(255, 225, 0, 0.72)" }),
    stroke: new Stroke({ color: "#e0a500", width: 5 }),
    image: new CircleStyle({
      radius: 8,
      fill: new Fill({ color: "#ffe100" }),
      stroke: new Stroke({ color: "#ffffff", width: 2 }),
    }),
  }),
];

type IdentifiedFeature = {
  title: string;
  layer: string;
  attributes: Array<[string, unknown]>;
  loading?: boolean;
};

type IdentifyCandidate = { feature: Feature; title: string; layer: string };

function featureIdentity(feature: Feature) {
  const raw = feature.getProperties();
  const layer = String(raw.catalogName ?? raw.source_name ?? "Camada oficial");
  const title = String(
    raw.name ??
      raw.nome ??
      raw.nome_imovel ??
      raw.nome_parcela ??
      raw.denominacao_imovel ??
      raw.codigo_parcela ??
      raw.codigo_imovel ??
      raw.codigo_sigef ??
      raw.nome_uc ??
      raw.nome_proje ??
      raw.nom_pessoa ??
      raw.denominacao ??
      raw.external_id ??
      "Feição identificada",
  );
  return { raw, layer, title };
}

function fieldLabel(field: string) {
  const labels: Record<string, string> = {
    catalogName: "Camada",
    source_name: "Fonte",
    source_id: "Identificador da fonte",
    feature_id: "Identificador interno",
    external_id: "Identificador na origem",
  };
  return (
    labels[field] ??
    field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

function fieldValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function officialStyle(color: string) {
  if (!officialStyleCache.has(color)) {
    officialStyleCache.set(
      color,
      new Style({
        fill: new Fill({ color: `${color}38` }),
        stroke: new Stroke({ color, width: 2 }),
        image: new CircleStyle({
          radius: 5,
          fill: new Fill({ color }),
          stroke: new Stroke({ color: "#ffffff", width: 1 }),
        }),
      }),
    );
  }
  return officialStyleCache.get(color)!;
}

const UF_VIEW: Record<string, { center: [number, number]; zoom: number }> = {
  AC: { center: [-70.3, -9.0], zoom: 6.4 },
  AL: { center: [-36.6, -9.6], zoom: 7.6 },
  AP: { center: [-51.8, 1.4], zoom: 6.6 },
  AM: { center: [-64.6, -4.5], zoom: 5.4 },
  BA: { center: [-41.8, -12.5], zoom: 6.0 },
  CE: { center: [-39.5, -5.2], zoom: 6.8 },
  DF: { center: [-47.8, -15.8], zoom: 9.0 },
  ES: { center: [-40.5, -19.6], zoom: 7.4 },
  GO: { center: [-49.3, -15.9], zoom: 6.4 },
  MA: { center: [-45.3, -5.0], zoom: 6.2 },
  MT: { center: [-56.1, -12.6], zoom: 5.8 },
  MS: { center: [-54.5, -20.5], zoom: 6.1 },
  MG: { center: [-44.3, -18.5], zoom: 6.0 },
  PA: { center: [-52.5, -3.8], zoom: 5.8 },
  PB: { center: [-36.7, -7.1], zoom: 7.4 },
  PR: { center: [-51.5, -24.6], zoom: 6.5 },
  PE: { center: [-37.9, -8.4], zoom: 7.0 },
  PI: { center: [-42.7, -7.5], zoom: 6.3 },
  RJ: { center: [-43.2, -22.2], zoom: 7.4 },
  RN: { center: [-36.6, -5.8], zoom: 7.4 },
  RS: { center: [-53.2, -30.0], zoom: 6.0 },
  RO: { center: [-63.1, -10.9], zoom: 6.4 },
  RR: { center: [-61.3, 2.1], zoom: 6.4 },
  SC: { center: [-50.2, -27.3], zoom: 7.0 },
  SP: { center: [-48.7, -22.3], zoom: 6.5 },
  SE: { center: [-37.4, -10.6], zoom: 7.6 },
  TO: { center: [-48.3, -10.2], zoom: 6.3 },
  ALL: { center: [-52.3, -14.5], zoom: 4.2 },
};

export function GeoMap({ onGeometryChange, layers, incraUf, resetNonce = 0, hideAdvancedTools = false, focusRequest = null, analysisId = null, analysisPanelOpen = false, restorePiece = null, onPieceSaved, startTopconNonce = 0 }: GeoMapProps) {
  const mapElement = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef(new VectorSource());
  const measureSourceRef = useRef(new VectorSource());
  const attributeSearchSourceRef = useRef(new VectorSource());
  const [measureMode, setMeasureMode] = useState<"LineString" | "Polygon" | null>(null);
  const [measureValue, setMeasureValue] = useState("");
  const officialSourceRef = useRef(new VectorSource());
  const snapLayerSourceRef = useRef(new VectorSource());
  const vertexLabelSourceRef = useRef(new VectorSource());
  const baseLayerRef = useRef<TileLayer<OSM | XYZ> | null>(null);
  const autoFocusRef = useRef<string | null>(null);

  // Overlay exclusivo da ferramenta Identificar.
  // Toda feição selecionada, independentemente da base de origem,
  // será materializada aqui para garantir destaque visual uniforme.
  const identifySelectionSourceRef = useRef(
    new VectorSource(),
  );
  const wmsLayersRef = useRef(
    new globalThis.Map<string, ImageLayer<ImageWMS>>(),
  );
  const vectorTileLayersRef = useRef(
    new globalThis.Map<string, VectorTileLayer>(),
  );
  const layersRef = useRef(layers);
  const incraUfRef = useRef(incraUf);
  incraUfRef.current = incraUf;
  const identifyAbortRef = useRef<AbortController | null>(null);
  const drawRef = useRef<Draw | null>(null);
  const modifyRef = useRef<Modify | null>(null);
  const snapSubjectRef = useRef<Snap | null>(null);
  const snapLayersRef = useRef<Snap | null>(null);
  const identifyActiveRef = useRef(false);
  const selectedFeatureRef = useRef<Feature | null>(null);
  const identifyCandidateHistoryRef = useRef<IdentifyCandidate[]>([]);
  const selectFeatureRef = useRef<(feature: Feature) => void>(() => undefined);
  const [drawKind, setDrawKind] = useState<DrawKind>(null);
  const [modifyActive, setModifyActive] = useState(false);
  const [identifyActive, setIdentifyActive] = useState(false);
  const [featurePanelOffset, setFeaturePanelOffset] = useState({ x: 0, y: 0 });
  const featureDragRef = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null);
  const [identifiedFeature, setIdentifiedFeature] =
    useState<IdentifiedFeature | null>(null);
  const [identifyLoading, setIdentifyLoading] = useState(false);
  const [identifyLoadingMessage, setIdentifyLoadingMessage] = useState(
    "Aguardando informações…",
  );
  const [identifyCandidates, setIdentifyCandidates] = useState<
    IdentifyCandidate[]
  >([]);
  const [officialCount, setOfficialCount] = useState(0);
  const [snapSubjectEnabled, setSnapSubjectEnabled] = useState(true);
  const [snapLayersEnabled, setSnapLayersEnabled] = useState(false);
  const [advancedPanel, setAdvancedPanel] = useState<"coordinates" | "snap" | "basemap" | "memorial" | "polygons" | null>(null);
  const [polygons, setPolygons] = useState<Array<{ id: string; name: string; vertices: string[]; confrontants: string[]; altitudes: string[]; areaHa: number; perimeterM: number }>>([]);
  const [selectedPolygonIds, setSelectedPolygonIds] = useState<string[]>([]);
  const polygonSequenceRef = useRef(0);
  // Polígonos de trabalho desmarcados pelo usuário ficam ocultos no mapa.
  const hiddenPolygonIdsRef = useRef(new Set<string>());
  const downloadSourceRef = useRef(new VectorSource());
  const downloadSequenceRef = useRef(0);
  const [downloadParcels, setDownloadParcels] = useState<DownloadParcel[]>([]);
  const [downloadPanelOpen, setDownloadPanelOpen] = useState(true);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [croquiNote, setCroquiNote] = useState(true);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [manualMode, setManualMode] = useState<ManualCoordinateMode>("DD");
  const [manualText, setManualText] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [basemap, setBasemap] = useState("osm");
  const [googleTilesEnabled, setGoogleTilesEnabled] = useState(false);
  const [mapboxTilesEnabled, setMapboxTilesEnabled] = useState(false);
  const [googleCopyright, setGoogleCopyright] = useState("");
  const [googleBasemapError, setGoogleBasemapError] = useState("");
  const [extentMessage, setExtentMessage] = useState<string | null>(null);
  const [importingVector, setImportingVector] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importedMetadata, setImportedMetadata] = useState<Record<string, string> | null>(null);
  const [importNotice, setImportNotice] = useState<string | null>(null);

  // A confirmação de importação é transitória. O temporizador é
  // reiniciado para cada nova importação e cancelado na desmontagem.
  useEffect(() => {
    if (!importNotice) return;
    const timeout = window.setTimeout(() => setImportNotice(null), 7000);
    return () => window.clearTimeout(timeout);
  }, [importNotice]);
  const [geometryMetrics, setGeometryMetrics] = useState<{
    areaHectares: number | null;
    perimeterMeters: number | null;
    vertices: number;
  }>({ areaHectares: null, perimeterMeters: null, vertices: 0 });
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  // Começar em zero é essencial: GeoMap é montado novamente ao sair da
  // lista de peças e o pedido recebido nesse primeiro render não pode sumir.
  const lastStartTopconNonce = useRef(0);
  useEffect(() => {
    if (!startTopconNonce || startTopconNonce === lastStartTopconNonce.current) return;
    lastStartTopconNonce.current = startTopconNonce;
    // Novo projeto independente: limpar geometria, seleção, documento e
    // qualquer vínculo com peça ou TOPCON anteriormente restaurados.
    sourceRef.current.clear();
    vertexLabelSourceRef.current.clear();
    ++metricsRevision.current;
    setPolygons([]);
    setSelectedPolygonIds([]);
    hiddenPolygonIdsRef.current.clear();
    setImportedMetadata(null);
    setLegalMetadata({});
    setMemorialTitle("Novo projeto");
    setPlantHeading("PLANTA GEORREFERENCIADA");
    setMemorialHeading("MEMORIAL DESCRITIVO");
    setMemorialOwner("");
    setOwnerRg("");
    setOwnerCpf("");
    setPropertyAddress("");
    setEditedMemorial(null);
    setMemorialText("");
    setLastGeneratedPdfId(null);
    setSituationSnapshot(null);
    setGeometryMetrics({areaHectares:null,perimeterMeters:null,vertices:0});
    onGeometryChange(null);
    setAdvancedPanel(null);
    setCurrentPieceId(null);
    setLoadedTopconDraft(null);
    setLoadedTopconRevision(startTopconNonce);
    setLoadedMemorialDraft(null);
    setWorkspaceOpen(true);
  }, [startTopconNonce]);
  const [documentProfessional, setDocumentProfessional] = useState<ProfessionalDocumentProfile | null>(null);
  const [documentProfessionalLoading, setDocumentProfessionalLoading] = useState(false);
  const [documentProfessionalError, setDocumentProfessionalError] = useState("");
  const documentProfessionalEdited = useRef(false);
  const [reloadProfessional, setReloadProfessional] = useState(0);
  const [situationSnapshot, setSituationSnapshot] = useState<SituationSnapshot | null>(null);
  const [plantElements, setPlantElements] = useState<PlantElementFlags>({ ...DEFAULT_PLANT_ELEMENTS });
  const [magneticDeclination, setMagneticDeclination] = useState("");
  const [currentPieceId, setCurrentPieceId] = useState<string | null>(null);
  const [lastGeneratedPdfId, setLastGeneratedPdfId] = useState<string | null>(null);
  const [loadedMemorialDraft, setLoadedMemorialDraft] = useState<string | null>(null);
  const [loadedTopconDraft, setLoadedTopconDraft] = useState<TopconDraft | null>(null);
  const [loadedTopconRevision, setLoadedTopconRevision] = useState(0);
  const restoreNonceRef = useRef(0);
  useEffect(() => {
    if (!workspaceOpen) return;
    let active = true;
    setDocumentProfessionalLoading(true);
    setDocumentProfessionalError("");
    void fetch(`${getApiUrl()}/auth/me/professional-profile`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Não foi possível consultar o cadastro do responsável técnico.");
        return response.json();
      })
      .then((profile) => {
        if (!active || documentProfessionalEdited.current) return;
        const fields = ["full_name", "rg", "cpf", "profession", "specialization", "crea", "visto", "incra_code", "art"] as const;
        const draft = {} as ProfessionalDocumentProfile;
        for (const key of fields) draft[key] = String(profile[key] ?? "");
        setDocumentProfessional(draft);
      })
      .catch((error) => { if (active) setDocumentProfessionalError(error instanceof Error ? error.message : "Erro ao consultar perfil técnico."); })
      .finally(() => { if (active) setDocumentProfessionalLoading(false); });
    return () => { active = false; };
  }, [workspaceOpen, reloadProfessional]);

  const refreshDocumentProfessional = () => {
    documentProfessionalEdited.current = false;
    setReloadProfessional((previous) => previous + 1);
  };

  const [memorialLoading, setMemorialLoading] = useState(false);
  const [memorialText, setMemorialText] = useState("");
  const [editedMemorial, setEditedMemorial] = useState<string | null>(null);
  const [memorialTitle, setMemorialTitle] = useState("Área analisada");
  const [legalMetadata,setLegalMetadata] = useState<Record<string,string>>({});
  const [plantHeading, setPlantHeading] = useState("PLANTA GEORREFERENCIADA");
  const [memorialHeading, setMemorialHeading] = useState("MEMORIAL DESCRITIVO");
  const [paperFormat, setPaperFormat] = useState<"A4" | "A3" | "A2" | "A1" | "A0">("A2");
  const [paperOrientation, setPaperOrientation] = useState<"paisagem" | "retrato">("retrato");
  const [plantLayoutTemplate, setPlantLayoutTemplate] = useState<PecasData["layoutTemplate"]>("classic_lateral");
  const [scaleChoice, setScaleChoice] = useState("auto");
  const [customScale, setCustomScale] = useState("1500");
  const [surveyDate, setSurveyDate] = useState("");
  const [ownerRg, setOwnerRg] = useState("");
  const [ownerCpf, setOwnerCpf] = useState("");
  const [propertyAddress, setPropertyAddress] = useState("");
  const [memorialOwner, setMemorialOwner] = useState("");
  const [loadingOfficial, setLoadingOfficial] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState({ completed: 0, total: 0 });
  const [officialStatus, setOfficialStatus] = useState(
    "Preparando camadas oficiais…",
  );

  useEffect(() => {
    if (!resetNonce) return;
    sourceRef.current.clear();
    ++metricsRevision.current;
    setPolygons([]);
    setSelectedPolygonIds([]);
    hiddenPolygonIdsRef.current.clear();
    vertexLabelSourceRef.current.clear();
    identifySelectionSourceRef.current.clear();
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive(false);
    clearIdentifiedFeature();
  }, [resetNonce]);

  const focusSource = async (sourceId: string) => {
    const map = mapRef.current;
    if (!map) return;
    setExtentMessage(null);
    try {
      const response = await fetch(`${getApiUrl()}/sources/${sourceId}/extent`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("Não foi possível consultar a extensão da camada.");
      const payload = await response.json() as { bbox?: [number, number, number, number] | null; feature_count?: number };
      if (!payload.bbox || payload.bbox.length !== 4) {
        setExtentMessage("A camada ainda não possui feições para enquadrar.");
        return;
      }
      const [minLon, minLat, maxLon, maxLat] = payload.bbox;
      if (![minLon, minLat, maxLon, maxLat].every(Number.isFinite)) {
        throw new Error("A extensão geográfica da camada é inválida.");
      }
      const [minX, minY] = fromLonLat([minLon, minLat]);
      const [maxX, maxY] = fromLonLat([maxLon, maxLat]);
      const extent: [number, number, number, number] = [
        Math.min(minX, maxX), Math.min(minY, maxY),
        Math.max(minX, maxX), Math.max(minY, maxY),
      ];
      if (extent[0] === extent[2]) {
        extent[0] -= 250;
        extent[2] += 250;
      }
      if (extent[1] === extent[3]) {
        extent[1] -= 250;
        extent[3] += 250;
      }
      map.getView().fit(extent, {
        padding: [80, 80, 80, 80],
        maxZoom: 15,
        duration: 650,
      });
      const source = layersRef.current.find((layer) => layer.id === sourceId);
      if (source) {
        const minimum = source.slug === "sigef-interno" && (source.featureCount ?? Infinity) <= 10000
          ? 6
          : /sigef|parcela/i.test(source.name) ? 9 : 0;
        const targetZoom = Math.max(minimum + 0.2, map.getView().getZoom() ?? minimum);
        if (targetZoom > (map.getView().getZoom() ?? 0)) {
          map.getView().animate({
            zoom: targetZoom,
            duration: 650,
          });
        }
      }
    } catch (error) {
      setExtentMessage(error instanceof Error ? error.message : "Falha ao enquadrar camada.");
    }
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const target = UF_VIEW[incraUf] ?? UF_VIEW.ALL;

    setLoadingProgress({ completed: 0, total: 0 });
    setLoadingOfficial(true);
    setOfficialStatus(
      incraUf === "ALL"
        ? "Reposicionando mapa para o Brasil…"
        : `Reposicionando mapa para ${incraUf}…`,
    );

    map.getView().animate(
      {
        center: fromLonLat(target.center),
        zoom: target.zoom,
        duration: 650,
      },
    );
  }, [incraUf]);

  const polygonFeatures = (): Feature[] =>
    sourceRef.current.getFeatures().filter((feature) => feature.getGeometry() instanceof Polygon) as Feature[];

  const metricsRevision = useRef(0);
  const syncPolygonRegistry = () => {
    const revision = ++metricsRevision.current;
    const current = polygonFeatures();
    const registry = current.map((feature) => {
      const geometry = feature.getGeometry() as Polygon;
      const count = Math.max(0, (geometry.getCoordinates()[0]?.length ?? 1) - 1);
      let id = String(feature.get("workPolygonId") ?? "");
      if (!id) {
        polygonSequenceRef.current += 1;
        id = `POL-${polygonSequenceRef.current}`;
        feature.set("workPolygonId", id, true);
        feature.set("workPolygonName", `Polígono ${polygonSequenceRef.current}`, true);
      }
      const existing = (feature.get("vertexNames") as string[] | undefined) ?? [];
      const names = Array.from({ length: count }, (_, index) =>
        existing[index] ?? `${id}-V${String(index + 1).padStart(2, "0")}`,
      );
      feature.set("vertexNames", names, true);
      const oldConfrontants = (feature.get("confrontants") as string[] | undefined) ?? [];
      const oldAltitudes = (feature.get("altitudes") as string[] | undefined) ?? [];
      const confrontants = Array.from({ length: count }, (_, i) => oldConfrontants[i] ?? "");
      const altitudes = Array.from({ length: count }, (_, i) => oldAltitudes[i] ?? "");
      feature.set("confrontants", confrontants, true);
      feature.set("altitudes", altitudes, true);
      return {
        id,
        name: String(feature.get("workPolygonName") ?? id),
        vertices: names,
        coordinates: (geometry.getCoordinates()[0]??[]).slice(0,-1)
          .map(coord=>toLonLat(coord) as [number,number]),
        confrontants, altitudes,
        vertexDetails: names.map((_,i)=>({
          ...((feature.get("sigef_vertex_details") as Array<Record<string, unknown>> | undefined)?.[i]??{}),
          normal_altitude_m:(feature.get("normalAltitudeEstimates") as Array<number|null>|undefined)?.[i]??null,
        })),
        areaHa: getArea(geometry, { projection: "EPSG:3857" }) / 10000,
        perimeterM: getLength(new LineString(geometry.getCoordinates()[0] ?? []), {
          projection: "EPSG:3857",
        }),
      };
    });
    setPolygons(registry);
    if(registry.length){
      const inputs=current.map(feature=>({
        geometry:new GeoJSON().writeGeometryObject(feature.getGeometry()!,{
          featureProjection:"EPSG:3857",dataProjection:"EPSG:4326",decimals:9}),
        vertex_names:feature.get("vertexNames"),
        altitudes_m:((feature.get("altitudes") as string[]|undefined)??[]).map(v=>v?.trim()?Number(v.replace(",",".")):null)
      }));
      void fetch(getApiUrl()+"/technical-pieces/parcel-metrics",{
        method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({parcels:inputs})
      }).then(async response=>{
        if(!response.ok)throw Error("Cálculo técnico indisponível.");
        const body=await response.json();
        if(revision!==metricsRevision.current||body.parcels?.length!==registry.length)return;
        setPolygons(old=>old.map(p=>{
          const index=registry.findIndex(r=>r.id===p.id);
          const result=body.parcels[index];
          return result?{...p,areaHa:result.area_ha,perimeterM:result.perimeter_m}:p;
        }));
      }).catch(()=>{if(revision===metricsRevision.current)setDocumentError("Medidas esféricas preliminares: cálculo técnico do servidor indisponível.");});
    }
    setSelectedPolygonIds((old) => {
      const retained = old.filter((id) => registry.some((item) => item.id === id));
      if (retained.length) return retained;
      return registry.length ? [registry[registry.length - 1].id] : [];
    });
  };

  const selectedFeatures = () =>
    polygonFeatures().filter((feature) =>
      selectedPolygonIds.includes(String(feature.get("workPolygonId"))),
    );
  // Identidade geométrica: nomes/confrontantes não invalidam o recorte escolhido.
  const situationGeoJson = () => new GeoJSON().writeFeaturesObject(
    selectedFeatures().map((feature) => new Feature({
      geometry: feature.getGeometry()!.clone(),
    })),
    { featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 8 },
  );

  const setPolygonName = (id: string, name: string) => {
    const feature = polygonFeatures().find((item) => item.get("workPolygonId") === id);
    if (!feature) return;
    feature.set("workPolygonName", name, true);
    syncPolygonRegistry();
  };

  const renameVertex = (id: string, index: number, name: string) => {
    const feature = polygonFeatures().find((item) => item.get("workPolygonId") === id);
    if (!feature) return;
    const names = [...((feature.get("vertexNames") as string[] | undefined) ?? [])];
    names[index] = name;
    feature.set("vertexNames", names, true);
    syncPolygonRegistry();
    refreshVertexLabels();
  };

  const updateParcelVertexData = (
    id: string, index: number, type: "confrontants" | "altitudes", value: string,
  ) => {
    const feature = polygonFeatures().find((item) => item.get("workPolygonId") === id);
    if (!feature) return;
    const values = [...((feature.get(type) as string[] | undefined) ?? [])];
    values[index] = value;
    feature.set(type, values, true);
    syncPolygonRegistry();
  };

  const removeVertex = (id: string, index: number) => {
    setDocumentError(null);
    const feature = polygonFeatures().find((item) => item.get("workPolygonId") === id);
    if (!feature) return;
    const geometry = feature.getGeometry();
    if (!(geometry instanceof Polygon)) return;
    const rings = geometry.getCoordinates();
    const points = (rings[0] ?? []).slice(0, -1);
    if (points.length <= 3) {
      setDocumentError("O polígono precisa manter pelo menos três vértices.");
      return;
    }
    if (rings.length > 1) {
      setDocumentError("A exclusão de vértices de polígonos com ilhas deve ser feita no editor de geometria.");
      return;
    }
    const next = points.filter((_, i) => i !== index);
    const candidate = new Polygon([[...next, next[0]]]);
    if (getArea(candidate, { projection: "EPSG:3857" }) < 0.001) {
      setDocumentError("A exclusão geraria um polígono sem área. Operação cancelada.");
      return;
    }
    const names = ((feature.get("vertexNames") as string[] | undefined) ?? [])
      .filter((_, i) => i !== index);
    feature.set("vertexNames", names, true);
    for (const property of ["confrontants", "altitudes"]) {
      const values = ((feature.get(property) as string[] | undefined) ?? [])
        .filter((_, i) => i !== index);
      feature.set(property, values, true);
    }
    geometry.setCoordinates([[...next, next[0]]]);
    emitGeometry();
  };

  const removePolygon = (id: string) => {
    const feature = polygonFeatures().find((item) => item.get("workPolygonId") === id);
    if (feature) sourceRef.current.removeFeature(feature);
    emitGeometry();
  };

  const captureMapSituation = async (): Promise<{ raster_b64: string; raster_source: string }> => {
    const map = mapRef.current;
    if (!map) throw new Error("O mapa ainda não está pronto para a captura de situação.");
    const size = map.getSize();
    if (!size || size[0] <= 0 || size[1] <= 0) {
      throw new Error("O mapa precisa estar visível antes de gerar a planta.");
    }

    // A exportação utiliza os canvas raster/vetoriais já renderizados
    // pelo próprio OpenLayers, nunca uma imagem arbitrária enviada ao servidor.
    await new Promise<void>((resolve) => {
      let completed = false;
      const done = () => {
        if (completed) return;
        completed = true;
        map.un("rendercomplete", done);
        resolve();
      };
      map.once("rendercomplete", done);
      map.renderSync();
      window.setTimeout(done, 3000);
    });

    const output = document.createElement("canvas");
    const width = Math.min(1600, Math.round(size[0]));
    const height = Math.min(1200, Math.round(size[1]));
    output.width = width;
    output.height = height;
    const context = output.getContext("2d");
    if (!context) throw new Error("O navegador não permite capturar a imagem raster.");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, width, height);
    context.scale(width / size[0], height / size[1]);

    const canvases = Array.from(
      map.getViewport().querySelectorAll<HTMLCanvasElement>(".ol-layer canvas, canvas.ol-layer")
    ).filter((canvas) => canvas.width > 0 && canvas.height > 0);
    if (!canvases.length) throw new Error("Nenhum raster renderizado foi encontrado no mapa.");
    try {
      for (const layerCanvas of canvases) {
        const opacity = Number(layerCanvas.parentElement?.style.opacity || "1");
        context.save();
        context.globalAlpha = Number.isFinite(opacity) ? opacity : 1;
        const rawTransform = layerCanvas.style.transform;
        const matrix = rawTransform.match(/^matrix\(([^)]+)\)$/);
        if (matrix) {
          const numbers = matrix[1].split(",").map(Number);
          if (numbers.length === 6 && numbers.every(Number.isFinite)) {
            // Multiplica o transform do canvas pelo redimensionamento do raster.
            // setTransform() apagava o fator de escala e podia recortar/deslocar a imagem.
            context.transform(...(numbers as [number, number, number, number, number, number]));
          }
        } else {
          context.translate(layerCanvas.offsetLeft, layerCanvas.offsetTop);
        }
        context.drawImage(layerCanvas, 0, 0);
        context.restore();
      }
      const attribution = basemap === "esri-imagery" ? "Esri World Imagery - mapa de referência" :
        basemap === "esri-topo" ? "Esri World Topographic - mapa de referência" :
        "OpenStreetMap contributors - base cartográfica";
      return {
        raster_b64: output.toDataURL("image/jpeg", 0.88).split(",")[1],
        raster_source: attribution,
      };
    } catch {
      throw new Error(
        "A captura do raster foi bloqueada pelo provedor de imagens ou pelo navegador. " +
        "Selecione uma base autorizada para exportação e tente novamente."
      );
    }
  };

  const adoptTopconParcels = (parcels: Array<{
    number: string; name: string; vertices: TopconBoundaryPoint[];
  }>) => {
    const candidates: Feature[] = [];
    const ids: string[] = [];
    for (const parcel of parcels) {
      const vertices = parcel.vertices;
      if (vertices.length < 3) {
        throw new Error("Parcela " + parcel.number + ": informe ao menos três vértices.");
      }
      const xy = vertices.map((point) => {
        if (!Number.isFinite(point.longitude) || !Number.isFinite(point.latitude)) {
          throw new Error("Parcela " + parcel.number + ": ponto " + point.name + " sem coordenadas.");
        }
        return fromLonLat([point.longitude as number, point.latitude as number]);
      });
      if (new Set(xy.map((pair) => pair.join(","))).size < 3) {
        throw new Error("Parcela " + parcel.number + ": menos de três coordenadas distintas.");
      }
      const polygon = new Polygon([[...xy, xy[0]]]);
      if (!(getArea(polygon, { projection: "EPSG:3857" }) > 0.001)) {
        throw new Error("Parcela " + parcel.number + ": geometria sem área válida.");
      }
      const id = "TOPCON-PARCEL-" + parcel.number.replace(/[^a-zA-Z0-9_-]/g, "");
      const feature = new Feature({ geometry: polygon });
      feature.set("workPolygonId", id, true);
      feature.set("workPolygonName", parcel.name, true);
      feature.set("vertexNames", vertices.map((p) => p.sigef_vertex_code || p.name), true);
      feature.set("confrontants", vertices.map((p) => p.confrontant || ""), true);
      feature.set("altitudes", vertices.map((p) =>
        (!p.height_reference_confirmed && p.sigef_method !== "PB1") || p.ellipsoidal_height_m === null
          ? "" : String(p.ellipsoidal_height_m)), true);
      // HN interpolada é um atributo DE VISUALIZAÇÃO separado de h GNSS.
      feature.set("normalAltitudeEstimates", vertices.map(p =>
        p.derived_physical_model==="HN" && Number.isFinite(p.derived_physical_altitude_m)
          ? p.derived_physical_altitude_m : null), true);
      feature.set("mdtAltitudes",vertices.map(p=>p.sigef_method==="PB1" && typeof p.derived_calculation?.source_elevation_m==="number" ? p.derived_calculation.source_elevation_m : null),true);
      feature.set("technical_piece_status",
        vertices.some(p => (p.sigef_method === "PS4" || p.sigef_method === "PB1")
          && p.derived_calculation?.accuracy_verified !== true)
        ? "PRELIMINAR_NAO_CERTIFICADA" : "EM_REVISAO", true);
      feature.set("sigef_vertex_details", vertices.map((p) => ({
        name: p.name, sigef_vertex_code: p.sigef_vertex_code,
        sigef_method: p.sigef_method, boundary_type: p.boundary_type,
        boundary_detail: p.boundary_detail ?? "",
        sigma_lon_m: p.sigma_lon_m, sigma_lat_m: p.sigma_lat_m,
        sigma_h_m: p.sigma_h_m, height_reference_confirmed: p.height_reference_confirmed,
        parcel_number: p.parcel_number,
        preliminary_ps4: p.sigef_method === "PS4",
        accuracy_verified: p.derived_calculation?.accuracy_verified === true,
      })), true);
      ids.push(id);
      candidates.push(feature);
    }
    // Evita acumular a antiga parcela TOPCON sobre o traçado M–V revisado.
    // Apenas geometrias de trabalho TOPCON são substituídas, nunca camadas SIGEF oficiais.
    const incomingNumbers = new Set(parcels.map(p => p.number));
    for (const existing of polygonFeatures()) {
      const id = String(existing.get("workPolygonId") ?? "");
      const match = /^TOPCON-(?:\d+|PARCEL)-(.+)$/.exec(id);
      if (match && incomingNumbers.has(match[1])) sourceRef.current.removeFeature(existing);
    }
    sourceRef.current.addFeatures(candidates);
    setMemorialText("");
    setEditedMemorial(null);
    setLastGeneratedPdfId(null);
    syncPolygonRegistry();
    setSelectedPolygonIds(ids);
    setSituationSnapshot(null);
    refreshVertexLabels();
    emitGeometry();
    const map = mapRef.current;
    if (map) {
      const newSource = new VectorSource({ features: candidates });
      map.getView().fit(newSource.getExtent(), {
        padding: [60, 70, 60, 70], maxZoom: 17, duration: 300,
      });
    }
  };

  // Novo relatório TOPCON: o trabalho anterior (pontos, parcela M–V e V
  // construídos) não tem relação com o novo levantamento e é descartado.
  // Somente geometrias de trabalho TOPCON são removidas; camadas oficiais não.
  const resetTopconWork = () => {
    let removed = false;
    for (const existing of polygonFeatures()) {
      const id = String(existing.get("workPolygonId") ?? "");
      if (/^TOPCON-/.test(id)) { sourceRef.current.removeFeature(existing); removed = true; }
    }
    if (!removed) return;
    setMemorialText("");
    setEditedMemorial(null);
    setLastGeneratedPdfId(null);
    syncPolygonRegistry();
    setSelectedPolygonIds((old) => old.filter((id) => !/^TOPCON-/.test(id)));
    setSituationSnapshot(null);
    refreshVertexLabels();
    emitGeometry();
  };

  const documentParcels = () => {
    const features = selectedFeatures();
    if (!features.length) throw new Error("Selecione ao menos um polígono.");
    const parcels = features.map((feature) => ({
      name: String(feature.get("workPolygonName") ?? feature.get("workPolygonId")),
      geometry: new GeoJSON().writeGeometryObject(feature.getGeometry()!, {
        featureProjection: "EPSG:3857",
        dataProjection: "EPSG:4326",
        decimals: 9,
      }),
      vertex_names: feature.get("vertexNames") as string[],
      confrontants: feature.get("confrontants") as string[],
      is_preliminary: feature.get("technical_piece_status") === "PRELIMINAR_NAO_CERTIFICADA",
      normal_altitudes_m: feature.get("normalAltitudeEstimates") as Array<number|null> | undefined,
      mdt_altitudes_m: feature.get("mdtAltitudes") as Array<number|null> | undefined,
      altitudes_m: ((feature.get("altitudes") as string[] | undefined) ?? []).map((value) =>
        value?.trim() ? Number(value.replace(",", ".")) : null
      ),
    }));
    return parcels;
  };

  const saveCurrentPiece = async (editedMemorial: string, topconDraft: TopconDraft) => {
    const features = new GeoJSON().writeFeaturesObject(polygonFeatures(), {
      featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 9,
    });
    const ps1Consolidated = topconDraft.boundary.some(p => p.sigef_method === "PS1" && p.derived_calculation?.accuracy_verified === true);
    const pb1Consolidated = Boolean(topconDraft.pb1_closure?.confirmed && topconDraft.pb1_draft?.length);
    const approvedSelection = ps1Consolidated || pb1Consolidated
      ? [...new Set(topconDraft.boundary.map(p => "TOPCON-PARCEL-" + p.parcel_number.replace(/[^a-zA-Z0-9_-]/g, "")))]
      : selectedPolygonIds;
    const snapshot = {
      features,
      selected_ids: approvedSelection,
      imported_sigef_metadata: importedMetadata,
      legal_metadata: legalMetadata,
      data: {
        title: memorialTitle, plantHeading, memorialHeading,
        owner: memorialOwner, rg: ownerRg, cpf: ownerCpf,
        address: propertyAddress, croqui: croquiNote,
        format: paperFormat, orientation: paperOrientation,
        layoutTemplate: plantLayoutTemplate, scale: scaleChoice, customScale,
      },
      professional: documentProfessional,
      elements: plantElements,
      magnetic_declination: magneticDeclination,
      survey_date: surveyDate,
      memorial_edited: editedMemorial.trim() ? editedMemorial : null,
      generated_pdf_id: lastGeneratedPdfId,
      situation: situationSnapshot,
      topcon: topconDraft,
    };
    const url = currentPieceId
      ? `${getApiUrl()}/technical-pieces/${currentPieceId}`
      : `${getApiUrl()}/technical-pieces`;
    const response = await fetch(url, {
      method: currentPieceId ? "PUT" : "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: memorialTitle || "Imóvel sem nome", snapshot }),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) throw new Error(result?.detail ?? "Não foi possível salvar a peça.");
    setCurrentPieceId(result.id);
    onPieceSaved?.();
    return String(result.id);
  };

  const exportIndividualPolygon = async (id: string, format: "txt" | "kml" | "shp") => {
    const feature = polygonFeatures().find((item) => item.get("workPolygonId") === id);
    if (!feature) return;
    setExportBusy(true);
    setDocumentError(null);
    try {
      const payload = {
        geometry: new GeoJSON().writeGeometryObject(feature.getGeometry()!, {
          featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 9,
        }),
        filename: String(feature.get("workPolygonName") ?? id),
        vertex_names: feature.get("vertexNames"),
        format,
      };
      const response = await trackedFetch(`${getApiUrl()}/tools/export-polygon`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }, "Exportando o polígono");
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "Falha na exportação.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const disposition = response.headers.get("content-disposition") ?? "";
      const defaultName = `poligono-${id}.${format === "shp" ? "zip" : format}`;
      const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? defaultName;
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 3000);
    } catch (error) {
      setDocumentError(error instanceof Error ? error.message : "Falha na exportação.");
    } finally {
      setExportBusy(false);
    }
  };

  const refreshVertexLabels = () => {
    vertexLabelSourceRef.current.clear();
    for (const feature of polygonFeatures()) {
      if (hiddenPolygonIdsRef.current.has(String(feature.get("workPolygonId") ?? ""))) continue;
      const geometry = feature.getGeometry() as Polygon;
      const ring = geometry.getCoordinates()[0] ?? [];
      const names = (feature.get("vertexNames") as string[] | undefined) ?? [];
      for (const [index, coordinate] of ring.slice(0, -1).entries()) {
        vertexLabelSourceRef.current.addFeature(new Feature({
          geometry: new Point(coordinate),
          vertexName: names[index] ?? `V${String(index + 1).padStart(2, "0")}`,
        }));
      }
    }
  };

  const updateGeometryMetrics = () => {
    const geometry = sourceRef.current.getFeatures()[0]?.getGeometry();
    if (!geometry) {
      setGeometryMetrics({ areaHectares: null, perimeterMeters: null, vertices: 0 });
      return;
    }

    if (geometry instanceof Polygon) {
      const ring = geometry.getCoordinates()[0] ?? [];
      setGeometryMetrics({
        areaHectares: getArea(geometry, { projection: "EPSG:3857" }) / 10000,
        perimeterMeters: ring.length > 1
          ? getLength(new LineString(ring), { projection: "EPSG:3857" })
          : 0,
        vertices: Math.max(0, ring.length - 1),
      });
      return;
    }

    if (geometry instanceof MultiPolygon) {
      let area = 0;
      let perimeter = 0;
      let vertices = 0;
      for (const polygonCoordinates of geometry.getCoordinates()) {
        const polygon = new Polygon(polygonCoordinates);
        const ring = polygonCoordinates[0] ?? [];
        area += getArea(polygon, { projection: "EPSG:3857" });
        if (ring.length > 1) {
          perimeter += getLength(new LineString(ring), { projection: "EPSG:3857" });
        }
        vertices += Math.max(0, ring.length - 1);
      }
      setGeometryMetrics({
        areaHectares: area / 10000,
        perimeterMeters: perimeter,
        vertices,
      });
      return;
    }

    setGeometryMetrics({
      areaHectares: null,
      perimeterMeters: null,
      vertices: geometry instanceof Point ? 1 : 0,
    });
  };

  const currentGeometryGeoJson = () => {
    const geometry = sourceRef.current.getFeatures()[0]?.getGeometry();
    if (!geometry) return null;
    return new GeoJSON().writeGeometryObject(geometry, {
      featureProjection: "EPSG:3857",
      dataProjection: "EPSG:4326",
      decimals: 9,
    }) as Record<string, unknown>;
  };

  const emitGeometry = () => {
    const all = sourceRef.current.getFeatures();
    const feature = all.find((item) =>
      selectedPolygonIds.includes(String(item.get("workPolygonId")))
    ) ?? all[0];
    const geometry = feature?.getGeometry();
    if (!geometry) {
      onGeometryChange(null);
      syncPolygonRegistry();
      updateGeometryMetrics();
      refreshVertexLabels();
      return;
    }
    const output = new GeoJSON().writeGeometryObject(geometry, {
      featureProjection: "EPSG:3857",
      dataProjection: "EPSG:4326",
      decimals: 8,
    });
    onGeometryChange(output as Record<string, unknown>);
    syncPolygonRegistry();
    updateGeometryMetrics();
    refreshVertexLabels();
  };

  // Polígono marcado é sempre visível; desmarcado pelo usuário fica oculto.
  const setPolygonVisible = (id: string, visible: boolean) => {
    if (visible) hiddenPolygonIdsRef.current.delete(id);
    else hiddenPolygonIdsRef.current.add(id);
    sourceRef.current.changed();
    refreshVertexLabels();
  };

  useEffect(() => {
    let changed = false;
    for (const id of selectedPolygonIds) {
      if (hiddenPolygonIdsRef.current.delete(id)) changed = true;
    }
    if (changed) {
      sourceRef.current.changed();
      refreshVertexLabels();
    }
  }, [selectedPolygonIds]);

  useEffect(() => {
    const features = sourceRef.current.getFeatures();
    if (!features.length) return;
    const primary = features.find((feature) =>
      selectedPolygonIds.includes(String(feature.get("workPolygonId")))
    ) ?? features[0];
    const geometry = primary?.getGeometry();
    if (!geometry) return;
    onGeometryChange(new GeoJSON().writeGeometryObject(geometry, {
      featureProjection: "EPSG:3857",
      dataProjection: "EPSG:4326",
      decimals: 8,
    }) as Record<string, unknown>);
  }, [selectedPolygonIds]);

  // ---- Seleção de parcelas (qualquer base) para download em SHP/KML ----
  // Usa o perímetro destacado pelo Identificar (geometria integral do WFS
  // quando disponível) ou a própria geometria poligonal da feição.
  const identifiedPolygonGeometry = () => {
    const highlighted = identifySelectionSourceRef.current.getFeatures()
      .map((item) => item.getGeometry())
      .find((geometry) => geometry && ["Polygon", "MultiPolygon"].includes(geometry.getType()));
    if (highlighted) return highlighted;
    const own = selectedFeatureRef.current?.getGeometry();
    return own && ["Polygon", "MultiPolygon"].includes(own.getType()) ? own : null;
  };

  const addIdentifiedToDownload = () => {
    if (!identifiedFeature) return;
    const geometry = identifiedPolygonGeometry();
    if (!geometry) {
      setDownloadError("Esta feição não tem perímetro poligonal disponível para download.");
      setDownloadPanelOpen(true);
      return;
    }
    const key = (geometry: NonNullable<ReturnType<typeof identifiedPolygonGeometry>>) =>
      JSON.stringify(new GeoJSON().writeGeometryObject(geometry, {
        featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 7,
      }));
    const newKey = key(geometry);
    const duplicate = downloadSourceRef.current.getFeatures().some((item) => {
      const existing = item.getGeometry();
      return existing && ["Polygon", "MultiPolygon"].includes(existing.getType())
        && key(existing as typeof geometry) === newKey;
    });
    setDownloadError(null);
    setDownloadPanelOpen(true);
    if (duplicate) {
      setDownloadError("Esta parcela já está na seleção.");
      return;
    }
    downloadSequenceRef.current += 1;
    const id = `DL-${downloadSequenceRef.current}`;
    const properties: Record<string, string> = {};
    for (const [field, value] of identifiedFeature.attributes) {
      if (value === null || value === undefined || typeof value === "object") continue;
      const text = String(value).trim();
      if (text && !/^(Consultando|Localizando)/.test(text)) properties[field] = text;
    }
    const feature = new Feature({ geometry: geometry.clone() });
    feature.setId(id);
    feature.set("hidden", false);
    downloadSourceRef.current.addFeature(feature);
    setDownloadParcels((current) => [...current, {
      id,
      name: identifiedFeature.title || `Parcela ${downloadSequenceRef.current}`,
      layer: identifiedFeature.layer,
      properties,
      visible: true,
    }]);
  };

  const toggleDownloadParcel = (id: string, visible: boolean) => {
    const feature = downloadSourceRef.current.getFeatureById(id);
    feature?.set("hidden", !visible);
    setDownloadParcels((current) => current.map((item) => item.id === id ? { ...item, visible } : item));
  };

  const removeDownloadParcel = (id: string) => {
    const feature = downloadSourceRef.current.getFeatureById(id);
    if (feature) downloadSourceRef.current.removeFeature(feature);
    setDownloadParcels((current) => current.filter((item) => item.id !== id));
  };

  const clearDownloadParcels = () => {
    downloadSourceRef.current.clear();
    setDownloadParcels([]);
    setDownloadError(null);
  };

  const zoomToDownloadParcel = (id: string) => {
    const geometry = downloadSourceRef.current.getFeatureById(id)?.getGeometry();
    if (geometry) mapRef.current?.getView().fit(geometry.getExtent(), {
      padding: [70, 70, 70, 70], maxZoom: 17, duration: 300,
    });
  };

  const downloadSelectedParcels = async (format: "kml" | "shp") => {
    const chosen = downloadParcels.filter((item) => item.visible);
    if (!chosen.length) {
      setDownloadError("Marque ao menos uma parcela para baixar.");
      return;
    }
    setDownloadBusy(true);
    setDownloadError(null);
    try {
      const writer = new GeoJSON();
      const parcels = chosen.flatMap((item) => {
        const geometry = downloadSourceRef.current.getFeatureById(item.id)?.getGeometry();
        return geometry ? [{
          name: item.name,
          layer: item.layer,
          properties: item.properties,
          geometry: writer.writeGeometryObject(geometry, {
            featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 9,
          }),
        }] : [];
      });
      const response = await trackedFetch(`${getApiUrl()}/tools/export-parcels`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: "parcelas-selecionadas", format, parcels }),
      }, "Preparando o download das parcelas");
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "Falha no download das parcelas.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const disposition = response.headers.get("content-disposition") ?? "";
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = disposition.match(/filename="([^"]+)"/)?.[1]
        ?? `parcelas-selecionadas.${format === "shp" ? "zip" : "kml"}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 3000);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Falha no download das parcelas.");
    } finally {
      setDownloadBusy(false);
    }
  };

  const clearIdentifiedFeature = () => {
    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;
    setIdentifyLoading(false);
    if (selectedFeatureRef.current) {
      selectedFeatureRef.current.set("isSelected", false);
      selectedFeatureRef.current.changed();
      selectedFeatureRef.current = null;
    }
    identifySelectionSourceRef.current.clear();

    setIdentifiedFeature(null);
    setIdentifyCandidates([]);
    identifyCandidateHistoryRef.current = [];
  };

  selectFeatureRef.current = (feature: Feature) => {
    const preservedCandidates = [
      ...identifyCandidateHistoryRef.current,
    ];

    clearIdentifiedFeature();

    identifyCandidateHistoryRef.current =
      preservedCandidates;

    selectedFeatureRef.current = feature;

    feature.set("isSelected", true);
    feature.changed();

    /*
     * DESTAQUE UNIVERSAL
     *
     * Não dependemos do estilo da camada original.
     * Criamos uma cópia gráfica da geometria selecionada
     * e a colocamos no overlay superior do mapa.
     *
     * Isso funciona para qualquer GeoFeature armazenada
     * no PostGIS, independentemente da fonte.
     */
    const selectedGeometry = feature.getGeometry();

    if (selectedGeometry) {
      const highlightFeature = new Feature({
        geometry: selectedGeometry.clone(),
      });

      highlightFeature.set(
        "isIdentifyHighlight",
        true,
      );

      highlightFeature.set(
        "source_id",
        feature.get("source_id"),
      );

      highlightFeature.set(
        "feature_id",
        feature.get("feature_id"),
      );

      // O estilo é fixado também na própria feição para que o destaque
      // não dependa da função de estilo da camada ou da origem do vetor.
      highlightFeature.setStyle(identifyHighlightStyles);

      identifySelectionSourceRef.current.clear();
      identifySelectionSourceRef.current.addFeature(
        highlightFeature,
      );
      identifySelectionSourceRef.current.changed();

      // Render imediato: o usuário deve enxergar a seleção no mesmo clique,
      // antes mesmo de os atributos detalhados terminarem de carregar.
      mapRef.current?.renderSync();
    }
    const { raw, layer, title } = featureIdentity(feature);
    const sourceId = String(raw.source_id ?? "");
    const featureId = String(raw.feature_id ?? feature.getId() ?? "");
    const fallbackAttributes = Object.entries(raw).filter(
      ([key]) =>
        !["geometry", "displayColor", "isSelected", "catalogName", "wms_identified", "wms_no_geometry", "identifyOverlay", "identify_click_coordinate"].includes(
          key,
        ),
    );
    setIdentifiedFeature({
      title,
      layer,
      attributes: fallbackAttributes,
      loading: true,
    });
    // GetFeatureInfo do WMS já devolve os atributos oficiais.
    // Não existe correspondente em /sources/{id}/features/{id} (PostGIS).
    if (feature.get("wms_identified")) {
      const controller = new AbortController();
      identifyAbortRef.current = controller;
      setIdentifiedFeature({
        title,
        layer,
        attributes: [...fallbackAttributes,
          ["Última modificação da base oficial", "Consultando o INCRA…"]],
      });
      const updateProperties = (label: string, value: string) => {
        if (controller.signal.aborted || selectedFeatureRef.current !== feature) return;
        setIdentifiedFeature((current) => {
          if (!current) return current;
          const attributes = current.attributes.filter(([key]) => key !== label);
          return { ...current, attributes: [...attributes, [label, value]] };
        });
      };
      void fetch(
        `${getApiUrl()}/sources/${sourceId}/sigef-base-metadata`,
        { signal: controller.signal, credentials: "include" },
      ).then(async (response) => {
        if (!response.ok) throw new Error("metadados indisponíveis");
        return response.json();
      }).then((metadata) => {
        const rawDate = typeof metadata.last_updated === "string"
          ? metadata.last_updated : null;
        const parsed = rawDate ? new Date(rawDate) : null;
        const dateOnly = rawDate?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        const value = dateOnly
          ? `${dateOnly[3]}/${dateOnly[2]}/${dateOnly[1]}`
          : parsed && !Number.isNaN(parsed.getTime())
            ? new Intl.DateTimeFormat("pt-BR", {
                dateStyle: "short", timeStyle: "short",
                timeZone: "America/Belem",
              }).format(parsed)
            : "Não informada pelo provedor oficial";
        updateProperties("Última modificação da base oficial", value);
      }).catch(() => {
        updateProperties(
          "Última modificação da base oficial",
          "Não foi possível verificar no INCRA",
        );
      });

      // Sempre recuperar o perímetro integral via WFS/FEATUREID, inclusive
      // se o GetFeatureInfo devolver alguma geometria simplificada.
      if (sourceId) {
        updateProperties("Seleção do perímetro", "Localizando polígono oficial…");
        const parcelCode = String(raw.parcela_codigo ?? raw.codigo_parcela ?? "");
        const query = new URLSearchParams();
        if (featureId) query.set("feature_id", featureId);
        if (parcelCode) query.set("parcel_code", parcelCode);
        const clicked = (feature.get("identify_click_coordinate") as number[] | undefined)
          ?? (feature.getGeometry() instanceof Point
            ? (feature.getGeometry() as Point).getCoordinates() : null);

        const paintPolygon = (geometry: NonNullable<ReturnType<Feature["getGeometry"]>>) => {
          if (controller.signal.aborted || selectedFeatureRef.current !== feature) return;
          if (!["Polygon", "MultiPolygon"].includes(geometry.getType())) return;
          const highlight = new Feature({ geometry: geometry.clone() });
          highlight.setStyle(identifyHighlightStyles);
          highlight.set("isIdentifyHighlight", true);
          identifySelectionSourceRef.current.clear();
          identifySelectionSourceRef.current.addFeature(highlight);
          mapRef.current?.renderSync();
          updateProperties("Seleção do perímetro", "Parcela oficial destacada no mapa");
        };

        void (async () => {
          if (query.size) {
            try {
              const response = await fetch(
                `${getApiUrl()}/sources/${sourceId}/sigef-selected-geometry?${query}`,
                { signal: controller.signal, credentials: "include" },
              );
              if (!response.ok) throw new Error("WFS sem geometria por identificador");
              const payload = await response.json();
              const full = new GeoJSON().readFeature({
                type: "Feature", geometry: payload.geometry, properties: {},
              }, {
                dataProjection: "EPSG:4326",
                featureProjection: "EPSG:3857",
              }) as Feature;
              const geom = full.getGeometry();
              if (geom && ["Polygon", "MultiPolygon"].includes(geom.getType())) {
                paintPolygon(geom);
                return;
              }
            } catch (error) {
              if (controller.signal.aborted) return;
              console.warn("SIGEF: tentativa por identificador sem geometria", error);
            }
          }

          // Fallback espacial: usa o WFS já utilizado pela ferramenta SNAP.
          // Seleciona somente se houver exatamente UM polígono contendo o clique.
          // Nunca destaca um vizinho por simples proximidade.
          if (!clicked) throw new Error("Coordenada da parcela não disponível");
          const [lon, lat] = toLonLat(clicked, "EPSG:3857");
          const delta = 0.0002;
          const bbox = [lon - delta, lat - delta, lon + delta, lat + delta].join(",");
          const params = new URLSearchParams({
            bbox, uf: incraUfRef.current.toLowerCase(), limit: "50",
          });
          const response = await fetch(
            `${getApiUrl()}/sources/${sourceId}/sigef-snap?${params}`,
            { signal: controller.signal, credentials: "include" },
          );
          if (!response.ok) throw new Error("WFS oficial não disponível");
          const payload = await response.json();
          if (payload?.truncated || !Array.isArray(payload?.features)) {
            throw new Error("Consulta espacial inconclusiva");
          }
          const format = new GeoJSON();
          const matches = payload.features.flatMap((item: unknown) => {
            try {
              const vector = format.readFeature(item, {
                dataProjection: "EPSG:4326",
                featureProjection: "EPSG:3857",
              }) as Feature;
              const geom = vector.getGeometry();
              return geom && geom.intersectsCoordinate(clicked) ? [geom] : [];
            } catch {
              return [];
            }
          });
          if (matches.length !== 1) {
            throw new Error("Não foi possível determinar unicamente a parcela.");
          }
          paintPolygon(matches[0]);
        })().catch((error) => {
          if (controller.signal.aborted) return;
          updateProperties(
            "Seleção do perímetro",
            "Geometria não disponibilizada pelo WFS oficial nesta consulta",
          );
          console.warn("SIGEF: não foi possível destacar o perímetro", error);
        });
      }
      return;
    }
    if (!sourceId || !featureId) {
      setIdentifiedFeature({ title, layer, attributes: fallbackAttributes });
      return;
    }
    const controller = new AbortController();
    identifyAbortRef.current = controller;
    void fetch(
      `${getApiUrl()}/sources/${sourceId}/features/${featureId}`,
      { signal: controller.signal },
    )
      .then((response) => {
        if (!response.ok)
          throw new Error("Não foi possível consultar os atributos.");
        return response.json();
      })
      .then((detail) => {
        if (controller.signal.aborted || selectedFeatureRef.current !== feature)
          return;
        const properties = detail.properties ?? {};

        // Segundo passe determinístico:
        // substitui qualquer geometria MVT recortada/simplificada
        // pela geometria integral devolvida pelo PostGIS.
        if (detail?.geometry) {
          try {
            const detailFeature = new GeoJSON().readFeature(
              {
                type: "Feature",
                geometry: detail.geometry,
                properties: {},
              },
              {
                dataProjection: "EPSG:4326",
                featureProjection: "EPSG:3857",
              },
            ) as Feature;

            const detailGeometry = detailFeature.getGeometry();

            if (detailGeometry) {
              const persistentHighlight = new Feature({
                geometry: detailGeometry.clone(),
              });

              persistentHighlight.setStyle(identifyHighlightStyles);
              persistentHighlight.set(
                "isIdentifyHighlight",
                true,
              );
              persistentHighlight.set(
                "source_id",
                sourceId,
              );
              persistentHighlight.set(
                "feature_id",
                featureId,
              );

              identifySelectionSourceRef.current.clear();
              identifySelectionSourceRef.current.addFeature(
                persistentHighlight,
              );
              identifySelectionSourceRef.current.changed();

              mapRef.current?.renderSync();
            }
          } catch (highlightError) {
            console.warn(
              "Não foi possível reforçar o destaque com a geometria completa.",
              highlightError,
            );
          }
        }

        const detailTitle = String(
          properties.name ??
            properties.nome ??
            properties.nome_uc ??
            properties.nome_proje ??
            properties.nom_pessoa ??
            properties.denominacao ??
            properties.external_id ??
            title,
        );
        setIdentifiedFeature({
          title: detailTitle,
          layer,
          attributes: Object.entries(properties),
        });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        if (!controller.signal.aborted)
          setIdentifiedFeature({
            title,
            layer,
            attributes: [
              ...fallbackAttributes,
              [
                "consulta_atributos",
                "Não foi possível carregar os atributos completos.",
              ],
            ],
          });
      });
  };

  useEffect(() => {
    if (!mapElement.current || mapRef.current) return;
    const baseLayer = new TileLayer({ source: new OSM({ maxZoom: 19 }), zIndex: 0 });
    baseLayerRef.current = baseLayer;
    const map = new Map({
      target: mapElement.current,
      layers: [
        baseLayer,
        new VectorLayer({
          source: officialSourceRef.current,
          zIndex: 2,
          style: (feature) =>
            feature.get("isSelected")
              ? selectedOfficialStyle
              : officialStyle(String(feature.get("displayColor") ?? "#36a269")),
        }),
        new VectorLayer({
          source: sourceRef.current,
          zIndex: 3,
          style: (feature) =>
            hiddenPolygonIdsRef.current.has(String(feature.get("workPolygonId") ?? ""))
              ? undefined
              : subjectStyle,
        }),
        new VectorLayer({
          source: downloadSourceRef.current,
          zIndex: 6,
          style: (feature) => (feature.get("hidden") ? undefined : downloadParcelStyle),
        }),
        new VectorLayer({
          source: measureSourceRef.current, zIndex: 5,
          style: new Style({
            stroke: new Stroke({ color: "#eab308", width: 3, lineDash: [7, 5] }),
            fill: new Fill({ color: "rgba(234,179,8,0.16)" }),
            image: new CircleStyle({ radius: 5, fill: new Fill({ color: "#eab308" }),
              stroke: new Stroke({ color: "#fff", width: 2 }) }),
          }),
        }),
        new VectorLayer({
          source: vertexLabelSourceRef.current,
          zIndex: 4,
          style: (feature) =>
            new Style({
              image: new CircleStyle({
                radius: 4.5,
                fill: new Fill({ color: "#ffffff" }),
                stroke: new Stroke({ color: "#0d6847", width: 2 }),
              }),
              text: new TextStyle({
                text: String(feature.get("vertexName") ?? ""),
                offsetY: -13,
                font: "700 11px Inter, sans-serif",
                fill: new Fill({ color: "#0d3f2d" }),
                stroke: new Stroke({ color: "#ffffff", width: 3 }),
              }),
            }),
        }),

        // Destaque persistente de resultados localizados pela lupa de atributos.
        // Independente da ferramenta Identificar e do perímetro de análise.
        new VectorLayer({
          source: attributeSearchSourceRef.current,
          updateWhileAnimating: true,
          updateWhileInteracting: true,
          zIndex: 99999,
          style: identifyHighlightStyles,
        }),
                // Camada universal de seleção.
        // Fica acima das bases territoriais e da geometria consultada.
        new VectorLayer({
          source: identifySelectionSourceRef.current,
          updateWhileAnimating: true,
          updateWhileInteracting: true,
          zIndex: 100000,
          style: identifyHighlightStyles,
        }),
      ],
      view: new View({
        center: fromLonLat((UF_VIEW[incraUf] ?? UF_VIEW.ALL).center),
        zoom: (UF_VIEW[incraUf] ?? UF_VIEW.ALL).zoom,
      }),
    });
    mapRef.current = map;
    const identifyAtPixel = async (
      event: MapBrowserEvent<PointerEvent>,
    ) => {
      if (!identifyActiveRef.current) return;

      clearIdentifiedFeature();
      setIdentifyLoading(true);
      setIdentifyLoadingMessage("Consultando feições nas camadas ativas…");

      const enabledLayers = layersRef.current.filter(
        (layer) =>
          layer.enabled &&
          layer.id &&
          layer.slug !== "incra-sigef-brasil",
      );

      const enabledSourceIds = enabledLayers
        .map((layer) => layer.id)
        .filter((id): id is string => Boolean(id));

      const [longitude, latitude] = toLonLat(
        event.coordinate,
        map.getView().getProjection(),
      );

      /*
       * A identificação principal ocorre diretamente no PostGIS.
       *
       * Isso elimina a dependência da feição estar carregada no tile
       * visível e permite identificar igualmente:
       * - CAR/SICAR vetorial local;
       * - SPU vetorial local;
       * - SIGEF;
       * - SNCI;
       * - ANM;
       * - assentamentos;
       * - UC;
       * - bases estaduais/municipais;
       * - qualquer vetor adicional cadastrado por UF.
       */
      if (enabledSourceIds.length > 0) {
        identifyAbortRef.current?.abort();

        const controller = new AbortController();
        identifyAbortRef.current = controller;

        try {
          const response = await fetch(
            `${getApiUrl()}/sources/identify`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              signal: controller.signal,
              body: JSON.stringify({
                coordinate: [longitude, latitude],
                source_ids: enabledSourceIds,
                tolerance_m: Math.max(
                  2,
                  Math.min(
                    25,
                    Number(
                      map.getView().getResolution() ?? 1,
                    ) * 1.5,
                  ),
                ),
              }),
            },
          );

          const body = await response
            .json()
            .catch(() => null);

          if (!response.ok) {
            throw new Error(
              body?.detail ??
                "Não foi possível identificar as feições.",
            );
          }

          if (controller.signal.aborted) return;

          const returnedFeatures = Array.isArray(
            body?.features,
          )
            ? body.features
            : [];

          if (returnedFeatures.length > 0) {
            const format = new GeoJSON();

            const candidates: IdentifyCandidate[] = [];

            for (const item of returnedFeatures) {
              try {
                const feature = format.readFeature(
                  item,
                  {
                    dataProjection: "EPSG:4326",
                    featureProjection: "EPSG:3857",
                  },
                ) as Feature;

                const properties =
                  item?.properties ?? {};

                const sourceId = String(
                  item?.source_id ??
                    properties.source_id ??
                    "",
                );

                const layer = enabledLayers.find(
                  (candidate) =>
                    candidate.id === sourceId,
                );

                feature.set(
                  "source_id",
                  sourceId,
                );

                feature.set(
                  "source_name",
                  String(
                    item?.source_name ??
                      properties.source_name ??
                      layer?.name ??
                      "Camada territorial",
                  ),
                );

                feature.set(
                  "catalogName",
                  layer?.name ??
                    String(
                      item?.source_name ??
                        properties.source_name ??
                        "Camada territorial",
                    ),
                );

                feature.set(
                  "displayColor",
                  layer?.color ?? "#e08a24",
                );

                feature.set(
                  "identifyOverlay",
                  true,
                );

                feature.set(
                  "feature_id",
                  String(
                    properties.feature_id ??
                      item?.id ??
                      "",
                  ),
                );

                if (item?.id) {
                  feature.setId(String(item.id));
                }

                const identity =
                  featureIdentity(feature);

                candidates.push({
                  feature,
                  title: identity.title,
                  layer: identity.layer,
                });
              } catch (error) {
                console.warn(
                  "Não foi possível materializar uma feição identificada.",
                  error,
                );
              }
            }

            if (candidates.length === 1) {
              setIdentifyLoading(false);
              selectFeatureRef.current(
                candidates[0].feature,
              );
              return;
            }

            if (candidates.length > 1) {
              setIdentifyLoading(false);
              identifyCandidateHistoryRef.current =
                candidates;
              setIdentifyCandidates(candidates);
              return;
            }
          }
        } catch (error) {
          if (
            error instanceof DOMException &&
            error.name === "AbortError"
          ) {
            setIdentifyLoading(false);
            return;
          }

          console.warn(
            "Identificação vetorial local indisponível; tentando fallback visual/WMS.",
            error,
          );
          setIdentifyLoadingMessage("Verificando feições visíveis no mapa…");
        }
      }

      /*
       * Fallback 1:
       * feature já renderizada no MVT/OpenLayers.
       */
      const renderedCandidates = map
        .getFeaturesAtPixel(
          event.pixel,
          { hitTolerance: 7 },
        )
        .filter(
          (candidate): candidate is Feature =>
            candidate instanceof Feature &&
            Boolean(candidate.get("catalogName")),
        );

      if (renderedCandidates.length === 1) {
        setIdentifyLoading(false);
        selectFeatureRef.current(
          renderedCandidates[0],
        );
        return;
      }

      if (renderedCandidates.length > 1) {
        setIdentifyLoading(false);
        const candidates =
          renderedCandidates.map((feature) => ({
            feature,
            ...featureIdentity(feature),
          }));

        identifyCandidateHistoryRef.current =
          candidates;

        setIdentifyCandidates(candidates);
        return;
      }

      /*
       * Fallback oficial SIGEF Brasil — OGC WMS GetFeatureInfo.
       * A camada é visualizada por ImageWMS e não possui cópia PostGIS.
       * Consultar apenas quando estiver ativa, usando o mesmo proxy WMS
       * e o mesmo filtro estadual que desenharam a imagem no mapa.
       */
      const sigef = layersRef.current.find(
        (layer) =>
          layer.slug === "incra-sigef-brasil" &&
          layer.id &&
          layer.enabled &&
          layer.wmsEnabled,
      );
      const sigefSource = sigef?.id
        ? wmsLayersRef.current.get(sigef.id)?.getSource()
        : null;
      if (sigef && sigefSource) {
        const resolution = map.getView().getResolution();
        const infoUrl = resolution
          ? sigefSource.getFeatureInfoUrl(
              event.coordinate,
              resolution,
              map.getView().getProjection(),
              {
                INFO_FORMAT: "application/json",
                FEATURE_COUNT: 10,
              },
            )
          : undefined;
        if (infoUrl) {
          identifyAbortRef.current?.abort();
          const controller = new AbortController();
          identifyAbortRef.current = controller;
          setIdentifyLoadingMessage("Consultando atributos oficiais SIGEF/INCRA…");
          try {
            const response = await fetch(infoUrl, {
              credentials: "include",
              signal: controller.signal,
              headers: { Accept: "application/json" },
            });
            if (!response.ok) {
              throw new Error(`Serviço SIGEF indisponível (HTTP ${response.status}).`);
            }
            const body = await response.json().catch(() => {
              throw new Error(
                "O WMS SIGEF não retornou JSON; verifique a disponibilidade do GetFeatureInfo oficial.",
              );
            });
            if (controller.signal.aborted) return;
            if (body?.type !== "FeatureCollection" ||
                !Array.isArray(body.features)) {
              throw new Error("O WMS SIGEF não retornou informações em GeoJSON.");
            }

            const format = new GeoJSON();
            const candidates: IdentifyCandidate[] = [];
            for (const item of body.features.slice(0, 10)) {
              if (!item || item.type !== "Feature") continue;
              try {
                const feature = item.geometry
                  ? format.readFeature(item, {
                      featureProjection: map.getView().getProjection(),
                    }) as Feature
                  : new Feature({
                      geometry: new Point(event.coordinate.slice()),
                      ...(item.properties ?? {}),
                    });
                const props = item.properties ?? {};
                const featureId = String(item.id ?? props.fid ?? props.id ?? "");
                if (featureId) feature.setId(featureId);
                feature.set("source_id", sigef.id);
                feature.set("source_name", sigef.name);
                feature.set("catalogName", sigef.name);
                feature.set("feature_id", featureId);
                feature.set("displayColor", sigef.color);
                feature.set("wms_identified", true);
                feature.set("wms_no_geometry", !item.geometry);
                feature.set("identify_click_coordinate", event.coordinate.slice());
                const identity = featureIdentity(feature);
                candidates.push({
                  feature,
                  title: identity.title,
                  layer: identity.layer,
                });
              } catch (itemError) {
                console.warn("Feição WMS SIGEF com geometria inválida.", itemError);
              }
            }
            if (candidates.length === 1) {
              setIdentifyLoading(false);
              selectFeatureRef.current(candidates[0].feature);
              return;
            }
            if (candidates.length > 1) {
              setIdentifyLoading(false);
              identifyCandidateHistoryRef.current = candidates;
              setIdentifyCandidates(candidates);
              return;
            }
          } catch (error) {
            if (controller.signal.aborted) return;
            console.warn("Falha no GetFeatureInfo SIGEF Brasil.", error);
            setIdentifyLoading(false);
            setIdentifiedFeature({
              title: "Consulta SIGEF indisponível",
              layer: sigef.name,
              attributes: [["status",
                error instanceof Error ? error.message :
                "O serviço oficial não respondeu à identificação."]],
            });
            return;
          }
        }
      }
      setIdentifyLoading(false);
      setIdentifiedFeature(null);
    };
    const identifyListener = (event: Parameters<typeof identifyAtPixel>[0]) => {
      void identifyAtPixel(event);
    };
    map.on("singleclick", identifyListener as never);
    return () => {
      map.un("singleclick", identifyListener as never);
      identifyAbortRef.current?.abort();
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!focusRequest) return;
    void focusSource(focusRequest.sourceId);
  }, [focusRequest?.nonce, focusRequest?.sourceId]);

  useEffect(() => {
    const enabled = layers.filter((layer) => layer.id && layer.enabled);
    if (enabled.length !== 1 || enabled[0].slug !== "sigef-interno") return;
    const sourceId = enabled[0].id!;
    if (autoFocusRef.current === sourceId) return;
    if ((mapRef.current?.getView().getZoom() ?? 0) >= 9) return;
    autoFocusRef.current = sourceId;
    void focusSource(sourceId);
  }, [layers]);

  useEffect(() => {
    identifyActiveRef.current = identifyActive;
    if (!identifyActive) clearIdentifiedFeature();
  }, [identifyActive]);

  useEffect(() => {
    layersRef.current = layers;
    const map = mapRef.current;
    if (!map) return;

    const desiredVectorTiles = new Set<string>();

    const isParcelLayer = (layer: (typeof layers)[number]) =>
      layer.slug === "sigef-interno" ||
      layer.slug === "incra-fundiario" ||
      /sigef|parcela/i.test(layer.name);

    const minimumVectorZoom = (layer: (typeof layers)[number]) => {
      if (layer.slug === "sigef-interno" && (layer.featureCount ?? Infinity) <= 10000) return 6;
      if (isParcelLayer(layer)) return 9;

      if (layer.slug === "anm-processos-minerarios") return 7;

      if (layer.source === "IBAMA") return 7;
      if (layer.source === "FUNAI") return 5;
      if (layer.source === "ICMBio") return 5;

      if (layer.source === "IPHAN") {
        if (/sítio|sitio/i.test(layer.name)) return 8;
        return 7;
      }

      return 0;
    };

    for (const layer of layers) {
      if (!layer.id || !layer.enabled) continue;

      // SIGEF Brasil utiliza exclusivamente o serviço WMS.
      if (layer.slug === "incra-sigef-brasil") continue;

      // Demais camadas continuam utilizando vetores locais.
      // O WMS, quando habilitado, é referência adicional.

      // Vetores locais nacionais podem ser consultados em qualquer UF
      // ou no Brasil inteiro. O próprio endpoint MVT aplica o filtro
      // estadual quando uma UF específica é selecionada.
      const tileUf = incraUf === "ALL" ? "all" : incraUf.toLowerCase();
      desiredVectorTiles.add(layer.id);

      const existingVectorTile = vectorTileLayersRef.current.get(layer.id);

      if (existingVectorTile) {
        const nextUrl = `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`;
        const source = existingVectorTile.getSource();
        existingVectorTile.setMinZoom(minimumVectorZoom(layer));
        // Evita recarregar os mesmos tiles a cada render da interface.
        if (source?.getUrls()?.[0] !== nextUrl) {
          source?.setUrl(nextUrl);
        }
        continue;
      }

      const vectorTileSource = new VectorTileSource({
        format: new MVT({ featureClass: Feature as never }),
        url: `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
      });

      const vectorTileLayer = new VectorTileLayer({
        source: vectorTileSource,
        zIndex: 2,
        minZoom: minimumVectorZoom(layer),
        declutter: false,
        style: (feature) => {
          const mutableFeature = feature as unknown as Feature;
          mutableFeature.set("displayColor", layer.color);
          mutableFeature.set("catalogName", layer.name);

          return mutableFeature.get("isSelected")
            ? selectedOfficialStyle
            : officialStyle(layer.color);
        },
      });

      vectorTileLayersRef.current.set(layer.id, vectorTileLayer);
      map.addLayer(vectorTileLayer);
    }

    for (const [id, vectorTileLayer] of vectorTileLayersRef.current) {
      if (!desiredVectorTiles.has(id)) {
        map.removeLayer(vectorTileLayer);
        vectorTileLayersRef.current.delete(id);
      }
    }

    setOfficialStatus(
      desiredVectorTiles.size
        ? `${desiredVectorTiles.size} camada${desiredVectorTiles.size === 1 ? "" : "s"} vetorial${desiredVectorTiles.size === 1 ? "" : "is"} local${desiredVectorTiles.size === 1 ? "" : "is"} ativa${desiredVectorTiles.size === 1 ? "" : "s"}`
        : "Nenhuma camada vetorial local ativa",
    );
    setLoadingOfficial(false);

    const desired = new Set<string>();
    for (const layer of layers) {
      if (!layer.id || !layer.enabled || !layer.wmsEnabled || !layer.wmsTheme)
        continue;

      // O WMS do INCRA apresenta instabilidade/502 em diversas UFs.
      // Durante a navegação usamos o MVT local para não bloquear o mapa.
      if (
        layer.source === "INCRA" &&
        layer.slug !== "incra-sigef-brasil"
      )
        continue;

      const requiresSpecificUf =
        (layer.source === "INCRA" &&
          layer.slug !== "incra-sigef-brasil") ||
        layer.source === "SICAR" ||
        Boolean(layer.wmsAvailableUfs?.length);

      if (incraUf === "ALL" && requiresSpecificUf)
        continue;
      if (
        incraUf !== "ALL" &&
        layer.wmsAvailableUfs?.length &&
        !layer.wmsAvailableUfs.includes(incraUf.toUpperCase())
      )
        continue;
      desired.add(layer.id);
      const effectiveUf =
        layer.slug === "incra-sigef-brasil" && incraUf === "ALL"
          ? "all"
          : incraUf === "ALL" ? "AP" : incraUf;
      const ufSuffix =
        layer.wmsTheme.startsWith("sicar:") && effectiveUf === "DF"
          ? "DF"
          : effectiveUf.toLowerCase();
      const layerName =
        layer.wmsFixedLayer ?? `${layer.wmsTheme}_${ufSuffix}`;
      const url =
        `${getApiUrl()}/sources/${layer.id}/wms?uf=${effectiveUf.toLowerCase()}`;
      const existing = wmsLayersRef.current.get(layer.id);
      if (existing) {
        existing.getSource()?.setUrl(url);
        existing.getSource()?.updateParams({ LAYERS: layerName });
      } else {
        const imageSource = new ImageWMS({
          url,
          params: {
            LAYERS: layerName,
            VERSION: "1.1.1",
            FORMAT: "image/png",
            TRANSPARENT: true,
          },
          ratio: 1.2,
          crossOrigin: "use-credentials",
        });
        imageSource.on("imageloadstart", () =>
          setOfficialStatus(`Conectando ao WMS oficial…`),
        );
        imageSource.on("imageloadend", () =>
          setOfficialStatus(`WMS oficial conectado`),
        );
        imageSource.on("imageloaderror", () =>
          setOfficialStatus(`Falha na conexão WMS oficial`),
        );
        const wmsLayer = new ImageLayer({
          zIndex: 1,
          opacity: 0.68,
          source: imageSource,
        });
        wmsLayersRef.current.set(layer.id, wmsLayer);
        map.addLayer(wmsLayer);
      }
    }
    for (const [id, wmsLayer] of wmsLayersRef.current) {
      if (!desired.has(id)) {
        map.removeLayer(wmsLayer);
        wmsLayersRef.current.delete(id);
      }
    }
  }, [layers, incraUf]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !measureMode) return;
    const draw = new Draw({ source: measureSourceRef.current, type: measureMode });
    draw.on("drawend", ({ feature }) => {
      const geom = feature.getGeometry();
      if (geom instanceof LineString) {
        const meters = getLength(geom, { projection: map.getView().getProjection() });
        setMeasureValue(meters >= 1000
          ? `Distância: ${(meters / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 3 })} km`
          : `Distância: ${meters.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m`);
      } else if (geom instanceof Polygon) {
        const m2 = getArea(geom, { projection: map.getView().getProjection() });
        setMeasureValue(`Área: ${(m2 / 10000).toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ha | ${m2.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m²`);
      }
    });
    map.addInteraction(draw);
    return () => { map.removeInteraction(draw); };
  }, [measureMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (drawRef.current) map.removeInteraction(drawRef.current);
    drawRef.current = null;
    if (!drawKind || measureMode) return;

    const draw = new Draw({ source: sourceRef.current, type: drawKind });
    // Mantém os polígonos previamente desenhados, possibilitando loteamentos.
    draw.on("drawend", () => window.setTimeout(emitGeometry, 0));
    map.addInteraction(draw);
    drawRef.current = draw;
    return () => {
      map.removeInteraction(draw);
    };
  }, [drawKind]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (modifyRef.current) {
      map.removeInteraction(modifyRef.current);
      modifyRef.current = null;
    }

    if (!modifyActive) return;

    const modify = new Modify({
      source: sourceRef.current,
    });

    modify.on("modifyend", () => {
      window.setTimeout(emitGeometry, 0);
    });

    map.addInteraction(modify);
    modifyRef.current = modify;

    return () => {
      map.removeInteraction(modify);
      modifyRef.current = null;
    };
  }, [modifyActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const sigefLayer = layers.find(
      (layer) =>
        layer.slug === "incra-sigef-brasil" &&
        layer.enabled &&
        Boolean(layer.id),
    );

    let geoNodeFeatures: Feature[] = [];
    let wfsController: AbortController | null = null;
    let requestTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const refreshLayerSnapSource = () => {
      snapLayerSourceRef.current.clear();
      if (!snapLayersEnabled) return;

      const extent = map.getView().calculateExtent(map.getSize());
      let imported = 0;
      const MAX_VISIBLE_SNAP_FEATURES = 25000;

      const addGeometry = (feature: Feature) => {
        if (imported >= MAX_VISIBLE_SNAP_FEATURES) return;
        const geometry = feature.getGeometry();
        if (!geometry) return;

        snapLayerSourceRef.current.addFeature(
          new Feature({ geometry: geometry.clone() }),
        );
        imported += 1;
      };

      // SNAP das camadas locais: comportamento anterior preservado.
      for (const feature of officialSourceRef.current.getFeaturesInExtent(extent)) {
        if (imported >= MAX_VISIBLE_SNAP_FEATURES) break;
        addGeometry(feature);
      }

      for (const vectorTileLayer of vectorTileLayersRef.current.values()) {
        if (imported >= MAX_VISIBLE_SNAP_FEATURES) break;
        const visibleFeatures = vectorTileLayer.getFeaturesInExtent(extent);

        for (const candidate of visibleFeatures) {
          if (imported >= MAX_VISIBLE_SNAP_FEATURES) break;
          addGeometry(candidate as unknown as Feature);
        }
      }

      // SNAP GeoNode: geometrias WFS da área de trabalho.
      for (const feature of geoNodeFeatures) {
        if (imported >= MAX_VISIBLE_SNAP_FEATURES) break;
        addGeometry(feature);
      }
    };

    const loadGeoNodeSnap = async (signal: AbortSignal) => {
      if (!snapLayersEnabled || !sigefLayer?.id) return;

      const extent = map.getView().calculateExtent(map.getSize());
      const [west, south] = toLonLat([extent[0], extent[1]]);
      const [east, north] = toLonLat([extent[2], extent[3]]);

      // Não consultar uma base nacional em zoom muito afastado.
      if (
        ![west, south, east, north].every(Number.isFinite) ||
        east <= west ||
        north <= south ||
        east - west > 0.10 ||
        north - south > 0.10
      ) {
        return;
      }

      const params = new URLSearchParams({
        bbox: [west, south, east, north].join(","),
        uf: incraUf === "ALL" ? "all" : incraUf.toLowerCase(),
        limit: "60",
      });

      try {
        const response = await fetch(
          `${getApiUrl()}/sources/${sigefLayer.id}/sigef-snap?${params}`,
          {
            credentials: "include",
            signal,
          },
        );

        if (!response.ok) {
          if (response.status !== 422) {
            console.warn("SNAP GeoNode indisponível:", response.status);
          }
          return;
        }

        const payload = await response.json();

        if (signal.aborted || disposed) return;

        if (!Array.isArray(payload.features)) return;

        // Uma resposta truncada não deve ser tomada como cobertura completa.
        if (payload.truncated) {
          console.warn(
            "SNAP GeoNode: limite de parcelas atingido. " +
            "Aproxime o mapa para reduzir a área de trabalho.",
          );
          return;
        }

        const format = new GeoJSON();
        geoNodeFeatures = format.readFeatures(payload, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        }) as Feature[];

        refreshLayerSnapSource();
      } catch (error) {
        if (!signal.aborted) {
          console.warn("Falha ao carregar geometrias SNAP GeoNode:", error);
        }
      }
    };

    const scheduleGeoNodeSnap = () => {
      if (requestTimer !== null) {
        clearTimeout(requestTimer);
        requestTimer = null;
      }

      wfsController?.abort();
      wfsController = null;
      geoNodeFeatures = [];

      refreshLayerSnapSource();

      if (!snapLayersEnabled || !sigefLayer?.id) return;

      // Evitar solicitações sucessivas enquanto o mapa é movimentado.
      requestTimer = setTimeout(() => {
        requestTimer = null;
        if (disposed) return;

        const controller = new AbortController();
        wfsController = controller;
        void loadGeoNodeSnap(controller.signal);
      }, 300);
    };

    if (snapSubjectRef.current) {
      map.removeInteraction(snapSubjectRef.current);
      snapSubjectRef.current = null;
    }

    if (snapLayersRef.current) {
      map.removeInteraction(snapLayersRef.current);
      snapLayersRef.current = null;
    }

    refreshLayerSnapSource();

    const subjectSnap = snapSubjectEnabled
      ? new Snap({
          source: sourceRef.current,
          vertex: true,
          edge: true,
          intersection: true,
          pixelTolerance: 14,
        })
      : null;

    const layerSnap = snapLayersEnabled
      ? new Snap({
          source: snapLayerSourceRef.current,
          vertex: true,
          edge: true,
          intersection: true,
          pixelTolerance: 14,
        })
      : null;

    if (subjectSnap) {
      map.addInteraction(subjectSnap);
      snapSubjectRef.current = subjectSnap;
    }

    if (layerSnap) {
      map.addInteraction(layerSnap);
      snapLayersRef.current = layerSnap;
    }

    const handleMoveEnd = () => {
      scheduleGeoNodeSnap();
    };

    const handleRenderComplete = () => {
      // Atualiza os vetores locais sem repetir requisições WFS.
      refreshLayerSnapSource();
    };

    if (snapLayersEnabled) {
      map.on("moveend", handleMoveEnd);
      map.on("rendercomplete", handleRenderComplete);
      scheduleGeoNodeSnap();
    }

    return () => {
      disposed = true;

      if (requestTimer !== null) clearTimeout(requestTimer);
      wfsController?.abort();

      if (snapLayersEnabled) {
        map.un("moveend", handleMoveEnd);
        map.un("rendercomplete", handleRenderComplete);
      }

      if (subjectSnap) map.removeInteraction(subjectSnap);
      if (layerSnap) map.removeInteraction(layerSnap);

      if (snapSubjectRef.current === subjectSnap) {
        snapSubjectRef.current = null;
      }

      if (snapLayersRef.current === layerSnap) {
        snapLayersRef.current = null;
      }

      snapLayerSourceRef.current.clear();
    };
  }, [snapSubjectEnabled, snapLayersEnabled, drawKind, modifyActive, layers, incraUf]);

  const returnToIdentifyCandidates = () => {
    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;

    if (selectedFeatureRef.current) {
      selectedFeatureRef.current.set(
        "isSelected",
        false,
      );
      selectedFeatureRef.current.changed();
      selectedFeatureRef.current = null;
    }

    identifySelectionSourceRef.current.clear();
    setIdentifiedFeature(null);

    setIdentifyCandidates([
      ...identifyCandidateHistoryRef.current,
    ]);
  };

  const clear = () => {
    sourceRef.current.clear();
    ++metricsRevision.current;
    setPolygons([]);
    setSelectedPolygonIds([]);
    hiddenPolygonIdsRef.current.clear();
    vertexLabelSourceRef.current.clear();
    setGeometryMetrics({ areaHectares: null, perimeterMeters: null, vertices: 0 });
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive(false);
    clearIdentifiedFeature();
    onGeometryChange(null);
  };

  const locate = () => {
    navigator.geolocation?.getCurrentPosition((position) => {
      mapRef.current?.getView().animate({
        center: fromLonLat([
          position.coords.longitude,
          position.coords.latitude,
        ]),
        zoom: 15,
        duration: 650,
      });
    });
  };

  const importFile = async (file: File) => {
    setImportError(null);
    setImportNotice(null);
    setImportingVector(true);
    try {
      const extension = file.name.split(".").pop()?.toLowerCase();
      let features: Feature[] = [];
      let successNotice = "";

      if (extension === "ods") {
        const body = new FormData();
        body.append("file", file);
        const response = await trackedFetch(`${getApiUrl()}/technical-pieces/import-sigef-ods`, {
          method: "POST", credentials: "include", body,
        }, "Enviando a planilha SIGEF");
        const payload = await response.json().catch(() => null);
        if (!response.ok) throw new Error(typeof payload?.detail === "string"
          ? payload.detail : "Não foi possível importar a planilha SIGEF.");
        features = new GeoJSON().readFeatures(payload, {
          dataProjection: "EPSG:4326", featureProjection: "EPSG:3857",
        });
        const metadata = payload?.metadata as Record<string, string> | undefined;
        if (metadata) {
          setImportedMetadata(metadata);
          if (metadata.name) setMemorialTitle(metadata.name);
          if (metadata.owner) setMemorialOwner(metadata.owner);
          if (metadata.cpf_cnpj) setOwnerCpf(metadata.cpf_cnpj);
          if (metadata.municipality) setPropertyAddress(metadata.municipality);
        }
        const count = Number(payload?.vertex_count ?? 0);
        successNotice = `Planilha SIGEF importada: ${count} vértices originais preservados. Confira os dados na aba Peças Técnicas.`;
      } else if (extension === "kml") {
        const text = await file.text();
        features = new KML({ extractStyles: false }).readFeatures(text, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        });
      } else if (extension === "geojson" || extension === "json") {
        const text = await file.text();
        features = new GeoJSON().readFeatures(text, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        });
      } else {
        const body = new FormData();
        body.append("file", file);
        const response = await trackedFetch(`${getApiUrl()}/tools/convert-vector`, {
          method: "POST",
          credentials: "include",
          body,
        }, "Enviando o arquivo vetorial");
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(
            typeof payload?.detail === "string"
              ? payload.detail
              : "Não foi possível converter o arquivo vetorial.",
          );
        }
        features = new GeoJSON().readFeatures(payload, {
          // Coordenadas geográficas SIRGAS2000 do backend usam longitude/latitude.
          // A renderização web utiliza WGS84 como aproximação; projeção/métricas
          // documentais e exportação UTM são tratadas no backend com GRS80.
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        });
      }

      if (!features.length) throw new Error("O arquivo não contém feições utilizáveis.");
      if (extension !== "ods") {
        setImportedMetadata(null);
        successNotice = "Arquivo vetorial importado. Campos ausentes de vértices e confrontações deverão ser preenchidos manualmente.";
      }

      // Cada polígono importado permanece como objeto independente.
      const separate: Feature[] = [];
      for (const feature of features) {
        const geometry = feature.getGeometry();
        if (geometry instanceof MultiPolygon) {
          for (const coords of geometry.getCoordinates()) {
            separate.push(new Feature({ ...feature.getProperties(), geometry: new Polygon(coords) }));
          }
        } else {
          separate.push(feature);
        }
      }
      sourceRef.current.addFeatures(separate);
      setDrawKind(null);
      setModifyActive(false);
      setIdentifyActive(false);
      const extent = sourceRef.current.getExtent();
      mapRef.current?.getView().fit(extent, {
        padding: [90, 90, 90, 90],
        maxZoom: 17,
        duration: 500,
      });
      emitGeometry();
      setImportNotice(successNotice);
    } catch (error) {
      setImportNotice(null);
      setImportError(error instanceof Error ? error.message : "Falha ao importar arquivo.");
    } finally {
      setImportingVector(false);
    }
  };

  const applyManualCoordinates = () => {
    setManualError(null);
    try {
      const coordinates = parseManualCoordinates(manualText, manualMode);
      if (coordinates.length === 2) {
        throw new Error("Para polígono informe ao menos 3 vértices; para ponto informe apenas 1.");
      }
      const geometry =
        coordinates.length === 1
          ? new Point(fromLonLat(coordinates[0]))
          : new Polygon([
              [
                ...coordinates.map((coordinate) => fromLonLat(coordinate)),
                fromLonLat(coordinates[0]),
              ],
            ]);

      sourceRef.current.addFeature(new Feature({ geometry }));
      setDrawKind(null);
      setModifyActive(false);
      setIdentifyActive(false);
      mapRef.current?.getView().fit(geometry.getExtent(), {
        padding: [90, 90, 90, 90],
        maxZoom: 17,
        duration: 450,
      });
      emitGeometry();
      setAdvancedPanel(null);
    } catch (error) {
      setManualError(error instanceof Error ? error.message : "Coordenadas inválidas.");
    }
  };

  useEffect(() => {
    let active = true;
    void fetch(`${getApiUrl()}/google-tiles/status`, { credentials: "include" })
      .then((response) => response.ok ? response.json() : { enabled: false })
      .then((data) => { if (active) setGoogleTilesEnabled(Boolean(data.enabled)); })
      .catch(() => { if (active) setGoogleTilesEnabled(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    void fetch(`${getApiUrl()}/mapbox-satellite/status`, { credentials: "include" })
      .then(response => response.ok ? response.json() : { enabled: false })
      .then(data => { if (active) setMapboxTilesEnabled(Boolean(data.enabled)); })
      .catch(() => { if (active) setMapboxTilesEnabled(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (basemap !== "google-satellite") {
      setGoogleCopyright("");
      return;
    }
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;
    let controller: AbortController | null = null;
    const updateAttribution = () => {
      const size = map.getSize();
      if (!size) return;
      const extent = map.getView().calculateExtent(size);
      const sw = toLonLat([extent[0], extent[1]]);
      const ne = toLonLat([extent[2], extent[3]]);
      const south = Math.max(-89.999, Math.min(89.999, sw[1]));
      const north = Math.max(-89.999, Math.min(89.999, ne[1]));
      const west = Math.max(-179.999, Math.min(179.999, sw[0]));
      const east = Math.max(-179.999, Math.min(179.999, ne[0]));
      if (south >= north || west >= east) return;
      controller?.abort();
      controller = new AbortController();
      const params = new URLSearchParams({
        north: String(north), south: String(south),
        east: String(east), west: String(west),
        zoom: String(Math.max(0, Math.min(22, Math.round(map.getView().getZoom() ?? 0)))),
      });
      void fetch(`${getApiUrl()}/google-tiles/attribution?${params}`, {
        credentials: "include", signal: controller.signal,
      }).then(async (response) => {
        if (!response.ok) throw new Error("Atribuição indisponível");
        return response.json();
      }).then((data) => {
        if (!cancelled) setGoogleCopyright(String(data.copyright ?? ""));
      }).catch((error) => {
        if (!cancelled && error?.name !== "AbortError") setGoogleCopyright("Atribuição temporariamente indisponível");
      });
    };
    map.on("moveend", updateAttribution);
    updateAttribution();
    return () => {
      cancelled = true;
      controller?.abort();
      map.un("moveend", updateAttribution);
    };
  }, [basemap]);

  const changeBasemap = async (value: string) => {
    const layer = baseLayerRef.current;
    if (!layer) return;
    setGoogleBasemapError("");
    if (value === "mapbox-satellite") {
      if (!mapboxTilesEnabled) {
        setGoogleBasemapError("Mapbox indisponível ou bloqueada pelo limite mensal. Verifique Configurações → Controle de custos.");
        return;
      }
      layer.setSource(new XYZ({
        url: `${getApiUrl()}/mapbox-satellite/tiles/{z}/{x}/{y}`,
        maxZoom: 20, crossOrigin: "use-credentials",
        attributions: "© Mapbox",
      }));
      setBasemap(value);
      return;
    }
    if (value === "google-satellite") {
      if (!googleTilesEnabled) {
        setGoogleBasemapError("Integração Google não habilitada na API deste ambiente.");
        return;
      }
      try {
        const response = await fetch(`${getApiUrl()}/google-tiles/session`, {
          credentials: "include",
        });
        if (!response.ok) throw new Error("Sessão Google Map Tiles indisponível. Confira a API e a chave no servidor.");
        layer.setSource(new XYZ({
          url: `${getApiUrl()}/google-tiles/tiles/{z}/{x}/{y}`,
          maxZoom: 20,
          crossOrigin: "use-credentials",
          attributions: "Google Maps",
        }));
        setBasemap(value);
      } catch (error) {
        setGoogleBasemapError(error instanceof Error ? error.message : "Erro na conexão Google.");
      }
      return;
    }
    if (value === "esri-imagery") {
      layer.setSource(new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        maxZoom: 19, crossOrigin: "anonymous", attributions: "Tiles © Esri",
      }));
    } else if (value === "esri-topo") {
      layer.setSource(new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        maxZoom: 19, crossOrigin: "anonymous", attributions: "Tiles © Esri",
      }));
    } else {
      layer.setSource(new OSM({ maxZoom: 19 }));
    }
    setBasemap(value);
  };

  const generateMemorial = async () => {
    const geometry = currentGeometryGeoJson();
    if (!geometry) return;
    setMemorialLoading(true);
    setMemorialText("");
    try {
      const parcels = documentParcels();
      const response = await fetch(`${getApiUrl()}/tools/memorial-draft`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parcels,
          property_metadata: {...(importedMetadata??{}),...legalMetadata},
          title: memorialTitle,
          plant_heading: plantHeading,
          memorial_heading: memorialHeading,
          owner_name: memorialOwner || null,
          owner_rg: ownerRg || null,
          owner_cpf: ownerCpf || null,
          property_address: propertyAddress || null,
          include_croqui_warning: croquiNote,
          professional_override: documentProfessional,
          edited_memorial: editedMemorial,
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail ?? "Não foi possível gerar o memorial.");
      }
      setMemorialText(payload.memorial_text ?? "");
    } catch (error) {
      setMemorialText(
        `ERRO: ${error instanceof Error ? error.message : "Falha ao gerar memorial."}`,
      );
    } finally {
      setMemorialLoading(false);
    }
  };

  const downloadMemorialDocx = async () => {
    setMemorialLoading(true);
    try {
      const parcels = documentParcels();
      const response = await trackedFetch(`${getApiUrl()}/tools/memorial/docx`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parcels,
          property_metadata: {...(importedMetadata??{}),...legalMetadata},
          title: memorialTitle,
          memorial_heading: memorialHeading,
          owner_name: memorialOwner || null,
          owner_rg: ownerRg || null,
          owner_cpf: ownerCpf || null,
          property_address: propertyAddress || null,
          include_croqui_warning: croquiNote,
          professional_override: documentProfessional,
          edited_memorial: editedMemorial,
        }),
      }, "Gerando o memorial (DOCX)");
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "Falha no DOCX.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "amazonika-memorial.docx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (error) {
      throw new Error(error instanceof Error ? error.message : "Falha no Word.");
    } finally {
      setMemorialLoading(false);
    }
  };

  // Serviço PDF único para pré-visualização e download; o mapa continua montado.
  const buildPlantMemorialPdfBlob = async (): Promise<Blob> => {
    const geometry = currentGeometryGeoJson();
    if (!geometry) throw new Error("Selecione um polígono válido.");
    const parcels = documentParcels();

    const geometryKey = JSON.stringify(situationGeoJson());
    if (situationSnapshot && situationSnapshot.geometry_key !== geometryKey) {
      throw new Error("A geometria selecionada mudou. Volte à etapa Dados do imóvel e registre novamente o enquadramento da Planta de Situação.");
    }
    const capture = situationSnapshot ?? await captureMapSituation();
    const { raster_b64, raster_source } = capture;
    const response = await trackedFetch(`${getApiUrl()}/tools/plant-memorial/pdf`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        parcels,
        property_metadata: {...(importedMetadata??{}),...legalMetadata},
        title: memorialTitle,
        plant_heading: plantHeading,
        memorial_heading: memorialHeading,
        owner_name: memorialOwner || null,
        owner_rg: ownerRg || null,
        owner_cpf: ownerCpf || null,
        property_address: propertyAddress || null,
        include_croqui_warning: croquiNote,
        professional_override: documentProfessional,
        edited_memorial: editedMemorial,
        raster_b64,
        raster_source,
        paper_format: paperFormat,
        orientation: paperOrientation,
        layout_template: plantLayoutTemplate,
        plant_elements: plantElements,
        magnetic_declination_degrees: plantElements.magnetic_declination && magneticDeclination.trim()
          ? Number(magneticDeclination) : null,
        survey_date: surveyDate || null,
        scale_denominator: scaleChoice === "auto"
          ? null : scaleChoice === "custom"
            ? Number(customScale)
            : Number(scaleChoice),
      }),
    }, "Gerando a planta e o memorial (PDF)");
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail
        : Array.isArray(detail) ? detail.map((issue: { loc?: unknown[]; msg?: string }) =>
            `${Array.isArray(issue.loc) ? issue.loc.join(".") + ": " : ""}${issue.msg ?? "Campo inválido"}`
          ).join("; ")
        : "Não foi possível gerar o PDF.";
      throw new Error(message);
    }
    setLastGeneratedPdfId(response.headers.get("X-Document-Id"));
    return response.blob();
  };

  const downloadSigefOds = async () => {
    const incompletePs4 = selectedFeatures().some(feature => {
      const details = feature.get("sigef_vertex_details") as Array<{
        sigef_method?: string; accuracy_verified?: boolean;
        sigma_lon_m?: number | null; sigma_lat_m?: number | null;
        sigma_h_m?: number | null; height_reference_confirmed?: boolean;
      }> | undefined;
      return details?.some(point => point.sigef_method === "PS4" && (
        point.accuracy_verified !== true ||
        point.height_reference_confirmed !== true ||
        ![point.sigma_lon_m, point.sigma_lat_m, point.sigma_h_m]
          .every(value => typeof value === "number" && Number.isFinite(value) && value > 0)
      ));
    });
    if (incompletePs4 || selectedFeatures().some(
      feature => feature.get("technical_piece_status") === "PRELIMINAR_NAO_CERTIFICADA"
    )) {
      throw new Error("ODS SIGEF bloqueada: vértice PS4 sem acurácia horizontal, altura elipsoidal confirmada ou sigmas individuais completos.");
    }
    if (!analysisId) throw new Error("Conclua uma análise espacial antes de exportar o ODS SIGEF.");
    const response = await trackedFetch(`${getApiUrl()}/analyses/${analysisId}/sigef-ods`, {
      credentials: "include",
    }, "Baixando a ODS SIGEF");
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? "Não foi possível exportar o ODS SIGEF.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `SIMULACAO_SIGEF_${analysisId.slice(0, 8)}.ods`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 3000);
  };

  useEffect(() => {
    if (!restorePiece || restorePiece.nonce === restoreNonceRef.current) return;
    const snapshot = restorePiece.snapshot;
    const data = snapshot.data ?? {};
    try {
      const features = new GeoJSON().readFeatures(snapshot.features ?? {
        type: "FeatureCollection", features: [],
      }, { dataProjection: "EPSG:4326", featureProjection: "EPSG:3857" });
      sourceRef.current.clear();
      hiddenPolygonIdsRef.current.clear();
      sourceRef.current.addFeatures(features as Feature[]);
      polygonSequenceRef.current = Math.max(
        polygonSequenceRef.current,
        ...features.map((feature) => {
          const id = String(feature.get("workPolygonId") ?? "");
          return Number(id.match(/^POL-(\d+)$/)?.[1] ?? 0);
        }),
      );
      setSelectedPolygonIds(Array.isArray(snapshot.selected_ids) ? snapshot.selected_ids : []);
      setImportedMetadata((snapshot.imported_sigef_metadata ?? null) as Record<string, string> | null);
      setLegalMetadata((snapshot.legal_metadata??{}) as Record<string,string>);
      setMemorialTitle(String(data.title ?? "Área analisada"));
      setPlantHeading(String(data.plantHeading ?? "PLANTA GEORREFERENCIADA"));
      setMemorialHeading(String(data.memorialHeading ?? "MEMORIAL DESCRITIVO"));
      setMemorialOwner(String(data.owner ?? ""));
      setOwnerRg(String(data.rg ?? ""));
      setOwnerCpf(String(data.cpf ?? ""));
      setPropertyAddress(String(data.address ?? ""));
      setCroquiNote(Boolean(data.croqui));
      setPaperFormat(["A0","A1","A2","A3","A4"].includes(String(data.format)) ? data.format as typeof paperFormat : "A2");
      setPaperOrientation(data.orientation === "paisagem" ? "paisagem" : "retrato");
      setPlantLayoutTemplate(typeof data.layoutTemplate === "string" && ["classic_lateral", "cartographic_frame", "modern_lateral"].includes(data.layoutTemplate) ? data.layoutTemplate as PecasData["layoutTemplate"] : "classic_lateral");
      setScaleChoice(String(data.scale ?? "auto"));
      setCustomScale(String(data.customScale ?? "1500"));
      if (snapshot.professional) {
        setDocumentProfessional(snapshot.professional as ProfessionalDocumentProfile);
        documentProfessionalEdited.current = true;
      }
      if (snapshot.elements) setPlantElements(snapshot.elements as PlantElementFlags);
      setMagneticDeclination(String(snapshot.magnetic_declination ?? ""));
      setSurveyDate(String(snapshot.survey_date ?? ""));
      setSituationSnapshot((snapshot.situation ?? null) as SituationSnapshot | null);
      setLoadedMemorialDraft(String(snapshot.memorial_edited ?? ""));
      setLoadedTopconDraft((snapshot.topcon ?? null) as TopconDraft | null);
      setLoadedTopconRevision(restorePiece.nonce);
      setEditedMemorial(snapshot.memorial_edited ? String(snapshot.memorial_edited) : null);
      setCurrentPieceId(restorePiece.id);
      setLastGeneratedPdfId(typeof snapshot.generated_pdf_id === "string" ? snapshot.generated_pdf_id : null);
      setMemorialText("");
      emitGeometry();
      const extent = sourceRef.current.getExtent();
      if (extent.every(Number.isFinite)) mapRef.current?.getView().fit(extent, {
        padding: [75, 75, 75, 75], maxZoom: 16,
      });
      setWorkspaceOpen(true);
      restoreNonceRef.current = restorePiece.nonce;
    } catch (error) {
      setDocumentError(error instanceof Error ? error.message : "Não foi possível restaurar a peça.");
    }
  }, [restorePiece?.nonce]);

  const changePecasData = (key: keyof PecasData, value: string | boolean) => {
    switch (key) {
      case "title": setMemorialTitle(String(value)); break;
      case "plantHeading": setPlantHeading(String(value)); break;
      case "memorialHeading": setMemorialHeading(String(value)); break;
      case "owner": setMemorialOwner(String(value)); break;
      case "rg": setOwnerRg(String(value)); break;
      case "cpf": setOwnerCpf(String(value)); break;
      case "address": setPropertyAddress(String(value)); break;
      case "croqui": setCroquiNote(Boolean(value)); break;
      case "format": setPaperFormat(["A0","A1","A2","A3","A4"].includes(String(value)) ? value as typeof paperFormat : "A2"); break;
      case "orientation": setPaperOrientation(value === "paisagem" ? "paisagem" : "retrato"); break;
      case "layoutTemplate": {
        const chosen = value as PecasData["layoutTemplate"];
        setPlantLayoutTemplate(chosen);
        if (["classic_lateral", "cartographic_frame", "modern_lateral"].includes(chosen)) {
          setPlantElements(prev => ({...prev, coordinates: true}));
        }
        break;
      }
      case "scale": setScaleChoice(String(value)); break;
      case "customScale": setCustomScale(String(value)); break;
    }
  };

  const activateDraw = (kind: Exclude<DrawKind, null>) => {
    setMeasureMode(null);
    setIdentifyActive(false);
    setModifyActive(false);
    setDrawKind((current) => (current === kind ? null : kind));
  };

  const toggleModify = () => {
    setMeasureMode(null);
    if (sourceRef.current.getFeatures().length === 0) return;

    setDrawKind(null);
    setIdentifyActive(false);
    setModifyActive((current) => !current);
  };

  const toggleMeasure = (mode: "LineString" | "Polygon") => {
    setIdentifyActive(false);
    setDrawKind(null);
    setModifyActive(false);
    setMeasureValue("");
    setMeasureMode(current => current === mode ? null : mode);
  };

  const focusAttributeSearchResult = (item: LayerSearchResult, layerName: string) => {
    try {
      const map = mapRef.current;
      if (!map || !item.geometry) throw new Error("Mapa ainda não está pronto.");
      const feature = new GeoJSON().readFeature({
        type: "Feature",
        geometry: item.geometry,
        properties: item.properties ?? {},
      }, { dataProjection: "EPSG:4326", featureProjection: map.getView().getProjection() });
      // Some OpenLayers GeoJSON typings admit Feature[] as well as Feature.
      const selectedFeature = Array.isArray(feature) ? feature[0] : feature;
      if (!selectedFeature) throw new Error("Resultado sem feição vetorial.");
      const geometry = selectedFeature.getGeometry();
      if (!geometry) throw new Error("Resultado sem geometria vetorial.");
      const extent = geometry.getExtent();
      if (!extent.every(Number.isFinite)) throw new Error("Extensão inválida.");
      attributeSearchSourceRef.current.clear();
      attributeSearchSourceRef.current.addFeature(selectedFeature);
      map.getView().fit(extent, {
        size: map.getSize(),
        padding: [90, 90, 90, 90],
        maxZoom: 17,
        duration: 650,
      });
      setIdentifiedFeature({
        title: item.title,
        layer: layerName,
        attributes: [
          ["external_id", item.external_id ?? "—"],
          ...Object.entries(item.properties ?? {}).filter(([key]) =>
            !["geometry", "geom"].includes(key)
          ).slice(0, 40),
        ],
      });
      setIdentifyCandidates([]);
      setFeaturePanelOffset({ x: 0, y: 0 });
      setExtentMessage(null);
    } catch (error) {
      setExtentMessage(error instanceof Error ? error.message : "Não foi possível localizar a feição.");
    }
  };

  const toggleIdentify = () => {
    setMeasureMode(null);
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive((current) => !current);
  };

  return (
    <div className="real-map-wrap">
      <LayerAttributeSearch layers={layers} onSelect={focusAttributeSearchResult} hidden={hideAdvancedTools} />
      <div
        ref={mapElement}
        className={`real-map ${identifyActive ? "identify-mode" : ""}`}
      />
      <div className="geo-tools" aria-label="Ferramentas do mapa">
        <button
          className={identifyActive ? "active" : ""}
          onClick={toggleIdentify}
          title="Identificar uma feição"
        >
          <Info size={17} />
          <span>Identificar</span>
        </button>
        <button
          className={drawKind === "Point" ? "active" : ""}
          onClick={() => activateDraw("Point")}
          title="Desenhar ponto"
        >
          <MapPin size={17} />
          <span>Ponto</span>
        </button>
        <button
          className={drawKind === "Polygon" ? "active" : ""}
          onClick={() => activateDraw("Polygon")}
          title="Desenhar polígono"
        >
          <Pentagon size={17} />
          <span>Polígono</span>
        </button>
        <button
          className={modifyActive ? "active" : ""}
          onClick={toggleModify}
          title="Editar vértices da geometria"
          disabled={sourceRef.current.getFeatures().length === 0}
        >
          <Pencil size={16} />
          <span>Editar</span>
        </button>
        <label title="Importar planilha SIGEF ODS, KML, SHP.ZIP, GeoJSON ou GeoPackage">
          <FileUp size={17} />
          <span>Importar</span>
          <input
            type="file"
            accept=".ods,.kml,.geojson,.json,.zip,.gpkg,application/vnd.oasis.opendocument.spreadsheet,application/geo+json,application/zip"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importFile(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
        <button className={measureMode === "LineString" ? "active" : ""}
          onClick={() => toggleMeasure("LineString")} title="Medir distâncias em metros ou quilômetros">
          <Ruler size={16} /><span>Distância</span>
        </button>
        <button className={measureMode === "Polygon" ? "active" : ""}
          onClick={() => toggleMeasure("Polygon")} title="Medir áreas em hectares e metros quadrados">
          <Pentagon size={16} /><span>Área</span>
        </button>
        <button onClick={locate} title="Minha localização">
          <Crosshair size={16} />
          <span>Localizar</span>
        </button>
        <button onClick={clear} title="Limpar geometria">
          <Eraser size={16} />
          <span>Limpar</span>
        </button>
      </div>
      {(measureMode || measureValue) && (
        <div className="geo-measure-panel" role="status">
          <strong>{measureValue || (measureMode === "LineString"
            ? "Clique nos pontos e dê dois cliques para concluir a distância"
            : "Clique nos vértices e dê dois cliques para concluir a área")}</strong>
          <button type="button" onClick={() => { measureSourceRef.current.clear(); setMeasureValue(""); }}>Limpar medição</button>
          <button type="button" onClick={() => setMeasureMode(null)}>Concluir</button>
        </div>
      )}
      {!hideAdvancedTools && <div className="geo-advanced-tools" aria-label="Ferramentas avançadas">
        <button className={advancedPanel === "coordinates" ? "active" : ""} onClick={() => setAdvancedPanel((current) => current === "coordinates" ? null : "coordinates")} title="Inserir coordenadas manualmente"><MapPin size={18} /></button>
        <button className={snapSubjectEnabled || snapLayersEnabled ? "active" : ""} onClick={() => setAdvancedPanel((current) => current === "snap" ? null : "snap")} title="Configurar Snap"><Magnet size={18} /></button>
        <button className={advancedPanel === "basemap" ? "active" : ""} onClick={() => setAdvancedPanel((current) => current === "basemap" ? null : "basemap")} title="Mapa base / satélite"><Satellite size={18} /></button>
        <button className={advancedPanel === "polygons" ? "active" : ""} onClick={() => setAdvancedPanel((current) => current === "polygons" ? null : "polygons")} title="Polígonos e exportação"><Layers3 size={18} /></button>
        <button className={advancedPanel === "memorial" ? "active" : ""} disabled={!sourceRef.current.getFeatures().length} onClick={() => setAdvancedPanel((current) => current === "memorial" ? null : "memorial")} title="Gerar memorial descritivo"><Sparkles size={18} /></button>
      </div>}

      {!hideAdvancedTools && advancedPanel === "coordinates" && (
        <aside className="geo-advanced-panel coordinates-panel">
          <header><strong>Inserir coordenadas</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <div className="coordinate-mode-tabs">
            {(["DD", "DMS", "UTM"] as ManualCoordinateMode[]).map((mode) => (
              <button key={mode} className={manualMode === mode ? "active" : ""} onClick={() => setManualMode(mode)}>{mode}</button>
            ))}
          </div>
          <small>{manualMode === "DD" ? "Uma linha por vértice: longitude, latitude" : manualMode === "DMS" ? 'Uma linha por vértice: 51 30 00 W ; 0 02 00 N' : "Uma linha por vértice: Este, Norte, Fuso, Hemisfério (ex.: 532685, 137648, 22, N)"}</small>
          <textarea value={manualText} onChange={(event) => setManualText(event.target.value)} rows={7} placeholder="Cole as coordenadas aqui" />
          {manualError && <p className="geo-tool-error">{manualError}</p>}
          <button className="geo-tool-primary" onClick={applyManualCoordinates}>Aplicar no mapa</button>
        </aside>
      )}

      {!hideAdvancedTools && advancedPanel === "snap" && (
        <aside className="geo-advanced-panel snap-panel">
          <header><strong>Snap / atração magnética</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <label><input type="checkbox" checked={snapSubjectEnabled} onChange={(event) => setSnapSubjectEnabled(event.target.checked)} /><span>Vértices e arestas da geometria em edição</span></label>
          <label><input type="checkbox" checked={snapLayersEnabled} onChange={(event) => setSnapLayersEnabled(event.target.checked)} /><span>Camadas vetoriais carregadas no mapa</span></label>
          <small>O Snap pode ser ativado ou desligado a qualquer momento durante desenho e edição.</small>
        </aside>
      )}

      {!hideAdvancedTools && advancedPanel === "basemap" && (
        <aside className="geo-advanced-panel basemap-panel">
          <header><strong>Mapa base</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <button className={basemap === "osm" ? "active" : ""} onClick={() => changeBasemap("osm")}>OpenStreetMap</button>
          <button className={basemap === "esri-imagery" ? "active" : ""} onClick={() => changeBasemap("esri-imagery")}>Esri World Imagery</button>
          <button className={basemap === "esri-topo" ? "active" : ""} onClick={() => changeBasemap("esri-topo")}>Esri World Topographic</button>
          <button disabled={!googleTilesEnabled} className={basemap === "google-satellite" ? "active" : ""}
            onClick={() => void changeBasemap("google-satellite")}>
            Google Satélite {googleTilesEnabled ? "(visualização)" : "(aguardando configuração)"}
          </button>
          <button disabled={!mapboxTilesEnabled} className={basemap === "mapbox-satellite" ? "active" : ""}
            onClick={() => void changeBasemap("mapbox-satellite")}>
            Mapbox Satellite {mapboxTilesEnabled ? "(visualização)" : "(indisponível ou limite atingido)"}
          </button>
          {googleBasemapError && <small role="alert">{googleBasemapError}</small>}
          <small>Google e Mapbox são exibidos para visualização online, sem captura ou exportação PDF nesta integração.</small>
        </aside>
      )}

      {basemap === "google-satellite" && (
        <aside className="geo-google-attribution" aria-label="Créditos das imagens Google">
          <strong aria-label="Google Maps">Google Maps</strong>
          <span>{googleCopyright || "Google Maps — carregando créditos"}</span>
        </aside>
      )}
      {!hideAdvancedTools && advancedPanel === "polygons" && (
        <aside className="geo-advanced-panel polygons-panel">
          <header>
            <strong>Polígonos, vértices e exportação ({polygons.length})</strong>
            <button onClick={() => setAdvancedPanel(null)} aria-label="Fechar"><X size={17} /></button>
          </header>
          <small>Desenhe quantos polígonos desejar. Marque as áreas que entrarão em uma única planta e memorial. Exporte cada uma individualmente em TXT UTM, KML ou Shapefile ZIP.</small>
          {polygons.map((polygon) => (
            <div className="work-polygon" key={polygon.id}>
              <div className="work-polygon-heading">
                <input
                  aria-label={`Selecionar ${polygon.name}`}
                  type="checkbox"
                  checked={selectedPolygonIds.includes(polygon.id)}
                  title="Marcar mostra o polígono no mapa; desmarcar oculta"
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setPolygonVisible(polygon.id, checked);
                    setSelectedPolygonIds((current) =>
                      checked
                        ? [...new Set([...current, polygon.id])]
                        : current.filter((id) => id !== polygon.id)
                    );
                  }}
                />
                <input
                  aria-label="Nome do polígono"
                  className="work-polygon-name"
                  value={polygon.name}
                  onChange={(event) => setPolygonName(polygon.id, event.target.value)}
                />
                <button title="Excluir somente este polígono" aria-label="Excluir polígono" onClick={() => removePolygon(polygon.id)}>
                  <Trash2 size={16} />
                </button>
              </div>
              <small>{polygon.areaHa.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ha · {polygon.perimeterM.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m de perímetro · {polygon.vertices.length} vértices</small>
              <details className="work-vertex-details">
                <summary>Renomear vértices antes da emissão</summary>
                <button
                  onClick={() => {
                    for (const [index] of polygon.vertices.entries()) {
                      renameVertex(polygon.id, index, `V${String(index + 1).padStart(2, "0")}`);
                    }
                  }}
                >Padronizar V01, V02…</button>
                <div className="work-vertex-grid">
                  {polygon.vertices.map((name, index) => (
                    <label key={index}>
                      <span>Vértice {index + 1}</span>
                      <div className="work-vertex-action">
                        <input
                          value={name}
                          onChange={(event) => renameVertex(polygon.id, index, event.target.value)}
                        />
                        <button
                          type="button"
                          title={`Excluir vértice ${name}`}
                          aria-label={`Excluir vértice ${name}`}
                          onClick={() => removeVertex(polygon.id, index)}
                        ><Trash2 size={15}/></button>
                      </div>
                      <span>Altitude do vértice (m, opcional)</span>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={polygon.altitudes[index] ?? ""}
                        onChange={(event) => updateParcelVertexData(
                          polygon.id, index, "altitudes", event.target.value
                        )}
                      />
                      <span>Confrontante no segmento que começa neste vértice</span>
                      <input
                        value={polygon.confrontants[index] ?? ""}
                        placeholder="Nome do confrontante ou via"
                        onChange={(event) => updateParcelVertexData(
                          polygon.id, index, "confrontants", event.target.value
                        )}
                      />
                    </label>
                  ))}
                </div>
              </details>
              <div className="work-polygon-export">
                {(["txt", "kml", "shp"] as const).map((format) => (
                  <button
                    key={format}
                    disabled={exportBusy}
                    onClick={() => void exportIndividualPolygon(polygon.id, format)}
                  >
                    <Download size={13} />
                    {format === "shp" ? "ZIP (SHP)" : format.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          ))}
          {polygons.length === 0 && <p>Desenhe ou importe ao menos um polígono.</p>}
          {documentError && <p className="geo-tool-error" role="alert">{documentError}</p>}
        </aside>
      )}

      {!hideAdvancedTools && advancedPanel === "memorial" && (
        <aside className="geo-advanced-panel memorial-panel">
          <header><strong>Planta e memorial</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <p>Elabore as peças técnicas em cinco etapas, com dados, vértices, memorial, conferência do PDF e exportações.</p>
          <small><strong>{selectedPolygonIds.length} polígono(s) selecionado(s)</strong>. O mapa, as geometrias e os serviços atuais serão preservados.</small>
          <div className="memorial-actions">
            <button type="button" className="geo-tool-primary" disabled={!selectedPolygonIds.length}
              onClick={() => { setAdvancedPanel(null); setWorkspaceOpen(true); }}>
              Avançar — elaborar peças técnicas
            </button>
          </div>
        </aside>
      )}

      <PecasTecnicasWorkspace
        open={workspaceOpen}
        onClose={() => setWorkspaceOpen(false)}
        data={{
          title: memorialTitle, plantHeading, memorialHeading, owner: memorialOwner,
          rg: ownerRg, cpf: ownerCpf, address: propertyAddress, croqui: croquiNote,
          format: paperFormat, orientation: paperOrientation,
          layoutTemplate: plantLayoutTemplate, scale: scaleChoice, customScale,
        }}
        onDataChange={changePecasData}
        onLegalMetadataChange={(updates)=> {
          setLegalMetadata(old=>({...old,...updates}));
          setMemorialText("");
          setEditedMemorial(null);
          setLastGeneratedPdfId(null);
        }}
        polygons={polygons}
        importedMetadata={importedMetadata}
        selectedIds={selectedPolygonIds}
        rtProfile={documentProfessional}
        rtLoading={documentProfessionalLoading}
        rtError={documentProfessionalError}
        onRtChange={(key, value) => {
          documentProfessionalEdited.current = true;
          setDocumentProfessional((previous) => previous ? { ...previous, [key]: value } : previous);
        }}
        onRtReload={refreshDocumentProfessional}
        situationGeometry={situationGeoJson() as unknown as Record<string, unknown>}
        situationKey={JSON.stringify(situationGeoJson())}
        situationSaved={situationSnapshot}
        onSaveSituation={setSituationSnapshot}
        elements={plantElements}
        onToggleElement={(key: PlantElementKey, checked: boolean) =>
          setPlantElements((previous) => ({ ...previous, [key]: checked }))
        }
        declination={magneticDeclination}
        onDeclinationChange={setMagneticDeclination}
        surveyDate={surveyDate}
        onSurveyDateChange={setSurveyDate}
        rasterKey={JSON.stringify([mapRef.current?.getView().getCenter(), mapRef.current?.getView().getZoom(), basemap, situationSnapshot?.token])}
        onSelect={(id, checked) => setSelectedPolygonIds((current) =>
          checked ? [...new Set([...current, id])] : current.filter((item) => item !== id)
        )}
        onRenamePolygon={setPolygonName}
        onAdoptTopconParcels={adoptTopconParcels}
        onResetTopconWork={resetTopconWork}
        onRenameVertex={renameVertex}
        onConfrontant={(id, index, value) => updateParcelVertexData(id, index, "confrontants", value)}
        memorialText={memorialText}
        memorialLoading={memorialLoading}
        externalError={documentError}
        onGenerateMemorial={generateMemorial}
        onBuildPdf={buildPlantMemorialPdfBlob}
        onDownloadDocx={downloadMemorialDocx}
        onExportPolygon={exportIndividualPolygon}
        onDownloadSigef={downloadSigefOds}
        onSavePiece={saveCurrentPiece}
        onSaveMemorial={setEditedMemorial}
        loadedPieceId={currentPieceId}
        loadedMemorialDraft={loadedMemorialDraft}
        loadedTopconDraft={loadedTopconDraft}
        loadedTopconRevision={loadedTopconRevision}
        sigefAvailable={Boolean(analysisId)}
      />

      {sourceRef.current.getFeatures().length > 0 && (
        <div className="geometry-metrics-card">
          <Ruler size={16} />
          <span>{geometryMetrics.areaHectares == null ? "Geometria pontual" : `${geometryMetrics.areaHectares.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ha`}</span>
          {geometryMetrics.perimeterMeters != null && <span>{geometryMetrics.perimeterMeters.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m</span>}
          <span>{geometryMetrics.vertices} vértice{geometryMetrics.vertices === 1 ? "" : "s"}</span>
        </div>
      )}

      {extentMessage && <div className="map-operation-feedback error" role="alert" onClick={() => setExtentMessage(null)}>{extentMessage}</div>}
      {importingVector && <div className="map-operation-feedback">Importando e convertendo arquivo vetorial…</div>}
      {importError && <div className="map-operation-feedback error">{importError}</div>}
      {importNotice && (
        <div className="map-operation-feedback import-notice" role="status">
          <span>{importNotice}</span>
          <button
            type="button"
            className="import-notice-dismiss"
            onClick={() => setImportNotice(null)}
            aria-label="Fechar aviso de importação"
            title="Fechar aviso"
          >
            ×
          </button>
        </div>
      )}

      <div
        className={`official-layer-status ${loadingOfficial ? "loading" : ""}`}
      >
        {loadingOfficial ? "Carregando camadas visíveis…" : officialStatus}
      </div>
      {identifyLoading && (
        <div className="identify-request-loading" role="status" aria-live="polite">
          <span className="identify-request-spinner" aria-hidden="true" />
          <div>
            <strong>Aguardando informações</strong>
            <small>{identifyLoadingMessage}</small>
          </div>
        </div>
      )}
      {identifyActive &&
        !identifyLoading &&
        !identifiedFeature &&
        identifyCandidates.length === 0 && (
          <div className="identify-hint">
            Clique sobre uma feição territorial para consultar seus dados
          </div>
        )}
      {identifyCandidates.length > 1 && (
        <aside
          className="identify-candidates-panel"
          aria-label="Feições encontradas no ponto"
        >
          <header>
            <div>
              <small>FEIÇÕES SOBREPOSTAS</small>
              <strong>{identifyCandidates.length} opções neste ponto</strong>
            </div>
            <button onClick={clearIdentifiedFeature} aria-label="Fechar opções">
              <X size={18} />
            </button>
          </header>
          <div>
            {identifyCandidates.map((candidate, index) => (
              <button
                key={`${candidate.layer}-${candidate.title}-${index}`}
                onClick={() => selectFeatureRef.current(candidate.feature)}
              >
                <span>{candidate.layer}</span>
                <strong>{candidate.title}</strong>
              </button>
            ))}
          </div>
        </aside>
      )}
      {identifiedFeature && (
        <aside
          className="feature-info-panel"
          style={{ transform: `translate(${featurePanelOffset.x}px, ${featurePanelOffset.y}px)` }}
          aria-label="Informações da feição identificada"
        >
          <header className="feature-info-drag-handle" title="Arraste para mover a janela"
            onPointerDown={(event) => {
              if ((event.target as HTMLElement).closest("button")) return;
              featureDragRef.current = {
                x: event.clientX, y: event.clientY,
                originX: featurePanelOffset.x, originY: featurePanelOffset.y,
              };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              const drag = featureDragRef.current;
              if (!drag) return;
              setFeaturePanelOffset({
                x: Math.max(-window.innerWidth + 360, Math.min(window.innerWidth - 380, drag.originX + event.clientX - drag.x)),
                y: Math.max(-window.innerHeight + 240, Math.min(window.innerHeight - 200, drag.originY + event.clientY - drag.y)),
              });
            }}
            onPointerUp={(event) => {
              featureDragRef.current = null;
              if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
            }}
            onPointerCancel={() => { featureDragRef.current = null; }}>
            <div>
              <small>FEIÇÃO IDENTIFICADA · ARRASTE PARA MOVER</small>
              <strong>{identifiedFeature.title}</strong>
              <span>{identifiedFeature.layer}</span>
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {identifyCandidateHistoryRef.current.length > 1 && (
                <button
                  onClick={returnToIdentifyCandidates}
                  aria-label="Voltar às feições encontradas"
                  title="Voltar às feições encontradas"
                >
                  <ArrowLeft size={18} />
                </button>
              )}

              <button
                onClick={clearIdentifiedFeature}
                aria-label="Fechar informações"
              >
                <X size={18} />
              </button>
            </div>
          </header>
          {identifiedFeature.loading ? (
            <div className="feature-info-loading">
              <span className="identify-request-spinner" aria-hidden="true" />
              <div>
                <strong>Carregando informações</strong>
                <small>Consultando atributos completos da feição…</small>
              </div>
            </div>
          ) : (
            <dl>
              {identifiedFeature.attributes.map(([field, value]) => (
                <div key={field}>
                  <dt>{fieldLabel(field)}</dt>
                  <dd>{fieldValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="feature-info-actions">
            <button type="button" onClick={addIdentifiedToDownload}
              title="Adiciona esta parcela à lista para baixar em SHP (.zip) ou KML">
              <ListPlus size={15} /> Adicionar à seleção para download
            </button>
          </div>
        </aside>
      )}
      {(downloadParcels.length > 0 || downloadError) && (
        <aside className={`download-parcels-panel ${downloadPanelOpen ? "" : "collapsed"}`}
          aria-label="Parcelas selecionadas para download">
          <header>
            <button type="button" className="download-parcels-toggle"
              onClick={() => setDownloadPanelOpen((open) => !open)}
              aria-expanded={downloadPanelOpen}>
              <Download size={15} />
              <strong>Parcelas para download ({downloadParcels.filter((item) => item.visible).length}/{downloadParcels.length})</strong>
            </button>
            <button type="button" onClick={clearDownloadParcels} aria-label="Limpar seleção" title="Limpar seleção">
              <X size={16} />
            </button>
          </header>
          {downloadPanelOpen && (
            <>
              <small>Use Identificar, clique numa parcela de qualquer base e escolha “Adicionar à seleção para download”. Somente as parcelas marcadas aparecem no mapa e entram no arquivo.</small>
              <ul>
                {downloadParcels.map((item) => (
                  <li key={item.id}>
                    <input type="checkbox" checked={item.visible}
                      aria-label={`Mostrar e incluir ${item.name}`}
                      title="Marcar mostra no mapa e inclui no download; desmarcar oculta"
                      onChange={(event) => toggleDownloadParcel(item.id, event.target.checked)} />
                    <button type="button" className="download-parcel-name"
                      onClick={() => zoomToDownloadParcel(item.id)} title="Aproximar no mapa">
                      <strong>{item.name}</strong>
                      <span>{item.layer}</span>
                    </button>
                    <button type="button" onClick={() => removeDownloadParcel(item.id)}
                      aria-label={`Remover ${item.name}`} title="Remover da seleção">
                      <Trash2 size={14} />
                    </button>
                  </li>
                ))}
              </ul>
              {downloadError && <p className="geo-tool-error" role="alert">{downloadError}</p>}
              <div className="download-parcels-actions">
                <button type="button" disabled={downloadBusy || !downloadParcels.some((item) => item.visible)}
                  onClick={() => void downloadSelectedParcels("shp")}>
                  <Download size={13} /> ZIP (SHP)
                </button>
                <button type="button" disabled={downloadBusy || !downloadParcels.some((item) => item.visible)}
                  onClick={() => void downloadSelectedParcels("kml")}>
                  <Download size={13} /> KML
                </button>
              </div>
            </>
          )}
        </aside>
      )}
      {drawKind && (
        <div className="draw-hint">
          {drawKind === "Point"
            ? "Clique no mapa para marcar o ponto"
            : "Clique nos vértices e dê duplo clique para concluir"}
        </div>
      )}

      {modifyActive && (
        <div className="draw-hint">
          Arraste os vértices para ajustar a geometria. Clique em Editar novamente para finalizar.
        </div>
      )}
    </div>
  );
}
