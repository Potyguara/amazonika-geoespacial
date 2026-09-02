"use client";

import { useEffect, useRef, useState } from "react";
import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import MVT from "ol/format/MVT";
import KML from "ol/format/KML";
import Draw from "ol/interaction/Draw";
import Modify from "ol/interaction/Modify";
import Map from "ol/Map";
import MapBrowserEvent from "ol/MapBrowserEvent";
import ImageLayer from "ol/layer/Image";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorTileLayer from "ol/layer/VectorTile";
import { fromLonLat } from "ol/proj";
import OSM from "ol/source/OSM";
import ImageWMS from "ol/source/ImageWMS";
import VectorSource from "ol/source/Vector";
import VectorTileSource from "ol/source/VectorTile";
import { Fill, Stroke, Style, Circle as CircleStyle } from "ol/style";
import View from "ol/View";
import { getApiUrl } from "@/lib/api";
import {
  Crosshair,
  Eraser,
  FileUp,
  Info,
  MapPin,
  Pencil,
  Pentagon,
  X,
} from "lucide-react";

type DrawKind = "Point" | "Polygon" | null;

interface GeoMapProps {
  onGeometryChange: (geometry: Record<string, unknown> | null) => void;
  incraUf: string;
  layers: Array<{
    id?: string;
    slug?: string;
    name: string;
    color: string;
    enabled: boolean;
    source?: string;
    wmsEnabled?: boolean;
    wmsTheme?: string;
    wmsFixedLayer?: string;
    wmsAvailableUfs?: string[];
  }>;
}

const subjectStyle = new Style({
  fill: new Fill({ color: "rgba(27, 126, 85, 0.18)" }),
  stroke: new Stroke({ color: "#0d6847", width: 3 }),
  image: new CircleStyle({
    radius: 8,
    fill: new Fill({ color: "#e44f5f" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});

const officialStyleCache = new globalThis.Map<string, Style>();
const selectedOfficialStyle = new Style({
  fill: new Fill({ color: "rgba(255, 193, 7, 0.35)" }),
  stroke: new Stroke({ color: "#ff9f1c", width: 4 }),
  image: new CircleStyle({
    radius: 7,
    fill: new Fill({ color: "#ff9f1c" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});

type IdentifiedFeature = {
  title: string;
  layer: string;
  attributes: Array<[string, unknown]>;
  loading?: boolean;
};

type IdentifyCandidate = { feature: Feature; title: string; layer: string };

function featureIdentity(feature: Feature) {
  const raw = feature.getProperties();
  const layer = String(raw.catalogName ?? raw.source_name ?? "Camada oficial");
  const title = String(
    raw.name ??
      raw.nome ??
      raw.nome_uc ??
      raw.nome_proje ??
      raw.nom_pessoa ??
      raw.denominacao ??
      raw.external_id ??
      "Feição identificada",
  );
  return { raw, layer, title };
}

function fieldLabel(field: string) {
  const labels: Record<string, string> = {
    catalogName: "Camada",
    source_name: "Fonte",
    source_id: "Identificador da fonte",
    feature_id: "Identificador interno",
    external_id: "Identificador na origem",
  };
  return (
    labels[field] ??
    field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

function fieldValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function officialStyle(color: string) {
  if (!officialStyleCache.has(color)) {
    officialStyleCache.set(
      color,
      new Style({
        fill: new Fill({ color: `${color}38` }),
        stroke: new Stroke({ color, width: 2 }),
        image: new CircleStyle({
          radius: 5,
          fill: new Fill({ color }),
          stroke: new Stroke({ color: "#ffffff", width: 1 }),
        }),
      }),
    );
  }
  return officialStyleCache.get(color)!;
}

const UF_VIEW: Record<string, { center: [number, number]; zoom: number }> = {
  AC: { center: [-70.3, -9.0], zoom: 6.4 },
  AL: { center: [-36.6, -9.6], zoom: 7.6 },
  AP: { center: [-51.8, 1.4], zoom: 6.6 },
  AM: { center: [-64.6, -4.5], zoom: 5.4 },
  BA: { center: [-41.8, -12.5], zoom: 6.0 },
  CE: { center: [-39.5, -5.2], zoom: 6.8 },
  DF: { center: [-47.8, -15.8], zoom: 9.0 },
  ES: { center: [-40.5, -19.6], zoom: 7.4 },
  GO: { center: [-49.3, -15.9], zoom: 6.4 },
  MA: { center: [-45.3, -5.0], zoom: 6.2 },
  MT: { center: [-56.1, -12.6], zoom: 5.8 },
  MS: { center: [-54.5, -20.5], zoom: 6.1 },
  MG: { center: [-44.3, -18.5], zoom: 6.0 },
  PA: { center: [-52.5, -3.8], zoom: 5.8 },
  PB: { center: [-36.7, -7.1], zoom: 7.4 },
  PR: { center: [-51.5, -24.6], zoom: 6.5 },
  PE: { center: [-37.9, -8.4], zoom: 7.0 },
  PI: { center: [-42.7, -7.5], zoom: 6.3 },
  RJ: { center: [-43.2, -22.2], zoom: 7.4 },
  RN: { center: [-36.6, -5.8], zoom: 7.4 },
  RS: { center: [-53.2, -30.0], zoom: 6.0 },
  RO: { center: [-63.1, -10.9], zoom: 6.4 },
  RR: { center: [-61.3, 2.1], zoom: 6.4 },
  SC: { center: [-50.2, -27.3], zoom: 7.0 },
  SP: { center: [-48.7, -22.3], zoom: 6.5 },
  SE: { center: [-37.4, -10.6], zoom: 7.6 },
  TO: { center: [-48.3, -10.2], zoom: 6.3 },
  ALL: { center: [-52.3, -14.5], zoom: 4.2 },
};

export function GeoMap({ onGeometryChange, layers, incraUf }: GeoMapProps) {
  const mapElement = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef(new VectorSource());
  const officialSourceRef = useRef(new VectorSource());
  const wmsLayersRef = useRef(
    new globalThis.Map<string, ImageLayer<ImageWMS>>(),
  );
  const vectorTileLayersRef = useRef(
    new globalThis.Map<string, VectorTileLayer>(),
  );
  const layersRef = useRef(layers);
  const incraUfRef = useRef(incraUf);
  incraUfRef.current = incraUf;
  const identifyAbortRef = useRef<AbortController | null>(null);
  const drawRef = useRef<Draw | null>(null);
  const modifyRef = useRef<Modify | null>(null);
  const identifyActiveRef = useRef(false);
  const selectedFeatureRef = useRef<Feature | null>(null);
  const selectFeatureRef = useRef<(feature: Feature) => void>(() => undefined);
  const [drawKind, setDrawKind] = useState<DrawKind>(null);
  const [modifyActive, setModifyActive] = useState(false);
  const [identifyActive, setIdentifyActive] = useState(false);
  const [identifiedFeature, setIdentifiedFeature] =
    useState<IdentifiedFeature | null>(null);
  const [identifyCandidates, setIdentifyCandidates] = useState<
    IdentifyCandidate[]
  >([]);
  const [officialCount, setOfficialCount] = useState(0);
  const [loadingOfficial, setLoadingOfficial] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState({ completed: 0, total: 0 });
  const [officialStatus, setOfficialStatus] = useState(
    "Preparando camadas oficiais…",
  );

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const target = UF_VIEW[incraUf] ?? UF_VIEW.ALL;

    setLoadingProgress({ completed: 0, total: 0 });
    setLoadingOfficial(true);
    setOfficialStatus(
      incraUf === "ALL"
        ? "Reposicionando mapa para o Brasil…"
        : `Reposicionando mapa para ${incraUf}…`,
    );

    map.getView().animate(
      {
        center: fromLonLat(target.center),
        zoom: target.zoom,
        duration: 650,
      },
    );
  }, [incraUf]);

  const emitGeometry = () => {
    const feature = sourceRef.current.getFeatures()[0];
    const geometry = feature?.getGeometry();
    if (!geometry) {
      onGeometryChange(null);
      return;
    }
    const output = new GeoJSON().writeGeometryObject(geometry, {
      featureProjection: "EPSG:3857",
      dataProjection: "EPSG:4326",
      decimals: 8,
    });
    onGeometryChange(output as Record<string, unknown>);
  };

  const clearIdentifiedFeature = () => {
    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;
    if (selectedFeatureRef.current) {
      selectedFeatureRef.current.set("isSelected", false);
      selectedFeatureRef.current.changed();
      selectedFeatureRef.current = null;
    }
    officialSourceRef.current.clear();
    setIdentifiedFeature(null);
    setIdentifyCandidates([]);
  };

  selectFeatureRef.current = (feature: Feature) => {
    clearIdentifiedFeature();
    selectedFeatureRef.current = feature;
    feature.set("isSelected", true);
    feature.changed();
    const { raw, layer, title } = featureIdentity(feature);
    const sourceId = String(raw.source_id ?? "");
    const featureId = String(raw.feature_id ?? feature.getId() ?? "");
    const fallbackAttributes = Object.entries(raw).filter(
      ([key]) =>
        !["geometry", "displayColor", "isSelected", "catalogName"].includes(
          key,
        ),
    );
    setIdentifiedFeature({
      title,
      layer,
      attributes: fallbackAttributes,
      loading: true,
    });
    if (!sourceId || !featureId) {
      setIdentifiedFeature({ title, layer, attributes: fallbackAttributes });
      return;
    }
    const controller = new AbortController();
    identifyAbortRef.current = controller;
    void fetch(
      `${getApiUrl()}/sources/${sourceId}/features/${featureId}`,
      { signal: controller.signal },
    )
      .then((response) => {
        if (!response.ok)
          throw new Error("Não foi possível consultar os atributos.");
        return response.json();
      })
      .then((detail) => {
        if (controller.signal.aborted || selectedFeatureRef.current !== feature)
          return;
        const properties = detail.properties ?? {};
        const detailTitle = String(
          properties.name ??
            properties.nome ??
            properties.nome_uc ??
            properties.nome_proje ??
            properties.nom_pessoa ??
            properties.denominacao ??
            properties.external_id ??
            title,
        );
        setIdentifiedFeature({
          title: detailTitle,
          layer,
          attributes: Object.entries(properties),
        });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        if (!controller.signal.aborted)
          setIdentifiedFeature({
            title,
            layer,
            attributes: [
              ...fallbackAttributes,
              [
                "consulta_atributos",
                "Não foi possível carregar os atributos completos.",
              ],
            ],
          });
      });
  };

  useEffect(() => {
    if (!mapElement.current || mapRef.current) return;
    const map = new Map({
      target: mapElement.current,
      layers: [
        new TileLayer({ source: new OSM(), zIndex: 0 }),
        new VectorLayer({
          source: officialSourceRef.current,
          zIndex: 2,
          style: (feature) =>
            feature.get("isSelected")
              ? selectedOfficialStyle
              : officialStyle(String(feature.get("displayColor") ?? "#36a269")),
        }),
        new VectorLayer({
          source: sourceRef.current,
          zIndex: 3,
          style: subjectStyle,
        }),
      ],
      view: new View({
        center: fromLonLat((UF_VIEW[incraUf] ?? UF_VIEW.ALL).center),
        zoom: (UF_VIEW[incraUf] ?? UF_VIEW.ALL).zoom,
      }),
    });
    mapRef.current = map;
    const identifyAtPixel = (event: MapBrowserEvent<PointerEvent>) => {
      if (!identifyActiveRef.current) return;
      const candidates = map
        .getFeaturesAtPixel(event.pixel, { hitTolerance: 7 })
        .filter(
          (candidate): candidate is Feature =>
            candidate instanceof Feature &&
            Boolean(candidate.get("catalogName")),
        );
      clearIdentifiedFeature();
      if (!candidates.length) {
        const sicar =
          layersRef.current.find(
            (layer) =>
              layer.enabled &&
              layer.id &&
              layer.source === "SPU",
          ) ??
          layersRef.current.find(
            (layer) =>
              layer.enabled &&
              layer.id &&
              layer.source === "SICAR",
          );

        if (!sicar?.id) return;

        const wmsSource = wmsLayersRef.current
          .get(sicar.id)
          ?.getSource();

        const resolution = map.getView().getResolution();
        const projection = map.getView().getProjection();

        if (!wmsSource || !resolution) return;

        const infoUrl = wmsSource.getFeatureInfoUrl(
          event.coordinate,
          resolution,
          projection,
          {
            INFO_FORMAT: "application/json",
            FEATURE_COUNT: 10,
          },
        );

        if (!infoUrl) return;

        identifyAbortRef.current?.abort();
        const controller = new AbortController();
        identifyAbortRef.current = controller;

        setIdentifiedFeature({
          title: `Consultando ${sicar.name}…`,
          layer: sicar.name,
          attributes: [],
          loading: true,
        });

        void fetch(infoUrl, { signal: controller.signal })
          .then(async (response) => {
            if (!response.ok)
              throw new Error(`HTTP ${response.status}`);

            return response.json();
          })
          .then((result) => {
            if (controller.signal.aborted) return;

            const feature = result?.features?.[0];

            if (!feature) {
              setIdentifiedFeature(null);
              return;
            }

            const properties = feature.properties ?? {};

            if (feature.geometry) {
              try {
                const highlightFeature = new GeoJSON().readFeature(feature, {
                  dataProjection: "EPSG:3857",
                  featureProjection: "EPSG:3857",
                });

                highlightFeature.set("isSelected", true);
                selectedFeatureRef.current = highlightFeature;

                officialSourceRef.current.clear();
                officialSourceRef.current.addFeature(highlightFeature);
              } catch (error) {
                console.warn(`Falha ao destacar ${sicar.source}`, error);
              }
            }

            setIdentifiedFeature({
              title: String(
                properties.cod_imovel ??
                  properties.RIP ??
                  properties.rip ??
                  properties.nome_imovel ??
                  properties.nome ??
                  properties.denominacao ??
                  sicar.name
              ),
              layer: sicar.name,
              attributes: Object.entries(properties),
            });
          })
          .catch((error) => {
            if (
              error instanceof DOMException &&
              error.name === "AbortError"
            ) return;

            setIdentifiedFeature({
              title: sicar.name,
              layer: sicar.name,
              attributes: [
                ["consulta_atributos", String(error)],
              ],
            });
          });

        return;
      }
      if (candidates.length === 1) {
        selectFeatureRef.current(candidates[0]);
        return;
      }
      setIdentifyCandidates(
        candidates
          .map((feature) => ({ feature, ...featureIdentity(feature) }))
          .map(({ feature, title, layer }) => ({ feature, title, layer })),
      );
    };
    map.on("singleclick", identifyAtPixel);
    return () => {
      map.un("singleclick", identifyAtPixel);
      identifyAbortRef.current?.abort();
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    identifyActiveRef.current = identifyActive;
    if (!identifyActive) clearIdentifiedFeature();
  }, [identifyActive]);

  useEffect(() => {
    layersRef.current = layers;
    const map = mapRef.current;
    if (!map) return;

    const desiredVectorTiles = new Set<string>();

    const isParcelLayer = (layer: (typeof layers)[number]) =>
      layer.slug === "sigef-interno" ||
      layer.slug === "incra-fundiario" ||
      /sigef|parcela/i.test(layer.name);

    const minimumVectorZoom = (layer: (typeof layers)[number]) => {
      if (isParcelLayer(layer)) return 9;

      if (layer.slug === "anm-processos-minerarios") return 7;

      if (layer.source === "IBAMA") return 7;
      if (layer.source === "FUNAI") return 5;
      if (layer.source === "ICMBio") return 5;

      if (layer.source === "IPHAN") {
        if (/sítio|sitio/i.test(layer.name)) return 8;
        return 7;
      }

      return 0;
    };

    for (const layer of layers) {
      if (!layer.id || !layer.enabled) continue;

      // Fontes oficiais particionadas que já possuem WMS permanecem
      // exclusivamente no serviço oficial enquanto a cópia vetorial
      // local não estiver completa. O SIGEF interno da Amazônika,
      // que não depende desse WMS, continua usando MVT local.
      const useOfficialWmsOnly =
        (layer.source === "SICAR" ||
          layer.source === "SPU") &&
        layer.wmsEnabled &&
        layer.wmsTheme;

      if (useOfficialWmsOnly) {
        const staleVectorTile = vectorTileLayersRef.current.get(layer.id);
        if (staleVectorTile) {
          staleVectorTile.getSource()?.clear();
          map.removeLayer(staleVectorTile);
          vectorTileLayersRef.current.delete(layer.id);
        }
        continue;
      }

      // Vetores locais nacionais podem ser consultados em qualquer UF
      // ou no Brasil inteiro. O próprio endpoint MVT aplica o filtro
      // estadual quando uma UF específica é selecionada.
      const tileUf = incraUf === "ALL" ? "all" : incraUf.toLowerCase();
      desiredVectorTiles.add(layer.id);

      const existingVectorTile = vectorTileLayersRef.current.get(layer.id);

      if (existingVectorTile) {
        existingVectorTile.setMinZoom(minimumVectorZoom(layer));
        existingVectorTile.getSource()?.setUrl(
          `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
        );
        existingVectorTile.getSource()?.refresh();
        continue;
      }

      const vectorTileSource = new VectorTileSource({
        format: new MVT({ featureClass: Feature }),
        url: `${getApiUrl()}/sources/${layer.id}/tiles/${tileUf}/{z}/{x}/{y}.pbf`,
      });

      const vectorTileLayer = new VectorTileLayer({
        source: vectorTileSource,
        zIndex: 2,
        minZoom: minimumVectorZoom(layer),
        declutter: false,
        style: (feature) => {
          feature.set("displayColor", layer.color);
          feature.set("catalogName", layer.name);

          return feature.get("isSelected")
            ? selectedOfficialStyle
            : officialStyle(layer.color);
        },
      });

      vectorTileLayersRef.current.set(layer.id, vectorTileLayer);
      map.addLayer(vectorTileLayer);
    }

    for (const [id, vectorTileLayer] of vectorTileLayersRef.current) {
      if (!desiredVectorTiles.has(id)) {
        map.removeLayer(vectorTileLayer);
        vectorTileLayersRef.current.delete(id);
      }
    }

    setOfficialStatus(
      desiredVectorTiles.size
        ? `${desiredVectorTiles.size} camada${desiredVectorTiles.size === 1 ? "" : "s"} vetorial${desiredVectorTiles.size === 1 ? "" : "is"} local${desiredVectorTiles.size === 1 ? "" : "is"} ativa${desiredVectorTiles.size === 1 ? "" : "s"}`
        : "Nenhuma camada vetorial local ativa",
    );
    setLoadingOfficial(false);

    const desired = new Set<string>();
    for (const layer of layers) {
      if (!layer.id || !layer.enabled || !layer.wmsEnabled || !layer.wmsTheme)
        continue;

      // O WMS do INCRA apresenta instabilidade/502 em diversas UFs.
      // Durante a navegação usamos o MVT local para não bloquear o mapa.
      if (layer.source === "INCRA")
        continue;

      const requiresSpecificUf =
        layer.source === "INCRA" ||
        layer.source === "SICAR" ||
        Boolean(layer.wmsAvailableUfs?.length);

      if (incraUf === "ALL" && requiresSpecificUf)
        continue;
      if (
        incraUf !== "ALL" &&
        layer.wmsAvailableUfs?.length &&
        !layer.wmsAvailableUfs.includes(incraUf.toUpperCase())
      )
        continue;
      desired.add(layer.id);
      const effectiveUf = incraUf === "ALL" ? "AP" : incraUf;
      const ufSuffix =
        layer.wmsTheme.startsWith("sicar:") && effectiveUf === "DF"
          ? "DF"
          : effectiveUf.toLowerCase();
      const layerName =
        layer.wmsFixedLayer ?? `${layer.wmsTheme}_${ufSuffix}`;
      const url =
        `${getApiUrl()}/sources/${layer.id}/wms?uf=${effectiveUf.toLowerCase()}`;
      const existing = wmsLayersRef.current.get(layer.id);
      if (existing) {
        existing.getSource()?.setUrl(url);
        existing.getSource()?.updateParams({ LAYERS: layerName });
      } else {
        const imageSource = new ImageWMS({
          url,
          params: {
            LAYERS: layerName,
            VERSION: "1.1.1",
            FORMAT: "image/png",
            TRANSPARENT: true,
          },
          ratio: 1.2,
          crossOrigin: "anonymous",
        });
        imageSource.on("imageloadstart", () =>
          setOfficialStatus(`Conectando ao WMS oficial…`),
        );
        imageSource.on("imageloadend", () =>
          setOfficialStatus(`WMS oficial conectado`),
        );
        imageSource.on("imageloaderror", () =>
          setOfficialStatus(`Falha na conexão WMS oficial`),
        );
        const wmsLayer = new ImageLayer({
          zIndex: 1,
          opacity: 0.68,
          source: imageSource,
        });
        wmsLayersRef.current.set(layer.id, wmsLayer);
        map.addLayer(wmsLayer);
      }
    }
    for (const [id, wmsLayer] of wmsLayersRef.current) {
      if (!desired.has(id)) {
        map.removeLayer(wmsLayer);
        wmsLayersRef.current.delete(id);
      }
    }
  }, [layers, incraUf]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (drawRef.current) map.removeInteraction(drawRef.current);
    drawRef.current = null;
    if (!drawKind) return;

    const draw = new Draw({ source: sourceRef.current, type: drawKind });
    draw.on("drawstart", () => sourceRef.current.clear());
    draw.on("drawend", () => window.setTimeout(emitGeometry, 0));
    map.addInteraction(draw);
    drawRef.current = draw;
    return () => map.removeInteraction(draw);
  }, [drawKind]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (modifyRef.current) {
      map.removeInteraction(modifyRef.current);
      modifyRef.current = null;
    }

    if (!modifyActive) return;

    const modify = new Modify({
      source: sourceRef.current,
    });

    modify.on("modifyend", () => {
      window.setTimeout(emitGeometry, 0);
    });

    map.addInteraction(modify);
    modifyRef.current = modify;

    return () => {
      map.removeInteraction(modify);
      modifyRef.current = null;
    };
  }, [modifyActive]);

  const clear = () => {
    sourceRef.current.clear();
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive(false);
    clearIdentifiedFeature();
    onGeometryChange(null);
  };

  const locate = () => {
    navigator.geolocation?.getCurrentPosition((position) => {
      mapRef.current?.getView().animate({
        center: fromLonLat([
          position.coords.longitude,
          position.coords.latitude,
        ]),
        zoom: 15,
        duration: 650,
      });
    });
  };

  const importFile = async (file: File) => {
    const text = await file.text();
    const extension = file.name.split(".").pop()?.toLowerCase();
    const format =
      extension === "kml" ? new KML({ extractStyles: false }) : new GeoJSON();
    const features = format.readFeatures(text, {
      dataProjection: "EPSG:4326",
      featureProjection: "EPSG:3857",
    });
    if (!features.length) return;
    sourceRef.current.clear();
    sourceRef.current.addFeatures([features[0]]);
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive(false);
    const extent = sourceRef.current.getExtent();
    mapRef.current
      ?.getView()
      .fit(extent, { padding: [90, 90, 90, 90], maxZoom: 17, duration: 500 });
    emitGeometry();
  };

  const activateDraw = (kind: Exclude<DrawKind, null>) => {
    setIdentifyActive(false);
    setModifyActive(false);
    setDrawKind((current) => (current === kind ? null : kind));
  };

  const toggleModify = () => {
    if (sourceRef.current.getFeatures().length === 0) return;

    setDrawKind(null);
    setIdentifyActive(false);
    setModifyActive((current) => !current);
  };

  const toggleIdentify = () => {
    setDrawKind(null);
    setModifyActive(false);
    setIdentifyActive((current) => !current);
  };

  return (
    <div className="real-map-wrap">
      <div
        ref={mapElement}
        className={`real-map ${identifyActive ? "identify-mode" : ""}`}
      />
      <div className="geo-tools" aria-label="Ferramentas do mapa">
        <button
          className={identifyActive ? "active" : ""}
          onClick={toggleIdentify}
          title="Identificar uma feição"
        >
          <Info size={17} />
          <span>Identificar</span>
        </button>
        <button
          className={drawKind === "Point" ? "active" : ""}
          onClick={() => activateDraw("Point")}
          title="Desenhar ponto"
        >
          <MapPin size={17} />
          <span>Ponto</span>
        </button>
        <button
          className={drawKind === "Polygon" ? "active" : ""}
          onClick={() => activateDraw("Polygon")}
          title="Desenhar polígono"
        >
          <Pentagon size={17} />
          <span>Polígono</span>
        </button>
        <button
          className={modifyActive ? "active" : ""}
          onClick={toggleModify}
          title="Editar vértices da geometria"
          disabled={sourceRef.current.getFeatures().length === 0}
        >
          <Pencil size={16} />
          <span>Editar</span>
        </button>
        <label title="Importar KML ou GeoJSON">
          <FileUp size={17} />
          <span>Importar</span>
          <input
            type="file"
            accept=".kml,.geojson,.json,application/geo+json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void importFile(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
        <button onClick={locate} title="Minha localização">
          <Crosshair size={16} />
          <span>Localizar</span>
        </button>
        <button onClick={clear} title="Limpar geometria">
          <Eraser size={16} />
          <span>Limpar</span>
        </button>
      </div>
      <div
        className={`official-layer-status ${loadingOfficial ? "loading" : ""}`}
      >
        {loadingOfficial ? "Carregando camadas visíveis…" : officialStatus}
      </div>
      {identifyActive &&
        !identifiedFeature &&
        identifyCandidates.length === 0 && (
          <div className="identify-hint">
            Clique sobre uma feição oficial para consultar seus dados
          </div>
        )}
      {identifyCandidates.length > 1 && (
        <aside
          className="identify-candidates-panel"
          aria-label="Feições encontradas no ponto"
        >
          <header>
            <div>
              <small>FEIÇÕES SOBREPOSTAS</small>
              <strong>{identifyCandidates.length} opções neste ponto</strong>
            </div>
            <button onClick={clearIdentifiedFeature} aria-label="Fechar opções">
              <X size={18} />
            </button>
          </header>
          <div>
            {identifyCandidates.map((candidate, index) => (
              <button
                key={`${candidate.layer}-${candidate.title}-${index}`}
                onClick={() => selectFeatureRef.current(candidate.feature)}
              >
                <span>{candidate.layer}</span>
                <strong>{candidate.title}</strong>
              </button>
            ))}
          </div>
        </aside>
      )}
      {identifiedFeature && (
        <aside
          className="feature-info-panel"
          aria-label="Informações da feição identificada"
        >
          <header>
            <div>
              <small>FEIÇÃO IDENTIFICADA</small>
              <strong>{identifiedFeature.title}</strong>
              <span>{identifiedFeature.layer}</span>
            </div>
            <button
              onClick={clearIdentifiedFeature}
              aria-label="Fechar informações"
            >
              <X size={18} />
            </button>
          </header>
          {identifiedFeature.loading ? (
            <div className="feature-info-loading">
              Consultando atributos completos…
            </div>
          ) : (
            <dl>
              {identifiedFeature.attributes.map(([field, value]) => (
                <div key={field}>
                  <dt>{fieldLabel(field)}</dt>
                  <dd>{fieldValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </aside>
      )}
      {drawKind && (
        <div className="draw-hint">
          {drawKind === "Point"
            ? "Clique no mapa para marcar o ponto"
            : "Clique nos vértices e dê duplo clique para concluir"}
        </div>
      )}

      {modifyActive && (
        <div className="draw-hint">
          Arraste os vértices para ajustar a geometria. Clique em Editar novamente para finalizar.
        </div>
      )}
    </div>
  );
}
