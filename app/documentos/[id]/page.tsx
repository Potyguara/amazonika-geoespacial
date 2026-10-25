"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

export default function DocumentoAcesso() {
  const params = useParams();
  const documentId = String(params.id ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [needLogin, setNeedLogin] = useState(false);

  const download = async () => {
    setError(""); setNeedLogin(false); setLoading(true);
    try {
      if (!/^[a-f\d-]{36}$/i.test(documentId)) {
        throw new Error("Código de documento inválido.");
      }
      const response = await fetch(`/api/v1/tools/documents/${documentId}`, {
        credentials: "include",
        cache: "no-store",
      });
      if (response.status === 401 || response.status === 403) {
        setNeedLogin(true);
        throw new Error("É necessário estar autenticado e autorizado para acessar este documento.");
      }
      if (!response.ok) throw new Error("Documento não encontrado ou indisponível.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `amazonika-planta-memorial-${documentId.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível baixar o documento.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{
      minHeight: "100vh", display: "grid", placeItems: "center",
      padding: 25, background: "#f3f7f4", fontFamily: "Arial, sans-serif",
    }}>
      <section style={{
        width: "min(470px, 100%)", borderRadius: 18, background: "white",
        padding: 32, boxShadow: "0 12px 35px #123a2a18",
      }}>
        <h1 style={{ color: "#124d36", margin: "0 0 12px" }}>Amazônika Geoespacial</h1>
        <h2 style={{ fontSize: 20 }}>Acesso à Planta e Memorial</h2>
        <p style={{ fontSize: 13, color: "#63786e", lineHeight: 1.6 }}>
          Este documento foi gerado pelo sistema. Por conter dados cadastrais e territoriais,
          o download exige uma sessão autorizada.
        </p>
        <p style={{ fontFamily: "monospace", fontSize: 11, wordBreak: "break-all" }}>
          Identificador: {documentId}
        </p>
        <button
          type="button"
          disabled={loading}
          onClick={() => void download()}
          style={{
            border: 0, borderRadius: 9, background: "#12533e",
            color: "white", fontWeight: 700, padding: "12px 18px", cursor: "pointer",
          }}
        >{loading ? "Verificando acesso…" : "Baixar PDF"}</button>
        {error && <p role="alert" style={{ color: "#a53a3e", fontSize: 12 }}>{error}</p>}
        {needLogin && <p style={{ fontSize: 12 }}>
          <a href="/" style={{ color: "#12533e" }}>Entrar no sistema</a> e retornar a esta página para baixar.
        </p>}
      </section>
    </main>
  );
}
