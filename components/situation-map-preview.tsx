"use client";

import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import GeoJSON from "ol/format/GeoJSON";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import Polygon from "ol/geom/Polygon";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import { Fill, Stroke, Style, Circle as CircleStyle, Text as TextStyle } from "ol/style";
import { toLonLat } from "ol/proj";
import { getApiUrl } from "@/lib/api";

export type SituationSnapshot = {
  raster_b64: string;
  raster_source: string;
  geometry_key: string;
  token: number;
  center: number[];
  zoom: number;
  basemap: "osm" | "satellite";
};

type Props = {
  geometry: Record<string, unknown>;
  geometryKey: string;
  saved: SituationSnapshot | null;
  onSave: (snapshot: SituationSnapshot) => void;
  vertexNames?: string[][];
  showVertices?: boolean;
};

const polygonStyle = new Style({
  fill: new Fill({ color: "rgba(0, 114, 77, 0.22)" }),
  stroke: new Stroke({ color: "#00b782", width: 3 }),
});

export function SituationMapPreview({ geometry, geometryKey, saved, onSave, vertexNames = [], showVertices = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const baseRef = useRef<TileLayer<OSM | XYZ> | null>(null);
  const vertexSourceRef = useRef(new VectorSource());
  const vertexNamesKey = JSON.stringify(vertexNames);
  const [basemap, setBasemap] = useState<"osm" | "satellite" | "google">(saved?.basemap ?? "satellite");
  const [busy, setBusy] = useState(false);
  const [googleAvailable, setGoogleAvailable] = useState(false);
  const [copyright, setCopyright] = useState("");
  const [googleError, setGoogleError] = useState("");
  const [licenseConfirmed, setLicenseConfirmed] = useState(false);
  const [licenseReference, setLicenseReference] = useState("");

  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    void fetch(`${getApiUrl()}/google-tiles/status`, { credentials: "include" })
      .then((r) => r.ok ? r.json() : { enabled: false })
      .then((data) => { if (active) setGoogleAvailable(Boolean(data.enabled)); })
      .catch(() => { if (active) setGoogleAvailable(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (basemap !== "google") { setCopyright(""); return; }
    const map = mapRef.current;
    if (!map) return;
    let active = true;
    let pending: AbortController | null = null;
    const update = () => {
      const size = map.getSize();
      if (!size) return;
      const extent = map.getView().calculateExtent(size);
      const sw = toLonLat([extent[0], extent[1]]);
      const ne = toLonLat([extent[2], extent[3]]);
      const south = Math.max(-89.999, Math.min(89.999, sw[1]));
      const north = Math.max(-89.999, Math.min(89.999, ne[1]));
      const west = Math.max(-179.999, Math.min(179.999, sw[0]));
      const east = Math.max(-179.999, Math.min(179.999, ne[0]));
      if (!(south < north && west < east)) return;
      pending?.abort();
      pending = new AbortController();
      const q = new URLSearchParams({
        south: String(south), north: String(north),
        west: String(west), east: String(east),
        zoom: String(Math.max(0, Math.min(22, Math.round(map.getView().getZoom() ?? 0)))),
      });
      void fetch(`${getApiUrl()}/google-tiles/attribution?${q}`, {
        credentials: "include", signal: pending.signal,
      }).then((r) => {
        if (!r.ok) throw new Error("Créditos indisponíveis");
        return r.json();
      }).then((data) => { if (active) setCopyright(String(data.copyright ?? "")); })
        .catch((err) => {
          if (active && err?.name !== "AbortError") setCopyright("Créditos indisponíveis");
        });
    };
    map.on("moveend", update);
    update();
    return () => { active = false; pending?.abort(); map.un("moveend", update); };
  }, [basemap, geometryKey]);

  const geoKeyRef = useRef(geometryKey);
  geoKeyRef.current = geometryKey;
  const saveRef = useRef(onSave);
  saveRef.current = onSave;

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const features = new GeoJSON().readFeatures(geometry, {
      dataProjection: "EPSG:4326",
      featureProjection: "EPSG:3857",
    });
    const source = new VectorSource({ features });
    const base = new TileLayer({
      source: new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        crossOrigin: "anonymous", maxZoom: 19,
      }),
    });
    baseRef.current = base;
    const extent = source.getExtent();
    const valid = extent.every(Number.isFinite);
    const midpoint = valid
      ? [(extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2]
      : [0, 0];
    const useSaved = saved?.geometry_key === geometryKey;
    const map = new Map({
      target: container.current,
      layers: [
        base, new VectorLayer({ source, style: polygonStyle }),
        new VectorLayer({
          source: vertexSourceRef.current,
          style: (feature) => new Style({
            image: new CircleStyle({
              radius: 4, fill: new Fill({ color: "#fff" }),
              stroke: new Stroke({ color: "#087c50", width: 2 }),
            }),
            text: new TextStyle({
              text: String(feature.get("label") ?? ""), offsetY: -13,
              font: "700 11px sans-serif",
              fill: new Fill({ color: "#0a5137" }),
              stroke: new Stroke({ color: "#fff", width: 3 }),
            }),
          }),
        }),
      ],
      view: new View({
        center: useSaved && saved ? saved.center : midpoint,
        zoom: useSaved && saved ? saved.zoom : 12,
        maxZoom: 19,
      }),
      controls: [],
    });
    mapRef.current = map;
    requestAnimationFrame(() => {
      if (mapRef.current !== map) return;
      map.updateSize();
      if (!useSaved && valid) map.getView().fit(extent, {
        size: map.getSize(), padding: [50, 50, 50, 50],
        maxZoom: 17, duration: 0,
      });
    });
    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
      baseRef.current = null;
    };
    // Reconstrói o mapa ao alterar as geometrias; usa a captura anterior
    // apenas se o identificador geométrico ainda for o mesmo.
  }, [geometryKey]);

  useEffect(() => {
    if (basemap === "google") {
      if (!googleAvailable) {
        setGoogleError("Google Satélite não está habilitado nesta API.");
        return;
      }
      let active = true;
      setGoogleError("");
      void fetch(`${getApiUrl()}/google-tiles/session`, { credentials: "include" })
        .then((r) => { if (!r.ok) throw new Error("Sessão Google indisponível"); return r.json(); })
        .then(() => {
          if (!active) return;
          baseRef.current?.setSource(new XYZ({
            url: `${getApiUrl()}/google-tiles/tiles/{z}/{x}/{y}`,
            crossOrigin: "use-credentials", maxZoom: 20,
            attributions: "Google Maps",
          }));
        })
        .catch((e) => { if (active) setGoogleError(e instanceof Error ? e.message : "Falha Google"); });
      return () => { active = false; };
    }
    const source = basemap === "satellite"
      ? new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        crossOrigin: "anonymous", maxZoom: 19,
      })
      : new OSM({ maxZoom: 19, crossOrigin: "anonymous" });
    baseRef.current?.setSource(source);
  }, [basemap, geometryKey, googleAvailable]);

  useEffect(() => {
    const labelsSource = vertexSourceRef.current;
    labelsSource.clear();
    if (!showVertices) return;
    const features = new GeoJSON().readFeatures(geometry, {
      dataProjection: "EPSG:4326", featureProjection: "EPSG:3857",
    });
    for (const [polygonIndex, feature] of features.entries()) {
      const shape = feature.getGeometry();
      if (!(shape instanceof Polygon)) continue;
      for (const [index, coordinate] of (shape.getCoordinates()[0] ?? []).slice(0, -1).entries()) {
        labelsSource.addFeature(new Feature({
          geometry: new Point(coordinate),
          label: vertexNames[polygonIndex]?.[index] ?? `V${index+1}`,
        }));
      }
    }
  }, [geometryKey, vertexNamesKey, showVertices]);

  const fit = () => {
    const map = mapRef.current;
    if (!map) return;
    const layers = map.getLayers().getArray();
    const vector = layers.find((item) => item instanceof VectorLayer) as VectorLayer<VectorSource> | undefined;
    const extent = vector?.getSource()?.getExtent();
    if (extent?.every(Number.isFinite)) {
      map.updateSize();
      map.getView().fit(extent, { size: map.getSize(), padding: [50, 50, 50, 50], maxZoom: 17 });
    }
  };

  const capture = async () => {
    if (!licenseConfirmed || !licenseReference.trim()) {
      setMessage("Informe a referência da licença e confirme o direito de reprodução no PDF antes da captura.");
      return;
    }
    if (basemap === "google") {
      setMessage("A base Google é somente para visualização. Selecione Esri ou OSM e registre o enquadramento para o PDF.");
      return;
    }
    const map = mapRef.current;
    if (!map) return;
    setBusy(true);
    setMessage("");
    try {
      const size = map.getSize();
      if (!size || !size[0] || !size[1]) throw new Error("Mapa de situação ainda não está pronto.");
      await new Promise<void>((resolve) => {
        let finished = false;
        const done = () => {
          if (finished) return;
          finished = true;
          map.un("rendercomplete", done);
          resolve();
        };
        map.once("rendercomplete", done);
        map.renderSync();
        window.setTimeout(done, 5000);
      });
      const result = document.createElement("canvas");
      // Recorte 4:3, igual ao quadro da prancha, sem distorcer a imagem.
      const width = Math.min(1200, Math.max(600, size[0] * 2));
      const height = Math.round(width * 0.75);
      result.width = width; result.height = height;
      const context = result.getContext("2d");
      if (!context) throw new Error("Canvas indisponível.");
      context.fillStyle = "#fff"; context.fillRect(0, 0, width, height);
      const cropWidth = Math.min(size[0], size[1] * 4 / 3);
      const cropHeight = cropWidth * 3 / 4;
      const cropX = (size[0] - cropWidth) / 2;
      const cropY = (size[1] - cropHeight) / 2;
      context.scale(width / cropWidth, height / cropHeight);
      context.translate(-cropX, -cropY);
      let layersRendered = 0;
      for (const canvas of map.getViewport().querySelectorAll<HTMLCanvasElement>(".ol-layer canvas, canvas.ol-layer")) {
        if (!canvas.width || !canvas.height) continue;
        context.save();
        const opacity = Number(canvas.parentElement?.style.opacity || "1");
        context.globalAlpha = Number.isFinite(opacity) ? opacity : 1;
        const matrix = canvas.style.transform.match(/^matrix\(([^)]+)\)$/);
        if (matrix) {
          const parts = matrix[1].split(",").map(Number);
          if (parts.length === 6 && parts.every(Number.isFinite))
            context.transform(...(parts as [number, number, number, number, number, number]));
        } else context.translate(canvas.offsetLeft, canvas.offsetTop);
        context.drawImage(canvas, 0, 0);
        context.restore();
        layersRendered++;
      }
      if (!layersRendered) throw new Error("O mapa ainda não renderizou as camadas.");
      const center = map.getView().getCenter();
      if (!center) throw new Error("Centro cartográfico indisponível.");
      saveRef.current({
        raster_b64: result.toDataURL("image/jpeg", 0.9).split(",")[1],
        raster_source: (basemap === "satellite" ? "Esri World Imagery" : "OpenStreetMap") + " | " + licenseReference.trim(),
        geometry_key: geoKeyRef.current, token: Date.now(),
        center: [...center], zoom: map.getView().getZoom() ?? 12,
        basemap: basemap === "osm" ? "osm" : "satellite",
      });
      setMessage("Enquadramento registrado para a Planta de Situação.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao capturar a planta de situação.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="pecas-situation-pane">
      <h3>Enquadramento da Planta de Situação</h3>
      <p>Arraste o mapa e ajuste o zoom. A captura será inserida no PDF sem distorção.</p>
      <div className="pecas-situation-map" ref={container} aria-label="Mapa interativo de enquadramento" />
      <div className="pecas-situation-actions">
        <select aria-label="Base cartográfica" value={basemap}
          onChange={(event) => {
            setBasemap(event.target.value as "osm" | "satellite" | "google");
            setLicenseConfirmed(false);
            setLicenseReference("");
          }}>
          <option value="satellite">Esri World Imagery (para PDF)</option>
          <option value="osm">Mapa OSM (para PDF)</option>
          <option value="google" disabled={!googleAvailable}>Google Satélite (somente visualizar)</option>
        </select>
        <button type="button" onClick={() => mapRef.current?.getView().setZoom((mapRef.current?.getView().getZoom() ?? 12) + 1)}>Zoom +</button>
        <button type="button" onClick={() => mapRef.current?.getView().setZoom((mapRef.current?.getView().getZoom() ?? 12) - 1)}>Zoom −</button>
        <button type="button" onClick={fit}>Enquadrar área</button>
      </div>
      <div className="pecas-source-license">
        <h4>Fonte e licença da imagem da planta</h4>
        <p>Google Satélite permanece somente para visualização. A seleção de outra fonte não concede direitos de reprodução automaticamente.</p>
        <label>
          <span>Comprovante, contrato ou referência de permissão para emissão da planta</span>
          <input value={licenseReference} onChange={(event) => { setLicenseReference(event.target.value); setLicenseConfirmed(false); }}
            placeholder="Ex.: contrato/licença e número de referência" disabled={basemap === "google"} />
        </label>
        <label className="pecas-license-check">
          <input type="checkbox" checked={licenseConfirmed} disabled={basemap === "google" || !licenseReference.trim()}
            onChange={(event) => setLicenseConfirmed(event.target.checked)} />
          <span>Confirmo que possuo autorização para reproduzir esta imagem em PDF técnico e me responsabilizo por registrar a fonte e a licença.</span>
        </label>
        <details>
          <summary>Outros provedores em avaliação</summary>
          <p>Mapbox Satellite e Airbus OneAtlas: conectores dependentes de credenciais oficiais e licença de exportação. Imagens próprias e GeoTIFF serão integrados em etapa posterior.</p>
        </details>
      </div>
      {basemap === "google" && <div className="pecas-google-attribution" aria-label="Créditos Google">
        <strong>Google Maps</strong><span>{copyright || "Carregando créditos…"}</span>
      </div>}
      {googleError && <p className="pecas-warning" role="alert">{googleError}</p>}
      <button type="button" className="pecas-primary pecas-capture" disabled={busy || basemap === "google" || !licenseConfirmed || !licenseReference.trim()}
        onClick={() => void capture()}>
        {busy ? "Capturando mapa…" : basemap === "google" ? "Selecione Esri ou OSM para gerar PDF" : "Usar este enquadramento na planta"}
      </button>
      <p className="pecas-note" role="status">{message || (saved?.geometry_key === geometryKey
        ? "Enquadramento salvo. É possível voltar e ajustá-lo novamente."
        : "Enquadramento automático até você salvar uma captura.")}</p>
    </aside>
  );
}
