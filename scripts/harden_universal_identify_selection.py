from pathlib import Path

GEO = Path("components/geo-map.tsx")
CSS = Path("app/globals.css")
API = Path("backend/app/api/routes/sources.py")

geo = GEO.read_text()
css = CSS.read_text()
api = API.read_text()

for path, content, suffix in [
    (GEO, geo, ".bak-identify-harden-20260902"),
    (CSS, css, ".bak-identify-harden-20260902"),
    (API, api, ".bak-identify-harden-20260902"),
]:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(content)

# ------------------------------------------------------------------
# 1. Estilo de pré-visualização para múltiplas feições encontradas.
# ------------------------------------------------------------------
if "const identifyCandidatePreviewStyles" not in geo:
    marker = "type IdentifiedFeature = {"
    if marker not in geo:
        raise SystemExit("ERRO [geo-map]: marcador IdentifiedFeature não localizado")
    block = '''const identifyCandidatePreviewStyles = [
  new Style({
    fill: new Fill({ color: "rgba(255, 193, 7, 0.10)" }),
    stroke: new Stroke({
      color: "rgba(255,255,255,0.98)",
      width: 8,
    }),
    image: new CircleStyle({
      radius: 10,
      fill: new Fill({ color: "rgba(255,255,255,0.98)" }),
      stroke: new Stroke({ color: "#f59e0b", width: 2 }),
    }),
  }),
  new Style({
    fill: new Fill({ color: "rgba(245, 158, 11, 0.16)" }),
    stroke: new Stroke({
      color: "#f59e0b",
      width: 3,
      lineDash: [9, 6],
    }),
    image: new CircleStyle({
      radius: 7,
      fill: new Fill({ color: "#f59e0b" }),
      stroke: new Stroke({ color: "#ffffff", width: 2 }),
    }),
  }),
];

'''
    geo = geo.replace(marker, block + marker, 1)

# ------------------------------------------------------------------
# 2. Função única de materialização do destaque.
#    Ela não depende da camada de origem e faz dupla renderização.
# ------------------------------------------------------------------
if "const renderIdentifyFeatures = (" not in geo:
    marker = "  const clearIdentifiedFeature = () => {"
    if marker not in geo:
        raise SystemExit("ERRO [geo-map]: clearIdentifiedFeature não localizado")
    block = '''  const renderIdentifyFeatures = (
    features: Feature[],
    mode: "selected" | "candidates" = "selected",
  ) => {
    const selectionSource = identifySelectionSourceRef.current;
    selectionSource.clear();

    const style =
      mode === "selected"
        ? identifyHighlightStyles
        : identifyCandidatePreviewStyles;

    for (const feature of features) {
      const geometry = feature.getGeometry();
      if (!geometry) continue;

      const highlightFeature = new Feature({
        geometry: geometry.clone(),
      });

      highlightFeature.set("isIdentifyHighlight", true);
      highlightFeature.set("source_id", feature.get("source_id"));
      highlightFeature.set("feature_id", feature.get("feature_id"));
      highlightFeature.setStyle(style);
      selectionSource.addFeature(highlightFeature);
    }

    selectionSource.changed();
    mapRef.current?.renderSync();

    // Alguns tiles MVT terminam o frame logo após a seleção. Um segundo
    // frame garante que o overlay permaneça acima deles de forma determinística.
    window.requestAnimationFrame(() => {
      identifySelectionSourceRef.current.changed();
      mapRef.current?.renderSync();
    });
  };

'''
    geo = geo.replace(marker, block + marker, 1)

# ------------------------------------------------------------------
# 3. Depois da materialização existente, reafirma seleção com helper.
# ------------------------------------------------------------------
needle = '''      identifySelectionSourceRef.current.addFeature(
        highlightFeature,
      );
      identifySelectionSourceRef.current.changed();

      // Render imediato: o usuário deve enxergar a seleção no mesmo clique,
      // antes mesmo de os atributos detalhados terminarem de carregar.
      mapRef.current?.renderSync();
'''
if "renderIdentifyFeatures([feature], \"selected\")" not in geo:
    if needle in geo:
        geo = geo.replace(
            needle,
            needle + '''
      renderIdentifyFeatures([feature], "selected");
''',
            1,
        )
    else:
        # Compatibilidade se o patch anterior ainda não tiver o comentário completo.
        fallback = '''      identifySelectionSourceRef.current.addFeature(
        highlightFeature,
      );
'''
        if fallback not in geo:
            raise SystemExit("ERRO [geo-map]: materialização de highlight não localizada")
        geo = geo.replace(
            fallback,
            fallback + '''      renderIdentifyFeatures([feature], "selected");
''',
            1,
        )

# ------------------------------------------------------------------
# 4. A geometria detalhada do PostGIS passa a ser a fonte autoritativa do
#    destaque final. Isso elimina diferenças entre MVT, fallback e identify.
# ------------------------------------------------------------------
if "GEOMETRIA AUTORITATIVA DO DESTAQUE" not in geo:
    marker = '''        const properties = detail.properties ?? {};
        const detailTitle = String(
'''
    if marker not in geo:
        raise SystemExit("ERRO [geo-map]: retorno de detalhe da feição não localizado")
    replacement = '''        const properties = detail.properties ?? {};

        // GEOMETRIA AUTORITATIVA DO DESTAQUE
        // O endpoint de detalhe devolve a geometria completa armazenada no PostGIS.
        // Recriamos o overlay com ela para não depender de geometria de tile,
        // simplificação visual ou timing de carregamento do MVT.
        if (detail?.geometry) {
          try {
            const detailFeature = new GeoJSON().readFeature(
              {
                type: "Feature",
                geometry: detail.geometry,
                properties: {
                  source_id: sourceId,
                  feature_id: featureId,
                },
              },
              {
                dataProjection: "EPSG:4674",
                featureProjection: "EPSG:3857",
              },
            );
            renderIdentifyFeatures([detailFeature], "selected");
          } catch (geometryError) {
            console.warn(
              "Não foi possível atualizar o destaque com a geometria completa.",
              geometryError,
            );
            renderIdentifyFeatures([feature], "selected");
          }
        } else {
          renderIdentifyFeatures([feature], "selected");
        }

        const detailTitle = String(
'''
    geo = geo.replace(marker, replacement, 1)

# ------------------------------------------------------------------
# 5. Ao haver múltiplos candidatos, mostra todos no mapa em preview.
# ------------------------------------------------------------------
needle = '''            if (candidates.length > 1) {
              setIdentifyLoading(false);
              identifyCandidateHistoryRef.current =
                candidates;
              setIdentifyCandidates(candidates);
              return;
            }
'''
if 'renderIdentifyFeatures(candidates.map((candidate) => candidate.feature), "candidates")' not in geo:
    if needle in geo:
        geo = geo.replace(
            needle,
            '''            if (candidates.length > 1) {
              setIdentifyLoading(false);
              identifyCandidateHistoryRef.current =
                candidates;
              renderIdentifyFeatures(
                candidates.map((candidate) => candidate.feature),
                "candidates",
              );
              setIdentifyCandidates(candidates);
              return;
            }
''',
            1,
        )
    else:
        # versão anterior sem identifyLoading
        needle2 = '''            if (candidates.length > 1) {
              identifyCandidateHistoryRef.current =
                candidates;
              setIdentifyCandidates(candidates);
              return;
            }
'''
        if needle2 not in geo:
            raise SystemExit("ERRO [geo-map]: bloco de múltiplos candidatos PostGIS não localizado")
        geo = geo.replace(
            needle2,
            '''            if (candidates.length > 1) {
              identifyCandidateHistoryRef.current =
                candidates;
              renderIdentifyFeatures(
                candidates.map((candidate) => candidate.feature),
                "candidates",
              );
              setIdentifyCandidates(candidates);
              return;
            }
''',
            1,
        )

# fallback renderizado também recebe preview
if "renderIdentifyFeatures(\n          candidates.map((candidate) => candidate.feature),\n          \"candidates\",\n        );\n\n        identifyCandidateHistoryRef.current" not in geo:
    marker = '''        identifyCandidateHistoryRef.current =
          candidates;

        setIdentifyCandidates(candidates);
'''
    if marker in geo:
        geo = geo.replace(
            marker,
            '''        renderIdentifyFeatures(
          candidates.map((candidate) => candidate.feature),
          "candidates",
        );

        identifyCandidateHistoryRef.current =
          candidates;

        setIdentifyCandidates(candidates);
''',
            1,
        )

# ------------------------------------------------------------------
# 6. Botão voltar restaura também o preview geométrico dos candidatos.
# ------------------------------------------------------------------
if "renderIdentifyFeatures(\n      identifyCandidateHistoryRef.current.map" not in geo:
    marker = '''    identifySelectionSourceRef.current.clear();
    setIdentifiedFeature(null);

    setIdentifyCandidates([
      ...identifyCandidateHistoryRef.current,
    ]);
'''
    if marker not in geo:
        raise SystemExit("ERRO [geo-map]: returnToIdentifyCandidates não localizado")
    geo = geo.replace(
        marker,
        '''    identifySelectionSourceRef.current.clear();
    setIdentifiedFeature(null);

    renderIdentifyFeatures(
      identifyCandidateHistoryRef.current.map(
        (candidate) => candidate.feature,
      ),
      "candidates",
    );

    setIdentifyCandidates([
      ...identifyCandidateHistoryRef.current,
    ]);
''',
        1,
    )

# ------------------------------------------------------------------
# 7. Mostra contagem de atributos no cabeçalho.
# ------------------------------------------------------------------
old = '''              <span>{identifiedFeature.layer}</span>
'''
new = '''              <span>
                {identifiedFeature.layer} · {identifiedFeature.attributes.length}{" "}
                atributo{identifiedFeature.attributes.length === 1 ? "" : "s"}
              </span>
'''
if "identifiedFeature.attributes.length" not in geo:
    if old not in geo:
        raise SystemExit("ERRO [geo-map]: linha da camada no painel não localizada")
    geo = geo.replace(old, new, 1)

# ------------------------------------------------------------------
# 8. CSS: rolagem real, cabeçalho fixo e painel maior sem ocupar o mapa todo.
# ------------------------------------------------------------------
css_marker = "IDENTIFY ATTRIBUTES — SCROLL UNIVERSAL"
if css_marker not in css:
    css += r'''

/* =========================================================
   IDENTIFY ATTRIBUTES — SCROLL UNIVERSAL
   ========================================================= */
.feature-info-panel {
  width: min(390px, calc(100% - 28px));
  max-height: min(72vh, calc(100% - 150px));
}
.feature-info-panel > header {
  flex: 0 0 auto;
}
.feature-info-panel dl {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: #9eb6aa #eef3f0;
}
.feature-info-panel dl::-webkit-scrollbar {
  width: 9px;
}
.feature-info-panel dl::-webkit-scrollbar-track {
  background: #eef3f0;
}
.feature-info-panel dl::-webkit-scrollbar-thumb {
  background: #9eb6aa;
  border: 2px solid #eef3f0;
  border-radius: 999px;
}
.feature-info-panel dl > div {
  align-items: start;
}
.feature-info-panel dd {
  user-select: text;
}
@media (max-width: 760px) {
  .feature-info-panel {
    width: min(370px, calc(100% - 20px));
    right: 10px;
    max-height: min(68vh, calc(100% - 145px));
  }
}
'''

# ------------------------------------------------------------------
# 9. Backend: detalhe sempre em 2D e inclui metadados de proveniência/versão,
#    mantendo TODOS os campos originais de GeoFeature.properties.
# ------------------------------------------------------------------
if '"source_version_id"' not in api or '"reference_date"' not in api[api.find('def source_feature_detail'):api.find('def create_source')]:
    old = '''def source_feature_detail(source_id:UUID,feature_id:UUID,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    row=db.execute(
        select(GeoFeature.id,GeoFeature.external_id,GeoFeature.name,GeoFeature.properties,func.ST_AsGeoJSON(GeoFeature.geom))
        .join(SourceVersion,SourceVersion.id==GeoFeature.version_id)
        .where(GeoFeature.id==feature_id,SourceVersion.source_id==source_id)
    ).one_or_none()
    if not row: raise HTTPException(404,"Feição não encontrada.")
    internal_id,external_id,name,properties,geometry_json=row
    attributes=dict(properties or {})
    attributes.update({"feature_id":str(internal_id),"external_id":external_id,"name":name,"source_id":str(source_id),"source_name":source.name})
    return {"type":"Feature","id":str(internal_id),"geometry":json.loads(geometry_json),"properties":attributes}
'''
    new = '''def source_feature_detail(source_id:UUID,feature_id:UUID,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    row=db.execute(
        select(
            GeoFeature.id,
            GeoFeature.external_id,
            GeoFeature.name,
            GeoFeature.properties,
            func.ST_AsGeoJSON(func.ST_Force2D(GeoFeature.geom)),
            SourceVersion.id,
            SourceVersion.reference_date,
        )
        .join(SourceVersion,SourceVersion.id==GeoFeature.version_id)
        .where(GeoFeature.id==feature_id,SourceVersion.source_id==source_id)
    ).one_or_none()
    if not row: raise HTTPException(404,"Feição não encontrada.")
    internal_id,external_id,name,properties,geometry_json,version_id,reference_date=row
    # Preserva integralmente todos os atributos importados do arquivo de origem.
    attributes=dict(properties or {})
    # Acrescenta metadados técnicos e de proveniência sem remover nenhum campo original.
    attributes.update({
        "feature_id":str(internal_id),
        "external_id":external_id,
        "name":name,
        "source_id":str(source_id),
        "source_name":source.name,
        "institution":source.institution,
        "source_version_id":str(version_id),
        "reference_date":reference_date.isoformat() if reference_date else None,
    })
    return {"type":"Feature","id":str(internal_id),"geometry":json.loads(geometry_json),"properties":attributes}
'''
    if old not in api:
        raise SystemExit("ERRO [sources.py]: source_feature_detail não localizado no formato esperado")
    api = api.replace(old, new, 1)

GEO.write_text(geo)
CSS.write_text(css)
API.write_text(api)

print("OK [geo-map] - destaque estabilizado com geometria autoritativa do PostGIS")
print("OK [geo-map] - preview visual para múltiplas feições")
print("OK [geo-map] - dupla renderização defensiva aplicada")
print("OK [painel] - rolagem e contagem de atributos implementadas")
print("OK [API] - todos os atributos originais + metadados de versão/proveniência")
print("HARDEN_UNIVERSAL_IDENTIFY_SELECTION_OK")
