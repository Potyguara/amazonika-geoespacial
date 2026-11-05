"use client";

import { useState, type FormEvent } from "react";
import { FileSearch, MapPin, Search, ShieldCheck } from "lucide-react";
import { getApiUrl } from "@/lib/api";

const API_URL = getApiUrl();

type Candidate = {
  feature_id: string;
  source_id: string | null;
  source_slug: string;
  source_name: string;
  institution: string;
  name: string;
  cadastral_code: string | null;
  area_hectares: number | null;
  vertex_count: number | null;
  reference_date: string | null;
  imported_at: string | null;
  retrieval?: "LOCAL_VECTOR" | "OFFICIAL_WFS" | "OFFICIAL_CAR_WFS";
  declared_area_hectares?: number | null;
  status?: string | null;
  uf_id?: number | string | null;
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
  const [carCode, setCarCode] = useState("");
  const [result, setResult] = useState<LocateResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [officialWarning, setOfficialWarning] = useState<string | null>(null);
  const [finished, setFinished] = useState<AnalysisStatus | null>(null);
  const [monitoringCandidate, setMonitoringCandidate] = useState<Candidate | null>(null);
  const [monitoringGeometry, setMonitoringGeometry] = useState<Record<string, unknown> | null>(null);
  const [monitoringLayers, setMonitoringLayers] = useState<Array<{name: string; title: string; program: string}>>([]);
  const [monitoringLayer, setMonitoringLayer] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);
  const [monitoringPreview, setMonitoringPreview] = useState<{
    program: string; layer_title: string; interfering_features: number;
    overlap_hectares: number; overlap_percent: number | null;
    source: string; warning: string;
    features: Array<{id: string; overlap_hectares: number; attributes: Record<string, string>}>;
  } | null>(null);

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
    setOfficialWarning(null);
    try {
      const query = new URLSearchParams({
        latitude: String(lat),
        longitude: String(lon),
      });
      const [localLookup, officialLookup] = await Promise.allSettled([
        fetch(`${API_URL}/rural-diagnostics/locate?${query}`, {
          credentials: "include",
        }),
        fetch(`${API_URL}/rural-diagnostics/official-sigef/locate?${query}`, {
          credentials: "include",
        }),
      ]);
      const localResponse = localLookup.status === "fulfilled" ? localLookup.value : null;
      const officialResponse = officialLookup.status === "fulfilled" ? officialLookup.value : null;
      const localData = localResponse?.ok ? await localResponse.json() as LocateResult : null;
      const officialData = officialResponse?.ok ? await officialResponse.json() as LocateResult : null;
      if (!localData && !officialData) {
        throw new Error("As consultas cadasstrais local e oficial não estão disponíveis. Tente novamente.");
      }
      if (!officialData) {
        setOfficialWarning("GeoNode INCRA indisponível nesta consulta. Os candidatos exibidos são apenas das bases locais; não conclua ausência de parcelas oficiais.");
      }
      if (!localData) {
        setOfficialWarning("Consulta cadastral local indisponível. Exibindo somente os resultados do SIGEF oficial.");
      }
      const combined = [
        ...(officialData?.candidates ?? []),
        ...(localData?.candidates ?? []),
      ];
      setResult({
        coordinate: { latitude: lat, longitude: lon },
        candidate_count: combined.length,
        has_more: !!localData?.has_more || !!officialData?.has_more,
        candidates: combined,
        point_only: combined.length === 0,
        coverage: "SIGEF oficial (WFS) e perímetros cadastrais das versões locais do PostGIS.",
        notice: "Se houver diferentes parcelas ou versões sobre o ponto, confirme o código cadastral antes de analisar.",
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha na busca cadastral.");
    } finally {
      setBusy(false);
    }
  };

  const findCarByCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const code = carCode.trim().toUpperCase().replace(/\\s/g, "");
    if (!/^[A-Z]{2}-[0-9]{7}-[A-F0-9]{32}$/.test(code)) {
      setError("Código CAR inválido. Informe UF-IBGE(7 dígitos)-identificador(32 caracteres).");
      return;
    }
    setBusy(true);
    setError(null);
    setOfficialWarning(null);
    setFinished(null);
    setResult(null);
    try {
      const query = new URLSearchParams({ car_code: code });
      const response = await fetch(`${API_URL}/rural-diagnostics/official-car/lookup?${query}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error(await messageFromError(response));
      const data = await response.json() as {
        candidate_count: number; candidates: Candidate[];
        coverage: string; notice: string; status: string;
      };
      setResult({
        coordinate: { latitude: NaN, longitude: NaN },
        candidate_count: data.candidate_count,
        has_more: false,
        candidates: data.candidates,
        point_only: data.candidate_count === 0,
        coverage: data.coverage,
        notice: data.notice,
      });
      if (data.status === "NOT_FOUND_IN_PUBLIC_WFS") {
        setOfficialWarning("O código informado não foi localizado no WFS público. Isso não comprova inexistência do CAR; verifique o recibo e a disponibilidade do SICAR.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Consulta CAR indisponível.");
    } finally {
      setBusy(false);
    }
  };

  const resolveCandidateGeometry = async (candidate: Candidate) => {
    const isOfficial = candidate.retrieval === "OFFICIAL_WFS";
    const isCar = candidate.retrieval === "OFFICIAL_CAR_WFS";
    const url = isOfficial
      ? `${API_URL}/rural-diagnostics/official-sigef/perimeter`
      : isCar
        ? `${API_URL}/rural-diagnostics/official-car/perimeter`
        : `${API_URL}/rural-diagnostics/properties/${candidate.feature_id}`;
    const response = await fetch(url, {
      credentials: "include",
      ...(isOfficial || isCar ? {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          ...(isOfficial ? {
            latitude: result?.coordinate.latitude,
            longitude: result?.coordinate.longitude,
          } : {car_code: candidate.cadastral_code}),
          feature_token: candidate.feature_id,
        }),
      } : {}),
    });
    if (!response.ok) throw new Error(await messageFromError(response));
    return await response.json() as {name: string; geometry: Record<string, unknown>};
  };

  const openMonitoring = async (candidate: Candidate) => {
    setBusy(true);
    setError(null);
    setMonitoringPreview(null);
    setMonitoringCandidate(null);
    setMonitoringGeometry(null);
    try {
      const [detail, catalogResponse] = await Promise.all([
        resolveCandidateGeometry(candidate),
        fetch(`${API_URL}/rural-diagnostics/monitoring/layers`, {credentials: "include"}),
      ]);
      if (!catalogResponse.ok) throw new Error(await messageFromError(catalogResponse));
      const catalog = await catalogResponse.json() as {
        layers: Array<{name: string; title: string; program: string}>;
      };
      setMonitoringCandidate(candidate);
      setMonitoringGeometry(detail.geometry);
      setMonitoringLayers(catalog.layers);
      setMonitoringLayer(catalog.layers[0]?.name || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Monitoramento indisponível.");
    } finally {
      setBusy(false);
    }
  };

  const downloadMonitoringPdf = async () => {
    if (!monitoringCandidate || !monitoringLayer) return;
    setPdfBusy(true);
    setError(null);
    try {
      const isSigef = monitoringCandidate.retrieval === "OFFICIAL_WFS";
      const isCar = monitoringCandidate.retrieval === "OFFICIAL_CAR_WFS";
      const payload = {
        retrieval: isSigef ? "OFFICIAL_WFS" : isCar ? "OFFICIAL_CAR_WFS" : "LOCAL_VECTOR",
        feature_id: monitoringCandidate.feature_id,
        layer_name: monitoringLayer,
        ...(isSigef ? {
          latitude: result?.coordinate.latitude,
          longitude: result?.coordinate.longitude,
        } : {}),
        ...(isCar ? {car_code: monitoringCandidate.cadastral_code} : {}),
      };
      const response = await fetch(`${API_URL}/rural-diagnostics/monitoring/preview-pdf`, {
        method: "POST",
        credentials: "include",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await messageFromError(response));
      const blob = await response.blob();
      if (blob.type !== "application/pdf" || blob.size === 0) {
        throw new Error("O servidor não retornou um arquivo PDF válido.");
      }
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = "AMAZONIKA_DIAGNOSTICO_AMBIENTAL_PREVIA.pdf";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(downloadUrl), 15000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível gerar a prévia PDF.");
    } finally {
      setPdfBusy(false);
    }
  };

  const runMonitoring = async () => {
    if (!monitoringGeometry || !monitoringLayer) return;
    setBusy(true);
    setError(null);
    setMonitoringPreview(null);
    try {
      const response = await fetch(`${API_URL}/rural-diagnostics/monitoring/preview`, {
        method: "POST",
        credentials: "include",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({layer_name: monitoringLayer, geometry: monitoringGeometry}),
      });
      if (!response.ok) throw new Error(await messageFromError(response));
      setMonitoringPreview(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha na consulta ambiental.");
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
      const detail = await resolveCandidateGeometry(candidate);
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
            cadastral_retrieval: candidate.retrieval ?? "LOCAL_VECTOR",
            declared_area_hectares: candidate.declared_area_hectares ?? null,
            cadastral_status: candidate.status ?? null,
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

      <form className="rural-coordinate-form" onSubmit={(event) => void findCarByCode(event)}>
        <label>Código do imóvel no CAR
          <input value={carCode} onChange={(event) => setCarCode(event.target.value)}
            placeholder="AP-1600303-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" required />
        </label>
        <button type="submit" disabled={busy}>
          <Search size={17} /> {busy ? "Consultando…" : "Consultar CAR oficial"}
        </button>
      </form>

      <div className="rural-diagnostic-advisory">
        <MapPin size={18} />
        <p>Uma coordenada não define sozinha o perímetro. Quando houver vários cadastros sobrepostos, selecione o imóvel correto. Sem geometria encontrada, a análise de área exige CAR validado ou importação do perímetro.</p>
      </div>

      {error && <p className="rural-diagnostic-error" role="alert">{error}</p>}
      {officialWarning && <p className="rural-diagnostic-error" role="status">{officialWarning}</p>}

      {result && (
        <div className="rural-diagnostic-results">
          <h3>Imóveis candidatos ({result.candidate_count})</h3>
          <p>{result.coverage}</p>
          {result.has_more && <p className="rural-diagnostic-error">Há mais de 20 registros nesta coordenada. Refine a identificação com o código cadastral.</p>}
          {result.candidates.length === 0 && (
            <p>Nenhum perímetro foi encontrado nesta consulta. Isso não prova ausência de imóvel ou cadastro; confirme a cobertura da fonte selecionada.</p>
          )}
          {result.candidates.map((candidate) => (
            <article className="rural-candidate" key={candidate.feature_id}>
              <div>
                <strong>{candidate.name}</strong>
                <small>{candidate.source_name} · {candidate.institution}</small>
                {(candidate.retrieval === "OFFICIAL_WFS" || candidate.retrieval === "OFFICIAL_CAR_WFS") && <span className="rural-candidate-official">Consulta oficial em tempo real</span>}
                <span>Identificação: {candidate.cadastral_code || "não informada"}</span>
                <span>Área da geometria: {formatArea(candidate.area_hectares)}</span>
                {candidate.declared_area_hectares != null && <span>Área declarada no CAR: {formatArea(candidate.declared_area_hectares)}</span>}
                {candidate.status && <span>Status publicado: {candidate.status}</span>}
                <span>Referência: {candidate.reference_date || (candidate.retrieval === "OFFICIAL_WFS" ? "consulta WFS atual" : "não informada")}</span>
              </div>
              <div className="rural-candidate-buttons">
              <button type="button" disabled={busy || result.has_more}
                onClick={() => void analyzeProperty(candidate)}>
                <FileSearch size={17} />
                {busy && selectedId === candidate.feature_id ? "Analisando…" : "Analisar imóvel"}
              </button>
              <button type="button" className="rural-monitoring-button" disabled={busy || result.has_more}
                onClick={() => void openMonitoring(candidate)}>
                <FileSearch size={17} /> PRODES / DETER
              </button>
              </div>
            </article>
          ))}
          <p className="rural-diagnostic-note">{result.notice}</p>
        </div>
      )}

      {monitoringCandidate && (
        <section className="rural-diagnostic-results rural-monitoring-panel">
          <h3>Prévia ambiental — {monitoringCandidate.name}</h3>
          <p>Selecione uma camada publicada pelo INPE. A consulta retorna somente as feições na extensão do imóvel.</p>
          <label>Camada TerraBrasilis
            <select value={monitoringLayer} onChange={(event) => setMonitoringLayer(event.target.value)}>
              {monitoringLayers.map((layer) => (
                <option key={layer.name} value={layer.name}>{layer.program} — {layer.title}</option>
              ))}
            </select>
          </label>
          <div>
            <button type="button" disabled={busy || !monitoringLayer}
              onClick={() => void runMonitoring()}>Consultar monitoramento</button>
            <button type="button" className="rural-monitoring-cancel"
              onClick={() => {setMonitoringCandidate(null); setMonitoringPreview(null);}}>
              Fechar
            </button>
          </div>
          {monitoringPreview && (
            <section className="rural-diagnostic-complete">
              <div>
                <strong>{monitoringPreview.program} — {monitoringPreview.layer_title}</strong>
                <p>Feições com sobreposição: {monitoringPreview.interfering_features}.</p>
                <p>Área total de interseção: {formatArea(monitoringPreview.overlap_hectares)}.</p>
                <p>Percentual do imóvel: {monitoringPreview.overlap_percent == null
                  ? "Não calculado"
                  : monitoringPreview.overlap_percent.toLocaleString("pt-BR", {maximumFractionDigits: 2}) + "%"}.</p>
                <small>{monitoringPreview.warning}</small>
                <div className="rural-monitoring-report-action">
                  <button type="button" disabled={pdfBusy || busy}
                    onClick={() => void downloadMonitoringPdf()}>
                    <FileSearch size={17} />
                    {pdfBusy ? "Gerando PDF…" : "Baixar prévia PDF"}
                  </button>
                  <small>Documento preliminar: dados oficiais serão consultados novamente pelo servidor.</small>
                </div>
                {monitoringPreview.features.slice(0, 20).map((feature, index) => (
                  <p key={feature.id || index}>Feição {index + 1}: {formatArea(feature.overlap_hectares)}</p>
                ))}
              </div>
            </section>
          )}
        </section>
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
      <p className="rural-diagnostic-note">Etapa atual: busca por coordenada (SIGEF e PostGIS) ou código CAR (SICAR WFS público). PRODES, MapBiomas e outros serviços serão incorporados em etapas posteriores. Nenhum resultado é certificado automaticamente como regularidade ambiental ou dominial.</p>
    </section>
  );
}
