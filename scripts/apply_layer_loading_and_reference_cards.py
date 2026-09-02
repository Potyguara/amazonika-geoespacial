from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ERRO [{label}]: bloco não localizado em {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"OK [{label}] - {path}")


# ============================================================
# GEO MAP — feedback bloqueante SOMENTE ao ligar/desligar camada
# ============================================================
geo = Path("components/geo-map.tsx")
s = geo.read_text(encoding="utf-8")

old = '''  const layersRef = useRef(layers);
  const incraUfRef = useRef(incraUf);
'''
new = '''  const layersRef = useRef(layers);
  const previousLayerStateRef = useRef<Map<string, boolean> | null>(null);
  const layerTransitionTokenRef = useRef(0);
  const layerTransitionTimerRef = useRef<number | null>(null);
  const incraUfRef = useRef(incraUf);
'''
if old not in s:
    raise SystemExit("ERRO [geo-refs]: ponto de inserção não localizado")
s = s.replace(old, new, 1)

old = '''  const [officialStatus, setOfficialStatus] = useState(
    "Preparando camadas oficiais…",
  );
'''
new = '''  const [officialStatus, setOfficialStatus] = useState(
    "Preparando camadas oficiais…",
  );
  const [layerTransition, setLayerTransition] = useState<{
    active: boolean;
    name: string;
    action: "loading" | "removing";
  }>({ active: false, name: "", action: "loading" });
'''
if old not in s:
    raise SystemExit("ERRO [geo-state]: officialStatus não localizado")
s = s.replace(old, new, 1)

old = '''  useEffect(() => {
    layersRef.current = layers;
    const map = mapRef.current;
    if (!map) return;

    const desiredVectorTiles = new Set<string>();
'''
new = '''  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      layersRef.current = layers;
      return;
    }

    // Detecta exclusivamente alteração de liga/desliga. Mudanças de zoom,
    // pan ou renderização não acionam este bloqueio visual.
    const currentState = new Map<string, boolean>();
    for (const layer of layers) {
      if (layer.id) currentState.set(layer.id, Boolean(layer.enabled));
    }

    const previousState = previousLayerStateRef.current;
    let toggledLayer: (typeof layers)[number] | null = null;

    if (previousState) {
      toggledLayer =
        layers.find(
          (layer) =>
            Boolean(layer.id) &&
            previousState.has(layer.id!) &&
            previousState.get(layer.id!) !== Boolean(layer.enabled),
        ) ?? null;
    }

    previousLayerStateRef.current = currentState;
    layersRef.current = layers;

    const transitionToken = ++layerTransitionTokenRef.current;

    if (layerTransitionTimerRef.current !== null) {
      window.clearTimeout(layerTransitionTimerRef.current);
      layerTransitionTimerRef.current = null;
    }

    if (toggledLayer) {
      setLayerTransition({
        active: true,
        name: toggledLayer.name,
        action: toggledLayer.enabled ? "loading" : "removing",
      });
    }

    const finishLayerTransition = (delay = 260) => {
      if (!toggledLayer) return;

      if (layerTransitionTimerRef.current !== null) {
        window.clearTimeout(layerTransitionTimerRef.current);
      }

      layerTransitionTimerRef.current = window.setTimeout(() => {
        if (layerTransitionTokenRef.current !== transitionToken) return;
        setLayerTransition((current) => ({ ...current, active: false }));
        layerTransitionTimerRef.current = null;
      }, delay);
    };

    // Timeout defensivo: nenhum tile/servidor pode manter o usuário preso.
    if (toggledLayer) {
      layerTransitionTimerRef.current = window.setTimeout(() => {
        if (layerTransitionTokenRef.current !== transitionToken) return;
        setLayerTransition((current) => ({ ...current, active: false }));
        layerTransitionTimerRef.current = null;
      }, 12000);
    }

    const desiredVectorTiles = new Set<string>();
'''
if old not in s:
    raise SystemExit("ERRO [geo-effect-start]: efeito de layers não localizado")
s = s.replace(old, new, 1)

old = '''      if (existingVectorTile) {
        existingVectorTile.setMinZoom(minimumVectorZoom(layer));
        existingVectorTile.getSource()?.setUrl(
          `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
        );
        existingVectorTile.getSource()?.refresh();
        continue;
      }
'''
new = '''      if (existingVectorTile) {
        existingVectorTile.setMinZoom(minimumVectorZoom(layer));
        const existingSource = existingVectorTile.getSource();
        existingSource?.setUrl(
          `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
        );

        if (toggledLayer?.id === layer.id && toggledLayer.enabled && existingSource) {
          let started = 0;
          let finished = 0;

          const settle = () => {
            finished += 1;
            if (started > 0 && finished >= started) finishLayerTransition(360);
          };

          existingSource.on("tileloadstart", () => {
            if (layerTransitionTokenRef.current === transitionToken) started += 1;
          });
          existingSource.on("tileloadend", settle);
          existingSource.on("tileloaderror", settle);
        }

        existingSource?.refresh();
        continue;
      }
'''
if old not in s:
    raise SystemExit("ERRO [geo-existing-source]: bloco de MVT existente não localizado")
s = s.replace(old, new, 1)

old = '''      const vectorTileSource = new VectorTileSource({
        format: new MVT({ featureClass: Feature }),
        url: `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
      });

      const vectorTileLayer = new VectorTileLayer({
'''
new = '''      const vectorTileSource = new VectorTileSource({
        format: new MVT({ featureClass: Feature }),
        url: `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
      });

      if (toggledLayer?.id === layer.id && toggledLayer.enabled) {
        let started = 0;
        let finished = 0;

        const settle = () => {
          finished += 1;
          if (started > 0 && finished >= started) finishLayerTransition(360);
        };

        vectorTileSource.on("tileloadstart", () => {
          if (layerTransitionTokenRef.current === transitionToken) started += 1;
        });
        vectorTileSource.on("tileloadend", settle);
        vectorTileSource.on("tileloaderror", settle);
      }

      const vectorTileLayer = new VectorTileLayer({
'''
if old not in s:
    raise SystemExit("ERRO [geo-new-source]: criação do VectorTileSource não localizada")
s = s.replace(old, new, 1)

old = '''    for (const [id, vectorTileLayer] of vectorTileLayersRef.current) {
      if (!desiredVectorTiles.has(id)) {
        map.removeLayer(vectorTileLayer);
        vectorTileLayersRef.current.delete(id);
      }
    }

    setOfficialStatus(
'''
new = '''    for (const [id, vectorTileLayer] of vectorTileLayersRef.current) {
      if (!desiredVectorTiles.has(id)) {
        map.removeLayer(vectorTileLayer);
        vectorTileLayersRef.current.delete(id);
      }
    }

    if (toggledLayer && !toggledLayer.enabled) {
      // Remoção é síncrona; esperamos apenas o próximo ciclo visual.
      finishLayerTransition(220);
    } else if (toggledLayer?.enabled) {
      const source = toggledLayer.id
        ? vectorTileLayersRef.current.get(toggledLayer.id)?.getSource()
        : null;

      // Em zoom abaixo do minZoom nenhum tile será solicitado.
      // Nesse caso liberamos rapidamente após aplicar a camada.
      const minZoom = minimumVectorZoom(toggledLayer);
      const zoom = map.getView().getZoom() ?? 0;
      if (!source || zoom < minZoom) finishLayerTransition(320);
    }

    setOfficialStatus(
'''
if old not in s:
    raise SystemExit("ERRO [geo-after-remove]: final do gerenciamento MVT não localizado")
s = s.replace(old, new, 1)

old = '''      <div
        ref={mapElement}
        className={`real-map ${identifyActive ? "identify-mode" : ""}`}
      />
      <div className="geo-tools" aria-label="Ferramentas do mapa">
'''
new = '''      <div
        ref={mapElement}
        className={`real-map ${identifyActive ? "identify-mode" : ""}`}
      />
      {layerTransition.active && (
        <div
          className="map-layer-transition"
          role="status"
          aria-live="polite"
          aria-label="Carregando camada territorial"
        >
          <div className="map-layer-transition-card">
            <RefreshCw size={24} className="spin" />
            <div>
              <strong>
                {layerTransition.action === "loading"
                  ? "Carregando camada"
                  : "Atualizando mapa"}
              </strong>
              <span>{layerTransition.name}</span>
              <small>Aguarde a atualização da visualização…</small>
            </div>
          </div>
        </div>
      )}
      <div className="geo-tools" aria-label="Ferramentas do mapa">
'''
if old not in s:
    raise SystemExit("ERRO [geo-overlay-jsx]: elemento real-map não localizado")
s = s.replace(old, new, 1)

# Precisamos do ícone usado pelo overlay.
s = s.replace(
    '''  Pencil,\n  Pentagon,\n  X,\n} from "lucide-react";''',
    '''  Pencil,\n  Pentagon,\n  RefreshCw,\n  X,\n} from "lucide-react";''',
    1,
)

geo.write_text(s, encoding="utf-8")
print("OK [geo-map] - bloqueio visual por toggle implementado")


# ============================================================
# SOURCES MODULE — cards SICAR/SPU mostram vetores operacionais por UF
# ============================================================
sources = Path("components/sources-module.tsx")
s = sources.read_text(encoding="utf-8")

old = '''          const version = versions[source.id],
            age = versionAge(version),
            limit = Number(source.metadata_json.stale_after_days ?? 15),
            stale = !version || age === null || age > limit,
            wms = Boolean(
              source.metadata_json.wms_enabled &&
              source.metadata_json.wms_theme,
            ),
'''
new = '''          const version = versions[source.id],
            age = versionAge(version),
            limit = Number(source.metadata_json.stale_after_days ?? 15),
            referenceOnly =
              source.metadata_json.service_role === "WMS_REFERENCE" &&
              ["SICAR", "SPU"].includes(source.institution.toUpperCase()),
            operationalVectors = referenceOnly
              ? custom.filter((item) => {
                  const category = String(item.metadata_json.custom_category ?? "");
                  return source.institution.toUpperCase() === "SICAR"
                    ? category === "CAR_SICAR"
                    : category === "SPU";
                })
              : [],
            operationalFeatureCount = operationalVectors.reduce(
              (total, item) => total + Number(versions[item.id]?.feature_count ?? 0),
              0,
            ),
            stale = referenceOnly ? false : !version || age === null || age > limit,
            wms = Boolean(
              source.metadata_json.wms_enabled &&
              source.metadata_json.wms_theme,
            ),
'''
if old not in s:
    raise SystemExit("ERRO [source-card-vars]: variáveis do card não localizadas")
s = s.replace(old, new, 1)

old = '''            connected = wms || Boolean(version),
'''
new = '''            connected = wms || Boolean(version) || operationalVectors.length > 0,
'''
if old not in s:
    raise SystemExit("ERRO [source-connected]: connected não localizado")
s = s.replace(old, new, 1)

old = '''                {stale && (
                  <span className="source-stale-badge">
'''
new = '''                {referenceOnly ? (
                  <span className="source-reference-badge">
                    WMS REFERÊNCIA
                  </span>
                ) : stale && (
                  <span className="source-stale-badge">
'''
if old not in s:
    raise SystemExit("ERRO [source-badge]: badge stale não localizado")
s = s.replace(old, new, 1)

old = '''                    {!version
                      ? packageManaged
                        ? "Sem carga"
                        : vectorOnDemand
                          ? "Gerada ao identificar/analisar"
                          : "Sem carga"
                      : stale
                        ? `Desatualizada${age !== null ? ` há ${age} dias` : ""}`
                        : "Atualizada"}
'''
new = '''                    {referenceOnly
                      ? operationalVectors.length
                        ? `Operacional por UF · ${operationalVectors.length} camada${operationalVectors.length === 1 ? "" : "s"}`
                        : "Aguardando vetor por UF"
                      : !version
                        ? packageManaged
                          ? "Sem carga"
                          : vectorOnDemand
                            ? "Gerada ao identificar/analisar"
                            : "Sem carga"
                        : stale
                          ? `Desatualizada${age !== null ? ` há ${age} dias` : ""}`
                          : "Atualizada"}
'''
if old not in s:
    raise SystemExit("ERRO [source-base-vector]: Base vetorial não localizada")
s = s.replace(old, new, 1)

old = '''                    {version
                      ? version.feature_count.toLocaleString("pt-BR")
                      : "—"}
'''
new = '''                    {referenceOnly
                      ? operationalVectors.length
                        ? operationalFeatureCount.toLocaleString("pt-BR")
                        : "—"
                      : version
                        ? version.feature_count.toLocaleString("pt-BR")
                        : "—"}
'''
if old not in s:
    raise SystemExit("ERRO [source-features]: Feições não localizado")
s = s.replace(old, new, 1)

old = '''                  <dd>{formatDate(version?.imported_at)}</dd>
'''
new = '''                  <dd>
                    {referenceOnly
                      ? operationalVectors.length
                        ? `${operationalVectors.length} vetor${operationalVectors.length === 1 ? "" : "es"} estadual${operationalVectors.length === 1 ? "" : "is"}`
                        : "Ainda não carregado por UF"
                      : formatDate(version?.imported_at)}
                  </dd>
'''
if old not in s:
    raise SystemExit("ERRO [source-last-load]: Última carga não localizada")
s = s.replace(old, new, 1)

old = '''                {wms && (
                  <div>
                    <dt>Conexão oficial</dt>
                    <dd className="source-wms-connected">WMS conectado</dd>
                  </div>
                )}
'''
new = '''                {referenceOnly ? (
                  <>
                    <div>
                      <dt>Referência oficial</dt>
                      <dd className="source-wms-connected">
                        {wms ? "WMS disponível" : "WMS desligado"}
                      </dd>
                    </div>
                    <div>
                      <dt>Análise vetorial</dt>
                      <dd className="source-wms-connected">
                        PostGIS · Vetores adicionais por UF
                      </dd>
                    </div>
                  </>
                ) : wms && (
                  <div>
                    <dt>Conexão oficial</dt>
                    <dd className="source-wms-connected">WMS conectado</dd>
                  </div>
                )}
'''
if old not in s:
    raise SystemExit("ERRO [source-wms-row]: Conexão oficial não localizada")
s = s.replace(old, new, 1)

old = '''                    {packageManaged
                      ? "Vetor nacional · atualização por pacote"
                      : vectorOnDemand
'''
new = '''                    {referenceOnly
                      ? "WMS opcional · vetor operacional por UF"
                      : packageManaged
                        ? "Vetor nacional · atualização por pacote"
                        : vectorOnDemand
'''
if old not in s:
    raise SystemExit("ERRO [source-footer]: texto do footer não localizado")
s = s.replace(old, new, 1)

sources.write_text(s, encoding="utf-8")
print("OK [sources-module] - cards SICAR/SPU refletem PostGIS por UF")


# ============================================================
# CSS — overlay bloqueante e badge de referência
# ============================================================
css = Path("app/globals.css")
s = css.read_text(encoding="utf-8")
marker = "/* AMAZONIKA_LAYER_TRANSITION_V1 */"
if marker not in s:
    s += r'''

/* AMAZONIKA_LAYER_TRANSITION_V1 */
.map-layer-transition {
  position: absolute;
  inset: 0;
  z-index: 1200;
  display: grid;
  place-items: center;
  background: rgba(247, 250, 248, 0.46);
  backdrop-filter: blur(1.5px);
  cursor: wait;
  pointer-events: all;
}

.map-layer-transition-card {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: min(360px, calc(100% - 36px));
  padding: 16px 18px;
  border: 1px solid rgba(23, 63, 50, 0.18);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 48px rgba(20, 50, 40, 0.18);
  color: #173f32;
}

.map-layer-transition-card > div {
  display: grid;
  gap: 2px;
}

.map-layer-transition-card strong {
  font-size: 14px;
}

.map-layer-transition-card span {
  font-size: 13px;
  font-weight: 700;
}

.map-layer-transition-card small {
  margin-top: 2px;
  color: #667a71;
  font-size: 11px;
}

.source-reference-badge {
  margin-left: auto;
  padding: 5px 8px;
  border-radius: 999px;
  background: #e8f1ed;
  color: #285c49;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
'''
    css.write_text(s, encoding="utf-8")
    print("OK [globals.css] - feedback visual adicionado")
else:
    print("OK [globals.css] - CSS já presente")

print("\nPATCH DE FEEDBACK VISUAL E CARDS CONCLUÍDO")
