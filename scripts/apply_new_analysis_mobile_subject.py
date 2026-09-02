from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        print(f"OK [{label}] - já aplicado")
        return
    if old not in text:
        raise SystemExit(f"ERRO [{label}] - ponto de inserção não localizado em {path}")
    path.write_text(text.replace(old, new, 1))
    print(f"OK [{label}]")


# -----------------------------------------------------------------------------
# FRONTEND: fluxo explícito de Nova Análise + cadastro mínimo do detentor
# -----------------------------------------------------------------------------
PAGE = ROOT / "app/page.tsx"
page = PAGE.read_text()
backup = PAGE.with_suffix(PAGE.suffix + ".bak-new-analysis-mobile-subject-20260902")
if not backup.exists():
    backup.write_text(page)

replace_once(
    PAGE,
    '  const [analysisError, setAnalysisError] = useState<string | null>(null);\n',
    '  const [analysisError, setAnalysisError] = useState<string | null>(null);\n'
    '  const [analysisSessionOpen, setAnalysisSessionOpen] = useState(false);\n'
    '  const [analysisDraftReady, setAnalysisDraftReady] = useState(false);\n'
    '  const [analysisAreaName, setAnalysisAreaName] = useState("");\n'
    '  const [analysisHolderName, setAnalysisHolderName] = useState("");\n'
    '  const [analysisHolderDocument, setAnalysisHolderDocument] = useState("");\n'
    '  const [analysisResetNonce, setAnalysisResetNonce] = useState(0);\n',
    "page-state",
)

page = PAGE.read_text()
old = '''  const geometryChanged = useCallback(
    (geometry: Record<string, unknown> | null) => {
      setSubjectGeometry(geometry);
      setAnalysis(null);
      setAnalysisError(null);
    },
    [],
  );

  const runSpatialAnalysis = async () => {
'''
new = '''  const geometryChanged = useCallback(
    (geometry: Record<string, unknown> | null) => {
      setSubjectGeometry(geometry);
      setAnalysis(null);
      setAnalysisError(null);
    },
    [],
  );

  const beginNewAnalysis = () => {
    setActiveView("map");
    setAnalysisSessionOpen(true);
    setAnalysisDraftReady(false);
    setAnalysisAreaName("");
    setAnalysisHolderName("");
    setAnalysisHolderDocument("");
    setSubjectGeometry(null);
    setAnalysis(null);
    setAnalysisError(null);
    setAnalysisProgress("");
    setAnalysisResetNonce((current) => current + 1);
  };

  const confirmAnalysisRegistration = () => {
    const areaName = analysisAreaName.trim();
    const holderName = analysisHolderName.trim();
    const digits = analysisHolderDocument.replace(/\\D/g, "");

    if (!areaName || !holderName) {
      setAnalysisError("Informe o nome da área/imóvel e o detentor para iniciar a análise.");
      return;
    }

    if (digits && digits.length !== 11 && digits.length !== 14) {
      setAnalysisError("CPF/CNPJ deve possuir 11 ou 14 dígitos.");
      return;
    }

    setAnalysisError(null);
    setAnalysisDraftReady(true);
  };

  const runSpatialAnalysis = async () => {
'''
if "const beginNewAnalysis = () =>" not in page:
    if old not in page:
        raise SystemExit("ERRO [page-actions] bloco geometryChanged não localizado")
    PAGE.write_text(page.replace(old, new, 1))
    print("OK [page-actions]")
else:
    print("OK [page-actions] - já aplicado")

page = PAGE.read_text()
replace_once(
    PAGE,
    '          name: `Consulta ${new Date().toLocaleString("pt-BR")}`,\n          geometry: subjectGeometry,\n          source_ids: sourceIds,\n          incra_uf: incraUf,\n',
    '          name: analysisAreaName.trim() || `Consulta ${new Date().toLocaleString("pt-BR")}`,\n'
    '          geometry: subjectGeometry,\n'
    '          source_ids: sourceIds,\n'
    '          incra_uf: incraUf,\n'
    '          subject: {\n'
    '            area_name: analysisAreaName.trim(),\n'
    '            holder_name: analysisHolderName.trim(),\n'
    '            holder_document: analysisHolderDocument.replace(/\\D/g, ""),\n'
    '          },\n',
    "page-analysis-payload",
)

page = PAGE.read_text()
old = '''              <Button className="new-analysis">
                <Plus size={17} /> Nova análise
              </Button>
'''
new = '''              <Button className="mobile-layers-button" onClick={() => setLayerManagerOpen(true)}>
                <Layers3 size={17} /> Camadas
              </Button>
              <Button className="new-analysis" onClick={beginNewAnalysis}>
                <Plus size={17} /> Nova análise
              </Button>
'''
if 'onClick={beginNewAnalysis}' not in page:
    if old not in page:
        raise SystemExit("ERRO [page-new-analysis-button] botão Nova análise não localizado")
    PAGE.write_text(page.replace(old, new, 1))
    print("OK [page-new-analysis-button]")
else:
    print("OK [page-new-analysis-button] - já aplicado")

page = PAGE.read_text()
replace_once(
    PAGE,
    '''                <GeoMap
                  incraUf={incraUf}
                  onGeometryChange={geometryChanged}
''',
    '''                <GeoMap
                  incraUf={incraUf}
                  resetNonce={analysisResetNonce}
                  onGeometryChange={geometryChanged}
''',
    "page-map-reset",
)

page = PAGE.read_text()
legend_start = page.find('                <div className="map-legend">')
analysis_start = page.find('                <div className="analysis-card">', legend_start)
if legend_start != -1 and analysis_start != -1:
    page = page[:legend_start] + page[analysis_start:]
    PAGE.write_text(page)
    print("OK [page-remove-map-legend]")
elif 'className="map-legend"' not in page:
    print("OK [page-remove-map-legend] - já removido")
else:
    raise SystemExit("ERRO [page-remove-map-legend]")

page = PAGE.read_text()
old = '''                <div className="analysis-card">
                  <div className="analysis-title">
'''
new = '''                {analysisSessionOpen && (
                <div className="analysis-card analysis-card-session">
                  <div className="analysis-title">
'''
if "analysis-card-session" not in page:
    if old not in page:
        raise SystemExit("ERRO [page-analysis-card-open] card não localizado")
    page = page.replace(old, new, 1)
    PAGE.write_text(page)
    print("OK [page-analysis-card-open]")
else:
    print("OK [page-analysis-card-open] - já aplicado")

page = PAGE.read_text()
old = '''                  {analysis && (
                    <div className="metric-row">
'''
new = '''                  {!analysisDraftReady && (
                    <div className="analysis-registration">
                      <label>
                        <span>Área / imóvel</span>
                        <input
                          value={analysisAreaName}
                          onChange={(event) => setAnalysisAreaName(event.target.value)}
                          placeholder="Ex.: Fazenda São José"
                          autoFocus
                        />
                      </label>
                      <label>
                        <span>Detentor</span>
                        <input
                          value={analysisHolderName}
                          onChange={(event) => setAnalysisHolderName(event.target.value)}
                          placeholder="Nome ou razão social"
                        />
                      </label>
                      <label>
                        <span>CPF/CNPJ</span>
                        <input
                          value={analysisHolderDocument}
                          onChange={(event) => setAnalysisHolderDocument(event.target.value)}
                          placeholder="Opcional para análise · necessário para ODS SIGEF"
                          inputMode="numeric"
                        />
                      </label>
                      <Button className="analysis-register-button" onClick={confirmAnalysisRegistration}>
                        Iniciar análise
                      </Button>
                    </div>
                  )}
                  {analysisDraftReady && (
                    <div className="analysis-registration-summary">
                      <strong>{analysisAreaName}</strong>
                      <span>{analysisHolderName}</span>
                    </div>
                  )}
                  {analysisDraftReady && analysis && (
                    <div className="metric-row">
'''
if "analysis-registration" not in page:
    if old not in page:
        raise SystemExit("ERRO [page-analysis-registration] ponto não localizado")
    PAGE.write_text(page.replace(old, new, 1))
    print("OK [page-analysis-registration]")
else:
    print("OK [page-analysis-registration] - já aplicado")

page = PAGE.read_text()
# Os demais blocos de resultado e o botão executar só aparecem depois do cadastro inicial.
page = page.replace('{analysis && overlaps.length > 0 && (', '{analysisDraftReady && analysis && overlaps.length > 0 && (')
page = page.replace('{analysis && overlaps.length === 0 && (', '{analysisDraftReady && analysis && overlaps.length === 0 && (')
page = page.replace('{analyzing && analysisProgress && (', '{analysisDraftReady && analyzing && analysisProgress && (')
page = page.replace('{analysis?.warnings?.length ? (', '{analysisDraftReady && analysis?.warnings?.length ? (')
page = page.replace('disabled={!subjectGeometry || analyzing || !apiOnline}', 'disabled={!analysisDraftReady || !subjectGeometry || analyzing || !apiOnline}')
page = page.replace('{analysis && (\n                    <a', '{analysisDraftReady && analysis && (\n                    <a')
# Fecha o fragmento condicional do card logo após o próprio card.
needle = '''                </div>
              </section>
'''
if "analysis-card-session" in page and '''                </div>
                )}
              </section>
''' not in page:
    if needle not in page:
        raise SystemExit("ERRO [page-analysis-card-close] fechamento não localizado")
    page = page.replace(needle, '''                </div>
                )}
              </section>
''', 1)
PAGE.write_text(page)
print("OK [page-analysis-conditional]")

# -----------------------------------------------------------------------------
# GEOMAP: reset real ao iniciar nova análise
# -----------------------------------------------------------------------------
GEO = ROOT / "components/geo-map.tsx"
geo = GEO.read_text()
backup = GEO.with_suffix(GEO.suffix + ".bak-new-analysis-reset-20260902")
if not backup.exists():
    backup.write_text(geo)

replace_once(
    GEO,
    '  incraUf: string;\n  layers: Array<{\n',
    '  incraUf: string;\n  resetNonce?: number;\n  layers: Array<{\n',
    "geomap-prop-type",
)
geo = GEO.read_text()
replace_once(
    GEO,
    'export function GeoMap({ onGeometryChange, layers, incraUf }: GeoMapProps) {\n',
    'export function GeoMap({ onGeometryChange, layers, incraUf, resetNonce = 0 }: GeoMapProps) {\n',
    "geomap-prop-signature",
)
geo = GEO.read_text()
old = '''  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const target = UF_VIEW[incraUf] ?? UF_VIEW.ALL;
'''
new = '''  useEffect(() => {
    if (!resetNonce) return;
    sourceRef.current.clear();
    identifySelectionSourceRef.current.clear();
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive(false);
    clearIdentifiedFeature();
  }, [resetNonce]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const target = UF_VIEW[incraUf] ?? UF_VIEW.ALL;
'''
if "}, [resetNonce]);" not in geo:
    if old not in geo:
        raise SystemExit("ERRO [geomap-reset-effect] ponto não localizado")
    GEO.write_text(geo.replace(old, new, 1))
    print("OK [geomap-reset-effect]")
else:
    print("OK [geomap-reset-effect] - já aplicado")

# -----------------------------------------------------------------------------
# BACKEND: persistência mínima do detentor junto da análise
# -----------------------------------------------------------------------------
MODEL = ROOT / "backend/app/models/analysis.py"
model = MODEL.read_text()
if "subject_json" not in model:
    model = model.replace(
        '    source_status_json: Mapped[list]=mapped_column(JSON, default=list)\n',
        '    source_status_json: Mapped[list]=mapped_column(JSON, default=list)\n'
        '    subject_json: Mapped[dict]=mapped_column(JSON, default=dict)\n',
        1,
    )
    MODEL.write_text(model)
    print("OK [analysis-model-subject]")
else:
    print("OK [analysis-model-subject] - já aplicado")

SCHEMA = ROOT / "backend/app/schemas/analysis.py"
schema = SCHEMA.read_text()
if "subject:dict[str,Any]|None=None" not in schema:
    schema = schema.replace(
        '    incra_uf:str|None=Field(default=None,pattern="^[A-Za-z]{2}$")\n',
        '    incra_uf:str|None=Field(default=None,pattern="^[A-Za-z]{2}$")\n'
        '    subject:dict[str,Any]|None=None\n',
        1,
    )
    SCHEMA.write_text(schema)
    print("OK [analysis-schema-subject]")
else:
    print("OK [analysis-schema-subject] - já aplicado")

MAIN = ROOT / "backend/app/main.py"
main = MAIN.read_text()
if "subject_json" not in main:
    main = main.replace(
        '        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS source_status_json JSONB NOT NULL DEFAULT \'[]\'::jsonb"))\n',
        '        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS source_status_json JSONB NOT NULL DEFAULT \'[]\'::jsonb"))\n'
        '        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS subject_json JSONB NOT NULL DEFAULT \'{}\'::jsonb"))\n',
        1,
    )
    MAIN.write_text(main)
    print("OK [main-subject-migration]")
else:
    print("OK [main-subject-migration] - já aplicado")

ROUTES = ROOT / "backend/app/api/routes/analyses.py"
routes = ROUTES.read_text()
if "analysis.subject_json = dict(payload.subject or {})" not in routes:
    old = '''    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    background_tasks.add_task(run_analysis_background,analysis.id,payload.name,payload.geometry,payload.source_ids,payload.incra_uf)
'''
    new = '''    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    analysis.subject_json = dict(payload.subject or {})
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    background_tasks.add_task(run_analysis_background,analysis.id,payload.name,payload.geometry,payload.source_ids,payload.incra_uf)
'''
    if old not in routes:
        raise SystemExit("ERRO [analysis-route-subject] criação da análise não localizada")
    routes = routes.replace(old, new, 1)

if '"subject": analysis.subject_json or {},' not in routes:
    routes = routes.replace(
        '            "error_message": analysis.error_message,\n',
        '            "error_message": analysis.error_message,\n            "subject": analysis.subject_json or {},\n',
        1,
    )
    # Inclui também na resposta individual, na segunda ocorrência do bloco error_message.
    marker = '        "error_message": analysis.error_message,\n    }\n\n@router.get(\n    "/{analysis_id}/sigef-ods"'
    if marker in routes:
        routes = routes.replace(
            marker,
            '        "error_message": analysis.error_message,\n        "subject": analysis.subject_json or {},\n    }\n\n@router.get(\n    "/{analysis_id}/sigef-ods"',
            1,
        )
ROUTES.write_text(routes)
print("OK [analysis-route-subject]")

# -----------------------------------------------------------------------------
# ODS: já usa detentor/CPF-CNPJ real quando informado. Coordenadas DMS e
# municípios ficam para o patch seguinte, após comparação com o modelo enviado.
# -----------------------------------------------------------------------------
ODS = ROOT / "backend/app/services/sigef_ods.py"
ods = ODS.read_text()
if "holder_document" not in ods:
    old = '''        # Preenchimento mínimo para SIMULAÇÃO.
        _set_identification_value(
            identification,
            2,
            2,
            "Particular",
        )
'''
    new = '''        subject = dict(analysis.subject_json or {})
        holder_name = str(subject.get("holder_name") or "SIMULAÇÃO").strip() or "SIMULAÇÃO"
        holder_document = "".join(
            character
            for character in str(subject.get("holder_document") or "")
            if character.isdigit()
        )
        holder_kind = "Jurídica" if len(holder_document) == 14 else "Física"

        # Preenchimento mínimo para SIMULAÇÃO.
        _set_identification_value(
            identification,
            2,
            2,
            "Particular",
        )
'''
    if old not in ods:
        raise SystemExit("ERRO [sigef-subject] bloco de identificação não localizado")
    ods = ods.replace(old, new, 1)
    ods = ods.replace('            "Física",\n        )\n        _set_identification_value(\n            identification,\n            6,\n            2,\n            "SIMULAÇÃO",', '            holder_kind,\n        )\n        _set_identification_value(\n            identification,\n            6,\n            2,\n            holder_name,', 1)
    ods = ods.replace('            "000.000.000-00",\n        )', '            holder_document,\n        )', 1)
    ODS.write_text(ods)
    print("OK [sigef-subject]")
else:
    print("OK [sigef-subject] - já aplicado")

# -----------------------------------------------------------------------------
# CSS: responsividade + card de cadastro de análise + mapa limpo
# -----------------------------------------------------------------------------
CSS = ROOT / "app/globals.css"
css = CSS.read_text()
backup = CSS.with_suffix(CSS.suffix + ".bak-mobile-analysis-20260902")
if not backup.exists():
    backup.write_text(css)

block = r'''

/* ================================================================
   FLUXO NOVA ANÁLISE + RESPONSIVIDADE OPERACIONAL
   ================================================================ */
.mobile-layers-button {
  display: none !important;
}
.analysis-registration {
  display: grid;
  gap: 8px;
  margin: 10px 0 2px;
}
.analysis-registration label {
  display: grid;
  gap: 4px;
}
.analysis-registration label > span {
  color: #667a70;
  font-size: 8px;
  font-weight: 900;
  letter-spacing: .07em;
  text-transform: uppercase;
}
.analysis-registration input {
  width: 100%;
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid #ccd9d1;
  border-radius: 7px;
  outline: 0;
  background: #fff;
  color: #18312b;
  font-size: 10px;
}
.analysis-registration input:focus {
  border-color: #3e8063;
  box-shadow: 0 0 0 3px #3e806318;
}
.analysis-register-button {
  width: 100%;
  margin-top: 2px;
  background: #174d3a !important;
  color: #fff !important;
  font-weight: 800 !important;
}
.analysis-registration-summary {
  display: grid;
  gap: 2px;
  margin: 8px 0;
  padding: 8px 10px;
  border-radius: 7px;
  background: #eef5f1;
  border: 1px solid #d6e3dc;
}
.analysis-registration-summary strong {
  font-size: 10px;
  color: #173f33;
}
.analysis-registration-summary span {
  font-size: 8.5px;
  color: #687970;
}

@media (max-width: 900px) {
  .app-shell {
    display: block;
    min-height: 100dvh;
  }
  .sidebar {
    min-height: auto;
    width: 100%;
    padding: 8px 10px;
    flex-direction: row;
    align-items: center;
    gap: 10px;
    overflow-x: auto;
    position: relative;
    z-index: 60;
  }
  .brand {
    flex: none;
    padding: 0 10px 0 0;
    border: 0;
    border-right: 1px solid #ffffff24;
  }
  .brand-mark {
    width: 30px;
    height: 30px;
    font-size: 17px;
  }
  .brand strong { font-size: 10px; }
  .brand span { font-size: 7px; }
  .main-nav {
    display: flex;
    gap: 4px;
    padding: 0;
    flex: none;
  }
  .main-nav button,
  .main-nav a {
    width: auto;
    min-width: max-content;
    padding: 8px 9px;
    font-size: 10px;
    white-space: nowrap;
  }
  .sidebar-bottom {
    display: none;
  }
  .workspace {
    padding: 10px;
  }
  .topbar {
    gap: 8px;
    margin-bottom: 10px;
  }
  .topbar h1 {
    font-size: 20px;
  }
  .top-actions {
    gap: 6px;
  }
  .search-box {
    display: none;
  }
  .mobile-layers-button {
    display: inline-flex !important;
    background: #eef4f0 !important;
    color: #174d3a !important;
    border: 1px solid #ccd9d1 !important;
    font-size: 10px !important;
  }
  .new-analysis {
    min-height: 38px;
    font-size: 10px !important;
  }
  .status-strip {
    display: flex;
    overflow-x: auto;
    margin-bottom: 8px;
  }
  .status-strip > div {
    min-width: 230px;
    padding: 9px 10px;
  }
  .map-layout {
    display: block;
    height: calc(100dvh - 198px);
    min-height: 520px;
  }
  .layer-panel {
    display: none;
  }
  .map-canvas {
    width: 100%;
    height: 100%;
  }
  .analysis-card-session {
    right: 8px;
    bottom: 8px;
    width: min(340px, calc(100% - 16px));
    max-height: min(62dvh, 520px);
    overflow-y: auto;
  }
  .geo-tools {
    right: 8px;
    left: 8px;
    top: 8px;
    width: auto;
    overflow-x: auto;
    justify-content: flex-start;
    scrollbar-width: thin;
  }
  .geo-tools button,
  .geo-tools label {
    flex: none;
    min-width: 38px;
  }
  .official-layer-status {
    top: 58px;
    right: 8px;
    max-width: calc(100% - 16px);
  }
}

@media (max-width: 560px) {
  .workspace {
    padding: 6px;
  }
  .topbar > div:first-child p {
    display: none;
  }
  .topbar h1 {
    font-size: 17px;
  }
  .new-analysis span,
  .mobile-layers-button span {
    display: none;
  }
  .status-strip {
    display: none;
  }
  .map-layout {
    height: calc(100dvh - 118px);
    min-height: 480px;
    border-radius: 9px;
  }
  .analysis-card-session {
    left: 6px;
    right: 6px;
    bottom: 6px;
    width: auto;
    max-height: 56dvh;
  }
  .feature-info-panel {
    left: 6px;
    right: 6px;
    width: auto;
    top: 102px;
    max-height: calc(100% - 235px);
  }
}
'''
if "FLUXO NOVA ANÁLISE + RESPONSIVIDADE OPERACIONAL" not in css:
    CSS.write_text(css + block)
    print("OK [css-mobile-analysis]")
else:
    print("OK [css-mobile-analysis] - já aplicado")

print("NEW_ANALYSIS_MOBILE_SUBJECT_PATCH_OK")
