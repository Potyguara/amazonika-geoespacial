from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/globals.css"

css = CSS.read_text()
marker = "/* MOBILE_EXPERIENCE_V2 */"

if marker in css:
    print("OK [mobile-v2] - ajustes já aplicados")
    raise SystemExit(0)

css += r'''

/* MOBILE_EXPERIENCE_V2 */
@media (max-width: 900px) {
  html,
  body {
    width: 100%;
    max-width: 100%;
    overflow-x: hidden;
  }

  .app-shell,
  .app-shell.sidebar-collapsed {
    display: block !important;
    width: 100% !important;
    min-width: 0 !important;
    min-height: 100dvh !important;
  }

  .workspace {
    width: 100% !important;
    min-width: 0 !important;
    padding: 8px !important;
  }

  .topbar {
    display: grid !important;
    grid-template-columns: 44px minmax(0, 1fr) auto !important;
    align-items: center !important;
    gap: 8px !important;
    margin: 0 0 8px !important;
    min-height: 48px !important;
  }

  .mobile-main-menu-button {
    width: 42px !important;
    height: 42px !important;
    border-radius: 10px !important;
  }

  .topbar-title {
    min-width: 0 !important;
    overflow: hidden !important;
  }

  .topbar-title .eyebrow {
    display: none !important;
  }

  .topbar h1 {
    margin: 0 !important;
    max-width: 100% !important;
    font-size: 18px !important;
    line-height: 1.05 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
  }

  .top-actions {
    display: flex !important;
    min-width: 0 !important;
    gap: 6px !important;
  }

  .top-actions .search-box {
    display: none !important;
  }

  .new-analysis {
    height: 42px !important;
    min-width: 0 !important;
    padding: 0 12px !important;
    border-radius: 10px !important;
    font-size: 11px !important;
    white-space: nowrap !important;
  }

  .status-strip {
    display: none !important;
  }

  .map-layout,
  .map-layout.layer-panel-collapsed {
    display: block !important;
    position: relative !important;
    width: 100% !important;
    min-width: 0 !important;
    height: calc(100dvh - 76px) !important;
    min-height: 560px !important;
    border-radius: 12px !important;
    overflow: hidden !important;
  }

  .map-canvas {
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
  }

  /* Menu principal como drawer real, sempre vertical. */
  .sidebar,
  .sidebar-collapsed .sidebar {
    position: fixed !important;
    z-index: 150 !important;
    inset: 0 auto 0 0 !important;
    width: min(320px, 86vw) !important;
    height: 100dvh !important;
    min-height: 100dvh !important;
    padding: max(18px, env(safe-area-inset-top)) 14px max(18px, env(safe-area-inset-bottom)) !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
    align-items: stretch !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    transform: translateX(-104%) !important;
  }

  .mobile-sidebar-open .sidebar {
    transform: translateX(0) !important;
  }

  .sidebar .brand,
  .sidebar-collapsed .brand {
    display: flex !important;
    flex: 0 0 auto !important;
    width: 100% !important;
    justify-content: flex-start !important;
    align-items: center !important;
    gap: 11px !important;
    margin: 0 !important;
    padding: 4px 44px 18px 4px !important;
  }

  .sidebar .brand > div:not(.brand-mark),
  .sidebar-collapsed .brand > div:not(.brand-mark) {
    display: block !important;
  }

  .sidebar .main-nav,
  .sidebar-collapsed .main-nav {
    display: grid !important;
    grid-template-columns: 1fr !important;
    width: 100% !important;
    gap: 5px !important;
    padding: 14px 0 0 !important;
    margin: 0 !important;
  }

  .sidebar .main-nav button,
  .sidebar .main-nav a,
  .sidebar-collapsed .main-nav button,
  .sidebar-collapsed .main-nav a {
    display: flex !important;
    width: 100% !important;
    min-width: 0 !important;
    justify-content: flex-start !important;
    align-items: center !important;
    gap: 12px !important;
    padding: 12px !important;
    font-size: 13px !important;
    text-align: left !important;
  }

  .sidebar .sidebar-bottom,
  .sidebar-collapsed .sidebar-bottom {
    width: 100% !important;
    margin-top: auto !important;
    padding-top: 12px !important;
  }

  .sidebar .user-card,
  .sidebar-collapsed .user-card {
    width: 100% !important;
    justify-content: flex-start !important;
  }

  .sidebar .authenticated-user-info,
  .sidebar-collapsed .authenticated-user-info,
  .sidebar .logout-button,
  .sidebar-collapsed .logout-button {
    display: block !important;
  }

  .mobile-sidebar-backdrop {
    position: fixed !important;
    z-index: 140 !important;
    inset: 0 !important;
    display: block !important;
    width: 100vw !important;
    height: 100dvh !important;
    padding: 0 !important;
    border: 0 !important;
    background: rgba(7, 27, 21, 0.58) !important;
    backdrop-filter: blur(2px) !important;
  }

  /* Painel de camadas também vira drawer e não comprime o mapa. */
  .map-layout > .layer-panel,
  .map-layout.layer-panel-collapsed > .layer-panel {
    position: fixed !important;
    z-index: 145 !important;
    inset: 0 auto 0 0 !important;
    width: min(340px, 88vw) !important;
    height: 100dvh !important;
    min-height: 100dvh !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    background: #fff !important;
    border-right: 1px solid var(--line) !important;
    transform: translateX(-104%) !important;
    overflow: hidden !important;
  }

  .map-layout.mobile-layer-panel-open > .layer-panel {
    transform: translateX(0) !important;
  }

  .layer-panel .layer-list {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    -webkit-overflow-scrolling: touch !important;
  }

  .mobile-layer-backdrop {
    position: fixed !important;
    z-index: 144 !important;
    inset: 0 !important;
    display: block !important;
    width: 100vw !important;
    height: 100dvh !important;
    border: 0 !important;
    background: rgba(7, 27, 21, 0.42) !important;
    backdrop-filter: blur(1px) !important;
  }

  .layer-panel-open-button,
  .layer-panel-open-button.visible {
    display: grid !important;
    place-items: center !important;
    left: 12px !important;
    top: 132px !important;
    width: 44px !important;
    height: 44px !important;
    min-height: 44px !important;
    padding: 0 !important;
    border-radius: 10px !important;
  }

  .layer-panel-open-button span {
    display: none !important;
  }

  /* Ferramentas do mapa: compactas, uma única faixa rolável. */
  .map-toolbar,
  .geo-map-toolbar,
  .map-tools,
  .ol-map-toolbar {
    max-width: calc(100% - 24px) !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    scrollbar-width: none !important;
    -webkit-overflow-scrolling: touch !important;
  }

  .map-toolbar::-webkit-scrollbar,
  .geo-map-toolbar::-webkit-scrollbar,
  .map-tools::-webkit-scrollbar,
  .ol-map-toolbar::-webkit-scrollbar {
    display: none !important;
  }

  .analysis-card {
    right: 10px !important;
    bottom: 10px !important;
    left: 10px !important;
    width: auto !important;
    max-width: none !important;
    max-height: 46dvh !important;
    overflow-y: auto !important;
  }

  .identify-candidates-panel,
  .identified-feature-panel,
  .identify-panel {
    left: 10px !important;
    right: 10px !important;
    width: auto !important;
    max-width: none !important;
    max-height: 58dvh !important;
  }
}

@media (max-width: 430px) {
  .workspace {
    padding: 6px !important;
  }

  .topbar {
    grid-template-columns: 42px minmax(0, 1fr) auto !important;
    gap: 6px !important;
  }

  .topbar h1 {
    font-size: 16px !important;
  }

  .new-analysis {
    height: 40px !important;
    padding: 0 10px !important;
    font-size: 10px !important;
  }

  .map-layout,
  .map-layout.layer-panel-collapsed {
    height: calc(100dvh - 68px) !important;
    border-radius: 10px !important;
  }
}
'''

CSS.write_text(css)
print("OK [mobile-v2] - drawer principal reorganizado")
print("OK [mobile-v2] - painel de camadas não comprime o mapa")
print("OK [mobile-v2] - topbar e mapa priorizados no celular")
print("MOBILE_EXPERIENCE_V2_OK")
