"use client";

import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
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
  latitude: number | null;
  longitude: number | null;
};
type Props = {
  points: Pa2MapWitness[];
  selected: string[];
  intersection?: { latitude: number | null; longitude: number | null } | null;
  onPick: (name: string) => void;
  method?: "PA1" | "PA2" | "PT8";
  supportLineMode?: boolean;
  onPositionHint?: (point: { longitude: number; latitude: number }) => void;
  hint?: { longitude: number; latitude: number } | null;
};

/** Mapa de apoio PA2: clique nos dois testemunhos de cada alinhamento. */
export function Pa2WitnessMap({ points, selected, intersection, onPick,
  method = "PA2", supportLineMode = false, onPositionHint, hint }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef(new VectorSource());
  const baseRef = useRef<TileLayer<OSM | XYZ> | null>(null);
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

  useEffect(() => {
    if (!container.current) return;
    const source = sourceRef.current;
    const base = new TileLayer<OSM | XYZ>({ source: new OSM() });
    baseRef.current = base;
    const map = new Map({
      target: container.current,
      layers: [
        base,
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
      source.clear();
    };
  }, []);

  useEffect(() => {
    const source = sourceRef.current;
    source.clear();
    const positions = new globalThis.Map<string, number[]>();
    for (const point of points) {
      if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) continue;
      const coordinate = fromLonLat([point.longitude as number, point.latitude as number]);
      positions.set(point.name, coordinate);
      const feature = new Feature({ geometry: new Point(coordinate) });
      feature.set("label", point.name);
      feature.set("pointName", point.name);
      feature.set("chosen", selected.includes(point.name));
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
    if (map && positions.size && lastFitKey.current !== fitKey) {
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
      <button type="button" onClick={() => changeZoom(1)}>Zoom +</button>
      <button type="button" onClick={() => changeZoom(-1)}>Zoom −</button>
    </div>
    <div ref={container} style={{ height: "min(68vh, 700px)", minHeight: 390, width: "100%", borderRadius: 9,
      border: "1px solid #9ca3af", overflow: "hidden" }} aria-label="Mapa de apoio à interseção de retas PA2" />
    {baseError && <p role="status">{baseError}</p>}
    {basemap === "google" && <p style={{ fontSize: 11 }}>Google Maps {googleAttribution}</p>}
    <p style={{ fontSize: 12, marginTop: 8 }}>
      Clique nos marcos para definir o alinhamento. Um clique no terreno indica
      posição aproximada, lado ou sentido; não é uma medição topográfica.
      Use o zoom para escolher visualmente o local.
    </p>
  </div>;
}
