"use client";

import { useState } from "react";
import { getApiUrl } from "@/lib/api";

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

export function InpeCbersSceneSearch() {
  const [bounds, setBounds] = useState({ west: "", south: "", east: "", north: "" });
  const [kind, setKind] = useState<"rgb" | "ortho">("rgb");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const update = (field: keyof typeof bounds, value: string) =>
    setBounds((current) => ({ ...current, [field]: value }));

  async function search() {
    setError("");
    setResults(null);
    const values = Object.values(bounds).map((v) => Number(v.trim().replace(",", ".")));
    if (Object.values(bounds).some((v) => !v.trim()) || values.some((v) => !Number.isFinite(v))) {
      setError("Preencha os quatro limites em graus decimais WGS84.");
      return;
    }
    const [west, south, east, north] = values;
    if (west >= east || south >= north || east - west > 1 || north - south > 1) {
      setError("Informe um retângulo válido, com até 1° em cada eixo.");
      return;
    }
    setBusy(true);
    try {
      const qs = new URLSearchParams({
        west: String(west), south: String(south),
        east: String(east), north: String(north), kind, limit: "10",
      });
      const response = await fetch(`${getApiUrl()}/inpe-cbers/scenes?${qs}`, {
        credentials: "include", cache: "no-store",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Consulta INPE indisponível.");
      setResults(data as SearchResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível consultar o INPE.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pecas-card" aria-label="Consulta de imagens CBERS-4A INPE">
      <h4>INPE · CBERS-4A WPM (GEO-90)</h4>
      <p>Busque cenas ortorretificadas L4 do INPE pelo retângulo geográfico.
        Esta consulta não gera vértices nem valida o método PS4.</p>
      <div className="pecas-form-grid">
        {(["west", "south", "east", "north"] as const).map((field) => (
          <label className="pecas-field" key={field}>
            <span>{{ west: "Oeste (longitude)", south: "Sul (latitude)",
              east: "Leste (longitude)", north: "Norte (latitude)" }[field]}</span>
            <input inputMode="decimal" placeholder={field === "west" ? "-51,10" : "Graus decimais"}
              value={bounds[field]} onChange={(event) => update(field, event.target.value)} />
          </label>
        ))}
      </div>
      <label className="pecas-field">
        <span>Coleção de imagens</span>
        <select value={kind} onChange={(event) => setKind(event.target.value as "rgb" | "ortho")}>
          <option value="rgb">CBERS-4A WPM · RGB fusionado (COG derivado de L4)</option>
          <option value="ortho">CBERS-4A WPM · L4 original ortorretificado</option>
        </select>
      </label>
      <button type="button" className="pecas-secondary" onClick={() => void search()} disabled={busy}>
        {busy ? "Consultando INPE..." : "Buscar imagens na área"}
      </button>
      {error && <p role="alert" className="pecas-warning">{error}</p>}
      {results && (
        <div aria-live="polite">
          <p><strong>{results.scenes.length} cena(s)</strong> recebidas do catálogo {results.collection}.</p>
          <p className="pecas-note">{results.warning}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" }}>
            {results.scenes.map((scene) => (
              <article key={scene.id} style={{ border: "1px solid #b6c4c4", padding: "12px", borderRadius: "8px" }}>
                <strong style={{ overflowWrap: "anywhere" }}>{scene.id}</strong>
                <p>{scene.datetime ? new Date(scene.datetime).toLocaleDateString("pt-BR") : "Data não informada"}</p>
                <p className="pecas-note">PS4: acurácia pendente de comprovação</p>
                <a href={scene.stac_item_url} target="_blank" rel="noopener noreferrer">
                  Ver metadados no INPE
                </a>
              </article>
            ))}
          </div>
          <p className="pecas-note">A sobreposição georreferenciada do raster,
            a análise RMS e a vetorização são etapas posteriores (GEO-91/92).</p>
        </div>
      )}
    </div>
  );
}
