from pathlib import Path

GEO = Path("components/geo-map.tsx")
geo = GEO.read_text()

backup = GEO.with_suffix(GEO.suffix + ".bak-identify-highlight-render-20260902")
if not backup.exists():
    backup.write_text(geo)

# 1. Make the universal highlight unmistakable.
old = '''const identifyHighlightStyles = [
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
new = '''const identifyHighlightStyles = [
  // halo branco: separa a seleção de qualquer simbologia existente
  new Style({
    fill: new Fill({ color: "rgba(255, 159, 28, 0.10)" }),
    stroke: new Stroke({ color: "rgba(255,255,255,0.98)", width: 10 }),
    image: new CircleStyle({
      radius: 12,
      fill: new Fill({ color: "rgba(255,255,255,0.98)" }),
      stroke: new Stroke({ color: "rgba(23,63,50,0.35)", width: 2 }),
    }),
  }),
  // corpo laranja: seleção propriamente dita
  new Style({
    fill: new Fill({ color: "rgba(255, 159, 28, 0.42)" }),
    stroke: new Stroke({ color: "#ff7a00", width: 5 }),
    image: new CircleStyle({
      radius: 8,
      fill: new Fill({ color: "#ff7a00" }),
      stroke: new Stroke({ color: "#ffffff", width: 2 }),
    }),
  }),
];
'''
if old in geo:
    geo = geo.replace(old, new, 1)
elif "const identifyHighlightStyles" not in geo:
    raise SystemExit("ERRO: identifyHighlightStyles não localizado")

# 2. Force style on the materialized feature itself, not only on the layer.
old = '''      highlightFeature.set(
        "feature_id",
        feature.get("feature_id"),
      );

      identifySelectionSourceRef.current.clear();
      identifySelectionSourceRef.current.addFeature(
        highlightFeature,
      );
'''
new = '''      highlightFeature.set(
        "feature_id",
        feature.get("feature_id"),
      );

      // O estilo é fixado também na própria feição para que o destaque
      // não dependa da função de estilo da camada ou da origem do vetor.
      highlightFeature.setStyle(identifyHighlightStyles);

      identifySelectionSourceRef.current.clear();
      identifySelectionSourceRef.current.addFeature(
        highlightFeature,
      );
      identifySelectionSourceRef.current.changed();

      // Render imediato: o usuário deve enxergar a seleção no mesmo clique,
      // antes mesmo de os atributos detalhados terminarem de carregar.
      mapRef.current?.renderSync();
'''
if "highlightFeature.setStyle(identifyHighlightStyles)" not in geo:
    if old not in geo:
        raise SystemExit("ERRO: bloco de materialização do destaque não localizado")
    geo = geo.replace(old, new, 1)

# 3. Raise overlay far above all dynamically-added MVT/WMS layers.
old = '''          source: identifySelectionSourceRef.current,
          zIndex: 1000,
          style: identifyHighlightStyles,
'''
new = '''          source: identifySelectionSourceRef.current,
          zIndex: 100000,
          style: identifyHighlightStyles,
'''
if "zIndex: 100000" not in geo:
    if old not in geo:
        raise SystemExit("ERRO: camada universal de seleção não localizada")
    geo = geo.replace(old, new, 1)

GEO.write_text(geo)

print("OK [geo-map] - destaque fixado na própria feição")
print("OK [geo-map] - renderSync após seleção")
print("OK [geo-map] - overlay elevado acima de qualquer camada dinâmica")
print("UNIVERSAL_IDENTIFY_HIGHLIGHT_RENDER_OK")
