from pathlib import Path

PAGE = Path("app/page.tsx")
CSS = Path("app/globals.css")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"ERRO [{label}]: ponto de alteração não localizado")
    return text.replace(old, new, 1)


# ============================================================
# PAGE.TSX — feedback no nível React, sem tocar no ciclo OpenLayers
# ============================================================
s = PAGE.read_text(encoding="utf-8")

if "layerUiTransition" not in s:
    s = replace_once(
        s,
        'import { useCallback, useEffect, useState, type FormEvent } from "react";',
        'import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";',
        "react-import",
    )

    needle = '''  const [showPassword, setShowPassword] = useState(false);\n'''
    insert = '''  const [showPassword, setShowPassword] = useState(false);\n  const [layerUiTransition, setLayerUiTransition] = useState<{\n    layerName: string;\n    enabling: boolean;\n  } | null>(null);\n  const layerUiTimerRef = useRef<number | null>(null);\n'''
    s = replace_once(s, needle, insert, "layer-transition-state")

    old = '''  const setLayerEnabled = (index: number, checked: boolean) =>\n    setEnabled((current) =>\n      current.map((value, i) => (i === index ? checked : value)),\n    );\n'''
    new = '''  const setLayerEnabled = (index: number, checked: boolean) => {\n    const layer = catalog[index];\n    if (!layer || layerUiTransition) return;\n\n    setLayerUiTransition({\n      layerName: layer.name,\n      enabling: checked,\n    });\n\n    setEnabled((current) =>\n      current.map((value, i) => (i === index ? checked : value)),\n    );\n\n    if (layerUiTimerRef.current !== null) {\n      window.clearTimeout(layerUiTimerRef.current);\n    }\n\n    // Feedback deliberadamente fora do OpenLayers: evita interferir em\n    // tileload, zoom, pan ou ciclo de vida do mapa. O bloqueio cobre apenas\n    // a troca explícita feita pelo usuário no catálogo.\n    layerUiTimerRef.current = window.setTimeout(() => {\n      setLayerUiTransition(null);\n      layerUiTimerRef.current = null;\n    }, 1100);\n  };\n\n  useEffect(() => {\n    return () => {\n      if (layerUiTimerRef.current !== null) {\n        window.clearTimeout(layerUiTimerRef.current);\n      }\n    };\n  }, []);\n'''
    s = replace_once(s, old, new, "set-layer-enabled")

    old = '''                          disabled={Boolean(incraUf !== "ALL" && layer.scopeUf && layer.scopeUf !== incraUf)}\n'''
    new = '''                          disabled={\n                            Boolean(layerUiTransition) ||\n                            Boolean(\n                              incraUf !== "ALL" &&\n                              layer.scopeUf &&\n                              layer.scopeUf !== incraUf\n                            )\n                          }\n'''
    s = replace_once(s, old, new, "switch-disabled")

    needle = '''              >\n                <GeoMap\n'''
    insert = '''              >\n                {layerUiTransition && (\n                  <div\n                    className="layer-toggle-feedback"\n                    role="status"\n                    aria-live="polite"\n                    aria-busy="true"\n                  >\n                    <div className="layer-toggle-feedback-card">\n                      <div className="layer-toggle-feedback-spinner" />\n                      <div>\n                        <strong>\n                          {layerUiTransition.enabling\n                            ? "Carregando camada…"\n                            : "Atualizando camadas…"}\n                        </strong>\n                        <span>{layerUiTransition.layerName}</span>\n                      </div>\n                    </div>\n                  </div>\n                )}\n                <GeoMap\n'''
    s = replace_once(s, needle, insert, "map-overlay")

    PAGE.write_text(s, encoding="utf-8")
    print("OK [page.tsx] - feedback universal de toggle aplicado fora do OpenLayers")
else:
    print("OK [page.tsx] - feedback universal já estava aplicado")


# ============================================================
# CSS — overlay contido apenas no mapa
# ============================================================
c = CSS.read_text(encoding="utf-8")
marker = ".layer-toggle-feedback {"
if marker not in c:
    c += r'''

/* Feedback universal ao ligar/desligar camadas.
   Não é acionado por zoom, pan ou tileload interno do OpenLayers. */
.map-canvas {
  position: relative;
}

.layer-toggle-feedback {
  position: absolute;
  inset: 0;
  z-index: 2500;
  display: grid;
  place-items: center;
  background: rgba(244, 248, 246, 0.44);
  backdrop-filter: blur(1.5px);
  pointer-events: all;
  cursor: wait;
}

.layer-toggle-feedback-card {
  min-width: 270px;
  max-width: min(420px, calc(100% - 40px));
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 16px 18px;
  border: 1px solid #bfd0c7;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 14px 38px rgba(23, 63, 51, 0.18);
  color: #173f32;
}

.layer-toggle-feedback-card strong,
.layer-toggle-feedback-card span {
  display: block;
}

.layer-toggle-feedback-card strong {
  font-size: 13px;
  line-height: 1.3;
}

.layer-toggle-feedback-card span {
  margin-top: 3px;
  font-size: 10px;
  color: #61756b;
}

.layer-toggle-feedback-spinner {
  width: 28px;
  height: 28px;
  flex: none;
  border: 3px solid #d4e1da;
  border-top-color: #237152;
  border-radius: 999px;
  animation: layer-toggle-spin 0.8s linear infinite;
}

@keyframes layer-toggle-spin {
  to {
    transform: rotate(360deg);
  }
}
'''
    CSS.write_text(c, encoding="utf-8")
    print("OK [globals.css] - overlay seguro adicionado")
else:
    print("OK [globals.css] - overlay seguro já existia")

print("SAFE_LAYER_TOGGLE_FEEDBACK_OK")
