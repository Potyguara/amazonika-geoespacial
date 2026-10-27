"use client";

import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import GeoJSON from "ol/format/GeoJSON";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import { Fill, Stroke, Style } from "ol/style";

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
};

const polygonStyle = new Style({
  fill: new Fill({ color: "rgba(0, 114, 77, 0.22)" }),
  stroke: new Stroke({ color: "#00b782", width: 3 }),
});

export function SituationMapPreview({ geometry, geometryKey, saved, onSave }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const baseRef = useRef<TileLayer<OSM | XYZ> | null>(null);
  const [basemap, setBasemap] = useState<"osm" | "satellite">(saved?.basemap ?? "satellite");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
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
      layers: [base, new VectorLayer({ source, style: polygonStyle })],
      view: new View({
        center: useSaved ? saved.center : midpoint,
        zoom: useSaved ? saved.zoom : 12,
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
    const source = basemap === "satellite"
      ? new XYZ({
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        crossOrigin: "anonymous", maxZoom: 19,
      })
      : new OSM({ maxZoom: 19, crossOrigin: "anonymous" });
    baseRef.current?.setSource(source);
  }, [basemap, geometryKey]);

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
        raster_source: basemap === "satellite" ? "Esri World Imagery - referência" : "OpenStreetMap - referência",
        geometry_key: geoKeyRef.current, token: Date.now(),
        center: [...center], zoom: map.getView().getZoom() ?? 12, basemap,
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
          onChange={(event) => setBasemap(event.target.value as "osm" | "satellite")}>
          <option value="satellite">Imagem de satélite</option>
          <option value="osm">Mapa OSM</option>
        </select>
        <button type="button" onClick={() => mapRef.current?.getView().setZoom((mapRef.current?.getView().getZoom() ?? 12) + 1)}>Zoom +</button>
        <button type="button" onClick={() => mapRef.current?.getView().setZoom((mapRef.current?.getView().getZoom() ?? 12) - 1)}>Zoom −</button>
        <button type="button" onClick={fit}>Enquadrar área</button>
      </div>
      <button type="button" className="pecas-primary pecas-capture" disabled={busy}
        onClick={() => void capture()}>
        {busy ? "Capturando mapa…" : "Usar este enquadramento na planta"}
      </button>
      <p className="pecas-note" role="status">{message || (saved?.geometry_key === geometryKey
        ? "Enquadramento salvo. É possível voltar e ajustá-lo novamente."
        : "Enquadramento automático até você salvar uma captura.")}</p>
    </aside>
  );
}
