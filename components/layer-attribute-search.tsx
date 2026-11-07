"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Search, X, Loader2, LocateFixed, ChevronDown } from "lucide-react";
import { getApiUrl } from "@/lib/api";

export type LayerSearchResult = {
  feature_id: string;
  title: string;
  external_id?: string | null;
  matched_field: string;
  matched_value: string;
  bbox: number[];
  geometry: Record<string, unknown>;
  properties: Record<string, unknown>;
};

type SearchLayer = {
  id?: string;
  name: string;
  enabled: boolean;
  slug?: string;
};

type FieldResponse = {
  fields: string[];
  default_field: string;
  source_name: string;
};

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  if (status === 401) return "Sua sessão expirou. Entre novamente.";
  return `A pesquisa não pôde ser concluída (HTTP ${status}).`;
}

const CAR_OFFICIAL = "__car_official__";
const ANM_OFFICIAL = "__anm_official__";

export function LayerAttributeSearch({
  layers,
  onSelect,
  hidden = false,
}: {
  layers: SearchLayer[];
  onSelect: (item: LayerSearchResult, label: string) => void;
  hidden?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [sourceId, setSourceId] = useState(CAR_OFFICIAL);
  const [fields, setFields] = useState<string[]>(["cod_imovel"]);
  const [field, setField] = useState("cod_imovel");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LayerSearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldBusy, setFieldBusy] = useState(false);

  // Dismiss the search while a global layers/dialog panel is active.
  useEffect(() => {
    if (hidden) setExpanded(false);
  }, [hidden]);

  useEffect(() => {
    if (sourceId === CAR_OFFICIAL || sourceId === ANM_OFFICIAL) {
      setFields(sourceId === CAR_OFFICIAL ? ["cod_imovel"] : ["PROCESSO"]);
      setField(sourceId === CAR_OFFICIAL ? "cod_imovel" : "PROCESSO");
      setError("");
      return;
    }
    const controller = new AbortController();
    setFieldBusy(true);
    setError("");
    setResults([]);
    fetch(`${getApiUrl()}/layer-search/fields?source_id=${encodeURIComponent(sourceId)}`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(errorMessage(response.status, body));
        return body as FieldResponse;
      })
      .then((body) => {
        setFields(body.fields);
        setField(body.default_field);
      })
      .catch((reason) => {
        if (controller.signal.aborted) return;
        setFields([]);
        setField("");
        setError(reason instanceof Error ? reason.message : "Falha ao consultar atributos.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setFieldBusy(false);
      });
    return () => controller.abort();
  }, [sourceId]);

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setError("");
    setResults([]);
    try {
      const url = sourceId === CAR_OFFICIAL
        ? `${getApiUrl()}/layer-search/car?car_code=${encodeURIComponent(q)}`
        : sourceId === ANM_OFFICIAL
        ? `${getApiUrl()}/layer-search/anm-process?process_number=${encodeURIComponent(q)}`
        : `${getApiUrl()}/layer-search/features?${new URLSearchParams({
            source_id: sourceId, field, q, limit: "15",
          })}`;
      const response = await fetch(url, { credentials: "include" });
      const body = await response.json();
      if (!response.ok) throw new Error(errorMessage(response.status, body));
      const found = Array.isArray(body.results)
        ? body.results as LayerSearchResult[] : [];
      setResults(found);
      if (!found.length) setError("Nenhuma feição encontrada com esse valor na fonte consultada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Pesquisa indisponível.");
    } finally {
      setBusy(false);
    }
  };

  const selectedName = sourceId === CAR_OFFICIAL
    ? "CAR oficial — SICAR"
    : sourceId === ANM_OFFICIAL
    ? "Processos minerários — ANM SIGMINE"
    : layers.find((layer) => layer.id === sourceId)?.name ?? "Camada";

  if (hidden) return null;

  return (
    <div className="layer-attribute-search" data-testid="layer-attribute-search">
      {!expanded ? (
        <button type="button"
          onClick={() => setExpanded(true)}
          title="Pesquisar feições pelos atributos da camada"
          className="layer-attribute-search-toggle flex items-center gap-2 rounded-xl border border-emerald-700/20 bg-white px-4 py-3 font-semibold text-emerald-950 shadow-lg hover:bg-emerald-50">
          <Search size={17}/> Pesquisar camadas
        </button>
      ) : (
        <section aria-label="Pesquisa por atributos das camadas"
          className="layer-attribute-search-panel rounded-2xl border border-emerald-900/15 bg-white p-4 shadow-2xl">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold text-emerald-950">
              <Search size={18}/> Localizar feição
            </div>
            <button type="button" aria-label="Fechar pesquisa"
              onClick={() => setExpanded(false)}
              className="rounded-md p-1 hover:bg-gray-100"><X size={18}/></button>
          </div>
          <form onSubmit={search} className="space-y-3">
            <label className="block text-xs font-semibold text-slate-700">
              Camada
              <select value={sourceId} onChange={(e) => {
                  setSourceId(e.target.value);
                  setResults([]);
                  setError("");
                }}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5 text-sm text-slate-900">
                <optgroup label="Consultas oficiais externas — fora do catálogo">
                  <option value={CAR_OFFICIAL}>CAR — SICAR (consultar código)</option>
                  <option value={ANM_OFFICIAL}>Processos minerários — ANM (consultar número)</option>
                </optgroup>
                <optgroup label="Camadas cadastradas no sistema">
                  {layers.filter(layer => layer.id).map(layer => (
                    <option key={layer.id} value={layer.id}>
                      {layer.name}{layer.enabled ? "" : " (oculta no mapa)"}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
            {sourceId !== CAR_OFFICIAL && sourceId !== ANM_OFFICIAL && (
              <label className="block text-xs font-semibold text-slate-700">
                Atributo
                <select value={field} onChange={(e) => setField(e.target.value)}
                  disabled={fieldBusy || fields.length === 0}
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5 text-sm text-slate-900">
                  {fields.map(value => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
            )}
            <label className="block text-xs font-semibold text-slate-700">
              {sourceId === CAR_OFFICIAL ? "Código completo do CAR" : sourceId === ANM_OFFICIAL ? "Número do processo ANM" : "Valor do atributo"}
              <input value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={sourceId === CAR_OFFICIAL ? "AP-160... (código completo)" : sourceId === ANM_OFFICIAL ? "850.123/2020" : "Digite o código, processo ou nome"}
                maxLength={120}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5 text-sm text-slate-900"
              />
            </label>
            <button type="submit"
              disabled={busy || fieldBusy || !query.trim() || (sourceId !== CAR_OFFICIAL && sourceId !== ANM_OFFICIAL && !field)}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-800 px-3 py-2.5 font-bold text-white disabled:opacity-50">
              {busy ? <Loader2 size={16} className="animate-spin"/> : <Search size={16}/>}
              {busy ? "Pesquisando…" : "Buscar e localizar"}
            </button>
          </form>
          {error && <p role="alert" className="mt-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">{error}</p>}
          {results.length > 0 && (
            <div className="mt-3 max-h-64 space-y-1 overflow-y-auto border-t pt-2">
              <p className="pb-1 text-xs font-semibold text-slate-600">
                {results.length} resultado(s) — selecione para destacar no mapa
              </p>
              {results.map((result) => (
                <button key={result.feature_id} type="button"
                  onClick={() => onSelect(result, selectedName)}
                  className="flex w-full items-start gap-2 rounded-lg border border-slate-200 p-2 text-left hover:border-emerald-600 hover:bg-emerald-50">
                  <LocateFixed size={17} className="mt-0.5 shrink-0 text-emerald-700"/>
                  <span className="min-w-0">
                    <span className="block truncate font-semibold text-slate-900">
                      {result.title}
                    </span>
                    <span className="block break-all text-xs text-slate-600">
                      {result.matched_field}: {result.matched_value}
                    </span>
                  </span>
                  <ChevronDown size={14} className="ml-auto shrink-0 text-emerald-700"/>
                </button>
              ))}
            </div>
          )}
          <p className="mt-3 text-[11px] leading-4 text-slate-500">
            {sourceId === CAR_OFFICIAL || sourceId === ANM_OFFICIAL
              ? "Consulta pontual à fonte oficial externa. CAR e ANM ainda não são camadas do catálogo nem ficam automaticamente ativadas no mapa; a geometria encontrada aparece em destaque."
              : "Consulta à versão vetorial local cadastrada. Uma camada exibida apenas por WMS precisa de WFS ou de base vetorial sincronizada para permitir pesquisa."}
          </p>
        </section>
      )}
    </div>
  );
}
