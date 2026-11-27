#!/usr/bin/env python3
"""Aplica sobre uma cópia do código da produção (geo44 web / geo71 api):
- download de parcelas selecionadas de qualquer base (SHP .zip / KML);
- correção "too many values to unpack (expected 2)" na exportação individual;
- checkbox dos polígonos de trabalho mostra/oculta o polígono no mapa.

Uso:  python3 aplicar_parcelas_geo44.py web <pasta-do-frontend>
      python3 aplicar_parcelas_geo44.py api <pasta-backend-app>   (pasta que contém app/)
Aborta sem gravar nada se algum trecho esperado não for encontrado.
"""
import pathlib
import re
import sys

STYLE = '// Parcelas escolhidas para download (qualquer base).\nconst downloadParcelStyle = new Style({\n  fill: new Fill({ color: "rgba(255, 128, 0, 0.22)" }),\n  stroke: new Stroke({ color: "#ff8000", width: 3, lineDash: [8, 4] }),\n});\n\ntype DownloadParcel = {\n  id: string;\n  name: string;\n  layer: string;\n  properties: Record<string, string>;\n  visible: boolean;\n};\n\n'
FUNCS = '  // ---- Seleção de parcelas (qualquer base) para download em SHP/KML ----\n  // Usa o perímetro destacado pelo Identificar (geometria integral do WFS\n  // quando disponível) ou a própria geometria poligonal da feição.\n  const identifiedPolygonGeometry = () => {\n    const highlighted = identifySelectionSourceRef.current.getFeatures()\n      .map((item) => item.getGeometry())\n      .find((geometry) => geometry && ["Polygon", "MultiPolygon"].includes(geometry.getType()));\n    if (highlighted) return highlighted;\n    const own = selectedFeatureRef.current?.getGeometry();\n    return own && ["Polygon", "MultiPolygon"].includes(own.getType()) ? own : null;\n  };\n\n  const addIdentifiedToDownload = () => {\n    if (!identifiedFeature) return;\n    const geometry = identifiedPolygonGeometry();\n    if (!geometry) {\n      setDownloadError("Esta feição não tem perímetro poligonal disponível para download.");\n      setDownloadPanelOpen(true);\n      return;\n    }\n    const key = (geometry: NonNullable<ReturnType<typeof identifiedPolygonGeometry>>) =>\n      JSON.stringify(new GeoJSON().writeGeometryObject(geometry, {\n        featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 7,\n      }));\n    const newKey = key(geometry);\n    const duplicate = downloadSourceRef.current.getFeatures().some((item) => {\n      const existing = item.getGeometry();\n      return existing && ["Polygon", "MultiPolygon"].includes(existing.getType())\n        && key(existing as typeof geometry) === newKey;\n    });\n    setDownloadError(null);\n    setDownloadPanelOpen(true);\n    if (duplicate) {\n      setDownloadError("Esta parcela já está na seleção.");\n      return;\n    }\n    downloadSequenceRef.current += 1;\n    const id = `DL-${downloadSequenceRef.current}`;\n    const properties: Record<string, string> = {};\n    for (const [field, value] of identifiedFeature.attributes) {\n      if (value === null || value === undefined || typeof value === "object") continue;\n      const text = String(value).trim();\n      if (text && !/^(Consultando|Localizando)/.test(text)) properties[field] = text;\n    }\n    const feature = new Feature({ geometry: geometry.clone() });\n    feature.setId(id);\n    feature.set("hidden", false);\n    downloadSourceRef.current.addFeature(feature);\n    setDownloadParcels((current) => [...current, {\n      id,\n      name: identifiedFeature.title || `Parcela ${downloadSequenceRef.current}`,\n      layer: identifiedFeature.layer,\n      properties,\n      visible: true,\n    }]);\n  };\n\n  const toggleDownloadParcel = (id: string, visible: boolean) => {\n    const feature = downloadSourceRef.current.getFeatureById(id);\n    feature?.set("hidden", !visible);\n    setDownloadParcels((current) => current.map((item) => item.id === id ? { ...item, visible } : item));\n  };\n\n  const removeDownloadParcel = (id: string) => {\n    const feature = downloadSourceRef.current.getFeatureById(id);\n    if (feature) downloadSourceRef.current.removeFeature(feature);\n    setDownloadParcels((current) => current.filter((item) => item.id !== id));\n  };\n\n  const clearDownloadParcels = () => {\n    downloadSourceRef.current.clear();\n    setDownloadParcels([]);\n    setDownloadError(null);\n  };\n\n  const zoomToDownloadParcel = (id: string) => {\n    const geometry = downloadSourceRef.current.getFeatureById(id)?.getGeometry();\n    if (geometry) mapRef.current?.getView().fit(geometry.getExtent(), {\n      padding: [70, 70, 70, 70], maxZoom: 17, duration: 300,\n    });\n  };\n\n  const downloadSelectedParcels = async (format: "kml" | "shp") => {\n    const chosen = downloadParcels.filter((item) => item.visible);\n    if (!chosen.length) {\n      setDownloadError("Marque ao menos uma parcela para baixar.");\n      return;\n    }\n    setDownloadBusy(true);\n    setDownloadError(null);\n    try {\n      const writer = new GeoJSON();\n      const parcels = chosen.flatMap((item) => {\n        const geometry = downloadSourceRef.current.getFeatureById(item.id)?.getGeometry();\n        return geometry ? [{\n          name: item.name,\n          layer: item.layer,\n          properties: item.properties,\n          geometry: writer.writeGeometryObject(geometry, {\n            featureProjection: "EPSG:3857", dataProjection: "EPSG:4326", decimals: 9,\n          }),\n        }] : [];\n      });\n      const response = await fetch(`${getApiUrl()}/tools/export-parcels`, {\n        method: "POST",\n        credentials: "include",\n        headers: { "Content-Type": "application/json" },\n        body: JSON.stringify({ filename: "parcelas-selecionadas", format, parcels }),\n      });\n      if (!response.ok) {\n        const body = await response.json().catch(() => null);\n        throw new Error(typeof body?.detail === "string" ? body.detail : "Falha no download das parcelas.");\n      }\n      const blob = await response.blob();\n      const url = URL.createObjectURL(blob);\n      const disposition = response.headers.get("content-disposition") ?? "";\n      const anchor = document.createElement("a");\n      anchor.href = url;\n      anchor.download = disposition.match(/filename="([^"]+)"/)?.[1]\n        ?? `parcelas-selecionadas.${format === "shp" ? "zip" : "kml"}`;\n      document.body.appendChild(anchor);\n      anchor.click();\n      anchor.remove();\n      window.setTimeout(() => URL.revokeObjectURL(url), 3000);\n    } catch (error) {\n      setDownloadError(error instanceof Error ? error.message : "Falha no download das parcelas.");\n    } finally {\n      setDownloadBusy(false);\n    }\n  };\n\n'
PANEL = '      {(downloadParcels.length > 0 || downloadError) && (\n        <aside className={`download-parcels-panel ${downloadPanelOpen ? "" : "collapsed"}`}\n          aria-label="Parcelas selecionadas para download">\n          <header>\n            <button type="button" className="download-parcels-toggle"\n              onClick={() => setDownloadPanelOpen((open) => !open)}\n              aria-expanded={downloadPanelOpen}>\n              <Download size={15} />\n              <strong>Parcelas para download ({downloadParcels.filter((item) => item.visible).length}/{downloadParcels.length})</strong>\n            </button>\n            <button type="button" onClick={clearDownloadParcels} aria-label="Limpar seleção" title="Limpar seleção">\n              <X size={16} />\n            </button>\n          </header>\n          {downloadPanelOpen && (\n            <>\n              <small>Use Identificar, clique numa parcela de qualquer base e escolha “Adicionar à seleção para download”. Somente as parcelas marcadas aparecem no mapa e entram no arquivo.</small>\n              <ul>\n                {downloadParcels.map((item) => (\n                  <li key={item.id}>\n                    <input type="checkbox" checked={item.visible}\n                      aria-label={`Mostrar e incluir ${item.name}`}\n                      title="Marcar mostra no mapa e inclui no download; desmarcar oculta"\n                      onChange={(event) => toggleDownloadParcel(item.id, event.target.checked)} />\n                    <button type="button" className="download-parcel-name"\n                      onClick={() => zoomToDownloadParcel(item.id)} title="Aproximar no mapa">\n                      <strong>{item.name}</strong>\n                      <span>{item.layer}</span>\n                    </button>\n                    <button type="button" onClick={() => removeDownloadParcel(item.id)}\n                      aria-label={`Remover ${item.name}`} title="Remover da seleção">\n                      <Trash2 size={14} />\n                    </button>\n                  </li>\n                ))}\n              </ul>\n              {downloadError && <p className="geo-tool-error" role="alert">{downloadError}</p>}\n              <div className="download-parcels-actions">\n                <button type="button" disabled={downloadBusy || !downloadParcels.some((item) => item.visible)}\n                  onClick={() => void downloadSelectedParcels("shp")}>\n                  <Download size={13} /> ZIP (SHP)\n                </button>\n                <button type="button" disabled={downloadBusy || !downloadParcels.some((item) => item.visible)}\n                  onClick={() => void downloadSelectedParcels("kml")}>\n                  <Download size={13} /> KML\n                </button>\n              </div>\n            </>\n          )}\n        </aside>\n      )}\n'
CSS = '\n/* Parcelas selecionadas (qualquer base) para download em SHP/KML */\n.feature-info-actions {\n  flex: 0 0 auto;\n  padding: 10px 15px 12px;\n  border-top: 1px solid #dce7df;\n}\n.feature-info-actions button {\n  display: flex; align-items: center; justify-content: center; gap: 6px;\n  width: 100%; padding: 9px 10px;\n  border: 1px solid #f0b37a; border-radius: 8px;\n  background: #fff4e8; color: #8a4300;\n  font-size: 12px; font-weight: 800; cursor: pointer;\n}\n.feature-info-actions button:hover { background: #ffe8d0; }\n.download-parcels-panel {\n  position: absolute;\n  z-index: 31;\n  left: 14px;\n  bottom: 78px;\n  width: min(330px, calc(100% - 28px));\n  max-height: min(55vh, calc(100% - 180px));\n  display: flex;\n  flex-direction: column;\n  gap: 8px;\n  padding: 10px 12px 12px;\n  background: #fffffff8;\n  border: 1px solid #f0c9a0;\n  border-radius: 12px;\n  box-shadow: 0 14px 38px #173f3340;\n}\n.download-parcels-panel.collapsed { padding-bottom: 10px; }\n.download-parcels-panel header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }\n.download-parcels-panel header button {\n  border: 0; background: transparent; color: #8a4300; cursor: pointer; padding: 4px;\n  display: flex; align-items: center; gap: 6px; text-align: left;\n}\n.download-parcels-panel header strong { font-size: 12px; color: #5c2d00; }\n.download-parcels-panel > small { color: #667a70; font-size: 10px; line-height: 1.35; }\n.download-parcels-panel ul {\n  list-style: none; margin: 0; padding: 0;\n  overflow-y: auto; min-height: 0; flex: 1 1 auto;\n  display: grid; gap: 6px;\n}\n.download-parcels-panel li {\n  display: flex; align-items: center; gap: 8px;\n  padding: 6px 8px; border: 1px solid #f2dcc5; border-radius: 8px; background: #fffaf5;\n}\n.download-parcels-panel li > input { width: 17px; height: 17px; flex-shrink: 0; }\n.download-parcels-panel li > button:last-child {\n  border: 0; background: #fff0ee; color: #9b3333; border-radius: 6px; padding: 6px; cursor: pointer;\n}\n.download-parcel-name {\n  flex: 1; min-width: 0; border: 0; background: transparent; padding: 0;\n  display: grid; text-align: left; cursor: pointer;\n}\n.download-parcel-name strong, .download-parcel-name span {\n  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;\n}\n.download-parcel-name strong { font-size: 11px; color: #173f33; }\n.download-parcel-name span { font-size: 10px; color: #7a8a82; }\n.download-parcels-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }\n.download-parcels-actions button {\n  display: flex; justify-content: center; align-items: center; gap: 4px;\n  border: 1px solid #f0b37a; background: #ff8000; color: #fff;\n  padding: 8px 4px; border-radius: 7px; cursor: pointer; font-size: 11px; font-weight: 800;\n}\n.download-parcels-actions button + button { background: #fff; color: #8a4300; }\n.download-parcels-actions button:disabled { opacity: .5; cursor: not-allowed; }\n@media (max-width: 760px) {\n  .download-parcels-panel { left: 10px; right: 10px; width: auto; bottom: 70px; }\n}\n'
SVC = '"""Exportação de parcelas selecionadas no mapa (qualquer base) em SHP ou KML.\n\nCada parcela chega em GeoJSON (EPSG:4326, como o mapa as entrega) com o nome,\na camada de origem e os atributos consultados pelo Identificar. O resultado\né um único arquivo com todas as parcelas, preservando os atributos.\n"""\nfrom __future__ import annotations\n\nimport csv\nimport io\nimport re\nimport tempfile\nimport unicodedata\nimport zipfile\nfrom pathlib import Path\nfrom xml.sax.saxutils import escape\n\nimport geopandas as gpd\nfrom pyproj import Geod\nfrom shapely import force_2d, make_valid\nfrom shapely.geometry import MultiPolygon, Polygon, shape\nfrom shapely.geometry.base import BaseGeometry\n\nMAX_PARCELS = 500\n_GEOD = Geod(ellps="GRS80")\n_FIXED = ("NOME", "CAMADA", "AREA_HA")\n\n\ndef _slug(value: str) -> str:\n    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")[:65] or "parcelas"\n\n\ndef _ascii(value: str) -> str:\n    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")\n\n\ndef _polygonal(value: dict) -> Polygon | MultiPolygon:\n    geometry: BaseGeometry = force_2d(shape(value))\n    if geometry.is_empty:\n        raise ValueError("Parcela sem geometria.")\n    if not geometry.is_valid:\n        geometry = make_valid(geometry)\n    if geometry.geom_type == "GeometryCollection":\n        parts = [g for g in geometry.geoms if isinstance(g, (Polygon, MultiPolygon))]\n        polys = [p for g in parts for p in (g.geoms if isinstance(g, MultiPolygon) else [g])]\n        geometry = MultiPolygon(polys) if len(polys) > 1 else (polys[0] if polys else geometry)\n    if not isinstance(geometry, (Polygon, MultiPolygon)):\n        raise ValueError("Somente parcelas poligonais podem ser exportadas.")\n    return geometry\n\n\ndef _area_ha(geometry: Polygon | MultiPolygon) -> float:\n    return abs(_GEOD.geometry_area_perimeter(geometry)[0]) / 10000\n\n\ndef _text(value) -> str:\n    if value is None:\n        return ""\n    return str(value).strip()\n\n\ndef _field_names(keys: list[str]) -> dict[str, str]:\n    """Nomes de campo DBF: até 10 caracteres ASCII, únicos e sem colidir com os fixos."""\n    used = set(_FIXED)\n    mapping: dict[str, str] = {}\n    for key in keys:\n        base = re.sub(r"[^A-Za-z0-9_]+", "_", _ascii(key)).strip("_").upper() or "CAMPO"\n        candidate = base[:10]\n        counter = 1\n        while candidate in used:\n            suffix = str(counter)\n            candidate = base[: 10 - len(suffix)] + suffix\n            counter += 1\n        used.add(candidate)\n        mapping[key] = candidate\n    return mapping\n\n\ndef _prepare(parcels: list[dict]) -> list[dict]:\n    if not parcels:\n        raise ValueError("Selecione ao menos uma parcela para exportar.")\n    if len(parcels) > MAX_PARCELS:\n        raise ValueError(f"Exporte no máximo {MAX_PARCELS} parcelas por vez.")\n    prepared = []\n    for index, parcel in enumerate(parcels, start=1):\n        name = _text(parcel.get("name")) or f"Parcela {index}"\n        try:\n            geometry = _polygonal(parcel.get("geometry") or {})\n        except Exception as exc:  # shapely lança erros variados para GeoJSON inválido\n            raise ValueError(f"{name}: {exc}") from exc\n        properties = {\n            _text(key): _text(value)\n            for key, value in (parcel.get("properties") or {}).items()\n            if _text(key)\n        }\n        prepared.append({\n            "name": name,\n            "layer": _text(parcel.get("layer")),\n            "geometry": geometry,\n            "area_ha": _area_ha(geometry),\n            "properties": properties,\n        })\n    return prepared\n\n\ndef _kml_polygon(polygon: Polygon) -> str:\n    def ring(coords) -> str:\n        return " ".join(f"{x:.9f},{y:.9f},0" for x, y in coords)\n\n    inner = "".join(\n        f"<innerBoundaryIs><LinearRing><coordinates>{ring(interior.coords)}"\n        "</coordinates></LinearRing></innerBoundaryIs>"\n        for interior in polygon.interiors\n    )\n    return (\n        f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{ring(polygon.exterior.coords)}"\n        f"</coordinates></LinearRing></outerBoundaryIs>{inner}</Polygon>"\n    )\n\n\ndef _kml(prepared: list[dict], title: str) -> bytes:\n    placemarks = []\n    for parcel in prepared:\n        geometry = parcel["geometry"]\n        polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]\n        body = "".join(_kml_polygon(p) for p in polygons)\n        if len(polygons) > 1:\n            body = f"<MultiGeometry>{body}</MultiGeometry>"\n        data = {"Camada": parcel["layer"], "Área (ha)": f"{parcel[\'area_ha\']:.4f}", **parcel["properties"]}\n        extended = "".join(\n            f\'<Data name="{escape(key, {chr(34): "&quot;"})}"><value>{escape(value)}</value></Data>\'\n            for key, value in data.items()\n        )\n        placemarks.append(\n            f"<Placemark><name>{escape(parcel[\'name\'])}</name><styleUrl>#parcela</styleUrl>"\n            f"<ExtendedData>{extended}</ExtendedData>{body}</Placemark>"\n        )\n    kml = (\n        \'<?xml version="1.0" encoding="UTF-8"?>\'\n        \'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>\'\n        f"<name>{escape(title)}</name>"\n        "<description>Parcelas selecionadas no Amazônika Geoespacial (WGS84).</description>"\n        \'<Style id="parcela"><LineStyle><color>ff0080ff</color><width>2</width></LineStyle>\'\n        "<PolyStyle><color>400080ff</color></PolyStyle></Style>"\n        + "".join(placemarks)\n        + "</Document></kml>"\n    )\n    return kml.encode("utf-8")\n\n\ndef _shapefile_zip(prepared: list[dict], title: str) -> bytes:\n    keys: list[str] = []\n    for parcel in prepared:\n        for key in parcel["properties"]:\n            if key not in keys:\n                keys.append(key)\n    mapping = _field_names(keys)\n    rows = []\n    for parcel in prepared:\n        row = {\n            "NOME": parcel["name"][:254],\n            "CAMADA": parcel["layer"][:254],\n            "AREA_HA": round(parcel["area_ha"], 4),\n        }\n        for key, field in mapping.items():\n            row[field] = parcel["properties"].get(key, "")[:254]\n        rows.append(row)\n    frame = gpd.GeoDataFrame(\n        rows,\n        geometry=[parcel["geometry"] for parcel in prepared],\n        crs="EPSG:4326",\n    )\n    # Shapefile exige um único tipo; polígonos simples viram MultiPolygon de uma parte.\n    frame["geometry"] = frame.geometry.apply(\n        lambda g: MultiPolygon([g]) if isinstance(g, Polygon) else g\n    )\n    with tempfile.TemporaryDirectory(prefix="amazonika-parcelas-") as directory:\n        root = Path(directory)\n        frame.to_file(\n            root / "parcelas.shp", driver="ESRI Shapefile", engine="pyogrio",\n            layer_options={"ENCODING": "UTF-8"},\n        )\n        with open(root / "atributos.csv", "w", encoding="utf-8-sig", newline="") as handle:\n            writer = csv.writer(handle, delimiter=";")\n            writer.writerow(["NOME", "CAMADA", "AREA_HA", *keys])\n            for parcel in prepared:\n                writer.writerow([\n                    parcel["name"], parcel["layer"], f"{parcel[\'area_ha\']:.4f}".replace(".", ","),\n                    *[parcel["properties"].get(key, "") for key in keys],\n                ])\n        legend = "\\n".join(f"{field} = {key}" for key, field in mapping.items())\n        (root / "leia-me.txt").write_text(\n            f"{title}\\n"\n            f"{len(prepared)} parcela(s) selecionada(s) no Amazônika Geoespacial.\\n"\n            "Sistema de referência: WGS84 (EPSG:4326), coordenadas geográficas.\\n"\n            "AREA_HA calculada no elipsoide GRS80.\\n"\n            "Os nomes de campo do Shapefile são limitados a 10 caracteres; "\n            "os atributos completos estão em atributos.csv.\\n"\n            + (f"\\nCampos:\\n{legend}\\n" if legend else ""),\n            encoding="utf-8",\n        )\n        output = io.BytesIO()\n        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:\n            for path in sorted(root.iterdir()):\n                if path.is_file():\n                    archive.write(path, path.name)\n        return output.getvalue()\n\n\ndef export_parcels(*, parcels: list[dict], filename: str, format: str) -> tuple[bytes, str, str]:\n    prepared = _prepare(parcels)\n    stem = _slug(filename)\n    title = filename.strip() or "Parcelas selecionadas"\n    if format == "kml":\n        return _kml(prepared, title), f"{stem}.kml", "application/vnd.google-earth.kml+xml"\n    if format == "shp":\n        return _shapefile_zip(prepared, title), f"{stem}-shapefile.zip", "application/zip"\n    raise ValueError("Formato inválido. Use kml ou shp.")\n'
ROUTE = 'class SelectedParcel(BaseModel):\n    name: str = Field(default="", max_length=255)\n    layer: str = Field(default="", max_length=255)\n    geometry: dict[str, Any]\n    properties: dict[str, Any] = Field(default_factory=dict)\n\n\nclass ExportParcelsRequest(BaseModel):\n    filename: str = Field(default="parcelas-selecionadas", min_length=1, max_length=180)\n    format: str = Field(pattern="^(kml|shp)$")\n    parcels: list[SelectedParcel] = Field(min_length=1, max_length=500)\n\n\n@router.post("/export-parcels")\ndef download_selected_parcels(payload: ExportParcelsRequest):\n    """Baixa, num único arquivo, as parcelas selecionadas de qualquer base."""\n    try:\n        data, filename, media_type = export_parcels(\n            parcels=[item.model_dump() for item in payload.parcels],\n            filename=payload.filename,\n            format=payload.format,\n        )\n    except ValueError as exc:\n        raise HTTPException(422, str(exc)) from exc\n    return Response(\n        content=data,\n        media_type=media_type,\n        headers={\n            "Content-Disposition": f\'attachment; filename="{filename}"\',\n            "Cache-Control": "no-store",\n        },\n    )\n\n\n'


def fail(msg):
    print("ERRO:", msg)
    print("Nada foi gravado.")
    sys.exit(1)


def rep(text, old, new, label, count=1):
    found = text.count(old)
    if found != count:
        fail(f"trecho '{label}' encontrado {found} vez(es), esperado {count}")
    return text.replace(old, new)


def web(root: pathlib.Path):
    tsx_path = root / "components/geo-map.tsx"
    css_path = root / "app/globals.css"
    s = tsx_path.read_text(encoding="utf-8")
    if "downloadParcelStyle" in s:
        fail("geo-map.tsx já contém o download de parcelas")

    m = re.search(r'import \{([^}]*)\} from "lucide-react";', s)
    if not m:
        fail("import do lucide-react")
    if "ListPlus" not in m.group(1):
        s = s[:m.start(1)] + "\n  ListPlus," + m.group(1) + s[m.end(1):]

    s = rep(s, "const officialStyleCache = new globalThis.Map<string, Style>();\n",
            STYLE + "const officialStyleCache = new globalThis.Map<string, Style>();\n", "officialStyleCache")
    s = rep(s, "  const polygonSequenceRef = useRef(0);\n", """  const polygonSequenceRef = useRef(0);
  // Polígonos de trabalho desmarcados pelo usuário ficam ocultos no mapa.
  const hiddenPolygonIdsRef = useRef(new Set<string>());
  const downloadSourceRef = useRef(new VectorSource());
  const downloadSequenceRef = useRef(0);
  const [downloadParcels, setDownloadParcels] = useState<DownloadParcel[]>([]);
  const [downloadPanelOpen, setDownloadPanelOpen] = useState(true);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
""", "polygonSequenceRef")
    s = rep(s, """        new VectorLayer({
          source: sourceRef.current,
          zIndex: 3,
          style: subjectStyle,
        }),
""", """        new VectorLayer({
          source: sourceRef.current,
          zIndex: 3,
          style: (feature) =>
            hiddenPolygonIdsRef.current.has(String(feature.get("workPolygonId") ?? ""))
              ? undefined
              : subjectStyle,
        }),
        new VectorLayer({
          source: downloadSourceRef.current,
          zIndex: 6,
          style: (feature) => (feature.get("hidden") ? undefined : downloadParcelStyle),
        }),
""", "camada sourceRef")
    s = rep(s, """    for (const feature of polygonFeatures()) {
      const geometry = feature.getGeometry() as Polygon;
      const ring = geometry.getCoordinates()[0] ?? [];
      const names = (feature.get("vertexNames") as string[] | undefined) ?? [];""",
            """    for (const feature of polygonFeatures()) {
      if (hiddenPolygonIdsRef.current.has(String(feature.get("workPolygonId") ?? ""))) continue;
      const geometry = feature.getGeometry() as Polygon;
      const ring = geometry.getCoordinates()[0] ?? [];
      const names = (feature.get("vertexNames") as string[] | undefined) ?? [];""", "refreshVertexLabels")
    s = rep(s, """  useEffect(() => {
    const features = sourceRef.current.getFeatures();
    if (!features.length) return;
    const primary""", """  // Polígono marcado é sempre visível; desmarcado pelo usuário fica oculto.
  const setPolygonVisible = (id: string, visible: boolean) => {
    if (visible) hiddenPolygonIdsRef.current.delete(id);
    else hiddenPolygonIdsRef.current.add(id);
    sourceRef.current.changed();
    refreshVertexLabels();
  };

  useEffect(() => {
    let changed = false;
    for (const id of selectedPolygonIds) {
      if (hiddenPolygonIdsRef.current.delete(id)) changed = true;
    }
    if (changed) {
      sourceRef.current.changed();
      refreshVertexLabels();
    }
  }, [selectedPolygonIds]);

  useEffect(() => {
    const features = sourceRef.current.getFeatures();
    if (!features.length) return;
    const primary""", "useEffect selectedPolygonIds")
    s = rep(s, """                  onChange={(event) => setSelectedPolygonIds((current) =>
                    event.target.checked
                      ? [...new Set([...current, polygon.id])]
                      : current.filter((id) => id !== polygon.id)
                  )}""", """                  title="Marcar mostra o polígono no mapa; desmarcar oculta"
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setPolygonVisible(polygon.id, checked);
                    setSelectedPolygonIds((current) =>
                      checked
                        ? [...new Set([...current, polygon.id])]
                        : current.filter((id) => id !== polygon.id)
                    );
                  }}""", "checkbox do polígono")
    s = re.sub(r"(?m)^    setSelectedPolygonIds\(\[\]\);$",
               "    setSelectedPolygonIds([]);\n    hiddenPolygonIdsRef.current.clear();", s)
    s = s.replace("""      sourceRef.current.clear();
      sourceRef.current.addFeatures(features as Feature[]);""", """      sourceRef.current.clear();
      hiddenPolygonIdsRef.current.clear();
      sourceRef.current.addFeatures(features as Feature[]);""")
    s = rep(s, "  const clearIdentifiedFeature = () => {",
            FUNCS + "  const clearIdentifiedFeature = () => {", "clearIdentifiedFeature")
    s = rep(s, """                  <dd>{fieldValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
""", """                  <dd>{fieldValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="feature-info-actions">
            <button type="button" onClick={addIdentifiedToDownload}
              title="Adiciona esta parcela à lista para baixar em SHP (.zip) ou KML">
              <ListPlus size={15} /> Adicionar à seleção para download
            </button>
          </div>
""", "painel Identificar")
    s = rep(s, """      {drawKind && (
        <div className="draw-hint">""", PANEL + """      {drawKind && (
        <div className="draw-hint">""", "drawKind")

    css = css_path.read_text(encoding="utf-8")
    if ".download-parcels-panel" not in css:
        css = css.rstrip("\n") + "\n" + CSS
    tsx_path.write_text(s, encoding="utf-8")
    css_path.write_text(css, encoding="utf-8")
    print("web: geo-map.tsx e globals.css atualizados")


def api(root: pathlib.Path):
    export_path = root / "app/services/geospatial_export.py"
    tools_path = root / "app/api/routes/tools.py"
    svc_path = root / "app/services/parcel_selection_export.py"
    e = export_path.read_text(encoding="utf-8")
    t = tools_path.read_text(encoding="utf-8")
    if "force_2d" not in e:
        e = rep(e, "from shapely.geometry import MultiPolygon, Point, Polygon, shape\n",
                "from shapely import force_2d\nfrom shapely.geometry import MultiPolygon, Point, Polygon, shape\n",
                "import shapely em geospatial_export")
        e = rep(e, """def _geometry(value: dict) -> Polygon:
    geometry = shape(value)
""", """def _geometry(value: dict) -> Polygon:
    # Polígonos importados (KML/SIGEF) ou com altitude informada chegam com
    # coordenadas XYZ; a exportação planimétrica usa somente X/Y.
    geometry = force_2d(shape(value))
    if isinstance(geometry, MultiPolygon) and len(geometry.geoms) == 1:
        geometry = geometry.geoms[0]
""", "_geometry em geospatial_export")
    if "/export-parcels" not in t:
        t = rep(t, "from app.services.geospatial_export import export_polygon\n",
                "from app.services.geospatial_export import export_polygon\n"
                "from app.services.parcel_selection_export import export_parcels\n",
                "import export_polygon em tools.py")
        t = rep(t, '@router.post("/convert-vector")', ROUTE + '@router.post("/convert-vector")',
                "rota convert-vector em tools.py")
    svc_path.write_text(SVC, encoding="utf-8")
    export_path.write_text(e, encoding="utf-8")
    tools_path.write_text(t, encoding="utf-8")
    print("api: geospatial_export.py, tools.py e parcel_selection_export.py atualizados")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"web", "api"}:
        fail(__doc__)
    {"web": web, "api": api}[sys.argv[1]](pathlib.Path(sys.argv[2]))
