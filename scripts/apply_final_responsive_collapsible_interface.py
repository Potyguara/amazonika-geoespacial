from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app/page.tsx"
CSS = ROOT / "app/globals.css"

page = PAGE.read_text()
css = CSS.read_text()

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
page = page.replace(
    "  FolderKanban,\n",
    "",
)

if "  PanelLeftClose," not in page:
    page = page.replace(
        "  Map,\n",
        "  Map,\n  Menu,\n  PanelLeftClose,\n  PanelLeftOpen,\n",
    )

# -----------------------------------------------------------------------------
# State
# -----------------------------------------------------------------------------
state_anchor = '  const [layerManagerOpen, setLayerManagerOpen] = useState(false);\n'
state_block = (
    state_anchor
    + '  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);\n'
    + '  const [layerPanelCollapsed, setLayerPanelCollapsed] = useState(false);\n'
    + '  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);\n'
    + '  const [mobileLayerPanelOpen, setMobileLayerPanelOpen] = useState(false);\n'
)
if "sidebarCollapsed" not in page:
    if state_anchor not in page:
        raise SystemExit("ERRO [page]: ponto de estado layerManagerOpen não encontrado")
    page = page.replace(state_anchor, state_block, 1)

# -----------------------------------------------------------------------------
# App shell and main sidebar
# -----------------------------------------------------------------------------
page = page.replace(
    '<main className="app-shell">',
    '<main className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileSidebarOpen ? "mobile-sidebar-open" : ""}`}>',
    1,
)
page = page.replace(
    '<aside className="sidebar">',
    '<aside className="sidebar">\n        <button\n          type="button"\n          className="sidebar-collapse-button"\n          onClick={() => {\n            if (window.matchMedia("(max-width: 900px)").matches) {\n              setMobileSidebarOpen(false);\n            } else {\n              setSidebarCollapsed((value) => !value);\n            }\n          }}\n          title={sidebarCollapsed ? "Expandir menu" : "Recolher menu"}\n          aria-label={sidebarCollapsed ? "Expandir menu principal" : "Recolher menu principal"}\n        >\n          {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}\n        </button>',
    1,
)

# Close mobile drawer whenever a main navigation destination is chosen.
for view in ["map", "sigef", "analyses", "sources", "users"]:
    old = f'onClick={{() => setActiveView("{view}")}}'
    new = f'onClick={{() => {{ setActiveView("{view}"); setMobileSidebarOpen(false); }}}}'
    page = page.replace(old, new)

# Remove placeholder menu items requested by user.
projects = '''          <a href="#">\n            <FolderKanban size={18} /> Projetos\n          </a>\n'''
reports = '''          <a href="#">\n            <FileText size={18} /> Relatórios\n          </a>\n'''
page = page.replace(projects, "")
page = page.replace(reports, "")

# -----------------------------------------------------------------------------
# Mobile menu trigger in topbar
# -----------------------------------------------------------------------------
topbar_anchor = '''        <header className="topbar">\n          <div>\n'''
topbar_replacement = '''        <header className="topbar">\n          <button\n            type="button"\n            className="mobile-main-menu-button"\n            onClick={() => setMobileSidebarOpen(true)}\n            aria-label="Abrir menu principal"\n            title="Menu"\n          >\n            <Menu size={20} />\n          </button>\n          <div className="topbar-title">\n'''
if "mobile-main-menu-button" not in page:
    if topbar_anchor not in page:
        raise SystemExit("ERRO [page]: topbar não localizada")
    page = page.replace(topbar_anchor, topbar_replacement, 1)

# Backdrop for mobile main drawer.
workspace_anchor = '      <section className="workspace">\n'
if "mobile-sidebar-backdrop" not in page:
    page = page.replace(
        workspace_anchor,
        '      {mobileSidebarOpen && (\n        <button\n          type="button"\n          className="mobile-sidebar-backdrop"\n          onClick={() => setMobileSidebarOpen(false)}\n          aria-label="Fechar menu principal"\n        />\n      )}\n' + workspace_anchor,
        1,
    )

# -----------------------------------------------------------------------------
# Layer panel desktop collapse + mobile drawer
# -----------------------------------------------------------------------------
page = page.replace(
    '<div className="map-layout">',
    '<div className={`map-layout ${layerPanelCollapsed ? "layer-panel-collapsed" : ""} ${mobileLayerPanelOpen ? "mobile-layer-panel-open" : ""}`}>',
    1,
)
page = page.replace(
    '<section className="layer-panel">',
    '<section className="layer-panel">',
    1,
)

panel_heading_anchor = '''                <div className="panel-heading">\n                  <div>\n                    <p className="eyebrow">CATÁLOGO</p>\n                    <h2>Camadas de análise</h2>\n                  </div>\n                  <Badge variant="secondary">\n                    {enabled.filter(Boolean).length} ativas\n                  </Badge>\n                </div>\n'''
panel_heading_new = '''                <div className="panel-heading">\n                  <div>\n                    <p className="eyebrow">CATÁLOGO</p>\n                    <h2>Camadas de análise</h2>\n                  </div>\n                  <div className="panel-heading-actions">\n                    <Badge variant="secondary">\n                      {enabled.filter(Boolean).length} ativas\n                    </Badge>\n                    <button\n                      type="button"\n                      className="layer-panel-collapse-button"\n                      onClick={() => {\n                        if (window.matchMedia("(max-width: 900px)").matches) {\n                          setMobileLayerPanelOpen(false);\n                        } else {\n                          setLayerPanelCollapsed(true);\n                        }\n                      }}\n                      aria-label="Recolher painel de camadas"\n                      title="Recolher camadas"\n                    >\n                      <PanelLeftClose size={17} />\n                    </button>\n                  </div>\n                </div>\n'''
if "layer-panel-collapse-button" not in page:
    if panel_heading_anchor not in page:
        raise SystemExit("ERRO [page]: cabeçalho do painel de camadas não localizado")
    page = page.replace(panel_heading_anchor, panel_heading_new, 1)

map_canvas_anchor = '''              <section\n                className="map-canvas"\n                aria-label="Mapa de análise territorial"\n              >\n'''
map_canvas_new = map_canvas_anchor + '''                <button\n                  type="button"\n                  className={`layer-panel-open-button ${layerPanelCollapsed ? "visible" : ""}`}\n                  onClick={() => {\n                    if (window.matchMedia("(max-width: 900px)").matches) {\n                      setMobileLayerPanelOpen(true);\n                    } else {\n                      setLayerPanelCollapsed(false);\n                    }\n                  }}\n                  aria-label="Abrir painel de camadas"\n                  title="Camadas"\n                >\n                  <Layers3 size={18} />\n                  <span>Camadas</span>\n                </button>\n'''
if "layer-panel-open-button" not in page:
    if map_canvas_anchor not in page:
        raise SystemExit("ERRO [page]: canvas do mapa não localizado")
    page = page.replace(map_canvas_anchor, map_canvas_new, 1)

# On mobile, button must always be available even though desktop state can be false.
# CSS handles visibility for <=900px.

# Mobile backdrop specifically for layer drawer, kept inside map layout.
geo_anchor = '                <GeoMap\n'
if "mobile-layer-backdrop" not in page:
    page = page.replace(
        geo_anchor,
        '                {mobileLayerPanelOpen && (\n                  <button\n                    type="button"\n                    className="mobile-layer-backdrop"\n                    onClick={() => setMobileLayerPanelOpen(false)}\n                    aria-label="Fechar painel de camadas"\n                  />\n                )}\n' + geo_anchor,
        1,
    )

# -----------------------------------------------------------------------------
# CSS
# -----------------------------------------------------------------------------
marker = "/* FINAL_RESPONSIVE_COLLAPSIBLE_INTERFACE */"
if marker not in css:
    css += r'''

/* FINAL_RESPONSIVE_COLLAPSIBLE_INTERFACE */
.app-shell,
.sidebar,
.workspace,
.map-layout,
.layer-panel {
  transition: grid-template-columns 180ms ease, width 180ms ease, transform 180ms ease, padding 180ms ease;
}

.sidebar {
  position: relative;
  overflow: hidden;
}

.sidebar-collapse-button {
  position: absolute;
  top: 14px;
  right: 10px;
  z-index: 5;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid #ffffff24;
  border-radius: 8px;
  background: #ffffff10;
  color: #d9ebe1;
  cursor: pointer;
}

.sidebar-collapse-button:hover {
  background: #ffffff1d;
  color: #fff;
}

.app-shell.sidebar-collapsed {
  grid-template-columns: 72px 1fr;
}

.sidebar-collapsed .sidebar {
  padding-left: 10px;
  padding-right: 10px;
}

.sidebar-collapsed .brand {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
  padding-top: 38px;
}

.sidebar-collapsed .brand > div:not(.brand-mark),
.sidebar-collapsed .main-nav button > :not(svg),
.sidebar-collapsed .main-nav a > :not(svg),
.sidebar-collapsed .sidebar-bottom > a > :not(svg),
.sidebar-collapsed .authenticated-user-info,
.sidebar-collapsed .logout-button {
  display: none;
}

.sidebar-collapsed .main-nav button,
.sidebar-collapsed .main-nav a,
.sidebar-collapsed .sidebar-bottom > a {
  width: 48px;
  min-width: 48px;
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
  font-size: 0;
}

.sidebar-collapsed .main-nav button svg,
.sidebar-collapsed .main-nav a svg,
.sidebar-collapsed .sidebar-bottom > a svg {
  margin: 0;
}

.sidebar-collapsed .user-card {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}

.mobile-main-menu-button,
.mobile-sidebar-backdrop {
  display: none;
}

.panel-heading-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.layer-panel-collapse-button {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  flex: none;
  border: 1px solid #d5e0da;
  border-radius: 7px;
  background: #f7faf8;
  color: #245440;
  cursor: pointer;
}

.layer-panel-collapse-button:hover {
  background: #eaf3ee;
}

.map-layout.layer-panel-collapsed {
  grid-template-columns: 0 1fr;
}

.layer-panel-collapsed > .layer-panel {
  width: 0;
  min-width: 0;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
  border-right: 0;
}

.layer-panel-open-button {
  position: absolute;
  z-index: 45;
  left: 12px;
  top: 78px;
  min-height: 38px;
  padding: 0 12px;
  display: none;
  align-items: center;
  gap: 7px;
  border: 1px solid #c7d5cd;
  border-radius: 9px;
  background: #fffffff2;
  color: #174d3a;
  box-shadow: 0 6px 20px #173f3324;
  backdrop-filter: blur(8px);
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}

.layer-panel-open-button.visible {
  display: flex;
}

.mobile-layer-backdrop {
  display: none;
}

@media (max-width: 1180px) {
  .workspace {
    padding: 18px;
  }
  .status-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .status-strip > div:nth-child(2) {
    border-right: 0;
  }
  .status-strip > div:last-child {
    grid-column: 1 / -1;
    border-top: 1px solid var(--line);
  }
  .map-layout {
    grid-template-columns: 275px 1fr;
  }
}

@media (max-width: 900px) {
  .app-shell,
  .app-shell.sidebar-collapsed {
    display: block;
    min-height: 100dvh;
  }

  .sidebar,
  .sidebar-collapsed .sidebar {
    position: fixed;
    z-index: 120;
    inset: 0 auto 0 0;
    width: min(290px, 86vw);
    min-height: 100dvh;
    padding: 22px 16px 18px;
    transform: translateX(-103%);
    box-shadow: 18px 0 45px #0d2e2550;
    overflow-y: auto;
  }

  .mobile-sidebar-open .sidebar {
    transform: translateX(0);
  }

  .sidebar-collapsed .brand > div:not(.brand-mark),
  .sidebar-collapsed .authenticated-user-info,
  .sidebar-collapsed .logout-button {
    display: block;
  }

  .sidebar-collapsed .brand,
  .brand {
    justify-content: flex-start;
    padding: 0 44px 22px 7px;
  }

  .sidebar-collapsed .main-nav button,
  .sidebar-collapsed .main-nav a,
  .sidebar-collapsed .sidebar-bottom > a {
    width: 100%;
    min-width: 0;
    justify-content: flex-start;
    padding: 11px 12px;
    font-size: 13px;
  }

  .sidebar-collapsed .user-card {
    justify-content: flex-start;
    padding: 12px 8px 0;
  }

  .sidebar-collapse-button {
    top: 16px;
    right: 13px;
  }

  .mobile-sidebar-backdrop {
    position: fixed;
    z-index: 110;
    inset: 0;
    display: block;
    border: 0;
    background: #071b158c;
    backdrop-filter: blur(2px);
  }

  .workspace {
    width: 100%;
    padding: 12px;
  }

  .topbar {
    gap: 10px;
    margin-bottom: 12px;
  }

  .mobile-main-menu-button {
    width: 40px;
    height: 40px;
    display: grid;
    place-items: center;
    flex: none;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: #fff;
    color: #174d3a;
  }

  .topbar-title {
    min-width: 0;
    flex: 1;
  }

  .topbar .eyebrow {
    display: none;
  }

  .topbar h1 {
    font-size: 20px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .top-actions {
    gap: 6px;
  }

  .search-box {
    display: none;
  }

  .new-analysis {
    min-height: 40px !important;
    padding: 0 12px !important;
    white-space: nowrap;
  }

  .status-strip {
    grid-template-columns: 1fr;
    margin-bottom: 10px;
    max-height: 116px;
    overflow-y: auto;
  }

  .status-strip > div,
  .status-strip > div:nth-child(2),
  .status-strip > div:last-child {
    grid-column: auto;
    border-right: 0;
    border-top: 1px solid var(--line);
    padding: 9px 11px;
  }

  .status-strip > div:first-child {
    border-top: 0;
  }

  .map-layout,
  .map-layout.layer-panel-collapsed {
    position: relative;
    display: block;
    height: calc(100dvh - 190px);
    min-height: 520px;
    overflow: hidden;
  }

  .map-layout > .layer-panel,
  .layer-panel-collapsed > .layer-panel {
    position: absolute;
    z-index: 70;
    inset: 0 auto 0 0;
    width: min(330px, 88vw);
    min-width: 0;
    height: 100%;
    opacity: 1;
    pointer-events: auto;
    transform: translateX(-103%);
    background: #fff;
    border-right: 1px solid var(--line);
    box-shadow: 14px 0 34px #173f3340;
    overflow: hidden;
  }

  .mobile-layer-panel-open > .layer-panel {
    transform: translateX(0);
  }

  .map-canvas {
    width: 100%;
    height: 100%;
  }

  .layer-panel-open-button,
  .layer-panel-open-button.visible {
    top: 72px;
    display: flex;
  }

  .mobile-layer-backdrop {
    position: absolute;
    z-index: 65;
    inset: 0;
    display: block;
    border: 0;
    background: #0a211a66;
  }

  .analysis-card {
    right: 8px;
    bottom: 8px;
    width: min(360px, calc(100% - 16px));
    max-height: 52%;
    overflow-y: auto;
  }
}

@media (max-width: 600px) {
  .workspace {
    padding: 8px;
  }

  .topbar {
    min-height: 44px;
  }

  .topbar h1 {
    font-size: 17px;
  }

  .new-analysis {
    font-size: 10px !important;
    padding-inline: 10px !important;
  }

  .new-analysis svg {
    width: 15px;
    height: 15px;
  }

  .status-strip {
    display: none;
  }

  .map-layout,
  .map-layout.layer-panel-collapsed {
    height: calc(100dvh - 70px);
    min-height: 460px;
    border-radius: 9px;
  }

  .layer-panel-open-button,
  .layer-panel-open-button.visible {
    top: 66px;
    left: 8px;
    padding: 0 9px;
  }

  .layer-panel-open-button span {
    display: none;
  }

  .map-toolbar {
    max-width: calc(100% - 16px);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .map-toolbar::-webkit-scrollbar {
    display: none;
  }

  .identify-panel,
  .identify-candidates-panel {
    right: 8px;
    width: calc(100% - 16px);
    max-width: none;
  }

  .analysis-card {
    left: 8px;
    right: 8px;
    width: auto;
    max-height: 46%;
  }
}
'''

PAGE.write_text(page)
CSS.write_text(css)
print("OK [page] - Projetos e Relatórios removidos do menu principal")
print("OK [page] - menu principal recolhível no desktop e drawer no mobile")
print("OK [page] - painel de camadas recolhível no desktop e drawer no mobile")
print("OK [css] - responsividade adaptativa para desktop, tablet e celular")
print("FINAL_RESPONSIVE_COLLAPSIBLE_INTERFACE_OK")
