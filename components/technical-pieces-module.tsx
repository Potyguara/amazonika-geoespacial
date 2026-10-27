"use client";

import { useCallback, useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

export type SavedTechnicalPiece = {
  id: string;
  title: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};
export type TechnicalPieceSnapshot = {
  features?: Record<string, unknown>;
  selected_ids?: string[];
  data?: Record<string, unknown>;
  professional?: Record<string, string> | null;
  elements?: Record<string, boolean>;
  magnetic_declination?: string;
  memorial_edited?: string;
  situation?: Record<string, unknown> | null;
};

type Props = {
  onOpen: (piece: { id: string; title: string; snapshot: TechnicalPieceSnapshot }) => void;
  revision?: number;
};

export function TechnicalPiecesModule({ onOpen, revision = 0 }: Props) {
  const [items, setItems] = useState<SavedTechnicalPiece[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces`, { credentials: "include" });
      if (!response.ok) throw new Error("Não foi possível listar as peças técnicas.");
      setItems(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Erro ao carregar peças.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load, revision]);

  const open = async (id: string) => {
    setError("");
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces/${id}`, { credentials: "include" });
      if (!response.ok) throw new Error("Não foi possível recuperar esta peça.");
      const record = await response.json();
      onOpen({ id: record.id, title: record.title, snapshot: record.snapshot });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Erro ao abrir.");
    }
  };
  const remove = async (id: string) => {
    if (!window.confirm("Excluir definitivamente este rascunho?")) return;
    setError("");
    try {
      const response = await fetch(`${getApiUrl()}/technical-pieces/${id}`, {
        method: "DELETE", credentials: "include",
      });
      if (!response.ok) throw new Error("Não foi possível excluir o rascunho.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Erro ao excluir.");
    }
  };

  return <section className="pecas-saved-list">
    <header className="pecas-rt-heading">
      <div><h2>Peças Técnicas</h2><p>Rascunhos salvos, disponíveis para continuar a edição e gerar novas versões.</p></div>
      <button className="pecas-secondary" type="button" onClick={() => void load()}>Atualizar lista</button>
    </header>
    {loading && <p>Carregando peças salvas…</p>}
    {error && <p className="pecas-warning" role="alert">{error}</p>}
    {!loading && !items.length && <p>Nenhuma peça salva. Inicie uma planta pelo mapa e clique em Salvar peça.</p>}
    <div className="pecas-saved-rows">
      {items.map((piece) => (
        <article className="pecas-saved-row" key={piece.id}>
          <div><strong>{piece.title}</strong>
            <small>Rascunho · Atualizado em {piece.updated_at ? new Date(piece.updated_at).toLocaleString("pt-BR") : "—"}</small>
          </div>
          <button className="pecas-primary" onClick={() => void open(piece.id)}>Abrir e editar</button>
          <button className="pecas-secondary" onClick={() => void remove(piece.id)}>Excluir</button>
        </article>
      ))}
    </div>
  </section>;
}
