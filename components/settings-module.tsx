"use client";

import { FormEvent, useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";
import { PaidMapsBudget } from "@/components/paid-maps-budget";
import { Check, FileImage, Save, Settings2, TriangleAlert } from "lucide-react";

const API_URL = getApiUrl();

type DocumentTemplate = {
  company_name: string;
  cnpj: string;
  address: string;
  email: string;
  responsible_name: string;
  responsible_registration: string;
  document_footer: string;
  logo_path?: string;
};

const EMPTY: DocumentTemplate = {
  company_name: "Amazonika Engenharia",
  cnpj: "49.158.834/0001-19",
  address: "Av. Almirante Barroso, 620-B, Centro, Macapá/AP.",
  email: "amazonika@amazonikaengenharia.com.br",
  responsible_name: "",
  responsible_registration: "",
  document_footer: "Documento técnico gerado pelo Amazônika Geoespacial.",
};

export function SettingsModule() {
  const [form, setForm] = useState<DocumentTemplate>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [logoUploading, setLogoUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/tools/document-template`, {
        credentials: "include",
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Não foi possível carregar as configurações.");
      setForm({ ...EMPTY, ...body });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao carregar configurações.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/tools/document-template`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Não foi possível salvar as configurações.");
      setForm({ ...EMPTY, ...body });
      setMessage("Modelo documental atualizado.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar configurações.");
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (file: File) => {
    setLogoUploading(true);
    setError(null);
    setMessage(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${API_URL}/tools/document-template/logo`, {
        method: "POST",
        credentials: "include",
        body,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail ?? "Não foi possível enviar a logomarca.");
      setForm({ ...EMPTY, ...(payload?.template ?? {}) });
      setMessage("Logomarca atualizada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao enviar logomarca.");
    } finally {
      setLogoUploading(false);
    }
  };

  if (loading) {
    return <section className="settings-module"><div className="settings-loading">Carregando configurações…</div></section>;
  }

  return (
    <section className="settings-module">
      <header className="settings-hero">
        <div>
          <p className="eyebrow">CONFIGURAÇÃO INSTITUCIONAL</p>
          <h2>Planta e Memorial Descritivo</h2>
          <p>Defina o padrão aplicado automaticamente aos documentos técnicos gerados pelo sistema.</p>
        </div>
        <Settings2 size={28} />
      </header>

      {message && <div className="users-message success"><Check size={17} />{message}</div>}
      {error && <div className="users-message error"><TriangleAlert size={17} />{error}</div>}

      <form className="settings-card" onSubmit={save}>
        <div className="settings-grid">
          <label>
            <span>Empresa / instituição</span>
            <input value={form.company_name} onChange={(e) => setForm((current) => ({ ...current, company_name: e.target.value }))} />
          </label>
          <label>
            <span>CNPJ</span>
            <input value={form.cnpj} onChange={(e) => setForm((current) => ({ ...current, cnpj: e.target.value }))} />
          </label>
          <label className="wide">
            <span>Endereço</span>
            <input value={form.address} onChange={(e) => setForm((current) => ({ ...current, address: e.target.value }))} />
          </label>
          <label className="wide">
            <span>E-mail</span>
            <input type="email" value={form.email} onChange={(e) => setForm((current) => ({ ...current, email: e.target.value }))} />
          </label>
          <label>
            <span>Responsável técnico padrão</span>
            <input value={form.responsible_name} onChange={(e) => setForm((current) => ({ ...current, responsible_name: e.target.value }))} />
          </label>
          <label>
            <span>Registro profissional</span>
            <input value={form.responsible_registration} onChange={(e) => setForm((current) => ({ ...current, responsible_registration: e.target.value }))} />
          </label>
          <label className="wide">
            <span>Rodapé padrão</span>
            <input value={form.document_footer} onChange={(e) => setForm((current) => ({ ...current, document_footer: e.target.value }))} />
          </label>
        </div>

        <label className="settings-logo-upload">
          <FileImage size={24} />
          <div>
            <strong>{logoUploading ? "Enviando logomarca…" : "Atualizar logomarca"}</strong>
            <small>PNG ou JPG, até 5 MB. A imagem será usada na Planta e no Memorial.</small>
          </div>
          <input
            type="file"
            accept=".png,.jpg,.jpeg,image/png,image/jpeg"
            disabled={logoUploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void uploadLogo(file);
              event.currentTarget.value = "";
            }}
          />
        </label>

        <footer className="settings-actions">
          <button type="submit" disabled={saving}>
            <Save size={16} />
            {saving ? "Salvando…" : "Salvar modelo padrão"}
          </button>
        </footer>
      </form>
      <PaidMapsBudget />
    </section>
  );
}
