from pathlib import Path

GEO = Path("components/geo-map.tsx")
CSS = Path("app/globals.css")

geo = GEO.read_text()
css = CSS.read_text()

# Backup local safety handled by script on VPS.
backup = GEO.with_suffix(GEO.suffix + ".bak-universal-identify-20260902")
if not backup.exists():
    backup.write_text(geo)

css_backup = CSS.with_suffix(CSS.suffix + ".bak-universal-identify-20260902")
if not css_backup.exists():
    css_backup.write_text(css)

# 1. Universal, high-contrast identify highlight. This is deliberately
# independent from source name, institution, feature count, or source style.
needle = '''const selectedOfficialStyle = new Style({
  fill: new Fill({ color: "rgba(255, 193, 7, 0.35)" }),
  stroke: new Stroke({ color: "#ff9f1c", width: 4 }),
  image: new CircleStyle({
    radius: 7,
    fill: new Fill({ color: "#ff9f1c" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});
'''
replacement = needle + '''
// Destaque universal da ferramenta Identificar.
// Duas passadas de estilo garantem contraste sobre qualquer camada/base.
const identifyHighlightStyles = [
  new Style({
    fill: new Fill({ color: "rgba(255, 159, 28, 0.12)" }),
    stroke: new Stroke({ color: "rgba(255,255,255,0.96)", width: 8 }),
    image: new CircleStyle({
      radius: 11,
      fill: new Fill({ color: "rgba(255,255,255,0.96)" }),
      stroke: new Stroke({ color: "rgba(23,63,50,0.35)", width: 2 }),
    }),
  }),
  selectedOfficialStyle,
];
'''
if "const identifyHighlightStyles" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: estilo de seleção base não localizado")
    geo = geo.replace(needle, replacement, 1)

# 2. Identify request state (separate from attribute-detail loading).
needle = '''  const [identifiedFeature, setIdentifiedFeature] =
    useState<IdentifiedFeature | null>(null);
'''
replacement = needle + '''  const [identifyLoading, setIdentifyLoading] = useState(false);
  const [identifyLoadingMessage, setIdentifyLoadingMessage] = useState(
    "Aguardando informações…",
  );
'''
if "const [identifyLoading, setIdentifyLoading]" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: estado identifiedFeature não localizado")
    geo = geo.replace(needle, replacement, 1)

# 3. Selection overlay always uses universal high-contrast styles.
needle = '''          source: identifySelectionSourceRef.current,
          zIndex: 1000,
          style: selectedOfficialStyle,
'''
replacement = '''          source: identifySelectionSourceRef.current,
          zIndex: 1000,
          style: identifyHighlightStyles,
'''
if "style: identifyHighlightStyles" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: camada overlay de identificação não localizada")
    geo = geo.replace(needle, replacement, 1)

# 4. Start feedback immediately on click, before PostGIS request.
needle = '''      if (!identifyActiveRef.current) return;

      clearIdentifiedFeature();

      const enabledLayers = layersRef.current.filter(
'''
replacement = '''      if (!identifyActiveRef.current) return;

      clearIdentifiedFeature();
      setIdentifyLoading(true);
      setIdentifyLoadingMessage("Consultando feições nas camadas ativas…");

      const enabledLayers = layersRef.current.filter(
'''
if 'setIdentifyLoadingMessage("Consultando feições nas camadas ativas…")' not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: início do identifyAtPixel não localizado")
    geo = geo.replace(needle, replacement, 1)

# 5. Stop request feedback before selecting one returned PostGIS feature.
needle = '''            if (candidates.length === 1) {
              selectFeatureRef.current(
                candidates[0].feature,
              );
              return;
            }
'''
replacement = '''            if (candidates.length === 1) {
              setIdentifyLoading(false);
              selectFeatureRef.current(
                candidates[0].feature,
              );
              return;
            }
'''
if "candidates.length === 1) {\n              setIdentifyLoading(false);" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: retorno de candidato único não localizado")
    geo = geo.replace(needle, replacement, 1)

# 6. Stop request feedback before showing multiple candidates.
needle = '''            if (candidates.length > 1) {
              identifyCandidateHistoryRef.current =
                candidates;
              setIdentifyCandidates(candidates);
              return;
            }
'''
replacement = '''            if (candidates.length > 1) {
              setIdentifyLoading(false);
              identifyCandidateHistoryRef.current =
                candidates;
              setIdentifyCandidates(candidates);
              return;
            }
'''
if "candidates.length > 1) {\n              setIdentifyLoading(false);" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: retorno de múltiplos candidatos não localizado")
    geo = geo.replace(needle, replacement, 1)

# 7. On backend failure, keep useful feedback while visual fallback runs.
needle = '''          console.warn(
            "Identificação vetorial local indisponível; tentando fallback visual/WMS.",
            error,
          );
'''
replacement = '''          console.warn(
            "Identificação vetorial local indisponível; tentando fallback visual/WMS.",
            error,
          );
          setIdentifyLoadingMessage("Verificando feições visíveis no mapa…");
'''
if 'setIdentifyLoadingMessage("Verificando feições visíveis no mapa…")' not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: fallback do identificar não localizado")
    geo = geo.replace(needle, replacement, 1)

# 8. Rendered candidate returns also stop request feedback.
needle = '''      if (renderedCandidates.length === 1) {
        selectFeatureRef.current(
          renderedCandidates[0],
        );
        return;
      }
'''
replacement = '''      if (renderedCandidates.length === 1) {
        setIdentifyLoading(false);
        selectFeatureRef.current(
          renderedCandidates[0],
        );
        return;
      }
'''
if "renderedCandidates.length === 1) {\n        setIdentifyLoading(false);" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: fallback candidato único não localizado")
    geo = geo.replace(needle, replacement, 1)

needle = '''      if (renderedCandidates.length > 1) {
        const candidates =
          renderedCandidates.map((feature) => ({
'''
replacement = '''      if (renderedCandidates.length > 1) {
        setIdentifyLoading(false);
        const candidates =
          renderedCandidates.map((feature) => ({
'''
if "renderedCandidates.length > 1) {\n        setIdentifyLoading(false);" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: fallback múltiplos candidatos não localizado")
    geo = geo.replace(needle, replacement, 1)

# 9. No feature found: end feedback cleanly.
needle = '''      // WMS é somente referência visual. A ferramenta Identificar
      // trabalha exclusivamente com geometrias vetoriais presentes no PostGIS.
      setIdentifiedFeature(null);
'''
replacement = '''      // WMS é somente referência visual. A ferramenta Identificar
      // trabalha exclusivamente com geometrias vetoriais presentes no PostGIS.
      setIdentifyLoading(false);
      setIdentifiedFeature(null);
'''
if "// trabalha exclusivamente com geometrias vetoriais presentes no PostGIS.\n      setIdentifyLoading(false);" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: final sem feição não localizado")
    geo = geo.replace(needle, replacement, 1)

# 10. Abort path must not leave loading feedback stuck.
needle = '''            return;
          }

          console.warn(
            "Identificação vetorial local indisponível; tentando fallback visual/WMS.",
'''
replacement = '''            setIdentifyLoading(false);
            return;
          }

          console.warn(
            "Identificação vetorial local indisponível; tentando fallback visual/WMS.",
'''
if "error.name === \"AbortError\"" in geo and "setIdentifyLoading(false);\n            return;\n          }\n\n          console.warn" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: caminho AbortError não localizado")
    geo = geo.replace(needle, replacement, 1)

# 11. Clear/disable identify also clears loading state.
needle = '''    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;
    if (selectedFeatureRef.current) {
'''
replacement = '''    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;
    setIdentifyLoading(false);
    if (selectedFeatureRef.current) {
'''
if "identifyAbortRef.current = null;\n    setIdentifyLoading(false);" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: clearIdentifiedFeature não localizado")
    geo = geo.replace(needle, replacement, 1)

# Because clearIdentifiedFeature above resets loading, click start sets it right after clear.

# 12. Add request-level feedback over map, separate from attribute panel.
needle = '''      {identifyActive &&
        !identifiedFeature &&
        identifyCandidates.length === 0 && (
          <div className="identify-hint">
            Clique sobre uma feição oficial para consultar seus dados
          </div>
        )}
'''
replacement = '''      {identifyLoading && (
        <div className="identify-request-loading" role="status" aria-live="polite">
          <span className="identify-request-spinner" aria-hidden="true" />
          <div>
            <strong>Aguardando informações</strong>
            <small>{identifyLoadingMessage}</small>
          </div>
        </div>
      )}
      {identifyActive &&
        !identifyLoading &&
        !identifiedFeature &&
        identifyCandidates.length === 0 && (
          <div className="identify-hint">
            Clique sobre uma feição territorial para consultar seus dados
          </div>
        )}
'''
if 'className="identify-request-loading"' not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: hint da ferramenta Identificar não localizado")
    geo = geo.replace(needle, replacement, 1)

# 13. Improve attribute-detail loading feedback with spinner.
needle = '''          {identifiedFeature.loading ? (
            <div className="feature-info-loading">
              Consultando atributos completos…
            </div>
'''
replacement = '''          {identifiedFeature.loading ? (
            <div className="feature-info-loading">
              <span className="identify-request-spinner" aria-hidden="true" />
              <div>
                <strong>Carregando informações</strong>
                <small>Consultando atributos completos da feição…</small>
              </div>
            </div>
'''
if "Consultando atributos completos da feição…" not in geo:
    if needle not in geo:
        raise SystemExit("ERRO [geo-map]: loading de atributos não localizado")
    geo = geo.replace(needle, replacement, 1)

GEO.write_text(geo)

# CSS: all scoped to identify UI, no OpenLayers lifecycle hooks.
css_block = r'''

/* =========================================================
   IDENTIFICAR — FEEDBACK E DESTAQUE UNIVERSAIS
   ========================================================= */
.identify-request-loading {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 1205;
  transform: translate(-50%, -50%);
  min-width: 270px;
  max-width: min(390px, calc(100% - 40px));
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid rgba(23, 77, 58, 0.18);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 18px 50px rgba(23, 63, 51, 0.28);
  color: #173f33;
  pointer-events: all;
}
.identify-request-loading::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  background: rgba(238, 244, 240, 0.16);
  backdrop-filter: blur(1px);
}
.identify-request-loading strong,
.identify-request-loading small {
  display: block;
}
.identify-request-loading strong {
  font-size: 12px;
  font-weight: 850;
  letter-spacing: 0.01em;
}
.identify-request-loading small {
  margin-top: 2px;
  font-size: 9.5px;
  line-height: 1.35;
  color: #677970;
}
.identify-request-spinner {
  width: 21px;
  height: 21px;
  flex: 0 0 21px;
  border: 3px solid #d9e6df;
  border-top-color: #1c7454;
  border-radius: 999px;
  animation: amazonika-identify-spin 0.75s linear infinite;
}
@keyframes amazonika-identify-spin {
  to { transform: rotate(360deg); }
}
.feature-info-loading {
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 11px;
  padding: 16px;
  color: #173f33;
  background: #f7faf8;
}
.feature-info-loading strong,
.feature-info-loading small {
  display: block;
}
.feature-info-loading strong {
  font-size: 10.5px;
  font-weight: 850;
}
.feature-info-loading small {
  margin-top: 2px;
  font-size: 9px;
  line-height: 1.35;
  color: #6b7b73;
}
'''

if "IDENTIFICAR — FEEDBACK E DESTAQUE UNIVERSAIS" not in css:
    css += css_block
    CSS.write_text(css)

print("OK [geo-map] - destaque universal reforçado para qualquer feição PostGIS")
print("OK [geo-map] - feedback imediato durante consulta de identificação")
print("OK [geo-map] - feedback de atributos completos melhorado")
print("OK [globals.css] - estados visuais universais adicionados")
print("UNIVERSAL_IDENTIFY_FEEDBACK_OK")
