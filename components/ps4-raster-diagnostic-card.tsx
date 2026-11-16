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
  visual_analysis?: {
    status: "ANALYZED" | "UNAVAILABLE";
    reason?: string;
    sample_width_px?: number;
    sample_height_px?: number;
    global_stretch_min?: number;
    global_stretch_max?: number;
    grayscale_stddev?: number;
    edge_mean?: number;
    extreme_brightness_pct?: number;
    quality_basis?: string;
    positional_accuracy_m?: null;
  };
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
    <div className="pecas-card ps4-analysis-card" aria-label="Diagnóstico próprio do GeoTIFF PS4">
      <style>{`
        .ps4-analysis-card{border:1px solid #dde7e1;border-radius:12px;background:#fff;}
        .ps4-analysis-card h4{margin:0;font-size:15px;}
        .ps4-analysis-card p{margin:7px 0;line-height:1.5;font-size:12px;}
        .ps4-radiometry{margin:12px 0;border:1px solid #dce7df;border-radius:10px;padding:12px;background:#f6faf7;}
        .ps4-radiometry>strong{font-size:12px;color:#124d3a;}
        .ps4-radiometry-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0;}
        .ps4-radiometry-grid>div{padding:11px 8px;background:white;border:1px solid #e1eae4;border-radius:8px;}
        .ps4-radiometry-grid small{display:block;font-size:10px;color:#677b6f;line-height:1.3;}
        .ps4-radiometry-grid strong{display:block;margin-top:6px;font-size:19px;color:#114331;}
        .ps4-radiometry>small{font-size:10px;color:#65786d;}
        @media(max-width:680px){.ps4-radiometry-grid{grid-template-columns:1fr;}}
      `}</style>
      <h4>Processamento próprio da imagem CBERS</h4>
      <p>Analise o GeoTIFF verdadeiro, sem arquivos demonstrativos: cobertura dos V,
        resolução, contraste global e indicadores visuais de textura. A análise
        não precisa de relatório PDF.</p>
      <button type="button" className="pecas-primary"
        disabled={!pieceId || !rasterSha256 || busy}
        onClick={() => void inspect()}>
        {busy ? "Processando amostra do raster..." : "Processar imagem CBERS agora"}
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
        {diagnostic.visual_analysis?.status === "ANALYZED" && <div className="ps4-radiometry">
          <strong>Análise radiométrica da imagem original</strong>
          <div className="ps4-radiometry-grid">
            <div><small>Contraste (desvio-padrão)</small>
              <strong>{diagnostic.visual_analysis.grayscale_stddev?.toLocaleString("pt-BR") ?? "—"}</strong></div>
            <div><small>Textura (gradiente exploratório)</small>
              <strong>{diagnostic.visual_analysis.edge_mean?.toLocaleString("pt-BR") ?? "—"}</strong></div>
            <div><small>Pixels nos extremos da escala</small>
              <strong>{diagnostic.visual_analysis.extreme_brightness_pct?.toLocaleString("pt-BR") ?? "—"}%</strong></div>
          </div>
          <small>Amostra de {diagnostic.visual_analysis.sample_width_px} × {diagnostic.visual_analysis.sample_height_px} pixels.
            Indicadores exploratórios de visualização, não de precisão geodésica.</small>
        </div>}
        {diagnostic.visual_analysis?.status === "UNAVAILABLE" &&
          <p className="ps4-alert-red" role="status">A análise radiométrica não foi concluída:{" "}
            {diagnostic.visual_analysis.reason ?? "Amostragem indisponível."}
            A cobertura e o georreferenciamento continuam conferidos.</p>}
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
