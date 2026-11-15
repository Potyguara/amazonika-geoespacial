"use client";

import { useEffect, useMemo, useState } from "react";
import { getApiUrl } from "@/lib/api";

export type InpeBounds = { west: number; south: number; east: number; north: number };

type Scene = {
  id: string;
  datetime: string | null;
  bbox: number[] | null;
  collection: string;
  thumbnail_url: string | null;
  stac_item_url: string;
  ps4_status: string;
};
type SearchResponse = {
  provider: string;
  collection: string;
  scenes: Scene[];
  warning: string;
};

/** Extract all GeoJSON polygon vertices (WGS84) and produce an INPE-compatible bbox.
 * Never use an unrelated default location and never silently truncate a large property.
 */
export function boundsFromPolygon(geometry: Record<string, unknown> | null | undefined): InpeBounds | null {
  if (!geometry) return null;
  const points: Array<[number, number]> = [];
  const visit = (value: unknown, depth = 0) => {
    if (!value || typeof value !== "object" || depth > 20) return;
    if (Array.isArray(value)) {
      if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
        const [lon, lat] = value;
        if (Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon) <= 180 && Math.abs(lat) <= 90) {
          points.push([lon, lat]);
        }
        return;
      }
      for (const item of value) visit(item, depth + 1);
      return;
    }
    const obj = value as Record<string, unknown>;
    if (obj.type === "FeatureCollection" && Array.isArray(obj.features)) {
      for (const feature of obj.features) visit(feature, depth + 1);
    } else if (obj.type === "Feature") visit(obj.geometry, depth + 1);
    else if ((obj.type === "Polygon" || obj.type === "MultiPolygon") && Array.isArray(obj.coordinates)) {
      visit(obj.coordinates, depth + 1);
    }
  };
  visit(geometry);
  if (points.length < 3) return null;
  const west = Math.min(...points.map(p => p[0]));
  const east = Math.max(...points.map(p => p[0]));
  const south = Math.min(...points.map(p => p[1]));
  const north = Math.max(...points.map(p => p[1]));
  if (east - west > 0.9 || north - south > 0.9) return null;
  const padding = Math.max(0.0003, Math.min(0.01, Math.max(east - west, north - south) * 0.1));
  const bounds = { west: west - padding, south: south - padding, east: east + padding, north: north + padding };
  if (bounds.east - bounds.west > 1 || bounds.north - bounds.south > 1 ||
      bounds.west < -180 || bounds.east > 180 || bounds.south < -90 || bounds.north > 90) return null;
  return bounds;
}

type Props = { geometry?: Record<string, unknown> | null; geometryKey?: string };

export function InpeCbersSceneSearch({ geometry, geometryKey = "" }: Props) {
  const [kind, setKind] = useState<"rgb" | "ortho">("rgb");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const bounds = useMemo(() => boundsFromPolygon(geometry), [geometryKey, geometry]);
  const bboxKey = bounds ? [bounds.west, bounds.south, bounds.east, bounds.north].join(",") : "";
  useEffect(() => {
    if (!bboxKey) {
      setResults(null);
      setError("");
      setBusy(false);
      return;
    }
    const controller = new AbortController();
    const [west, south, east, north] = bboxKey.split(",").map(Number);
    const qs = new URLSearchParams({
      west: String(west), south: String(south),
      east: String(east), north: String(north),
      kind, limit: "10",
    });
    setBusy(true);
    setResults(null);
    setError("");
    fetch(`${getApiUrl()}/inpe-cbers/scenes?${qs}`, {
      credentials: "include", cache: "no-store", signal: controller.signal,
    }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Consulta INPE indisponível.");
      return data as SearchResponse;
    }).then(data => { if (!controller.signal.aborted) setResults(data); })
      .catch(err => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Falha ao consultar o INPE.");
      })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [bboxKey, kind]);

  return (
    <div className="pecas-card" aria-label="Consulta automática de imagens CBERS-4A INPE">
      <h4>INPE · CBERS-4A WPM — enquadramento automático</h4>
      <p>O sistema pesquisa as cenas que intersectam a poligonal selecionada, sem exigir coordenadas manuais.</p>
      {!bounds ? (
        <p className="pecas-warning" role="status">
          Nenhuma poligonal válida disponível ou extensão superior a 0,9°.
          Selecione ou importe um imóvel no mapa para localizar as cenas CBERS-4A.
        </p>
      ) : (
        <>
          <p className="pecas-note">
            Enquadramento calculado: O {bounds.west.toFixed(6)}° · S {bounds.south.toFixed(6)}° ·
            L {bounds.east.toFixed(6)}° · N {bounds.north.toFixed(6)}° (WGS84)
          </p>
          <label className="pecas-field">
            <span>Coleção de imagens</span>
            <select value={kind} onChange={event => setKind(event.target.value as "rgb" | "ortho")}>
              <option value="rgb">CBERS-4A WPM · RGB fusionado (COG)</option>
              <option value="ortho">CBERS-4A WPM · L4 original ortorretificado</option>
            </select>
          </label>
          {busy && <p role="status">Consultando cenas no INPE para a área do imóvel...</p>}
          {error && <p role="alert" className="pecas-warning">{error}</p>}
          {results && (
            <div aria-live="polite">
              <p><strong>{results.scenes.length} cena(s)</strong> que intersectam o enquadramento do imóvel.</p>
              <p className="pecas-note">{results.warning}</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                {results.scenes.map(scene => (
                  <article key={scene.id} style={{ border: "1px solid #b6c4c4", borderRadius: 8, padding: 12 }}>
                    <strong style={{ overflowWrap: "anywhere" }}>{scene.id}</strong>
                    <p>{scene.datetime ? new Date(scene.datetime).toLocaleDateString("pt-BR") : "Data não informada"}</p>
                    <p className="pecas-note">PS4: acurácia pendente de comprovação.</p>
                    <a href={scene.stac_item_url} target="_blank" rel="noopener noreferrer">Ver metadados no INPE</a>
                  </article>
                ))}
              </div>
              {!results.scenes.length && <p>Nenhuma cena encontrada. Verifique a cobertura do catálogo para esse imóvel.</p>}
            </div>
          )}
        </>
      )}
    </div>
  );
}
