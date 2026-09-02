from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/globals.css"

css = CSS.read_text()
marker = "/* MOBILE_LAYER_DRAWER_V3 */"

if marker in css:
    print("OK [mobile-layer-v3] - correção já aplicada")
    raise SystemExit(0)

css += r'''

/* MOBILE_LAYER_DRAWER_V3
   O painel de camadas deve ficar SEMPRE acima do backdrop no celular.
   O backdrop escurece apenas o mapa e fecha o drawer ao toque.
*/
@media (max-width: 900px) {
  .map-layout {
    position: relative;
    overflow: visible !important;
  }

  .map-layout > .layer-panel {
    position: fixed !important;
    z-index: 162 !important;
    top: env(safe-area-inset-top, 0px) !important;
    bottom: 0 !important;
    left: 0 !important;
    right: auto !important;
    width: min(88vw, 360px) !important;
    max-width: 360px !important;
    height: 100dvh !important;
    min-height: 100dvh !important;
    display: block !important;
    opacity: 1 !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    overscroll-behavior: contain;
    background: #f8fbf9 !important;
    border-right: 1px solid #cddbd4 !important;
    box-shadow: 18px 0 48px rgba(7, 32, 24, .28) !important;
    transform: translate3d(-104%, 0, 0) !important;
    transition: transform 180ms ease !important;
    pointer-events: none !important;
    visibility: hidden !important;
  }

  .map-layout.mobile-layer-panel-open > .layer-panel {
    transform: translate3d(0, 0, 0) !important;
    pointer-events: auto !important;
    visibility: visible !important;
  }

  .mobile-layer-backdrop {
    position: fixed !important;
    z-index: 158 !important;
    inset: 0 !important;
    display: block !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: rgba(6, 27, 21, .48) !important;
    backdrop-filter: blur(1.5px) !important;
    -webkit-backdrop-filter: blur(1.5px) !important;
    cursor: pointer !important;
  }

  /* O botão Camadas precisa continuar clicável quando o drawer estiver fechado. */
  .layer-panel-open-button {
    z-index: 70 !important;
  }

  /* Quando o drawer está aberto, não deixamos controles do mapa atravessarem o painel. */
  .mobile-layer-panel-open .map-canvas,
  .mobile-layer-panel-open .geo-tools,
  .mobile-layer-panel-open .feature-info-panel {
    isolation: isolate;
  }

  .layer-panel .panel-heading {
    position: sticky;
    top: 0;
    z-index: 3;
    background: #f8fbf9;
  }

  .layer-panel-collapse-button {
    display: grid !important;
    width: 38px !important;
    height: 38px !important;
    flex: none !important;
  }
}

@media (max-width: 520px) {
  .map-layout > .layer-panel {
    width: min(92vw, 350px) !important;
  }
}
'''

CSS.write_text(css)
print("OK [mobile-layer-v3] - painel de camadas elevado acima do backdrop")
print("OK [mobile-layer-v3] - drawer fixo com rolagem e fechamento preservado")
print("MOBILE_LAYER_DRAWER_V3_OK")
