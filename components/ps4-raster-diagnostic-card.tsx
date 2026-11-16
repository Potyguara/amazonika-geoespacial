"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type Vertex = { name: string; longitude: number; latitude: number };
type Diagnostic = {
  status: "RASTER_STRUCTURALLY_VALID" | "COVERAGE_INCOMPLETE";
  accuracy_status: "UNVERIFIED";
  crs: string;
  width: number;
  height: number;
  pixel_size_x_m: number | null;
  pixel_size_y_m: number | null;
  vertices_checked: number;
  vertices_inside: number;
  vertices_outside: string[];
  horizontal_rms_m: null;
  warnings: string[];
};

export function Ps4RasterDiagnosticCard({
  pieceId, rasterSha256, vertices, sceneId,
}: {
  pieceId: string | null | undefined;
  rasterSha256: string | null;
  vertices: Vertex[];
  sceneId: string;
}) {
  const [diagnostic, setDiagnostic] = useState<Diagnostic | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setDiagnostic(null);
    setError("");
  }, [pieceId, rasterSha256, sceneId, vertices]);

  const inspect = async () => {
    if (!pieceId || !rasterSha256) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `${getApiUrl()}/technical-pieces/${pieceId}/ps4/raster-diagnostic`,
        {
          method: "POST", credentials: "include",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({vertices}),
          cache: "no-store",
        },
      );
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(typeof result?.detail === "string"
          ? result.detail : "Não foi possível inspecionar a imagem.");
      }
      setDiagnostic(result.diagnostic as Diagnostic);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha de diagnóstico PS4.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pecas-card" aria-label="Diagnóstico próprio do GeoTIFF PS4">
      <h4>Diagnóstico automático da imagem</h4>
      <p>O sistema verifica o raster privado, georreferenciamento, resolução do
        pixel e cobertura de cada V. Nenhum relatório PDF é necessário para
        executar este diagnóstico estrutural.</p>
      <button type="button" className="pecas-primary"
        disabled={!pieceId || !rasterSha256 || busy}
        onClick={() => void inspect()}>
        {busy ? "Analisando GeoTIFF..." : "Analisar imagem da peça"}
      </button>
      {!rasterSha256 && <p className="ps4-alert-red" role="status">
        É necessário importar ou selecionar um recorte GeoTIFF primeiro.
      </p>}
      {error && <p className="ps4-alert-red" role="alert">{error}</p>}
      {diagnostic && <div role="status" aria-live="polite">
        <p><strong>Integridade e cobertura:</strong>{" "}
          {diagnostic.status === "RASTER_STRUCTURALLY_VALID"
            ? "imagem estruturada e vértices cobertos"
            : "vértices fora da cobertura — revisar cena"}</p>
        <p><strong>SRC:</strong> {diagnostic.crs} ·
          <strong> Dimensões:</strong> {diagnostic.width} × {diagnostic.height} pixels</p>
        <p><strong>Pixel nominal:</strong>{" "}
          {diagnostic.pixel_size_x_m === null || diagnostic.pixel_size_y_m === null
            ? "Não disponível em metros"
            : `${diagnostic.pixel_size_x_m.toLocaleString("pt-BR")} × ${diagnostic.pixel_size_y_m.toLocaleString("pt-BR")} m`}</p>
        <p><strong>Cobertura:</strong> {diagnostic.vertices_inside} de{" "}
          {diagnostic.vertices_checked} vértices V.</p>
        {diagnostic.vertices_outside.length > 0 && <p className="ps4-alert-red" role="alert">
          Fora da cobertura: {diagnostic.vertices_outside.join(", ")}
        </p>}
        <div className="ps4-alert-red" role="alert">
          <strong>Precisão horizontal: NÃO COMPROVADA</strong>
          <p>GSD, SRC e recorte íntegro não fornecem RMS, EMQ ou sigmas.
            Estes indicadores não liberam validação RT ou ODS oficial.</p>
        </div>
      </div>}
    </div>
  );
}
