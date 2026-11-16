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
  method?: "PA1" | "PA2" | "PT8" | "PS4";
  ps4Points?: Array<{ name: string; latitude: number; longitude: number }>;
  ps4Candidate?: { latitude: number; longitude: number } | null;
  ps4ClosureGeometry?: { type: "Polygon"; coordinates: number[][][] } | null;
  onPs4Click?: (point: { longitude: number; latitude: number }) => void;
  supportLineMode?: boolean;
  onPositionHint?: (point: { longitude: number; latitude: number }) => void;
  hint?: { longitude: number; latitude: number } | null;
  polygonGeometry?: Record<string, unknown> | null;
  polygonKey?: string;
  ps4SceneId?: string;
  ps4Raster?: {
    pieceId: string; sha256: string;
    footprint?: { type: string; coordinates: number[][][] };
  } | null;
};

/** Mapa de apoio PA2: clique nos dois testemunhos de cada alinhamento. */
export function Pa2WitnessMap({ points, selected, intersection, onPick,
  method = "PA2", supportLineMode = false, onPositionHint, hint,
  polygonGeometry, polygonKey = "", ps4Points = [], ps4Candidate,
  ps4ClosureGeometry, onPs4Click, ps4Raster = null,
  ps4SceneId = "CBERS4A_WPM_PCA_RGB321_20261016_214_113" }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef(new VectorSource());
  const polygonSourceRef = useRef(new VectorSource());
  const ps4SourceRef = useRef(new VectorSource());
  const closureSourceRef = useRef(new VectorSource());
  const ps4ClickRef = useRef(onPs4Click);
  ps4ClickRef.current = onPs4Click;
  const methodRef = useRef(method);
  methodRef.current = method;
  const baseRef = useRef<TileLayer<OSM | XYZ> | null>(null);
  const cbersRef = useRef<TileLayer<XYZ> | null>(null);
  const rasterRef = useRef<TileLayer<XYZ> | null>(null);
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
  const stateKey = JSON.stringify([points, selected, intersection, method, hint, supportLineMode]);
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
      visible: false, opacity: 1, zIndex: 3,
      source: new XYZ({
        url: "/__ps4_unconfigured__/{z}/{x}/{y}.png",
        crossOrigin: "use-credentials",
        minZoom: 0, maxZoom: 19,
      }),
    });
    rasterRef.current = rasterLayer;
    const map = new Map({
      target: container.current,
      layers: [
        base,
        cbersLayer,
        rasterLayer,
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
          source,
          style: (feature) => {
            const isLine = feature.getGeometry() instanceof LineString;
            const isV = Boolean(feature.get("virtual"));
            const chosen = Boolean(feature.get("chosen"));
            return new Style({
              stroke: new Stroke({ color: isLine ? "#f97316" : "#0e7490", width: 3 }),
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
    mapRef.current = map;
    const handler = (event: { pixel: number[]; coordinate: number[] }) => {
      if (methodRef.current === "PS4" && ps4ClickRef.current) {
        const [longitude, latitude] = toLonLat(event.coordinate);
        if (!rasterReadyRef.current || !footprintRef.current) {
          setPs4MapWarning("Importe e carregue o GeoTIFF da peça antes de marcar V; imagens externas não são evidência PS4.");
        } else if (!footprintRef.current.intersectsCoordinate(event.coordinate)) {
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
      feature.set("label", point.label || point.name);
      feature.set("pointName", point.name);
      feature.set("chosen", selected.includes(point.name));
      feature.set("virtual", Boolean(point.virtual));
      source.addFeature(feature);
    }
    for (let i = 0; i + 1 < selected.length &&
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
      feature.set("label", point.name);
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
    if (method !== "PS4" || !ps4Raster?.pieceId || !ps4Raster?.sha256) {
      setRasterMapStatus("Ortoimagem privada não selecionada; digitalização PS4 bloqueada.");
      return;
    }
    const footprint = ps4Raster.footprint;
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
      url: getApiUrl() + "/technical-pieces/" + ps4Raster.pieceId +
        "/ps4/raster/tiles/" + ps4Raster.sha256 + "/{z}/{x}/{y}.png",
      crossOrigin: "use-credentials",
      minZoom: 0, maxZoom: 19,
      attributions: "Ortoimagem GeoTIFF anexada à peça — SHA256 " + ps4Raster.sha256.slice(0, 12),
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
  }, [method, ps4Raster?.pieceId, ps4Raster?.sha256]);

  useEffect(() => {
    if (method === "PS4") setCbersEnabled(!ps4Raster);
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
    cbersRef.current?.setVisible(cbersEnabled && !ps4Raster);
    cbersRef.current?.setOpacity(cbersOpacity);
    if (cbersEnabled) setCbersError("Cena selecionada " + ps4SceneId + " · PS4 experimental sem acurácia demonstrada.");
    else setCbersError("");
  }, [cbersEnabled, cbersOpacity, ps4SceneId, ps4Raster?.sha256]);

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
      <label style={{ display: "flex", alignItems: "center", gap: 5 }}>
        <input type="checkbox" checked={cbersEnabled} disabled={method === "PS4" && Boolean(ps4Raster)} onChange={e => setCbersEnabled(e.target.checked)} />
        CBERS-4A INPE (experimental)
      </label>
      {cbersEnabled && <label>Transparência CBERS-4A:
        <input aria-label="Opacidade da imagem CBERS-4A" type="range" min="0.2" max="1" step="0.1"
          value={cbersOpacity} onChange={e => setCbersOpacity(Number(e.target.value))} />
      </label>}
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
    <div ref={container} style={{ height: "min(68vh, 700px)", minHeight: 390, width: "100%", borderRadius: 9,
      border: "1px solid #9ca3af", overflow: "hidden" }} aria-label={method === "PS4" ? "Mapa de restituição experimental de vértices PS4" : "Mapa de construção de vértices"} />
    {baseError && <p role="status">{baseError}</p>}
    {cbersError && <p role="status" style={{ fontSize: 12 }}>{cbersError}</p>}
    {method === "PS4" && <p role="status" style={{ fontSize: 12, fontWeight: 700 }}>{rasterMapStatus}</p>}
    {ps4MapWarning && <p role="alert" style={{ fontSize: 12, color: "#9f1239" }}>{ps4MapWarning}</p>}
    {basemap === "google" && <p style={{ fontSize: 11 }}>Google Maps {googleAttribution}</p>}
    <p style={{ fontSize: 12, marginTop: 8 }}>
      {method === "PS4"
        ? "PS4: clique somente sobre a ortoimagem GeoTIFF anexada e coberta pelo relatório; os pontos permanecem preliminares até validação da precisão e do RT."
        : "Clique nos marcos para definir o alinhamento. Um clique no terreno indica posição aproximada, lado ou sentido; não é uma medição topográfica. Use o zoom para escolher visualmente o local."}
    </p>  </div>;
}
