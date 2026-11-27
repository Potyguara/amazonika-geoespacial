#!/usr/bin/env python3
"""Medição profissional de distância e área no mapa (components/geo-map.tsx).

- medida ao vivo junto ao cursor (segmento, azimute, total, área) durante o desenho;
- janela "Medições" com cada medição e a tabela de segmentos (distância e azimute);
- rótulos de distância em cada segmento e da área no mapa;
- snap nas medições ao desenhar o polígono, e polígono de trabalho a partir de uma área;
- cálculos geodésicos no elipsoide GRS80 (SIRGAS 2000): Vincenty e área elipsoidal;
- Backspace desfaz o último ponto, Enter conclui, Esc cancela.

Uso: python3 aplicar_medicao.py <pasta-do-frontend>
Aborta sem gravar nada se algum trecho esperado não for encontrado.
"""
import pathlib
import sys


def fail(msg):
    print("ERRO:", msg)
    print("Nada foi gravado.")
    sys.exit(1)


def rep(text, old, new, label):
    found = text.count(old)
    if found != 1:
        fail(f"trecho '{label}' encontrado {found} vez(es), esperado 1")
    return text.replace(old, new)


HELPERS = r'''// ---- Medição profissional: geodésia no elipsoide GRS80 (SIRGAS 2000) ----
const GRS80_A = 6378137;
const GRS80_F = 1 / 298.257222101;

type MeasureKind = "LineString" | "Polygon";
type MeasureSegment = { index: number; length: number; azimuth: number | null };
type MeasureStats = { segments: MeasureSegment[]; total: number; area: number | null };
type MeasureRecord = MeasureStats & { id: string; kind: MeasureKind; name: string; visible: boolean };

// Problema inverso de Vincenty: distância (m) e azimute direto (graus, 0–360).
function geodesicInverse(lon1: number, lat1: number, lon2: number, lat2: number) {
  const a = GRS80_A;
  const f = GRS80_F;
  const b = a * (1 - f);
  const rad = Math.PI / 180;
  const L = (lon2 - lon1) * rad;
  const U1 = Math.atan((1 - f) * Math.tan(lat1 * rad));
  const U2 = Math.atan((1 - f) * Math.tan(lat2 * rad));
  const sinU1 = Math.sin(U1), cosU1 = Math.cos(U1);
  const sinU2 = Math.sin(U2), cosU2 = Math.cos(U2);
  let lambda = L;
  let sinSigma = 0, cosSigma = 0, sigma = 0, cosSqAlpha = 0, cos2SigmaM = 0;
  let sinLambda = 0, cosLambda = 0;
  for (let iteration = 0; iteration < 200; iteration += 1) {
    sinLambda = Math.sin(lambda);
    cosLambda = Math.cos(lambda);
    sinSigma = Math.sqrt((cosU2 * sinLambda) ** 2
      + (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2);
    if (sinSigma === 0) return { distance: 0, azimuth: null as number | null };
    cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda;
    sigma = Math.atan2(sinSigma, cosSigma);
    const sinAlpha = (cosU1 * cosU2 * sinLambda) / sinSigma;
    cosSqAlpha = 1 - sinAlpha * sinAlpha;
    cos2SigmaM = cosSqAlpha !== 0 ? cosSigma - (2 * sinU1 * sinU2) / cosSqAlpha : 0;
    const C = (f / 16) * cosSqAlpha * (4 + f * (4 - 3 * cosSqAlpha));
    const previous = lambda;
    lambda = L + (1 - C) * f * sinAlpha
      * (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)));
    if (Math.abs(lambda - previous) < 1e-12) break;
  }
  const uSq = (cosSqAlpha * (a * a - b * b)) / (b * b);
  const A = 1 + (uSq / 16384) * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)));
  const B = (uSq / 1024) * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)));
  const deltaSigma = B * sinSigma * (cos2SigmaM + (B / 4) * (cosSigma * (-1 + 2 * cos2SigmaM * cos2SigmaM)
    - (B / 6) * cos2SigmaM * (-3 + 4 * sinSigma * sinSigma) * (-3 + 4 * cos2SigmaM * cos2SigmaM)));
  const distance = b * A * (sigma - deltaSigma);
  const alpha = Math.atan2(cosU2 * sinLambda, cosU1 * sinU2 - sinU1 * cosU2 * cosLambda);
  return { distance, azimuth: ((alpha / rad) + 360) % 360 };
}

// Área no elipsoide: projeção cilíndrica equivalente (latitude autálica).
function ellipsoidalArea(ring: number[][]): number {
  const e2 = GRS80_F * (2 - GRS80_F);
  const e = Math.sqrt(e2);
  const rad = Math.PI / 180;
  const q = (lat: number) => {
    const s = Math.sin(lat * rad);
    return (1 - e2) * (s / (1 - e2 * s * s) - (1 / (2 * e)) * Math.log((1 - e * s) / (1 + e * s)));
  };
  const lon0 = ring[0]?.[0] ?? 0;
  const points = ring.map(([lon, lat]) => {
    let dLon = lon - lon0;
    if (dLon > 180) dLon -= 360;
    if (dLon < -180) dLon += 360;
    return [GRS80_A * dLon * rad, (GRS80_A * q(lat)) / 2];
  });
  let sum = 0;
  for (let i = 0; i < points.length - 1; i += 1) {
    sum += points[i][0] * points[i + 1][1] - points[i + 1][0] * points[i][1];
  }
  return Math.abs(sum) / 2;
}

const formatLength = (meters: number) => meters >= 1000
  ? `${(meters / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} km`
  : `${meters.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} m`;

const formatAzimuth = (degrees: number | null) => {
  if (degrees === null) return "—";
  let totalSeconds = Math.round(degrees * 3600);
  totalSeconds = ((totalSeconds % 1296000) + 1296000) % 1296000;
  const d = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return `${d}°${String(m).padStart(2, "0")}'${String(s).padStart(2, "0")}"`;
};

const formatArea = (m2: number) =>
  `${(m2 / 10000).toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} ha · ${m2.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m²`;

// Coordenadas abertas (sem repetir o primeiro vértice) em EPSG:3857.
function openMeasureCoordinates(geometry: unknown): { kind: MeasureKind; coords: number[][] } | null {
  if (geometry instanceof LineString) return { kind: "LineString", coords: geometry.getCoordinates() };
  if (geometry instanceof Polygon) {
    const ring = geometry.getCoordinates()[0] ?? [];
    return { kind: "Polygon", coords: ring.slice(0, -1) };
  }
  return null;
}

// Linha que termina exatamente no ponto inicial (fechada pelo snap).
function isClosedPath(coords: number[][]) {
  if (coords.length < 4) return false;
  const first = coords[0];
  const last = coords[coords.length - 1];
  return Math.abs(first[0] - last[0]) < 1e-6 && Math.abs(first[1] - last[1]) < 1e-6;
}

function measureStatsFromCoordinates(kind: MeasureKind, coords: number[][]): MeasureStats {
  const lonLat = coords.map((coordinate) => toLonLat(coordinate));
  const path = kind === "Polygon" && lonLat.length >= 3 ? [...lonLat, lonLat[0]] : lonLat;
  const segments: MeasureSegment[] = [];
  let total = 0;
  for (let i = 0; i < path.length - 1; i += 1) {
    const result = geodesicInverse(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1]);
    total += result.distance;
    segments.push({ index: i + 1, length: result.distance, azimuth: result.azimuth });
  }
  const closedLine = kind === "LineString" && isClosedPath(coords);
  const area = kind === "Polygon" && lonLat.length >= 3
    ? ellipsoidalArea([...lonLat, lonLat[0]])
    : closedLine ? ellipsoidalArea(lonLat) : null;
  return { segments, total, area };
}

const measureLineStyle = new Style({
  stroke: new Stroke({ color: "#f59e0b", width: 3 }),
  fill: new Fill({ color: "rgba(245,158,11,0.14)" }),
});
const measureVertexStyle = new Style({
  image: new CircleStyle({ radius: 4.5, fill: new Fill({ color: "#ffffff" }),
    stroke: new Stroke({ color: "#b45309", width: 2 }) }),
});

function measureLabel(text: string, coordinate: number[], bold = false) {
  return new Style({
    geometry: new Point(coordinate),
    text: new TextStyle({
      text,
      font: `${bold ? 800 : 700} ${bold ? 13 : 11}px Inter, sans-serif`,
      fill: new Fill({ color: "#5c2d00" }),
      backgroundFill: new Fill({ color: "rgba(255,251,235,0.95)" }),
      backgroundStroke: new Stroke({ color: "#f59e0b", width: 1 }),
      padding: [2, 4, 2, 4],
      overflow: true,
    }),
  });
}

// Estilo das medições concluídas: linha, vértices e rótulo de cada segmento.
function measureLayerStyle(feature: FeatureLike) {
  const geometry = feature.getGeometry();
  const open = openMeasureCoordinates(geometry);
  if (!open) return measureLineStyle;
  const stats = (feature.get("measureStats") as MeasureStats | undefined)
    ?? measureStatsFromCoordinates(open.kind, open.coords);
  const path = open.kind === "Polygon" && open.coords.length >= 3
    ? [...open.coords, open.coords[0]] : open.coords;
  const styles: Style[] = [measureLineStyle,
    new Style({ geometry: new MultiPoint(open.coords), image: measureVertexStyle.getImage() ?? undefined })];
  stats.segments.forEach((segment, i) => {
    const a = path[i];
    const b = path[i + 1];
    if (!a || !b) return;
    styles.push(measureLabel(formatLength(segment.length), [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]));
  });
  if (open.kind === "LineString" && stats.area !== null) {
    const hectares = `${(stats.area / 10000).toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} ha`;
    styles.push(measureLabel(hectares, new Polygon([open.coords]).getInteriorPoint().getCoordinates(), true));
  } else if (open.kind === "Polygon" && stats.area !== null && geometry instanceof Polygon) {
    const hectares = `${(stats.area / 10000).toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} ha`;
    styles.push(measureLabel(hectares, geometry.getInteriorPoint().getCoordinates(), true));
  } else if (open.kind === "LineString" && stats.segments.length > 1) {
    const last = open.coords[open.coords.length - 1];
    styles.push(measureLabel(`Total ${formatLength(stats.total)}`, last, true));
  }
  return styles;
}

// Estilo do traço em desenho: segmentos já fixados com a distância rotulada.
const measureSketchLine = new Style({
  stroke: new Stroke({ color: "#d97706", width: 2.5, lineDash: [8, 5] }),
  fill: new Fill({ color: "rgba(245,158,11,0.10)" }),
});
const measureSketchCursor = new Style({
  image: new CircleStyle({ radius: 5, fill: new Fill({ color: "#d97706" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }) }),
});
function measureSketchStyle(feature: FeatureLike) {
  const geometry = feature.getGeometry();
  if (geometry instanceof Point) return measureSketchCursor;
  const open = openMeasureCoordinates(geometry);
  if (!open || open.coords.length < 2) return measureSketchLine;
  const styles: Style[] = [measureSketchLine,
    new Style({ geometry: new MultiPoint(open.coords.slice(0, -1)), image: measureVertexStyle.getImage() ?? undefined })];
  // O último segmento acompanha o cursor e é mostrado na etiqueta flutuante.
  const fixed = open.coords.slice(0, -1);
  for (let i = 0; i < fixed.length - 1; i += 1) {
    const a = toLonLat(fixed[i]);
    const b = toLonLat(fixed[i + 1]);
    const length = geodesicInverse(a[0], a[1], b[0], b[1]).distance;
    styles.push(measureLabel(formatLength(length),
      [(fixed[i][0] + fixed[i + 1][0]) / 2, (fixed[i][1] + fixed[i + 1][1]) / 2]));
  }
  return styles;
}

'''

STATE = '''  const [measurements, setMeasurements] = useState<MeasureRecord[]>([]);
  const [liveMeasure, setLiveMeasure] = useState<{
    segment: number; azimuth: number | null; total: number; area: number | null; count: number;
  } | null>(null);
  const [measurePanelOpen, setMeasurePanelOpen] = useState(true);
  const [measureCopied, setMeasureCopied] = useState(false);
  const measureSequenceRef = useRef(0);
  const measureOverlayRef = useRef<Overlay | null>(null);
  const hiddenMeasureFeaturesRef = useRef(new globalThis.Map<string, Feature>());
'''

EFFECT_OLD_START = '''  useEffect(() => {
    const map = mapRef.current;
    if (!map || !measureMode) return;
    const draw = new Draw({ source: measureSourceRef.current, type: measureMode });'''

EFFECT_NEW = r'''  useEffect(() => {
    const map = mapRef.current;
    if (!map || !measureMode) return;
    const kind = measureMode;
    const draw = new Draw({ source: measureSourceRef.current, type: kind, style: measureSketchStyle });
    // Etiqueta que acompanha o cursor com as medidas em tempo real.
    if (!measureOverlayRef.current) {
      const element = document.createElement("div");
      element.className = "measure-live-tooltip";
      measureOverlayRef.current = new Overlay({
        element, offset: [16, -12], positioning: "bottom-left", stopEvent: false,
      });
      map.addOverlay(measureOverlayRef.current);
    }
    const overlay = measureOverlayRef.current;
    const tooltip = overlay.getElement() as HTMLElement;
    // Snap nos vértices já clicados da própria medição, sobretudo o ponto
    // inicial, para fechar a figura exatamente no começo.
    const sketchSnapSource = new VectorSource();
    const sketchSnap = new Snap({ source: sketchSnapSource, vertex: true, edge: false, pixelTolerance: 16 });
    let snappedCount = -1;
    let changeKey: EventsKey | null = null;
    const stopLive = () => {
      if (changeKey) unByKey(changeKey);
      changeKey = null;
      sketchSnapSource.clear();
      snappedCount = -1;
      overlay.setPosition(undefined);
      setLiveMeasure(null);
    };
    draw.on("drawstart", (event) => {
      const geometry = event.feature.getGeometry();
      if (!geometry) return;
      changeKey = geometry.on("change", () => {
        const open = openMeasureCoordinates(geometry);
        if (!open || open.coords.length < 2) return;
        const fixed = open.coords.slice(0, -1);
        if (fixed.length !== snappedCount) {
          snappedCount = fixed.length;
          sketchSnapSource.clear();
          // O último vértice fixado fica de fora para não criar segmento nulo.
          sketchSnapSource.addFeatures(fixed.slice(0, -1).map((coordinate) => new Feature(new Point(coordinate))));
        }
        // Clique no ponto inicial fecha e conclui a distância automaticamente.
        if (kind === "LineString" && isClosedPath(fixed)) {
          window.setTimeout(() => draw.finishDrawing(), 0);
          return;
        }
        const lonLat = open.coords.map((coordinate) => toLonLat(coordinate));
        const last = lonLat.length - 1;
        const segment = geodesicInverse(lonLat[last - 1][0], lonLat[last - 1][1], lonLat[last][0], lonLat[last][1]);
        let total = 0;
        for (let i = 0; i < last; i += 1) {
          total += geodesicInverse(lonLat[i][0], lonLat[i][1], lonLat[i + 1][0], lonLat[i + 1][1]).distance;
        }
        const closing = kind === "LineString" && isClosedPath(open.coords);
        const area = kind === "Polygon" && lonLat.length >= 3
          ? ellipsoidalArea([...lonLat, lonLat[0]])
          : closing ? ellipsoidalArea(lonLat) : null;
        setLiveMeasure({ segment: segment.distance, azimuth: segment.azimuth, total, area, count: last });
        const lines = [
          `<strong>${formatLength(segment.distance)}</strong> · Az ${formatAzimuth(segment.azimuth)}`,
          `${kind === "Polygon" ? "Perímetro aberto" : "Total"}: ${formatLength(total)}`,
        ];
        if (closing) lines.push("Fechando no ponto inicial");
        if (area !== null) lines.push(`Área: ${formatArea(area)}`);
        tooltip.innerHTML = lines.join("<br>");
        // Perto da borda direita a etiqueta passa para o lado esquerdo do cursor.
        const pixel = map.getPixelFromCoordinate(open.coords[last]);
        const nearRight = pixel ? pixel[0] > (map.getSize()?.[0] ?? 0) - 280 : false;
        overlay.setPositioning(nearRight ? "bottom-right" : "bottom-left");
        overlay.setOffset(nearRight ? [-16, -12] : [16, -12]);
        overlay.setPosition(open.coords[last]);
      });
    });
    draw.on("drawabort", stopLive);
    draw.on("drawend", ({ feature }) => {
      stopLive();
      const open = openMeasureCoordinates(feature.getGeometry());
      if (!open) return;
      const stats = measureStatsFromCoordinates(open.kind, open.coords);
      measureSequenceRef.current += 1;
      const id = `MED-${measureSequenceRef.current}`;
      const name = `${kind === "Polygon" ? "Área" : "Distância"} ${measureSequenceRef.current}`;
      feature.setId(id);
      feature.set("measureStats", stats);
      setMeasurements((current) => [...current, { id, kind, name, ...stats, visible: true }]);
      setMeasureValue(stats.area !== null
        ? `${name}: ${formatArea(stats.area)} · perímetro ${formatLength(stats.total)}`
        : `${name}: ${formatLength(stats.total)}`);
      setMeasurePanelOpen(true);
    });
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.key === "Backspace" || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z")) {
        event.preventDefault();
        draw.removeLastPoint();
      } else if (event.key === "Escape") {
        draw.abortDrawing();
      } else if (event.key === "Enter") {
        draw.finishDrawing();
      }
    };
    window.addEventListener("keydown", onKey);
    map.addInteraction(draw);
    map.addInteraction(sketchSnap);
    return () => {
      window.removeEventListener("keydown", onKey);
      stopLive();
      map.removeInteraction(sketchSnap);
      map.removeInteraction(draw);
    };
  }, [measureMode]);

  const toggleMeasurementVisible = (id: string, visible: boolean) => {
    // Medição oculta sai da fonte: some do mapa e deixa de servir de snap.
    if (visible) {
      const feature = hiddenMeasureFeaturesRef.current.get(id);
      if (feature) measureSourceRef.current.addFeature(feature);
      hiddenMeasureFeaturesRef.current.delete(id);
    } else {
      const feature = measureSourceRef.current.getFeatureById(id);
      if (feature) {
        hiddenMeasureFeaturesRef.current.set(id, feature as Feature);
        measureSourceRef.current.removeFeature(feature as Feature);
      }
    }
    setMeasurements((current) => current.map((item) => item.id === id ? { ...item, visible } : item));
  };

  const removeMeasurement = (id: string) => {
    const feature = measureSourceRef.current.getFeatureById(id);
    if (feature) measureSourceRef.current.removeFeature(feature as Feature);
    hiddenMeasureFeaturesRef.current.delete(id);
    setMeasurements((current) => current.filter((item) => item.id !== id));
  };

  const clearMeasurements = () => {
    measureSourceRef.current.clear();
    hiddenMeasureFeaturesRef.current.clear();
    setMeasurements([]);
    setMeasureValue("");
  };

  const measurementFeature = (id: string) =>
    (measureSourceRef.current.getFeatureById(id) as Feature | null)
      ?? hiddenMeasureFeaturesRef.current.get(id) ?? null;

  const zoomToMeasurement = (id: string) => {
    const geometry = measurementFeature(id)?.getGeometry();
    if (geometry) mapRef.current?.getView().fit(geometry.getExtent(), {
      padding: [90, 420, 90, 90], maxZoom: 18, duration: 300,
    });
  };

  const measurementToPolygon = (id: string) => {
    const geometry = measurementFeature(id)?.getGeometry();
    let polygon: Polygon | null = null;
    if (geometry instanceof Polygon) polygon = geometry.clone();
    else if (geometry instanceof LineString && isClosedPath(geometry.getCoordinates())) {
      polygon = new Polygon([geometry.getCoordinates()]);
    }
    if (!polygon) return;
    sourceRef.current.addFeature(new Feature({ geometry: polygon }));
    window.setTimeout(emitGeometry, 0);
  };

  const copyMeasurements = () => {
    const rows = ["Medição\tSegmento\tDistância (m)\tAzimute\tTotal/Perímetro (m)\tÁrea (ha)"];
    for (const item of measurements) {
      for (const segment of item.segments) {
        rows.push([
          item.name, segment.index,
          segment.length.toFixed(3).replace(".", ","),
          formatAzimuth(segment.azimuth),
          item.total.toFixed(3).replace(".", ","),
          item.area === null ? "" : (item.area / 10000).toFixed(4).replace(".", ","),
        ].join("\t"));
      }
    }
    void navigator.clipboard?.writeText(rows.join("\n")).then(() => {
      setMeasureCopied(true);
      window.setTimeout(() => setMeasureCopied(false), 2000);
    });
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !measureMode) return;
    const draw = new Draw({ source: measureSourceRef.current, type: measureMode });'''

PANEL_OLD = '''      {(measureMode || measureValue) && (
        <div className="geo-measure-panel" role="status">
          <strong>{measureValue || (measureMode === "LineString"
            ? "Clique nos pontos e dê dois cliques para concluir a distância"
            : "Clique nos vértices e dê dois cliques para concluir a área")}</strong>
          <button type="button" onClick={() => { measureSourceRef.current.clear(); setMeasureValue(""); }}>Limpar medição</button>
          <button type="button" onClick={() => setMeasureMode(null)}>Concluir</button>
        </div>
      )}'''

PANEL_NEW = '''      {(measureMode || measurements.length > 0) && (
        <aside className="geo-measure-panel geo-measure-pro" aria-label="Medições">
          <header>
            <button type="button" className="measure-panel-toggle" aria-expanded={measurePanelOpen}
              onClick={() => setMeasurePanelOpen((open) => !open)}>
              <Ruler size={15} />
              <strong>Medições ({measurements.length})</strong>
            </button>
            <div>
              {measureMode && <button type="button" onClick={() => setMeasureMode(null)}>Concluir</button>}
              {measurements.length > 0 && (
                <button type="button" onClick={clearMeasurements} title="Apagar todas as medições">Limpar</button>
              )}
            </div>
          </header>
          {measurePanelOpen && (
            <>
              {measureMode && (
                <div className="measure-live" role="status" aria-live="polite">
                  {liveMeasure ? (
                    <>
                      <span>Segmento {liveMeasure.count}: <strong>{formatLength(liveMeasure.segment)}</strong> · Az {formatAzimuth(liveMeasure.azimuth)}</span>
                      <span>{measureMode === "Polygon" ? "Perímetro aberto" : "Total"}: <strong>{formatLength(liveMeasure.total)}</strong></span>
                      {liveMeasure.area !== null && <span>Área: <strong>{formatArea(liveMeasure.area)}</strong></span>}
                    </>
                  ) : (
                    <span>{measureMode === "LineString"
                      ? "Clique no ponto inicial e vá clicando: cada clique fecha um segmento. Dois cliques ou Enter concluem."
                      : "Clique nos vértices da área. Dois cliques ou Enter fecham o polígono."}</span>
                  )}
                  <small>Volte ao ponto inicial para fechar (o snap prende nele) · Backspace desfaz o último ponto · Esc cancela</small>
                </div>
              )}
              {measurements.length > 0 && (
                <ul className="measure-list">
                  {measurements.map((item, itemIndex) => (
                    <li key={item.id} className={item.visible ? "" : "is-hidden"}>
                      <div className="measure-item-head">
                        <input type="checkbox" checked={item.visible}
                          aria-label={`Mostrar ${item.name}`}
                          title="Marcar mostra no mapa; desmarcar oculta"
                          onChange={(event) => toggleMeasurementVisible(item.id, event.target.checked)} />
                        <button type="button" className="measure-name" onClick={() => zoomToMeasurement(item.id)} title="Aproximar no mapa">
                          <strong>{item.name}</strong>
                          <span>{item.area !== null
                            ? `${formatArea(item.area)} · perímetro ${formatLength(item.total)}`
                            : `${formatLength(item.total)} · ${item.segments.length} segmento(s)`}</span>
                        </button>
                        {item.area !== null && (
                          <button type="button" onClick={() => measurementToPolygon(item.id)}
                            title="Criar um polígono de trabalho com esta área" aria-label="Criar polígono">
                            <Pentagon size={14} />
                          </button>
                        )}
                        <button type="button" className="measure-remove" onClick={() => removeMeasurement(item.id)}
                          title="Excluir medição" aria-label={`Excluir ${item.name}`}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                      <details className="measure-segments-wrap" open={itemIndex === measurements.length - 1}>
                      <summary>Segmentos e azimutes</summary>
                      <table className="measure-segments">
                        <thead><tr><th>Seg.</th><th>Distância</th><th>Azimute</th></tr></thead>
                        <tbody>
                          {item.segments.map((segment) => (
                            <tr key={segment.index}>
                              <td>{segment.index}</td>
                              <td>{formatLength(segment.length)}</td>
                              <td>{formatAzimuth(segment.azimuth)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      </details>
                    </li>
                  ))}
                </ul>
              )}
              {measurements.length > 0 && (
                <div className="measure-actions">
                  <button type="button" onClick={copyMeasurements}>{measureCopied ? "Copiado" : "Copiar tabela"}</button>
                  <button type="button" className="primary" onClick={() => activateDraw("Polygon")}
                    title="Desenhar um polígono de trabalho com snap nas medições">
                    <Pentagon size={13} /> Desenhar polígono sobre as medições
                  </button>
                </div>
              )}
              <small className="measure-note">Distâncias e azimutes geodésicos (Vincenty) e área elipsoidal no GRS80 / SIRGAS 2000.</small>
            </>
          )}
        </aside>
      )}'''

CSS = '''
/* Medição profissional de distância e área */
.geo-measure-panel.geo-measure-pro {
  top: 92px; left: auto; right: 70px;
  width: min(370px, calc(100% - 90px));
  max-height: calc(100% - 120px);
  display: flex; flex-direction: column; flex-wrap: nowrap; align-items: stretch; gap: 8px;
  padding: 10px 12px 12px; border-color: #f3cf8f; border-radius: 12px; overflow: hidden;
}
.geo-measure-pro header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.geo-measure-pro header > div { display: flex; gap: 6px; }
.geo-measure-pro .measure-panel-toggle {
  display: flex; align-items: center; gap: 6px; border: 0; background: transparent; padding: 2px; color: #7c3d00;
}
.geo-measure-pro .measure-panel-toggle strong { font-size: 13px; color: #5c2d00; }
.measure-live {
  display: grid; gap: 3px; padding: 8px 10px; border-radius: 8px;
  background: #fffbeb; border: 1px solid #fde3a7; color: #5c2d00; font-size: 12px;
}
.measure-live small, .measure-note { color: #7a6a55; font-size: 10px; line-height: 1.35; }
.measure-list { list-style: none; margin: 0; padding: 0; overflow-y: auto; min-height: 0; flex: 1 1 auto; display: grid; gap: 8px; }
.measure-list li { border: 1px solid #f2dcc5; border-radius: 9px; background: #fffdf9; padding: 7px 8px; }
.measure-list li.is-hidden { opacity: .55; }
.measure-item-head { display: flex; align-items: center; gap: 7px; }
.measure-item-head > input { width: 16px; height: 16px; flex-shrink: 0; }
.geo-measure-pro .measure-item-head > button:not(.measure-name) {
  border: 1px solid #f0c48a; background: #fff7ed; color: #8a4300; border-radius: 6px; padding: 5px; cursor: pointer;
}
.geo-measure-pro .measure-item-head > button.measure-remove { border-color: #f3c4c4; background: #fff0ee; color: #9b3333; }
.geo-measure-pro .measure-name { flex: 1; min-width: 0; display: grid; text-align: left; border: 0; background: transparent; padding: 0; cursor: pointer; }
.measure-name strong { font-size: 12px; color: #173f33; }
.measure-name span { font-size: 10px; color: #6b7c74; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.measure-segments-wrap summary { cursor: pointer; margin-top: 5px; font-size: 10.5px; font-weight: 800; color: #8a4300; }
.measure-segments { width: 100%; margin-top: 6px; border-collapse: collapse; font-size: 10.5px; font-variant-numeric: tabular-nums; }
.measure-segments th { text-align: left; color: #8a6a45; font-weight: 800; border-bottom: 1px solid #f2dcc5; padding: 3px 4px; }
.measure-segments td { padding: 3px 4px; border-bottom: 1px dashed #f5e6d3; color: #2b3a33; }
.measure-actions { display: grid; grid-template-columns: auto 1fr; gap: 6px; }
.measure-actions button { display: flex; justify-content: center; align-items: center; gap: 5px; font-weight: 800; font-size: 11px; }
.geo-measure-pro .measure-actions button.primary { background: #f59e0b; border-color: #d97706; color: #fff; }
.measure-live-tooltip {
  pointer-events: none; white-space: nowrap; padding: 6px 9px; border-radius: 8px;
  background: rgba(23, 63, 51, .94); color: #fff; font: 600 11.5px/1.45 Inter, sans-serif;
  box-shadow: 0 6px 18px rgba(0,0,0,.25); font-variant-numeric: tabular-nums;
}
.measure-live-tooltip strong { color: #fcd34d; font-size: 13px; }
@media (max-width: 760px) {
  .geo-measure-panel.geo-measure-pro { left: 10px; right: 10px; width: auto; top: 140px; max-height: 50vh; }
}
'''


def main(root: pathlib.Path):
    tsx_path = root / "components/geo-map.tsx"
    css_path = root / "app/globals.css"
    s = tsx_path.read_text(encoding="utf-8")
    if "geodesicInverse" in s:
        fail("geo-map.tsx já contém a medição profissional")

    s = rep(s, 'import View from "ol/View";\n',
            'import View from "ol/View";\nimport Overlay from "ol/Overlay";\n'
            'import { unByKey } from "ol/Observable";\nimport type { EventsKey } from "ol/events";\n'
            'import type { FeatureLike } from "ol/Feature";\nimport MultiPoint from "ol/geom/MultiPoint";\n',
            "import View")
    s = rep(s, "const subjectStyle = new Style({", HELPERS + "const subjectStyle = new Style({", "subjectStyle")
    s = rep(s, '  const [measureValue, setMeasureValue] = useState("");\n',
            '  const [measureValue, setMeasureValue] = useState("");\n' + STATE, "measureValue")
    s = rep(s, '''          source: measureSourceRef.current, zIndex: 5,
          style: new Style({
            stroke: new Stroke({ color: "#eab308", width: 3, lineDash: [7, 5] }),
            fill: new Fill({ color: "rgba(234,179,8,0.16)" }),
            image: new CircleStyle({ radius: 5, fill: new Fill({ color: "#eab308" }),
              stroke: new Stroke({ color: "#fff", width: 2 }) }),
          }),
        }),''', '''          source: measureSourceRef.current, zIndex: 5,
          style: measureLayerStyle,
        }),''', "camada de medição")

    # Substitui o efeito antigo da medição pelo novo (com medida ao vivo).
    start = s.find(EFFECT_OLD_START)
    if start < 0 or s.count(EFFECT_OLD_START) != 1:
        fail("efeito de medição")
    end = s.find("  }, [measureMode]);\n", start)
    if end < 0:
        fail("fim do efeito de medição")
    end += len("  }, [measureMode]);\n")
    new_effect = EFFECT_NEW[: EFFECT_NEW.rfind("  useEffect(() => {\n    const map = mapRef.current;\n    if (!map || !measureMode) return;\n    const draw = new Draw({ source: measureSourceRef.current, type: measureMode });")]
    s = s[:start] + new_effect + s[end:]

    # Snap nas medições (sempre ativo), inclusive durante a própria medição.
    s = rep(s, '''    const layerSnap = snapLayersEnabled
      ? new Snap({''', '''    const measureSnap = new Snap({
      source: measureSourceRef.current,
      vertex: true,
      edge: true,
      intersection: true,
      pixelTolerance: 14,
    });
    map.addInteraction(measureSnap);

    const layerSnap = snapLayersEnabled
      ? new Snap({''', "snap de camadas")
    s = rep(s, '''      if (subjectSnap) map.removeInteraction(subjectSnap);
      if (layerSnap) map.removeInteraction(layerSnap);''', '''      if (subjectSnap) map.removeInteraction(subjectSnap);
      if (layerSnap) map.removeInteraction(layerSnap);
      map.removeInteraction(measureSnap);''', "remoção dos snaps")
    s = rep(s, "  }, [snapSubjectEnabled, snapLayersEnabled, drawKind, modifyActive, layers, incraUf]);",
            "  }, [snapSubjectEnabled, snapLayersEnabled, drawKind, modifyActive, measureMode, layers, incraUf]);",
            "dependências do snap")
    s = rep(s, PANEL_OLD, PANEL_NEW, "painel de medição")

    css = css_path.read_text(encoding="utf-8")
    if ".geo-measure-pro" not in css:
        css = css.rstrip("\n") + "\n" + CSS
    tsx_path.write_text(s, encoding="utf-8")
    css_path.write_text(css, encoding="utf-8")
    print("medição: geo-map.tsx e globals.css atualizados")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        fail(__doc__)
    main(pathlib.Path(sys.argv[1]))
