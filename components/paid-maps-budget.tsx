"use client";
import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type Budget = {
  provider: string; enabled: boolean; configured: boolean; limit: number;
  requests: number; remaining: number; blocked: boolean; period: string;
};
const API = getApiUrl();
const fmt = (n: number) => n.toLocaleString("pt-BR");

export function PaidMapsBudget() {
  const [items, setItems] = useState<Budget[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const load = async () => {
    try {
      const r = await fetch(`${API}/tile-budget`, { credentials: "include" });
      if (!r.ok) throw new Error(r.status === 403 ? "Apenas administradores podem consultar custos." : "Falha na consulta.");
      setItems(await r.json());
    } catch (err) { setMessage(err instanceof Error ? err.message : "Erro inesperado"); }
  };
  useEffect(() => { void load(); const id = window.setInterval(() => void load(), 60000); return () => window.clearInterval(id); }, []);
  const save = async (item: Budget) => {
    setBusy(item.provider); setMessage("");
    try {
      const r = await fetch(`${API}/tile-budget/${item.provider}`, {
        method: "PUT", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: item.enabled, monthly_limit: item.limit }),
      });
      if (!r.ok) { const p = await r.json().catch(() => null); throw new Error(p?.detail || "Falha ao salvar."); }
      setMessage("Limite atualizado. Bloqueio aplicado imediatamente no servidor.");
      await load();
    } catch (err) { setMessage(err instanceof Error ? err.message : "Falha ao salvar."); }
    finally { setBusy(""); }
  };
  return <section className="settings-card paid-map-budgets">
    <h3>Controle de custos — imagens de satélite</h3>
    <p>Contagem interna de requisições aos provedores, reiniciada automaticamente a cada mês (UTC). Não representa a fatura oficial. Falhas e tentativas também consomem a reserva interna.</p>
    {message && <p role="status">{message}</p>}
    {items.map(item => <div className="paid-map-entry" key={item.provider}>
      <h4>{item.provider === "google" ? "Google Map Tiles API" : "Mapbox Raster Tiles API"}</h4>
      <p>Período: {item.period} · {item.configured ? "Credencial configurada" : "Credencial ausente"} · {item.blocked ? "Bloqueado" : "Liberado pelo controle interno"}</p>
      <strong>{fmt(item.requests)} / {fmt(item.limit)} requisições</strong>
      <progress value={Math.min(item.requests, item.limit)} max={item.limit} aria-label={`Consumo ${item.provider}`} />
      <small>Saldo interno: {fmt(item.remaining)}</small>
      <label>Limite mensal de requisições
        <input type="number" min="1" max="10000000" value={item.limit}
          onChange={e => setItems(current => current.map(x => x.provider === item.provider ? { ...x, limit: Number(e.target.value) } : x))}/>
      </label>
      <label><input type="checkbox" checked={item.enabled}
        onChange={e => setItems(current => current.map(x => x.provider === item.provider ? { ...x, enabled: e.target.checked } : x))}/>
        Permitir novas requisições enquanto houver saldo
      </label>
      <button type="button" disabled={busy === item.provider || !Number.isInteger(item.limit) || item.limit < 1}
        onClick={() => void save(item)}>{busy === item.provider ? "Salvando…" : "Salvar controle"}</button>
    </div>)}
    <p><strong>Atenção:</strong> Google pode cobrar por solicitações diferentes dos tiles (sessões, créditos e outros serviços); confirme no Google Cloud Billing. O limite interno não interrompe cobranças externas independentes deste gateway.</p>
  </section>;
}
