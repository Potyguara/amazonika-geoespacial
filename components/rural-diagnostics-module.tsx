"use client";

import { useState, type FormEvent } from "react";
import { FileSearch, MapPin, Search, ShieldCheck } from "lucide-react";
import { getApiUrl } from "@/lib/api";

const API_URL = getApiUrl();

type Candidate = {
  feature_id: string;
  source_id: string;
  source_slug: string;
  source_name: string;
  institution: string;
  name: string;
  cadastral_code: string | null;
  area_hectares: number | null;
  vertex_count: number | null;
  reference_date: string | null;
  imported_at: string | null;
};

type LocateResult = {
  coordinate: { latitude: number; longitude: number };
  candidate_count: number;
  has_more: boolean;
  candidates: Candidate[];
  point_only: boolean;
  coverage: string;
  notice: string;
};

type AnalysisStatus = {
  analysis_id: string;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
  error_message?: string | null;
  results?: Array<{ intersects: boolean; matched_features: number; source_name: string }>;
  source_statuses?: Array<{ status: string; source_name: string; message?: string }>;
};

async function messageFromError(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string"
    ? body.detail
    : `Erro HTTP ${response.status} ao consultar a API.`;
}

function formatArea(value: number | null): string {
  return value == null ? "Não informada" : `${value.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })} ha`;
}

export function RuralDiagnosticsModule() {
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [result, setResult] = useState<LocateResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [finished, setFinished] = useState<AnalysisStatus | null>(null);

  const findProperties = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const lat = Number(latitude.replace(",", ".").trim());
    const lon = Number(longitude.replace(",", ".").trim());
    if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
        !latitude.trim() || !longitude.trim() ||
        lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setError("Informe latitude e longitude válidas em graus decimais.");
      return;
    }
    setBusy(true);
    setError(null);
    setFinished(null);
    setResult(null);
    setSelectedId(null);
    try {
      const query = new URLSearchParams({
        latitude: String(lat),
        longitude: String(lon),
      });
      const response = await fetch(`${API_URL}/rural-diagnostics/locate?${query}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error(await messageFromError(response));
      setResult(await response.json() as LocateResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha na busca cadastral.");
    } finally {
      setBusy(false);
    }
  };

  const analyzeProperty = async (candidate: Candidate) => {
    setBusy(true);
    setError(null);
    setFinished(null);
    setSelectedId(candidate.feature_id);
    try {
      const detailResponse = await fetch(
        `${API_URL}/rural-diagnostics/properties/${candidate.feature_id}`,
        { credentials: "include" },
      );
      if (!detailResponse.ok) throw new Error(await messageFromError(detailResponse));
      const detail = await detailResponse.json() as {
        name: string;
        geometry: Record<string, unknown>;
        source_name: string;
        reference_date: string | null;
      };
      setProgress("Iniciando cruzamento nas bases territoriais disponíveis…");
      const response = await fetch(`${API_URL}/analyses`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `Diagnóstico rural — ${detail.name}`,
          geometry: detail.geometry,
          incra_uf: "ALL",
          subject: {
            holder_name: detail.name,
            area_name: detail.name,
            rural_diagnostic: true,
            cadastral_source: candidate.source_name,
            cadastral_code: candidate.cadastral_code,
            cadastral_reference_date: candidate.reference_date,
            input_coordinate: result?.coordinate,
          },
        }),
      });
      if (!response.ok) throw new Error(await messageFromError(response));
      const created = await response.json() as { analysis_id: string };
      // The existing API executes asynchronously. Polling is bounded and
      // does not save raster downloads or generate an unrequested PDF.
      let completed: AnalysisStatus | null = null;
      for (let attempt = 0; attempt < 60; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const statusResponse = await fetch(`${API_URL}/analyses/${created.analysis_id}`, {
          credentials: "include",
        });
        if (!statusResponse.ok) throw new Error(await messageFromError(statusResponse));
        const status = await statusResponse.json() as AnalysisStatus;
        if (status.status === "FAILED") {
          throw new Error(status.error_message || "Falha na análise geoespacial.");
        }
        if (status.status === "COMPLETED") {
          completed = status;
          break;
        }
        setProgress("Consultando fontes e calculando interseções…");
      }
      if (!completed) {
        setProgress("");
        throw new Error(`A análise foi registrada (${created.analysis_id}), mas continua em processamento. Consulte o histórico de Análises.`);
      }
      setFinished(completed);
      setProgress("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível concluir a análise.");
      setProgress("");
    } finally {
      setBusy(false);
      setSelectedId(null);
    }
  };

  return (
    <section className="rural-diagnostic-workspace">
      <header className="rural-diagnostic-intro">
        <p className="eyebrow">INTELIGÊNCIA TERRITORIAL RURAL</p>
        <h2>Diagnóstico por coordenada</h2>
        <p>Localize o perímetro cadastral que contém o ponto informado e inicie uma análise das bases disponíveis na Amazonika.</p>
      </header>

      <form className="rural-coordinate-form" onSubmit={(event) => void findProperties(event)}>
        <label>Latitude (graus decimais)
          <input value={latitude} onChange={(event) => setLatitude(event.target.value)}
            placeholder="Ex.: 0.012345" inputMode="decimal" required />
        </label>
        <label>Longitude (graus decimais)
          <input value={longitude} onChange={(event) => setLongitude(event.target.value)}
            placeholder="Ex.: -51.123456" inputMode="decimal" required />
        </label>
        <button type="submit" disabled={busy}>
          <Search size={17} /> {busy ? "Consultando…" : "Localizar imóvel"}
        </button>
      </form>

      <div className="rural-diagnostic-advisory">
        <MapPin size={18} />
        <p>Uma coordenada não define sozinha o perímetro. Quando houver vários cadastros sobrepostos, selecione o imóvel correto. Sem geometria encontrada, a análise de área exige CAR validado ou importação do perímetro.</p>
      </div>

      {error && <p className="rural-diagnostic-error" role="alert">{error}</p>}

      {result && (
        <div className="rural-diagnostic-results">
          <h3>Imóveis candidatos ({result.candidate_count})</h3>
          <p>{result.coverage}</p>
          {result.has_more && <p className="rural-diagnostic-error">Há mais de 20 registros nesta coordenada. Refine a identificação com o código cadastral.</p>}
          {result.candidates.length === 0 && (
            <p>Não encontramos perímetro cadastral nas versões locais disponíveis. Nenhuma conclusão de ausência de cadastro deve ser feita com esse resultado.</p>
          )}
          {result.candidates.map((candidate) => (
            <article className="rural-candidate" key={candidate.feature_id}>
              <div>
                <strong>{candidate.name}</strong>
                <small>{candidate.source_name} · {candidate.institution}</small>
                <span>Identificação: {candidate.cadastral_code || "não informada"}</span>
                <span>Área da geometria: {formatArea(candidate.area_hectares)}</span>
                <span>Referência: {candidate.reference_date || "não informada"}</span>
              </div>
              <button type="button" disabled={busy || result.has_more}
                onClick={() => void analyzeProperty(candidate)}>
                <FileSearch size={17} />
                {busy && selectedId === candidate.feature_id ? "Analisando…" : "Analisar imóvel"}
              </button>
            </article>
          ))}
          <p className="rural-diagnostic-note">{result.notice}</p>
        </div>
      )}

      {progress && <p role="status" className="rural-diagnostic-progress">{progress}</p>}
      {finished && (
        <section className="rural-diagnostic-complete" role="status">
          <ShieldCheck size={22} />
          <div>
            <strong>Análise territorial concluída</strong>
            <p>
              {finished.results?.reduce((sum, item) => sum + item.matched_features, 0) ?? 0} feições identificadas nas fontes analisadas.
              {finished.source_statuses?.some((source) => source.status !== "ANALYZED")
                ? " Atenção: há fontes indisponíveis; consulte o histórico para o relatório completo."
                : " Consulte a aba Análises para emitir o relatório territorial."}
            </p>
            <small>Código interno: {finished.analysis_id}</small>
          </div>
        </section>
      )}
      <p className="rural-diagnostic-note">Etapa inicial: utiliza os dados locais existentes. PRODES, MapBiomas e outras consultas sob demanda serão adicionadas em etapas posteriores. Nenhum resultado é certificado automaticamente como regularidade ambiental ou dominial.</p>
    </section>
  );
}
