"use client";

import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import GeoJSON from "ol/format/GeoJSON";
import type Geometry from "ol/geom/Geometry";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import { getApiUrl } from "@/lib/api";
import { fromLonLat, toLonLat } from "ol/proj";
import { Circle as CircleStyle, Fill, Stroke, Style, Text as TextStyle } from "ol/style";

export type Pa2MapWitness = {
  name: string;
  label?: string;
  virtual?: boolean;
  latitude: number | null;
  longitude: number | null;
};
type Props = {
  points: Pa2MapWitness[];
  selected: string[];
  intersection?: { latitude: number | null; longitude: number | null } | null;
  onPick: (name: string) => void;
  method?: "PA1" | "PA2" | "PT8" | "PS4" | "PB1" | "PS1";
  ps4Points?: Array<{ name: string; latitude: number; longitude: number }>;
  ps4Candidate?: { latitude: number; longitude: number } | null;
  ps4ClosureGeometry?: { type: "Polygon"; coordinates: number[][][] } | null;
  onPs4Click?: (point: { longitude: number; latitude: number }) => void;
  ps4CheckCapture?: boolean;
  supportLineMode?: boolean;
  /** Paralela em série: liga todos os pontos selecionados na ordem do clique. */
  chainMode?: boolean;
  /** Linhas e vértices auxiliares (outras cadeias e V calculados). */
  overlayLines?: Array<{ label: string; coords: Array<[number, number]>; computed?: boolean }>;
  overlayPoints?: Array<{ name: string; longitude: number | null; latitude: number | null }>;
  onPositionHint?: (point: { longitude: number; latitude: number }) => void;
  hint?: { longitude: number; latitude: number } | null;
  polygonGeometry?: Record<string, unknown> | null;
  polygonKey?: string;
  ps4SceneId?: string;
  ps4ReportAttached?: boolean;
  pb1Raster?: {
    pieceId: string; sha256: string;
    footprint?: { type: string; coordinates: number[][][] };
  } | null;
  pb1Dtm?: {
    pieceId: string; sha256: string;
    footprint?: { type: string; coordinates: number[][][] };
  } | null;
  ps4Raster?: {
    pieceId: string; sha256: string;
    footprint?: { type: string; coordinates: number[][][] };
  } | null;
};

/** Mapa de apoio PA2: clique nos dois testemunhos de cada alinhamento. */
export function Pa2WitnessMap({ points, selected, intersection, onPick,
  method = "PA2", supportLineMode = false, chainMode = false, overlayLines = [], overlayPoints = [], onPositionHint, hint,
  polygonGeometry, polygonKey = "", ps4Points = [], ps4Candidate,
  ps4ClosureGeometry, onPs4Click, ps4CheckCapture = false, ps4Raster = null, ps4ReportAttached = false,
  ps4SceneId = "CBERS4A_WPM_PCA_RGB321_20261016_214_113", pb1Raster = null, pb1Dtm = null }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef(new VectorSource());
  const polygonSourceRef = useRef(new VectorSource());
  const ps4SourceRef = useRef(new VectorSource());
  const closureSourceRef = useRef(new VectorSource());
  const ps4ClickRef = useRef(onPs4Click);
  ps4ClickRef.current = onPs4Click;
  const ps4CheckCaptureRef = useRef(ps4CheckCapture);
  ps4CheckCaptureRef.current = ps4CheckCapture;
  const methodRef = useRef(method);
  methodRef.current = method;
  const baseRef = useRef<TileLayer<OSM | XYZ> | null>(null);
  const cbersRef = useRef<TileLayer<XYZ> | null>(null);
  const rasterRef = useRef<TileLayer<XYZ> | null>(null);
  const dtmRef = useRef<TileLayer<XYZ> | null>(null);
  const polygonLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const pointLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const vLayerRef = useRef<VectorLayer<VectorSource> | null>(null);
  const [pb1ColorVisible,setPb1ColorVisible] = useState(true);
  const [pb1DtmVisible,setPb1DtmVisible] = useState(false);
  const [pb1ColorOpacity,setPb1ColorOpacity] = useState(1);
  const [pb1DtmOpacity,setPb1DtmOpacity] = useState(0.6);
  const [pb1PerimeterVisible,setPb1PerimeterVisible] = useState(true);
  const [pb1GnssVisible,setPb1GnssVisible] = useState(true);
  const [pb1VerticesVisible,setPb1VerticesVisible] = useState(true);
  const rasterReadyRef = useRef(false);
  const footprintRef = useRef<Geometry | null>(null);
  const [cbersEnabled, setCbersEnabled] = useState(false);
  const [cbersOpacity, setCbersOpacity] = useState(0.8);
  const cbersActiveRef = useRef(false);
  const [ps4MapWarning, setPs4MapWarning] = useState("");
  const [rasterMapStatus, setRasterMapStatus] = useState("Ortoimagem não carregada.");
  const [cbersError, setCbersError] = useState("");
  const [basemap, setBasemap] = useState<"osm" | "esri" | "google" | "mapbox">("esri");
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [mapboxEnabled, setMapboxEnabled] = useState(false);
  const [baseError, setBaseError] = useState("");
  const [googleAttribution, setGoogleAttribution] = useState("");
  const lastFitKey = useRef("");
  const hintRef = useRef(onPositionHint);
  hintRef.current = onPositionHint;
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const stateKey = JSON.stringify([points, selected, intersection, method, hint, supportLineMode, chainMode, overlayLines, overlayPoints]);
  const lastPolygonFitRef = useRef("");

  useEffect(() => {
    if (!container.current) return;
    const source = sourceRef.current;
    const base = new TileLayer<OSM | XYZ>({ source: new OSM() });
    baseRef.current = base;
    const cbersLayer = new TileLayer({
      visible: false, opacity: 0.8,
      source: new XYZ({
        url: getApiUrl() + "/inpe-cbers/tiles/CBERS4A_WPM_PCA_RGB321_20261016_214_113/{z}/{x}/{y}.png",
        crossOrigin: "use-credentials", minZoom: 10, maxZoom: 18,
        attributions: "INPE / Brazil Data Cube · CBERS-4A WPM · 16/10/2026",
      }),
    });
    cbersRef.current = cbersLayer;
    const rasterLayer = new TileLayer<XYZ>({
      visible: false, opacity: 1,
      source: new XYZ({
        url: "/__ps4_unconfigured__/{z}/{x}/{y}.png",
        crossOrigin: "use-credentials",
        minZoom: 0, maxZoom: 19,
      }),
    });
    rasterRef.current = rasterLayer;
    const dtmLayer = new TileLayer<XYZ>({
      visible:false, opacity:0.6,
      source:new XYZ({url:"/__pb1_dtm_unconfigured__/{z}/{x}/{y}.png",
        crossOrigin:"use-credentials",minZoom:0,maxZoom:19}),
    });
    dtmRef.current = dtmLayer;
    const map = new Map({
      target: container.current,
      layers: [
        base,
        cbersLayer,
        rasterLayer,
        dtmLayer,
        new VectorLayer({
          source: polygonSourceRef.current,
          style: new Style({
            fill: new Fill({ color: "rgba(1, 130, 100, 0.12)" }),
            stroke: new Stroke({ color: "#01d4a0", width: 3 }),
          }),
        }),
        new VectorLayer({
          source: closureSourceRef.current,
          style: new Style({
            fill: new Fill({ color: "rgba(37,99,235,0.08)" }),
            stroke: new Stroke({ color: "#2563eb", width: 3, lineDash: [8, 5] }),
          }),
        }),
        new VectorLayer({
          declutter: true,
          source: ps4SourceRef.current,
          style: (feature) => new Style({
            stroke: new Stroke({ color: "#e11d48", width: 3 }),
            image: new CircleStyle({
              radius: 7, fill: new Fill({ color: "#fff1f2" }),
              stroke: new Stroke({ color: "#be123c", width: 2 }),
            }),
            text: new TextStyle({
              text: String(feature.get("label") || ""),
              offsetY: -19, font: "bold 12px sans-serif",
              fill: new Fill({ color: "#9f1239" }),
              stroke: new Stroke({ color: "#fff", width: 4 }),
            }),
          }),
        }),
        new VectorLayer({
          declutter: true,
          source,
          style: (feature) => {
            // Não permitir que a própria etiqueta GNSS seja o alvo de checagem.
            // Durante captura, somente os pixels da imagem permanecem visíveis.
            if (ps4CheckCaptureRef.current) return undefined;
            const isLine = feature.getGeometry() instanceof LineString;
            const isV = Boolean(feature.get("virtual"));
            const chosen = Boolean(feature.get("chosen"));
            const overlay = feature.get("overlay");
            return new Style({
              stroke: new Stroke({
                color: overlay === "computed" ? "#be123c" : overlay === "chain" ? "#94a3b8" : isLine ? "#f97316" : "#0e7490",
                width: 3, lineDash: overlay === "computed" ? [8, 5] : undefined,
              }),
              image: new CircleStyle({
                radius: isV ? 9 : chosen ? 8 : 6,
                fill: new Fill({ color: isV ? "#f97316" : chosen ? "#0e7490" : "#ffffff" }),
                stroke: new Stroke({ color: "#064e3b", width: 2 }),
              }),
              text: new TextStyle({
                text: String(feature.get("label") || ""),
                offsetY: -18, font: "bold 12px sans-serif",
                fill: new Fill({ color: "#064e3b" }),
                stroke: new Stroke({ color: "#ffffff", width: 4 }),
              }),
            });
          },
        }),
      ],
      view: new View({ center: fromLonLat([-51, 0]), zoom: 8, maxZoom: 20 }),
      controls: [],
    });
    polygonLayerRef.current = map.getLayers().item(4) as VectorLayer<VectorSource>;
    vLayerRef.current = map.getLayers().item(6) as VectorLayer<VectorSource>;
    pointLayerRef.current = map.getLayers().item(7) as VectorLayer<VectorSource>;
    mapRef.current = map;
    const handler = (event: { pixel: number[]; coordinate: number[] }) => {
      if ((methodRef.current === "PS4" || methodRef.current === "PB1" || methodRef.current === "PS1") && ps4ClickRef.current) {
        const [longitude, latitude] = toLonLat(event.coordinate);
        // Vetorização provisória pode usar o recorte próprio ou a cena INPE.
        // O PDF do RT continua obrigatório para aprovação, não para desenhar.
        // Para PB1, o pixel precisa vir exclusivamente do ORIXP RGB,
        // mesmo que a camada cinza seja exibida por cima.
        if(methodRef.current==="PB1"){
          // The server samples the mandatory numeric MDT and rejects NoData.
          // Without attached RGB, positioning remains a provisional visual trace.
          if(Number.isFinite(longitude)&&Number.isFinite(latitude)){
            setPs4MapWarning("");
            ps4ClickRef.current({longitude,latitude});
          }
          return;
        }
        const privateRasterVisible = Boolean(rasterRef.current?.getVisible());
        const imageLayer = methodRef.current === "PS1"
          ? rasterRef.current : privateRasterVisible ? rasterRef.current : cbersRef.current;
        const pixel = imageLayer?.getData(event.pixel);
        const alpha = pixel
          ? ("getUint8" in pixel ? pixel.getUint8(3) : pixel[3])
          : 0;
        if (methodRef.current === "PS1" && !imageLayer?.getVisible()) {
          setPs4MapWarning("Ative o ortomosaico PS1 para marcar o próximo V.");
        } else if (!pixel || typeof alpha !== "number" || alpha <= 0) {
          setPs4MapWarning(methodRef.current === "PS1"
            ? "Sem pixel RGB válido nesta posição. Confira a cobertura do ortomosaico, o carregamento do tile e o zoom."
            : "Aguarde carregar um pixel válido da imagem visível antes de marcar V provisório.");
        } else if (privateRasterVisible && (!rasterReadyRef.current || !footprintRef.current)) {
          setPs4MapWarning("Importe e carregue o GeoTIFF da peça antes de marcar V; imagens externas não são evidência PS4.");
        } else if (privateRasterVisible && !footprintRef.current!.intersectsCoordinate(event.coordinate)) {
          setPs4MapWarning("Fora da cobertura da ortoimagem anexada. Nenhum vértice criado.");
        } else if (Number.isFinite(longitude) && Number.isFinite(latitude)) {
          setPs4MapWarning("");
          ps4ClickRef.current({ longitude, latitude });
        }
        return;
      }
      const feature = map.forEachFeatureAtPixel(event.pixel, (candidate) =>
        typeof candidate.get("pointName") === "string" ? candidate : undefined, {
        hitTolerance: 12,
      });
      if (feature && typeof feature.get("pointName") === "string") {
        pickRef.current(feature.get("pointName") as string);
      } else if (hintRef.current) {
        const [longitude, latitude] = toLonLat(event.coordinate);
        hintRef.current({ longitude, latitude });
      }
    };
    map.on("singleclick", handler);
    return () => {
      map.un("singleclick", handler);
      map.setTarget(undefined);
      mapRef.current = null;
      baseRef.current = null;
      cbersRef.current = null;
      rasterRef.current = null;
      dtmRef.current = null;
      polygonLayerRef.current = null;
      pointLayerRef.current = null;
      vLayerRef.current = null;
      rasterReadyRef.current = false;
      footprintRef.current = null;
      source.clear();
      polygonSourceRef.current.clear();
      ps4SourceRef.current.clear();
      closureSourceRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const source = polygonSourceRef.current;
    source.clear();
    if (polygonGeometry) {
      try {
        source.addFeatures(new GeoJSON().readFeatures(polygonGeometry, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        }));
      } catch {
        // Invalid geometry stays unavailable; do not relocate the map to an unrelated place.
      }
    }
    const map = mapRef.current;
    const extent = source.getExtent();
    if (map && source.getFeatures().length && extent.every(Number.isFinite)
        && lastPolygonFitRef.current !== polygonKey) {
      lastPolygonFitRef.current = polygonKey;
      map.updateSize();
      map.getView().fit(extent, {
        size: map.getSize(), padding: [70, 70, 70, 70],
        maxZoom: 18, duration: 200,
      });
    }
  }, [polygonKey, polygonGeometry]);

  useEffect(() => {
    const source = sourceRef.current;
    source.clear();
    const positions = new globalThis.Map<string, number[]>();
    for (const point of points) {
      if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) continue;
      const coordinate = fromLonLat([point.longitude as number, point.latitude as number]);
      positions.set(point.name, coordinate);
      const feature = new Feature({ geometry: new Point(coordinate) });
      const order = chainMode ? selected.indexOf(point.name) : -1;
      feature.set("label", (order >= 0 ? (order + 1) + " · " : "") + (point.label || point.name));
      feature.set("pointName", point.name);
      feature.set("chosen", selected.includes(point.name));
      feature.set("virtual", Boolean(point.virtual));
      source.addFeature(feature);
    }
    if (chainMode) {
      const coords = selected.map(name => positions.get(name)).filter((c): c is number[] => Boolean(c));
      if (coords.length > 1) source.addFeature(new Feature({ geometry: new LineString(coords), label: "" }));
    }
    for (const line of overlayLines) {
      const coords = line.coords.filter(c => c.every(Number.isFinite)).map(c => fromLonLat(c));
      if (coords.length > 1) {
        const f = new Feature({ geometry: new LineString(coords), label: line.label });
        f.set("overlay", line.computed ? "computed" : "chain");
        source.addFeature(f);
      }
    }
    for (const point of overlayPoints) {
      if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) continue;
      const f = new Feature({ geometry: new Point(fromLonLat([point.longitude as number, point.latitude as number])) });
      f.set("label", point.name);
      f.set("virtual", true);
      source.addFeature(f);
    }
    for (let i = 0; !chainMode && i + 1 < selected.length &&
      i < (method === "PA2" && !supportLineMode ? 4 : 2); i += 2) {
      const a = positions.get(selected[i]);
      const b = positions.get(selected[i + 1]);
      if (a && b) source.addFeature(new Feature({
        geometry: new LineString([a, b]),
        label: i === 0 ? "Reta A" : "Reta B",
      }));
    }
    if (hint && Number.isFinite(hint.longitude) && Number.isFinite(hint.latitude)) {
      const marker = new Feature({ geometry: new Point(fromLonLat([hint.longitude, hint.latitude])) });
      marker.set("label", "Clique indicativo");
      marker.set("virtual", true);
      source.addFeature(marker);
    }
    if (intersection && Number.isFinite(intersection.longitude)
        && Number.isFinite(intersection.latitude)) {
      const point = new Feature({
        geometry: new Point(fromLonLat([
          intersection.longitude as number, intersection.latitude as number,
        ])),
      });
      point.set("label", method === "PT8" ? "P (pré-cálculo)" : "V (pré-cálculo)");
      point.set("virtual", true);
      source.addFeature(point);
    }
    const map = mapRef.current;
    const fitKey = JSON.stringify(points);
    if (map && positions.size && polygonSourceRef.current.getFeatures().length === 0
        && lastFitKey.current !== fitKey) {
      lastFitKey.current = fitKey;
      map.updateSize();
      const extent = source.getExtent();
      if (extent.every(Number.isFinite)) map.getView().fit(extent, {
        padding: [55, 50, 55, 50], maxZoom: 19, duration: 200,
      });
    }
  }, [stateKey]);

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetch(getApiUrl() + "/google-tiles/status", { credentials: "include" })
        .then(r => r.ok ? r.json() : { enabled: false }).catch(() => ({ enabled: false })),
      fetch(getApiUrl() + "/mapbox-satellite/status", { credentials: "include" })
        .then(r => r.ok ? r.json() : { enabled: false }).catch(() => ({ enabled: false })),
    ]).then(([google, mapbox]) => {
      if (!active) return;
      setGoogleEnabled(Boolean(google.enabled));
      setMapboxEnabled(Boolean(mapbox.enabled));
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setBaseError("");
    if (basemap === "google") {
      if (!googleEnabled) { setBaseError("Google Satélite não habilitado neste ambiente."); return; }
      void fetch(getApiUrl() + "/google-tiles/session", { credentials: "include" })
        .then(r => { if (!r.ok) throw new Error("Sessão Google indisponível"); return r.json(); })
        .then(() => {
          if (active) baseRef.current?.setSource(new XYZ({
            url: getApiUrl() + "/google-tiles/tiles/{z}/{x}/{y}",
            crossOrigin: "use-credentials", maxZoom: 20,
            attributions: "Google Maps",
          }));
        }).catch(e => { if (active) setBaseError(e instanceof Error ? e.message : "Falha Google"); });
    } else if (basemap === "mapbox") {
      if (!mapboxEnabled) { setBaseError("Mapbox Satélite não habilitado neste ambiente."); return; }
      baseRef.current?.setSource(new XYZ({
        url: getApiUrl() + "/mapbox-satellite/tiles/{z}/{x}/{y}",
        crossOrigin: "use-credentials", maxZoom: 20, attributions: "© Mapbox",
      }));
    } else if (basemap === "esri") {
      baseRef.current?.setSource(new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        crossOrigin: "anonymous", maxZoom: 19, attributions: "Esri World Imagery",
      }));
    } else baseRef.current?.setSource(new OSM({ maxZoom: 19 }));
    return () => { active = false; };
  }, [basemap, googleEnabled, mapboxEnabled]);

  useEffect(() => {
    if (basemap !== "google") { setGoogleAttribution(""); return; }
    const map = mapRef.current;
    if (!map) return;
    let active = true;
    const update = () => {
      const extent = map.getView().calculateExtent(map.getSize());
      const sw = toLonLat([extent[0], extent[1]]);
      const ne = toLonLat([extent[2], extent[3]]);
      if (!(sw[0] < ne[0] && sw[1] < ne[1])) return;
      const q = new URLSearchParams({
        south: String(sw[1]), north: String(ne[1]),
        west: String(sw[0]), east: String(ne[0]),
        zoom: String(Math.round(map.getView().getZoom() ?? 12)),
      });
      void fetch(getApiUrl() + "/google-tiles/attribution?" + q, { credentials: "include" })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (active) setGoogleAttribution(String(data?.copyright ?? "")); })
        .catch(() => { if (active) setGoogleAttribution("Créditos Google indisponíveis"); });
    };
    map.on("moveend", update); update();
    return () => { active = false; map.un("moveend", update); };
  }, [basemap]);

  const closureKey = JSON.stringify(ps4ClosureGeometry);
  useEffect(() => {
    const source = closureSourceRef.current;
    source.clear();
    if (!ps4ClosureGeometry) return;
    try {
      source.addFeatures(new GeoJSON().readFeatures(ps4ClosureGeometry, {
        dataProjection: "EPSG:4326",
        featureProjection: "EPSG:3857",
      }));
    } catch {
      setPs4MapWarning("Não foi possível visualizar a prévia de fechamento.");
    }
  }, [closureKey]);

  useEffect(() => {
    const source = ps4SourceRef.current;
    source.clear();
    for (const point of ps4Points) {
      if (!Number.isFinite(point.longitude) || !Number.isFinite(point.latitude)) continue;
      const feature = new Feature({
        geometry: new Point(fromLonLat([point.longitude, point.latitude])),
      });
      feature.set("label", point.name.replace(/^VIRTUAL-V-/i, "V-"));
      source.addFeature(feature);
    }
    if (ps4Candidate && Number.isFinite(ps4Candidate.longitude) && Number.isFinite(ps4Candidate.latitude)) {
      const f = new Feature({ geometry: new Point(fromLonLat([ps4Candidate.longitude, ps4Candidate.latitude])) });
      f.set("label", "V? confirmar");
      source.addFeature(f);
    }
    if (ps4Points.length > 1) {
      const coords = ps4Points.map(p => fromLonLat([p.longitude, p.latitude]));
      source.addFeature(new Feature({ geometry: new LineString(coords) }));
    }
  }, [JSON.stringify(ps4Points), ps4Candidate?.latitude, ps4Candidate?.longitude]);

  useEffect(() => {
    rasterReadyRef.current = false;
    footprintRef.current = null;
    const layer = rasterRef.current;
    layer?.setVisible(false);
    const raster = method === "PB1" ? pb1Raster : ps4Raster;
    if (!["PS4", "PB1", "PS1"].includes(method) || !raster?.pieceId || !raster?.sha256) {
      setRasterMapStatus("Ortoimagem privada não selecionada; digitalização PS4 bloqueada.");
      return;
    }
    const footprint = raster.footprint;
    if (!footprint) {
      setRasterMapStatus("GeoTIFF sem extensão WGS84; não é possível digitalizar.");
      return;
    }
    try {
      footprintRef.current = new GeoJSON().readGeometry(footprint, {
        dataProjection: "EPSG:4326", featureProjection: "EPSG:3857",
      });
    } catch {
      setRasterMapStatus("Extensão geográfica do GeoTIFF inválida.");
      return;
    }
    if (!layer) return;
    const source = new XYZ({
      url: getApiUrl() + "/technical-pieces/" + raster.pieceId +
        (method === "PS1" ? "/ps1/raster/tiles/" : method === "PB1" ? "/pb1/raster/tiles/pb1_color/" : "/ps4/raster/tiles/") + raster.sha256 + "/{z}/{x}/{y}.png",
      crossOrigin: "use-credentials",
      minZoom: 0, maxZoom: 19,
      attributions: (method === "PS1" ? "Ortomosaico PS1" : method === "PB1" ? "Base cartográfica PB1 · RGB" : "Ortoimagem PS4") + " · SHA256 " + raster.sha256.slice(0, 12),
    });
    const loaded = () => {
      rasterReadyRef.current = true;
      setRasterMapStatus("Ortoimagem da peça renderizada. Digitalize apenas feições identificáveis.");
    };
    const failed = () => {
      rasterReadyRef.current = false;
      setRasterMapStatus("Falha ao carregar o tile GeoTIFF; marcação PS4 suspensa.");
    };
    source.on("tileloadend", loaded);
    source.on("tileloaderror", failed);
    layer.setSource(source);
    layer.setVisible(true);
    setRasterMapStatus("Carregando raster georreferenciado no mapa...");
    return () => {
      source.un("tileloadend", loaded);
      source.un("tileloaderror", failed);
      rasterReadyRef.current = false;
      footprintRef.current = null;
      layer.setVisible(false);
    };
  }, [method, ps4Raster?.pieceId, ps4Raster?.sha256, pb1Raster?.pieceId, pb1Raster?.sha256]);

  useEffect(() => {
    const layer = dtmRef.current;
    layer?.setVisible(false);
    if(method !== "PB1" || !pb1Dtm?.pieceId || !pb1Dtm.sha256 || !layer)return;
    const source = new XYZ({
      url:getApiUrl()+"/technical-pieces/"+pb1Dtm.pieceId+
        "/pb1/raster/tiles/pb1_dtm/"+pb1Dtm.sha256+"/{z}/{x}/{y}.png",
      crossOrigin:"use-credentials", minZoom:0,maxZoom:19,
      attributions:"PB1 · MDT original cinza · "+pb1Dtm.sha256.slice(0,12),
    });
    layer.setSource(source);
    layer.setVisible(pb1DtmVisible);
    return ()=>{layer.setVisible(false);};
  },[method,pb1Dtm?.pieceId,pb1Dtm?.sha256]);

  useEffect(()=>{
    if(method!=="PB1"){
      polygonLayerRef.current?.setVisible(true);
      pointLayerRef.current?.setVisible(true);
      vLayerRef.current?.setVisible(true);
      dtmRef.current?.setVisible(false);
      return;
    }
    rasterRef.current?.setVisible(Boolean(pb1Raster)&&pb1ColorVisible);
    rasterRef.current?.setOpacity(pb1ColorOpacity);
    dtmRef.current?.setVisible(Boolean(pb1Dtm)&&pb1DtmVisible);
    dtmRef.current?.setOpacity(pb1DtmOpacity);
    polygonLayerRef.current?.setVisible(pb1PerimeterVisible);
    pointLayerRef.current?.setVisible(pb1GnssVisible);
    vLayerRef.current?.setVisible(pb1VerticesVisible);
  },[method,pb1Raster?.sha256,pb1Dtm?.sha256,pb1ColorVisible,pb1DtmVisible,
     pb1ColorOpacity,pb1DtmOpacity,pb1PerimeterVisible,pb1GnssVisible,pb1VerticesVisible]);

  useEffect(() => {
    if (method === "PS4" || method === "PB1" || method === "PS1") setCbersEnabled(false);
    else setPs4MapWarning("");
  }, [method, ps4Raster?.sha256]);

  useEffect(() => {
    if (!/^CBERS4A_WPM_PCA_RGB321_2026(?:1016|0815|0715)_214_113$/.test(ps4SceneId)) {
      setCbersError("Cena não disponibilizada no renderizador GEO98.");
      cbersRef.current?.setVisible(false);
      return;
    }
    cbersRef.current?.setSource(new XYZ({
      url: getApiUrl() + "/inpe-cbers/tiles/" + ps4SceneId + "/{z}/{x}/{y}.png",
      crossOrigin:"use-credentials",minZoom:10,maxZoom:18,
      attributions:"INPE / Brazil Data Cube · CBERS-4A WPM · " + ps4SceneId.split("_")[4],
    }));
  }, [ps4SceneId]);

  useEffect(() => {
    cbersActiveRef.current = cbersEnabled;
    const previewSupported = /^CBERS4A_WPM_PCA_RGB321_2026(?:1016|0815|0715)_214_113$/.test(ps4SceneId);
    const showPreview = cbersEnabled && previewSupported;
    cbersRef.current?.setVisible(showPreview);
    // Nunca esconder o recorte privado se a cena auxiliar não possuir tiles.
    rasterRef.current?.setVisible(Boolean(method === "PB1" ? pb1Raster&&pb1ColorVisible : ps4Raster) && !showPreview);
    cbersRef.current?.setOpacity(cbersOpacity);
    if (cbersEnabled) setCbersError(previewSupported
      ? "Cena INPE auxiliar selecionada; acurácia PS4 ainda não comprovada."
      : "Esta cena não possui tiles RGB auxiliares nesta versão. Exibindo o GeoTIFF privado, se disponível.");
    else setCbersError("");
  }, [cbersEnabled, cbersOpacity, ps4SceneId, ps4Raster?.sha256, pb1Raster?.sha256, method,pb1ColorVisible]);

  useEffect(() => {
    sourceRef.current.changed();
  }, [ps4CheckCapture]);

  const changeZoom = (delta: number) => {
    const map = mapRef.current;
    if (map) map.getView().setZoom(Math.min(21, Math.max(2, (map.getView().getZoom() ?? 12) + delta)));
  };

  return <div>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
      <label>Base cartográfica: <select value={basemap}
        onChange={event => setBasemap(event.target.value as typeof basemap)}>
        <option value="esri">Esri World Imagery</option>
        <option value="osm">OpenStreetMap</option>
        <option value="google" disabled={!googleEnabled}>Google Satélite</option>
        <option value="mapbox" disabled={!mapboxEnabled}>Mapbox Satélite</option>
      </select></label>
      {method === "PB1" && <span style={{fontSize:12,fontWeight:700,color:"#18543f"}}>
        {pb1Raster ? "ORIXP oficial privado · SHA-256 " + pb1Raster.sha256.slice(0,12) + "…"
          : "ORIXP RGB facultativo. Sem RGB, o traçado é provisório e depende de comprovação da fonte planimétrica."}
      </span>}
      {method === "PS4" && <span style={{fontSize:12,fontWeight:700,color:"#18543f"}}>
        {ps4Raster ? "GeoTIFF real vinculado à peça · SHA-256 " + ps4Raster.sha256.slice(0,12) + "…"
          : "Nenhuma imagem orbital privada disponível — importe uma cena na etapa 1."}
      </span>}
      <button type="button" onClick={() => {
        const map = mapRef.current;
        if (!map) return;
        const poly = polygonSourceRef.current;
        const vertices = sourceRef.current;
        const extent = poly.getFeatures().length ? poly.getExtent() : vertices.getExtent();
        if (extent.every(Number.isFinite)) {
          map.updateSize();
          map.getView().fit(extent, { size: map.getSize(), padding: [70, 70, 70, 70], maxZoom: 18 });
        }
      }}>Enquadrar poligonal</button>
      <button type="button" onClick={() => changeZoom(1)}>Zoom +</button>
      <button type="button" onClick={() => changeZoom(-1)}>Zoom −</button>
    </div>
    {method === "PB1" && <section aria-label="Camadas PB1" style={{
      display:"grid",gap:10,padding:12,margin:"8px 0",border:"1px solid #cbd5d1",
      borderRadius:10,background:"#f5faf7"
    }}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:8}}>
        <strong style={{fontSize:13}}>Camadas PB1 · visualização simultânea</strong>
        {pb1Raster && <button type="button" onClick={()=>{
          setPb1ColorVisible(true);
          setPs4MapWarning("");
        }} style={{padding:"7px 10px",borderRadius:7,background:"#095b47",color:"white",fontWeight:700}}>
          {pb1ColorVisible ? "Marcar próximo V no ORIXP" : "Reativar ORIXP e marcar próximo V"}
        </button>}
      </div>
      {!pb1ColorVisible && pb1Raster && <p role="alert" style={{
        margin:0,padding:"9px 10px",border:"1px solid #e8b59f",
        borderRadius:8,background:"#fff4ee",color:"#873d20",fontWeight:700,fontSize:12
      }}>A camada ORIXP está desativada. O traçado permanece preliminar e a cota será amostrada no MDT.</p>}
      <div style={{display:"flex",flexWrap:"wrap",gap:"10px 18px"}}>
        <label><input type="checkbox" checked={pb1ColorVisible} onChange={e=>setPb1ColorVisible(e.target.checked)}
          disabled={!pb1Raster}/> ORIXP Color</label>
        <label><input type="checkbox" checked={pb1DtmVisible} onChange={e=>setPb1DtmVisible(e.target.checked)}
          disabled={!pb1Dtm}/> MDT cinza</label>
        <label><input type="checkbox" checked={pb1PerimeterVisible} onChange={e=>setPb1PerimeterVisible(e.target.checked)}/> Perímetro</label>
        <label><input type="checkbox" checked={pb1GnssVisible} onChange={e=>setPb1GnssVisible(e.target.checked)}/> Marcos GNSS</label>
        <label><input type="checkbox" checked={pb1VerticesVisible} onChange={e=>setPb1VerticesVisible(e.target.checked)}/> Vértices V</label>
      </div>
      <div style={{display:"flex",gap:18,flexWrap:"wrap"}}>
        <label style={{fontSize:12}}>Opacidade ORIXP {Math.round(pb1ColorOpacity*100)}%
          <input type="range" min="0" max="100" step="5" value={Math.round(pb1ColorOpacity*100)}
            onChange={e=>setPb1ColorOpacity(Number(e.target.value)/100)} disabled={!pb1Raster}/>
        </label>
        <label style={{fontSize:12}}>Opacidade MDT {Math.round(pb1DtmOpacity*100)}%
          <input type="range" min="0" max="100" step="5" value={Math.round(pb1DtmOpacity*100)}
            onChange={e=>setPb1DtmOpacity(Number(e.target.value)/100)} disabled={!pb1Dtm}/>
        </label>
      </div>
      <small>O MDT numérico é exibido com contraste cinza e NoData transparente.
        A cota numérica válida no MDT é obrigatória. A imagem de fundo não comprova exatidão PB1.</small>
    </section>}
    {method === "PS4" && ps4CheckCapture && <p role="status" style={{background:"#fff3cf",color:"#7c4c06",padding:"9px 12px",borderRadius:8,fontWeight:750,fontSize:12}}>
      Modo checagem: marcadores GNSS temporariamente ocultos. Clique na feição real identificável na imagem, não na posição presumida do marco.
    </p>}
    <div ref={container} style={{ height: "min(68vh, 700px)", minHeight: 390, width: "100%", borderRadius: 9,
      border: "1px solid #9ca3af", overflow: "hidden" }} aria-label={method === "PS4" ? "Mapa de restituição experimental de vértices PS4" : "Mapa de construção de vértices"} />
    {baseError && <p role="status">{baseError}</p>}
    {cbersError && <p role="status" style={{ fontSize: 12 }}>{cbersError}</p>}
    {(method === "PS4" || method === "PB1" || method === "PS1") && <p role="status" style={{ fontSize: 12, fontWeight: 700 }}>{rasterMapStatus}</p>}
    {ps4MapWarning && <p role="alert" style={{ fontSize: 12, color: "#9f1239" }}>{ps4MapWarning}</p>}
    {basemap === "google" && <p style={{ fontSize: 11 }}>Google Maps {googleAttribution}</p>}
    <p style={{ fontSize: 12, marginTop: 8 }}>
      {method === "PB1" ? "PB1: traçado preliminar com amostragem no MDT obrigatório. A fonte planimétrica e o datum vertical exigem revisão."
        : method === "PS4"
        ? "PS4: clique somente sobre a ortoimagem GeoTIFF anexada e coberta pelo relatório; os pontos permanecem preliminares até validação da precisão e do RT."
        : "Clique nos marcos para definir o alinhamento. Um clique no terreno indica posição aproximada, lado ou sentido; não é uma medição topográfica. Use o zoom para escolher visualmente o local."}
    </p>  </div>;
}
