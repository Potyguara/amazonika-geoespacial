"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

type Profile = {
  full_name: string;
  rg: string;
  cpf: string;
  profession: string;
  specialization: string;
  crea: string;
  visto: string;
  incra_code: string;
  art: string;
};

const BLANK: Profile = {
  full_name: "", rg: "", cpf: "", profession: "", specialization: "",
  crea: "", visto: "", incra_code: "", art: "",
};
const FIELDS: Array<{ key: keyof Profile; label: string; description?: string }> = [
  { key: "full_name", label: "Nome completo" },
  { key: "rg", label: "RG / órgão emissor" },
  { key: "cpf", label: "CPF" },
  { key: "profession", label: "Título profissional" },
  { key: "specialization", label: "Especialização / habilitação" },
  { key: "crea", label: "CREA (UF e número)" },
  { key: "visto", label: "Visto CREA na UF" },
  { key: "incra_code", label: "Credenciamento INCRA, se houver" },
  { key: "art", label: "ART de referência (conferir em cada serviço)" },
];

export function ProfessionalProfile() {
  const [profile, setProfile] = useState<Profile>(BLANK);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`${getApiUrl()}/auth/me/professional-profile`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Não foi possível consultar o perfil técnico.");
        return response.json();
      })
      .then((value) => {
        if (!active) return;
        setProfile(Object.fromEntries(
          Object.keys(BLANK).map((key) => [key, String(value[key] ?? "")]),
        ) as Profile);
      })
      .catch((reason) => active && setError(String(reason.message ?? reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const save = async () => {
    setSaving(true); setError(""); setMessage("");
    try {
      const response = await fetch(`${getApiUrl()}/auth/me/professional-profile`, {
        method: "PUT", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "Falha ao atualizar perfil.");
      }
      setMessage("Dados profissionais salvos. As próximas peças técnicas usarão este cadastro.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Erro ao salvar.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="professional-profile">
      <h2>Meu perfil e carimbo profissional</h2>
      <p>Essas informações serão preenchidas automaticamente na planta e no memorial do usuário logado. Confirme a ART correspondente a cada serviço antes da emissão.</p>
      <div className="professional-profile-grid">
        {FIELDS.map((field) => (
          <label key={field.key}>
            <span>{field.label}</span>
            <input
              disabled={loading || saving}
              autoComplete="off"
              value={profile[field.key]}
              onChange={(event) => setProfile((current) => ({ ...current, [field.key]: event.target.value }))}
            />
          </label>
        ))}
      </div>
      {error && <p className="professional-error" role="alert">{error}</p>}
      {message && <p className="professional-message" role="status">{message}</p>}
      <button type="button" disabled={loading || saving} onClick={() => void save()}>
        {saving ? "Salvando…" : "Salvar meu perfil técnico"}
      </button>
    </section>
  );
}
