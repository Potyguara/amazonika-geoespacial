"use client";

import { useEffect, useMemo, useState } from "react";
import { getApiUrl } from "@/lib/api";
import {
  FileSpreadsheet,
  FileText,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from "lucide-react";

const API_URL = getApiUrl();

type AnalysisHistoryItem = {
  id: string;
  name: string;
  geometry_kind: string;
  area_hectares: number | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  created_by: {
    id: string;
    full_name: string;
    email: string;
  } | null;
  warnings_count: number;
  error_message: string | null;
};

function formatDate(value: string | null) {
  if (!value) return "—";

  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusLabel(status: string) {
  return (
    {
      COMPLETED: "Concluída",
      PROCESSING: "Processando",
      QUEUED: "Na fila",
      FAILED: "Falhou",
    } as Record<string, string>
  )[status] ?? status;
}

export function AnalysesModule() {
  const [items, setItems] = useState<AnalysisHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadAnalyses = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/analyses`, {
        credentials: "include",
      });

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : body?.detail?.message ??
              "Não foi possível carregar o histórico.",
        );
      }

      setItems(body);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao carregar as análises.",
      );
    } finally {
      setLoading(false);
    }
  };

  const excludeAnalysis = async (item: AnalysisHistoryItem) => {
    if (
      !window.confirm(
        `Excluir a análise "${item.name}" do histórico?\n\nOs relatórios já emitidos e seus códigos de verificação serão preservados.`,
      )
    ) return;

    setDeletingId(item.id);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/analyses/${item.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          typeof body?.detail === "string" ? body.detail : "Não foi possível excluir a análise.",
        );
      }
      setItems((existing) => existing.filter((row) => row.id !== item.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível excluir a análise.");
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    void loadAnalyses();
  }, []);

  const filtered = useMemo(() => {
    const normalized = search.trim().toLowerCase();

    return items.filter((item) => {
      const searchMatch =
        !normalized ||
        `${item.name} ${item.created_by?.full_name ?? ""} ${
          item.created_by?.email ?? ""
        }`
          .toLowerCase()
          .includes(normalized);

      const statusMatch =
        statusFilter === "ALL" || item.status === statusFilter;

      return searchMatch && statusMatch;
    });
  }, [items, search, statusFilter]);

  const completedCount = items.filter(
    (item) => item.status === "COMPLETED",
  ).length;

  const processingCount = items.filter(
    (item) =>
      item.status === "PROCESSING" || item.status === "QUEUED",
  ).length;

  return (
    <section className="analyses-module">
      <header className="analyses-hero">
        <div>
          <p className="eyebrow">HISTÓRICO TERRITORIAL</p>
          <h2>Análises realizadas</h2>
          <p>
            Consulte as análises executadas, responsável, data,
            área analisada e documentos vinculados.
          </p>
        </div>

        <button
          type="button"
          className="analyses-refresh"
          onClick={() => void loadAnalyses()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Atualizar
        </button>
      </header>

      <div className="analyses-summary">
        <article>
          <small>Total de análises</small>
          <strong>{items.length}</strong>
        </article>

        <article>
          <small>Concluídas</small>
          <strong>{completedCount}</strong>
        </article>

        <article>
          <small>Em processamento</small>
          <strong>{processingCount}</strong>
        </article>
      </div>

      {error && (
        <div className="analyses-message error">
          <TriangleAlert size={17} />
          {error}
        </div>
      )}

      <div className="analyses-toolbar">
        <label className="analyses-search">
          <Search size={17} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por análise ou responsável"
          />
        </label>

        <select
          className="analyses-filter"
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value)
          }
        >
          <option value="ALL">Todos os status</option>
          <option value="COMPLETED">Concluídas</option>
          <option value="PROCESSING">Processando</option>
          <option value="QUEUED">Na fila</option>
          <option value="FAILED">Falhas</option>
        </select>
      </div>

      <div className="analyses-table-card">
        <div className="analyses-table-head">
          <span>Data / hora</span>
          <span>Análise</span>
          <span>Responsável</span>
          <span>Área</span>
          <span>Status</span>
          <span>Ações</span>
        </div>

        {loading ? (
          <div className="analyses-empty">
            Carregando histórico…
          </div>
        ) : filtered.length === 0 ? (
          <div className="analyses-empty">
            Nenhuma análise encontrada.
          </div>
        ) : (
          filtered.map((item) => (
            <div className="analyses-table-row" key={item.id}>
              <span className="analyses-date">
                {formatDate(item.created_at)}
              </span>

              <div className="analyses-name">
                <strong>{item.name}</strong>
                <small>{item.geometry_kind}</small>
              </div>

              <div className="analyses-owner">
                <strong>
                  {item.created_by?.full_name ??
                    "Registro anterior"}
                </strong>
                <small>
                  {item.created_by?.email ??
                    "Responsável não registrado"}
                </small>
              </div>

              <span className="analyses-area">
                {item.area_hectares == null
                  ? "Ponto"
                  : `${item.area_hectares.toLocaleString(
                      "pt-BR",
                      {
                        minimumFractionDigits: 4,
                        maximumFractionDigits: 4,
                      },
                    )} ha`}
              </span>

              <span
                className={`analyses-status ${item.status.toLowerCase()}`}
              >
                {item.status === "COMPLETED" && (
                  <ShieldCheck size={13} />
                )}
                {statusLabel(item.status)}
              </span>

              <div className="analyses-actions">
                {item.status === "COMPLETED" && (
                  <>
                    <a
                      href={`${API_URL}/reports/analyses/${item.id}/pdf`}
                      target="_blank"
                      rel="noreferrer"
                      title="Abrir relatório"
                    >
                      <FileText size={15} />
                      Relatório
                    </a>

                    <a
                      href={`${API_URL}/analyses/${item.id}/sigef-ods`}
                      title="Gerar ODS para simulação SIGEF"
                    >
                      <FileSpreadsheet size={15} />
                      ODS SIGEF
                    </a>
                  </>
                )}
                {item.status !== "PROCESSING" && item.status !== "QUEUED" && (
                  <button
                    type="button"
                    className="analyses-delete"
                    disabled={deletingId !== null}
                    onClick={() => void excludeAnalysis(item)}
                    title="Excluir do histórico, preservando relatórios emitidos"
                    aria-label={`Excluir análise ${item.name} do histórico`}
                  >
                    <Trash2 size={15} />
                    {deletingId === item.id ? "Excluindo…" : "Excluir"}
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
