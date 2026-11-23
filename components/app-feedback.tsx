"use client";

/*
 * Camada global de retorno visual:
 * - detecta sessão expirada (401 da API) e abre um login centralizado que
 *   renova o cookie sem recarregar a página, preservando o que está na tela;
 * - mostra janelas centralizadas de progresso (percentual) para envio e
 *   recebimento de arquivos feitos com trackedFetch;
 * - marca como "ocupado" o botão que disparou uma chamada à API até ela
 *   terminar, e mostra uma barra de atividade no topo;
 * - exibe avisos centralizados com notify().
 */

import { useEffect, useState, type FormEvent } from "react";
import { getApiUrl } from "@/lib/api";

type Notice = { id: number; tone: "info" | "success" | "error"; title: string; message: string };
type Transfer = {
  id: number;
  label: string;
  direction: "upload" | "download";
  loaded: number;
  total: number | null;
  phase: "sending" | "waiting" | "receiving";
};

type State = {
  sessionExpired: boolean;
  notices: Notice[];
  transfers: Transfer[];
  activeRequests: number;
};

const state: State = { sessionExpired: false, notices: [], transfers: [], activeRequests: 0 };
const listeners = new Set<() => void>();
let seq = 0;

function emit() {
  for (const listener of listeners) listener();
}

function setState(patch: Partial<State>) {
  Object.assign(state, patch);
  emit();
}

function isApiUrl(url: string) {
  try {
    const api = new URL(getApiUrl(), window.location.href);
    const target = new URL(url, window.location.href);
    return target.origin === api.origin && target.pathname.startsWith(api.pathname);
  } catch {
    return false;
  }
}

function isAuthProbe(url: string) {
  return /\/auth\/(login|me|logout)(\?|$)/.test(url);
}

export function reportSessionExpired() {
  if (!state.sessionExpired) setState({ sessionExpired: true });
}

export function notify(notice: Omit<Notice, "id">) {
  const item = { ...notice, id: ++seq };
  setState({ notices: [...state.notices.filter((n) => n.message !== item.message), item] });
  return item.id;
}

function dismissNotice(id: number) {
  setState({ notices: state.notices.filter((n) => n.id !== id) });
}

function updateTransfer(id: number, patch: Partial<Transfer>) {
  setState({ transfers: state.transfers.map((t) => (t.id === id ? { ...t, ...patch } : t)) });
}

/* ---------- Botão ocupado: liga o clique à chamada de rede que ele dispara ---------- */

let lastButton: { el: HTMLButtonElement; at: number } | null = null;
const busyCount = new WeakMap<HTMLElement, number>();

function markBusy(el: HTMLElement | null, delta: 1 | -1) {
  if (!el) return;
  const next = Math.max(0, (busyCount.get(el) ?? 0) + delta);
  busyCount.set(el, next);
  if (next > 0) el.setAttribute("data-busy", "true");
  else el.removeAttribute("data-busy");
}

function buttonForThisRequest(): HTMLElement | null {
  if (!lastButton) return null;
  // Uma chamada iniciada logo após o clique pertence a esse botão.
  return performance.now() - lastButton.at < 800 ? lastButton.el : null;
}

function trackRequest<T>(promise: Promise<T>, button: HTMLElement | null) {
  setState({ activeRequests: state.activeRequests + 1 });
  markBusy(button, 1);
  const done = () => {
    setState({ activeRequests: Math.max(0, state.activeRequests - 1) });
    markBusy(button, -1);
  };
  promise.then(done, done);
  return promise;
}

let installed = false;

export function installApiGuard() {
  if (installed || typeof window === "undefined") return;
  installed = true;

  document.addEventListener(
    "click",
    (event) => {
      const el = (event.target as HTMLElement | null)?.closest?.("button");
      if (el instanceof HTMLButtonElement && !el.disabled) {
        lastButton = { el, at: performance.now() };
        el.classList.remove("app-press");
        void el.offsetWidth;
        el.classList.add("app-press");
        window.setTimeout(() => el.classList.remove("app-press"), 320);
      }
    },
    true,
  );

  const original = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!isApiUrl(url)) return original(input, init);
    const request = original(input, init).then((response) => {
      if (response.status === 401 && !isAuthProbe(url)) reportSessionExpired();
      return response;
    });
    return trackRequest(request, buttonForThisRequest());
  };
}

/* ---------- Transferências com percentual ---------- */

export type TrackedInit = {
  method?: string;
  body?: XMLHttpRequestBodyInit | null;
  headers?: Record<string, string>;
  credentials?: RequestCredentials;
  cache?: RequestCache;
};

/**
 * Igual a fetch, mas usa XMLHttpRequest para mostrar o percentual de envio e
 * de recebimento numa janela centralizada. Devolve um Response comum.
 */
export function trackedFetch(url: string, init: TrackedInit = {}, label = "Transferindo arquivo") {
  const id = ++seq;
  const hasBody = init.body != null;
  const direction: Transfer["direction"] = hasBody && typeof init.body !== "string" ? "upload" : "download";
  setState({
    transfers: [
      ...state.transfers,
      { id, label, direction, loaded: 0, total: null, phase: hasBody ? "sending" : "waiting" },
    ],
  });
  const button = buttonForThisRequest();
  const promise = new Promise<Response>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(init.method ?? (hasBody ? "POST" : "GET"), url);
    xhr.responseType = "blob";
    xhr.withCredentials = (init.credentials ?? "include") !== "omit";
    for (const [key, value] of Object.entries(init.headers ?? {})) xhr.setRequestHeader(key, value);
    xhr.upload.onprogress = (event) => {
      updateTransfer(id, {
        phase: "sending",
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : null,
      });
    };
    xhr.upload.onload = () => updateTransfer(id, { phase: "waiting" });
    xhr.onprogress = (event) => {
      updateTransfer(id, {
        phase: "receiving",
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : null,
      });
    };
    xhr.onload = () => {
      const headers = new Headers();
      for (const line of xhr.getAllResponseHeaders().trim().split(/[\r\n]+/)) {
        const index = line.indexOf(":");
        if (index > 0) headers.append(line.slice(0, index).trim(), line.slice(index + 1).trim());
      }
      if (xhr.status === 401) reportSessionExpired();
      const status = xhr.status >= 200 && xhr.status <= 599 ? xhr.status : 500;
      resolve(new Response(status === 204 ? null : xhr.response, { status, statusText: xhr.statusText, headers }));
    };
    xhr.onerror = () => reject(new TypeError("Falha de rede durante a transferência."));
    xhr.onabort = () => reject(new DOMException("Transferência cancelada.", "AbortError"));
    xhr.send(init.body ?? null);
  });
  const finish = () => setState({ transfers: state.transfers.filter((t) => t.id !== id) });
  promise.then(finish, finish);
  return trackRequest(promise, button);
}

/* ---------- Interface ---------- */

function useFeedbackState() {
  const [, force] = useState(0);
  useEffect(() => {
    const listener = () => force((n) => n + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  return state;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function TransferCard({ transfer }: { transfer: Transfer }) {
  const percent = transfer.total ? Math.min(100, Math.round((transfer.loaded / transfer.total) * 100)) : null;
  const phaseText =
    transfer.phase === "sending"
      ? "Enviando"
      : transfer.phase === "waiting"
        ? "Processando no servidor"
        : "Recebendo";
  const showPercent = transfer.phase !== "waiting" && percent !== null;
  return (
    <div className="app-transfer">
      <div className="app-transfer-head">
        <strong>{transfer.label}</strong>
        <span>{showPercent ? `${percent}%` : ""}</span>
      </div>
      <div className={`app-progress ${showPercent ? "" : "app-progress-indeterminate"}`}>
        <div style={{ width: showPercent ? `${percent}%` : undefined }} />
      </div>
      <small>
        {phaseText}
        {transfer.phase !== "waiting" && transfer.loaded > 0
          ? ` · ${formatBytes(transfer.loaded)}${transfer.total ? ` de ${formatBytes(transfer.total)}` : ""}`
          : "…"}
      </small>
    </div>
  );
}

function SessionDialog({ onRenewed }: { onRenewed: (name: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${getApiUrl()}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(response.status === 401 ? "E-mail ou senha inválidos." : payload?.detail ?? "Não foi possível entrar.");
      }
      setPassword("");
      onRenewed(payload?.user?.full_name ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-modal-backdrop" role="presentation">
      <form className="app-modal" role="dialog" aria-modal="true" aria-labelledby="app-session-title" onSubmit={submit}>
        <p className="app-modal-eyebrow">Sessão expirada</p>
        <h2 id="app-session-title">Entre novamente para continuar</h2>
        <p>
          A sessão de acesso vale 12 horas e terminou. O que está na tela foi mantido: depois de entrar, repita a
          última ação.
        </p>
        <label>
          <span>E-mail</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          <span>Senha</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p className="app-modal-error" role="alert">
            {error}
          </p>
        )}
        <div className="app-modal-actions">
          <button type="submit" className="app-modal-primary" disabled={busy} data-busy={busy ? "true" : undefined}>
            {busy ? "Entrando…" : "Entrar e continuar"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function AppFeedbackLayer() {
  const s = useFeedbackState();

  useEffect(() => {
    installApiGuard();
  }, []);

  useEffect(() => {
    const success = s.notices.filter((n) => n.tone !== "error");
    if (!success.length) return;
    const timers = success.map((n) => window.setTimeout(() => dismissNotice(n.id), 5000));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [s.notices]);

  const notice = s.notices[s.notices.length - 1];

  return (
    <>
      {s.activeRequests > 0 && <div className="app-activity-bar" aria-hidden="true" />}
      {s.transfers.length > 0 && !s.sessionExpired && (
        <div className="app-modal-backdrop" role="presentation">
          <div className="app-modal" role="status" aria-live="polite">
            <p className="app-modal-eyebrow">Transferência em andamento</p>
            {s.transfers.map((t) => (
              <TransferCard key={t.id} transfer={t} />
            ))}
          </div>
        </div>
      )}
      {notice && !s.sessionExpired && s.transfers.length === 0 && (
        <div className="app-modal-backdrop" role="presentation" onClick={() => dismissNotice(notice.id)}>
          <div
            className={`app-modal app-notice app-notice-${notice.tone}`}
            role={notice.tone === "error" ? "alertdialog" : "status"}
            aria-live="polite"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="app-modal-eyebrow">{notice.title}</p>
            <p>{notice.message}</p>
            <div className="app-modal-actions">
              <button type="button" className="app-modal-primary" autoFocus onClick={() => dismissNotice(notice.id)}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
      {s.sessionExpired && (
        <SessionDialog
          onRenewed={(name) => {
            setState({ sessionExpired: false });
            notify({
              tone: "success",
              title: "Sessão renovada",
              message: `${name ? name + ", a" : "A"} sessão foi renovada por mais 12 horas. Repita a última ação.`,
            });
          }}
        />
      )}
    </>
  );
}
