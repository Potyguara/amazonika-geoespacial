"use client";

import { useState } from "react";
import { getApiUrl } from "@/lib/api";

type Sheet = { inom: string; mi: string; bloco: string; area_overlap: boolean; boundary_touch_only: boolean };
type Lookup = { matched_sheets: Sheet[]; sheet_count: number; accuracy_status: string; notice: string };

export function Pb1SheetLookup({ geometry }: { geometry: Record<string, unknown> | null }) {
  const [result, setResult] = useState<Lookup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lookup = async () => {
    if (!geometry) return;
    setBusy(true);setError("");setResult(null);
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces/pb1/sheets/lookup`, {
        method:"POST",credentials:"include",cache:"no-store",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({geometry}),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof payload?.detail === "string"
        ? payload.detail : "Falha na identificação das folhas.");
      setResult(payload as Lookup);
    } catch (e) {setError(e instanceof Error?e.message:"Falha na articulação.");}
    finally {setBusy(false);}
  };
  return <section className="pecas-card" aria-label="Articulação de folhas oficiais PB1">
    <h4>PB1 · Base cartográfica oficial — folhas do Amapá</h4>
    <p>Localize automaticamente a articulação 1:25.000 (INOM, MI e bloco)
      para a parcela selecionada. O índice espacial é cadastrado uma única vez no servidor;
      o usuário não precisa enviar ortoimagens de todas as folhas.</p>
    <button className="pecas-primary" type="button" onClick={()=>void lookup()}
      disabled={!geometry || busy}>
      {busy?"Consultando articulação...":"Identificar folhas da parcela"}
    </button>
    {!geometry && <p className="pecas-note">Selecione uma parcela com geometria fechada
      no módulo para consultar a articulação.</p>}
    {error && <p role="alert" className="pecas-warning">{error}</p>}
    {result && <div role="status">
      <strong>{result.sheet_count} folha(s) encontrada(s) · referência 1:25.000</strong>
      {result.sheet_count===0 && <p>Imóvel fora da cobertura da articulação fornecida
        ou sem interseção. Não atribua uma folha por proximidade.</p>}
      {result.sheet_count>0 && <div style={{overflowX:"auto"}}>
        <table className="pecas-table">
          <thead><tr><th>Folha INOM</th><th>MI</th><th>Bloco</th><th>Interseção</th></tr></thead>
          <tbody>{result.matched_sheets.map(s=><tr key={s.inom}>
            <td>{s.inom}</td><td>{s.mi}</td><td>{s.bloco}</td>
            <td>{s.area_overlap?"Sobrepõe imóvel":"Contato de borda"}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      <p className="pecas-note">{result.notice}</p>
      <p className="pecas-note"><strong>PB1 exige precisão conhecida e verificável da fonte,
        inclusive compatibilidade com o limite.</strong> MDT Color sem metadados não define
        automaticamente posição horizontal ou sigmas; escala isoladamente não homologa ODS.</p>
    </div>}
  </section>;
}
