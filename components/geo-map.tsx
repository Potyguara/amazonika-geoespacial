"use client";

import { useEffect, useRef, useState } from "react";
import Feature from "ol/Feature";
import GeoJSON from "ol/format/GeoJSON";
import MVT from "ol/format/MVT";
import KML from "ol/format/KML";
import Draw from "ol/interaction/Draw";
import Modify from "ol/interaction/Modify";
import Snap from "ol/interaction/Snap";
import Map from "ol/Map";
import MapBrowserEvent from "ol/MapBrowserEvent";
import LineString from "ol/geom/LineString";
import MultiPolygon from "ol/geom/MultiPolygon";
import Point from "ol/geom/Point";
import Polygon from "ol/geom/Polygon";
import ImageLayer from "ol/layer/Image";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorTileLayer from "ol/layer/VectorTile";
import { fromLonLat, toLonLat } from "ol/proj";
import OSM from "ol/source/OSM";
import XYZ from "ol/source/XYZ";
import ImageWMS from "ol/source/ImageWMS";
import VectorSource from "ol/source/Vector";
import VectorTileSource from "ol/source/VectorTile";
import { Fill, Stroke, Style, Circle as CircleStyle, Text as TextStyle } from "ol/style";
import View from "ol/View";
import { getArea, getLength } from "ol/sphere";
import { getApiUrl } from "@/lib/api";
import { parseManualCoordinates, type ManualCoordinateMode } from "@/lib/geospatial-tools";
import {
  ArrowLeft,
  Crosshair,
  Eraser,
  FileUp,
  Info,
  MapPin,
  Magnet,
  Pencil,
  Pentagon,
  Ruler,
  Satellite,
  Sparkles,
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
  const baseLayerRef = useRef<TileLayer<OSM | XYZ> | null>(null);
  const snapSubjectRef = useRef<Snap | null>(null);
  const snapLayersRef = useRef<Snap | null>(null);
  const officialSourceRef = useRef(new VectorSource());
  const vertexLabelSourceRef = useRef(new VectorSource());

  // Overlay exclusivo da ferramenta Identificar.
  // Toda feição selecionada, independentemente da base de origem,
  // será materializada aqui para garantir destaque visual uniforme.
  const identifySelectionSourceRef = useRef(
    new VectorSource(),
  );
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
  const identifyCandidateHistoryRef = useRef<IdentifyCandidate[]>([]);
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
  const [snapSubjectEnabled, setSnapSubjectEnabled] = useState(true);
  const [snapLayersEnabled, setSnapLayersEnabled] = useState(false);
  const [advancedPanel, setAdvancedPanel] = useState<"coordinates" | "snap" | "basemap" | "memorial" | null>(null);
  const [manualMode, setManualMode] = useState<ManualCoordinateMode>("DD");
  const [manualText, setManualText] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [basemap, setBasemap] = useState("osm");
  const [importingVector, setImportingVector] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [geometryMetrics, setGeometryMetrics] = useState<{
    areaHectares: number | null;
    perimeterMeters: number | null;
    vertices: number;
  }>({ areaHectares: null, perimeterMeters: null, vertices: 0 });
  const [memorialLoading, setMemorialLoading] = useState(false);
  const [memorialText, setMemorialText] = useState("");
  const [memorialTitle, setMemorialTitle] = useState("Área analisada");
  const [memorialOwner, setMemorialOwner] = useState("");
  const [memorialResponsible, setMemorialResponsible] = useState("");
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

  const refreshVertexLabels = () => {
    vertexLabelSourceRef.current.clear();
    const geometry = sourceRef.current.getFeatures()[0]?.getGeometry();
    if (!geometry) return;

    let index = 0;
    const addRing = (ring: number[][]) => {
      for (const coordinate of ring.slice(0, -1)) {
        const feature = new Feature({
          geometry: new Point(coordinate),
          vertexName: `V${String(index + 1).padStart(2, "0")}`,
        });
        vertexLabelSourceRef.current.addFeature(feature);
        index += 1;
      }
    };

    if (geometry instanceof Polygon) {
      addRing(geometry.getCoordinates()[0] ?? []);
    } else if (geometry instanceof MultiPolygon) {
      for (const polygon of geometry.getCoordinates()) {
        addRing(polygon[0] ?? []);
      }
    }
  };

  const updateGeometryMetrics = () => {
    const geometry = sourceRef.current.getFeatures()[0]?.getGeometry();
    if (!geometry) {
      setGeometryMetrics({ areaHectares: null, perimeterMeters: null, vertices: 0 });
      return;
    }

    if (geometry instanceof Polygon) {
      const ring = geometry.getCoordinates()[0] ?? [];
      setGeometryMetrics({
        areaHectares: getArea(geometry, { projection: "EPSG:3857" }) / 10000,
        perimeterMeters: ring.length > 1
          ? getLength(new LineString(ring), { projection: "EPSG:3857" })
          : 0,
        vertices: Math.max(0, ring.length - 1),
      });
      return;
    }

    if (geometry instanceof MultiPolygon) {
      let area = 0;
      let perimeter = 0;
      let vertices = 0;
      for (const polygonCoordinates of geometry.getCoordinates()) {
        const polygon = new Polygon(polygonCoordinates);
        const ring = polygonCoordinates[0] ?? [];
        area += getArea(polygon, { projection: "EPSG:3857" });
        if (ring.length > 1) {
          perimeter += getLength(new LineString(ring), { projection: "EPSG:3857" });
        }
        vertices += Math.max(0, ring.length - 1);
      }
      setGeometryMetrics({
        areaHectares: area / 10000,
        perimeterMeters: perimeter,
        vertices,
      });
      return;
    }

    setGeometryMetrics({
      areaHectares: null,
      perimeterMeters: null,
      vertices: geometry instanceof Point ? 1 : 0,
    });
  };

  const currentGeometryGeoJson = () => {
    const geometry = sourceRef.current.getFeatures()[0]?.getGeometry();
    if (!geometry) return null;
    return new GeoJSON().writeGeometryObject(geometry, {
      featureProjection: "EPSG:3857",
      dataProjection: "EPSG:4326",
      decimals: 9,
    }) as Record<string, unknown>;
  };

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
    updateGeometryMetrics();
    refreshVertexLabels();
  };

  const clearIdentifiedFeature = () => {
    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;
    if (selectedFeatureRef.current) {
      selectedFeatureRef.current.set("isSelected", false);
      selectedFeatureRef.current.changed();
      selectedFeatureRef.current = null;
    }
    identifySelectionSourceRef.current.clear();

    setIdentifiedFeature(null);
    setIdentifyCandidates([]);
    identifyCandidateHistoryRef.current = [];
  };

  selectFeatureRef.current = (feature: Feature) => {
    const preservedCandidates = [
      ...identifyCandidateHistoryRef.current,
    ];

    clearIdentifiedFeature();

    identifyCandidateHistoryRef.current =
      preservedCandidates;

    selectedFeatureRef.current = feature;

    feature.set("isSelected", true);
    feature.changed();

    /*
     * DESTAQUE UNIVERSAL
     *
     * Não dependemos do estilo da camada original.
     * Criamos uma cópia gráfica da geometria selecionada
     * e a colocamos no overlay superior do mapa.
     *
     * Isso funciona para qualquer GeoFeature armazenada
     * no PostGIS, independentemente da fonte.
     */
    const selectedGeometry = feature.getGeometry();

    if (selectedGeometry) {
      const highlightFeature = new Feature({
        geometry: selectedGeometry.clone(),
      });

      highlightFeature.set(
        "isIdentifyHighlight",
        true,
      );

      highlightFeature.set(
        "source_id",
        feature.get("source_id"),
      );

      highlightFeature.set(
        "feature_id",
        feature.get("feature_id"),
      );

      identifySelectionSourceRef.current.clear();
      identifySelectionSourceRef.current.addFeature(
        highlightFeature,
      );
    }
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
    const baseLayer = new TileLayer({ source: new OSM(), zIndex: 0 });
    baseLayerRef.current = baseLayer;
    const map = new Map({
      target: mapElement.current,
      layers: [
        baseLayer,
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
        new VectorLayer({
          source: vertexLabelSourceRef.current,
          zIndex: 4,
          style: (feature) =>
            new Style({
              image: new CircleStyle({
                radius: 4.5,
                fill: new Fill({ color: "#ffffff" }),
                stroke: new Stroke({ color: "#0d6847", width: 2 }),
              }),
              text: new TextStyle({
                text: String(feature.get("vertexName") ?? ""),
                offsetY: -13,
                font: "700 11px Inter, sans-serif",
                fill: new Fill({ color: "#0d3f2d" }),
                stroke: new Stroke({ color: "#ffffff", width: 3 }),
              }),
            }),
        }),

        // Camada universal de seleção.
        // Fica acima das bases territoriais e da geometria consultada.
        new VectorLayer({
          source: identifySelectionSourceRef.current,
          zIndex: 1000,
          style: selectedOfficialStyle,
        }),
      ],
      view: new View({
        center: fromLonLat((UF_VIEW[incraUf] ?? UF_VIEW.ALL).center),
        zoom: (UF_VIEW[incraUf] ?? UF_VIEW.ALL).zoom,
      }),
    });
    mapRef.current = map;
    const identifyAtPixel = async (
      event: MapBrowserEvent<PointerEvent>,
    ) => {
      if (!identifyActiveRef.current) return;

      clearIdentifiedFeature();

      const enabledLayers = layersRef.current.filter(
        (layer) => layer.enabled && layer.id,
      );

      const enabledSourceIds = enabledLayers
        .map((layer) => layer.id)
        .filter((id): id is string => Boolean(id));

      const [longitude, latitude] = toLonLat(
        event.coordinate,
        map.getView().getProjection(),
      );

      /*
       * A identificação principal ocorre diretamente no PostGIS.
       *
       * Isso elimina a dependência da feição estar carregada no tile
       * visível e permite identificar igualmente:
       * - CAR/SICAR vetorial local;
       * - SPU vetorial local;
       * - SIGEF;
       * - SNCI;
       * - ANM;
       * - assentamentos;
       * - UC;
       * - bases estaduais/municipais;
       * - qualquer vetor adicional cadastrado por UF.
       */
      if (enabledSourceIds.length > 0) {
        identifyAbortRef.current?.abort();

        const controller = new AbortController();
        identifyAbortRef.current = controller;

        try {
          const response = await fetch(
            `${getApiUrl()}/sources/identify`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              signal: controller.signal,
              body: JSON.stringify({
                coordinate: [longitude, latitude],
                source_ids: enabledSourceIds,
                tolerance_m: Math.max(
                  2,
                  Math.min(
                    25,
                    Number(
                      map.getView().getResolution() ?? 1,
                    ) * 1.5,
                  ),
                ),
              }),
            },
          );

          const body = await response
            .json()
            .catch(() => null);

          if (!response.ok) {
            throw new Error(
              body?.detail ??
                "Não foi possível identificar as feições.",
            );
          }

          if (controller.signal.aborted) return;

          const returnedFeatures = Array.isArray(
            body?.features,
          )
            ? body.features
            : [];

          if (returnedFeatures.length > 0) {
            const format = new GeoJSON();

            const candidates: IdentifyCandidate[] = [];

            for (const item of returnedFeatures) {
              try {
                const feature = format.readFeature(
                  item,
                  {
                    dataProjection: "EPSG:4674",
                    featureProjection: "EPSG:3857",
                  },
                );

                const properties =
                  item?.properties ?? {};

                const sourceId = String(
                  item?.source_id ??
                    properties.source_id ??
                    "",
                );

                const layer = enabledLayers.find(
                  (candidate) =>
                    candidate.id === sourceId,
                );

                feature.set(
                  "source_id",
                  sourceId,
                );

                feature.set(
                  "source_name",
                  String(
                    item?.source_name ??
                      properties.source_name ??
                      layer?.name ??
                      "Camada territorial",
                  ),
                );

                feature.set(
                  "catalogName",
                  layer?.name ??
                    String(
                      item?.source_name ??
                        properties.source_name ??
                        "Camada territorial",
                    ),
                );

                feature.set(
                  "displayColor",
                  layer?.color ?? "#e08a24",
                );

                feature.set(
                  "identifyOverlay",
                  true,
                );

                feature.set(
                  "feature_id",
                  String(
                    properties.feature_id ??
                      item?.id ??
                      "",
                  ),
                );

                if (item?.id) {
                  feature.setId(String(item.id));
                }

                const identity =
                  featureIdentity(feature);

                candidates.push({
                  feature,
                  title: identity.title,
                  layer: identity.layer,
                });
              } catch (error) {
                console.warn(
                  "Não foi possível materializar uma feição identificada.",
                  error,
                );
              }
            }

            if (candidates.length === 1) {
              selectFeatureRef.current(
                candidates[0].feature,
              );
              return;
            }

            if (candidates.length > 1) {
              identifyCandidateHistoryRef.current =
                candidates;
              setIdentifyCandidates(candidates);
              return;
            }
          }
        } catch (error) {
          if (
            error instanceof DOMException &&
            error.name === "AbortError"
          ) {
            return;
          }

          console.warn(
            "Identificação vetorial local indisponível; tentando fallback visual/WMS.",
            error,
          );
        }
      }

      /*
       * Fallback 1:
       * feature já renderizada no MVT/OpenLayers.
       */
      const renderedCandidates = map
        .getFeaturesAtPixel(
          event.pixel,
          { hitTolerance: 7 },
        )
        .filter(
          (candidate): candidate is Feature =>
            candidate instanceof Feature &&
            Boolean(candidate.get("catalogName")),
        );

      if (renderedCandidates.length === 1) {
        selectFeatureRef.current(
          renderedCandidates[0],
        );
        return;
      }

      if (renderedCandidates.length > 1) {
        const candidates =
          renderedCandidates.map((feature) => ({
            feature,
            ...featureIdentity(feature),
          }));

        identifyCandidateHistoryRef.current =
          candidates;

        setIdentifyCandidates(candidates);
        return;
      }

      // WMS é somente referência visual. A ferramenta Identificar
      // trabalha exclusivamente com geometrias vetoriais presentes no PostGIS.
      setIdentifiedFeature(null);
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

      // O vetor local/PostGIS é sempre a camada operacional do sistema.
      // O WMS, quando habilitado, é apenas uma referência visual adicional.

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


  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (snapSubjectRef.current) {
      map.removeInteraction(snapSubjectRef.current);
      snapSubjectRef.current = null;
    }
    if (snapLayersRef.current) {
      map.removeInteraction(snapLayersRef.current);
      snapLayersRef.current = null;
    }

    const subjectSnap = snapSubjectEnabled
      ? new Snap({
          source: sourceRef.current,
          vertex: true,
          edge: true,
          pixelTolerance: 14,
        })
      : null;

    const layerSnap = snapLayersEnabled
      ? new Snap({
          source: officialSourceRef.current,
          vertex: true,
          edge: true,
          pixelTolerance: 14,
        })
      : null;

    // Snap é adicionado por último para processar o pointer event
    // antes de Draw/Modify, conforme a ordem de interações do OpenLayers.
    if (subjectSnap) {
      map.addInteraction(subjectSnap);
      snapSubjectRef.current = subjectSnap;
    }
    if (layerSnap) {
      map.addInteraction(layerSnap);
      snapLayersRef.current = layerSnap;
    }

    return () => {
      if (subjectSnap) map.removeInteraction(subjectSnap);
      if (layerSnap) map.removeInteraction(layerSnap);
      if (snapSubjectRef.current === subjectSnap) snapSubjectRef.current = null;
      if (snapLayersRef.current === layerSnap) snapLayersRef.current = null;
    };
  }, [snapSubjectEnabled, snapLayersEnabled, drawKind, modifyActive]);

  const returnToIdentifyCandidates = () => {
    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;

    if (selectedFeatureRef.current) {
      selectedFeatureRef.current.set(
        "isSelected",
        false,
      );
      selectedFeatureRef.current.changed();
      selectedFeatureRef.current = null;
    }

    identifySelectionSourceRef.current.clear();
    setIdentifiedFeature(null);

    setIdentifyCandidates([
      ...identifyCandidateHistoryRef.current,
    ]);
  };

  const clear = () => {
    sourceRef.current.clear();
    vertexLabelSourceRef.current.clear();
    setGeometryMetrics({ areaHectares: null, perimeterMeters: null, vertices: 0 });
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
    setImportError(null);
    setImportingVector(true);
    try {
      const extension = file.name.split(".").pop()?.toLowerCase();
      let features: Feature[] = [];

      if (extension === "kml") {
        const text = await file.text();
        features = new KML({ extractStyles: false }).readFeatures(text, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        });
      } else if (extension === "geojson" || extension === "json") {
        const text = await file.text();
        features = new GeoJSON().readFeatures(text, {
          dataProjection: "EPSG:4326",
          featureProjection: "EPSG:3857",
        });
      } else {
        const body = new FormData();
        body.append("file", file);
        const response = await fetch(`${getApiUrl()}/tools/convert-vector`, {
          method: "POST",
          credentials: "include",
          body,
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(
            typeof payload?.detail === "string"
              ? payload.detail
              : "Não foi possível converter o arquivo vetorial.",
          );
        }
        features = new GeoJSON().readFeatures(payload, {
          dataProjection: "EPSG:4674",
          featureProjection: "EPSG:3857",
        });
      }

      if (!features.length) throw new Error("O arquivo não contém feições utilizáveis.");

      sourceRef.current.clear();
      sourceRef.current.addFeatures(features);
      setDrawKind(null);
      setModifyActive(false);
      setIdentifyActive(false);
      const extent = sourceRef.current.getExtent();
      mapRef.current?.getView().fit(extent, {
        padding: [90, 90, 90, 90],
        maxZoom: 17,
        duration: 500,
      });
      emitGeometry();
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Falha ao importar arquivo.");
    } finally {
      setImportingVector(false);
    }
  };

  const applyManualCoordinates = () => {
    setManualError(null);
    try {
      const coordinates = parseManualCoordinates(manualText, manualMode);
      if (coordinates.length === 2) {
        throw new Error("Para polígono informe ao menos 3 vértices; para ponto informe apenas 1.");
      }
      const geometry =
        coordinates.length === 1
          ? new Point(fromLonLat(coordinates[0]))
          : new Polygon([
              [
                ...coordinates.map((coordinate) => fromLonLat(coordinate)),
                fromLonLat(coordinates[0]),
              ],
            ]);

      sourceRef.current.clear();
      sourceRef.current.addFeature(new Feature({ geometry }));
      setDrawKind(null);
      setModifyActive(false);
      setIdentifyActive(false);
      mapRef.current?.getView().fit(geometry.getExtent(), {
        padding: [90, 90, 90, 90],
        maxZoom: 17,
        duration: 450,
      });
      emitGeometry();
      setAdvancedPanel(null);
    } catch (error) {
      setManualError(error instanceof Error ? error.message : "Coordenadas inválidas.");
    }
  };

  const changeBasemap = (value: string) => {
    const layer = baseLayerRef.current;
    if (!layer) return;
    if (value === "esri-imagery") {
      layer.setSource(
        new XYZ({
          url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
          crossOrigin: "anonymous",
          attributions: "Tiles © Esri",
        }),
      );
    } else if (value === "esri-topo") {
      layer.setSource(
        new XYZ({
          url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
          crossOrigin: "anonymous",
          attributions: "Tiles © Esri",
        }),
      );
    } else {
      layer.setSource(new OSM());
    }
    setBasemap(value);
  };

  const generateMemorial = async () => {
    const geometry = currentGeometryGeoJson();
    if (!geometry) return;
    setMemorialLoading(true);
    setMemorialText("");
    try {
      const response = await fetch(`${getApiUrl()}/tools/memorial-draft`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          geometry,
          title: memorialTitle,
          owner_name: memorialOwner || null,
          responsible_name: memorialResponsible || null,
          vertex_prefix: "V",
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail ?? "Não foi possível gerar o memorial.");
      }
      setMemorialText(payload.memorial_text ?? "");
    } catch (error) {
      setMemorialText(
        `ERRO: ${error instanceof Error ? error.message : "Falha ao gerar memorial."}`,
      );
    } finally {
      setMemorialLoading(false);
    }
  };

  const downloadPlantMemorialPdf = async () => {
    const geometry = currentGeometryGeoJson();
    if (!geometry) return;
    setMemorialLoading(true);
    try {
      const response = await fetch(`${getApiUrl()}/tools/plant-memorial/pdf`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          geometry,
          title: memorialTitle,
          owner_name: memorialOwner || null,
          responsible_name: memorialResponsible || null,
          vertex_prefix: "V",
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "Não foi possível gerar o PDF.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${memorialTitle.trim().replace(/[^a-zA-Z0-9_-]+/g, "-") || "planta-memorial"}-planta-memorial.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMemorialText(
        `ERRO: ${error instanceof Error ? error.message : "Falha ao gerar PDF."}`,
      );
    } finally {
      setMemorialLoading(false);
    }
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
        <label title="Importar KML, GeoJSON, Shapefile ZIP ou GeoPackage">
          <FileUp size={17} />
          <span>Importar</span>
          <input
            type="file"
            accept=".kml,.geojson,.json,.zip,.gpkg,application/geo+json,application/zip"
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
      <div className="geo-advanced-tools" aria-label="Ferramentas avançadas">
        <button
          className={advancedPanel === "coordinates" ? "active" : ""}
          onClick={() => setAdvancedPanel((current) => current === "coordinates" ? null : "coordinates")}
          title="Inserir coordenadas manualmente"
        >
          <MapPin size={18} />
        </button>
        <button
          className={snapSubjectEnabled || snapLayersEnabled ? "active" : ""}
          onClick={() => setAdvancedPanel((current) => current === "snap" ? null : "snap")}
          title="Configurar Snap"
        >
          <Magnet size={18} />
        </button>
        <button
          className={advancedPanel === "basemap" ? "active" : ""}
          onClick={() => setAdvancedPanel((current) => current === "basemap" ? null : "basemap")}
          title="Mapa base / satélite"
        >
          <Satellite size={18} />
        </button>
        <button
          className={advancedPanel === "memorial" ? "active" : ""}
          disabled={!sourceRef.current.getFeatures().length}
          onClick={() => setAdvancedPanel((current) => current === "memorial" ? null : "memorial")}
          title="Gerar memorial descritivo"
        >
          <Sparkles size={18} />
        </button>
      </div>

      {advancedPanel === "coordinates" && (
        <aside className="geo-advanced-panel coordinates-panel">
          <header><strong>Inserir coordenadas</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <div className="coordinate-mode-tabs">
            {(["DD", "DMS", "UTM"] as ManualCoordinateMode[]).map((mode) => (
              <button key={mode} className={manualMode === mode ? "active" : ""} onClick={() => setManualMode(mode)}>{mode}</button>
            ))}
          </div>
          <small>
            {manualMode === "DD"
              ? "Uma linha por vértice: longitude, latitude"
              : manualMode === "DMS"
                ? 'Uma linha por vértice: 51 30 00 W ; 0 02 00 N'
                : "Uma linha por vértice: Este, Norte, Fuso, Hemisfério (ex.: 532685, 137648, 22, N)"}
          </small>
          <textarea value={manualText} onChange={(event) => setManualText(event.target.value)} rows={7} placeholder="Cole as coordenadas aqui" />
          {manualError && <p className="geo-tool-error">{manualError}</p>}
          <button className="geo-tool-primary" onClick={applyManualCoordinates}>Aplicar no mapa</button>
        </aside>
      )}

      {advancedPanel === "snap" && (
        <aside className="geo-advanced-panel snap-panel">
          <header><strong>Snap / atração magnética</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <label><input type="checkbox" checked={snapSubjectEnabled} onChange={(event) => setSnapSubjectEnabled(event.target.checked)} /><span>Vértices e arestas da geometria em edição</span></label>
          <label><input type="checkbox" checked={snapLayersEnabled} onChange={(event) => setSnapLayersEnabled(event.target.checked)} /><span>Camadas vetoriais carregadas no mapa</span></label>
          <small>O Snap pode ser ativado ou desligado a qualquer momento durante desenho e edição.</small>
        </aside>
      )}

      {advancedPanel === "basemap" && (
        <aside className="geo-advanced-panel basemap-panel">
          <header><strong>Mapa base</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <button className={basemap === "osm" ? "active" : ""} onClick={() => changeBasemap("osm")}>OpenStreetMap</button>
          <button className={basemap === "esri-imagery" ? "active" : ""} onClick={() => changeBasemap("esri-imagery")}>Esri World Imagery</button>
          <button className={basemap === "esri-topo" ? "active" : ""} onClick={() => changeBasemap("esri-topo")}>Esri World Topographic</button>
          <small>Google Map Tiles, Azure Maps (substituto do Bing) e outros provedores serão habilitados somente por conexão oficial/configurada, sem URLs não autorizadas.</small>
        </aside>
      )}

      {advancedPanel === "memorial" && (
        <aside className="geo-advanced-panel memorial-panel">
          <header><strong>Planta e memorial</strong><button onClick={() => setAdvancedPanel(null)}><X size={17} /></button></header>
          <label><span>Nome da área</span><input value={memorialTitle} onChange={(event) => setMemorialTitle(event.target.value)} /></label>
          <label><span>Detentor / interessado</span><input value={memorialOwner} onChange={(event) => setMemorialOwner(event.target.value)} /></label>
          <label><span>Responsável técnico</span><input value={memorialResponsible} onChange={(event) => setMemorialResponsible(event.target.value)} /></label>
          <div className="memorial-actions">
            <button className="geo-tool-primary" disabled={memorialLoading} onClick={() => void generateMemorial()}>
              {memorialLoading ? "Gerando…" : "Gerar texto do memorial"}
            </button>
            <button className="geo-tool-secondary" disabled={memorialLoading} onClick={() => void downloadPlantMemorialPdf()}>
              Gerar Planta + Memorial PDF
            </button>
          </div>
          {memorialText && <textarea className="memorial-output" readOnly value={memorialText} rows={12} />}
          <small>O PDF usa o modelo institucional salvo em Configurações, com logomarca, responsável, vértices, escala, área e perímetro.</small>
        </aside>
      )}

      {sourceRef.current.getFeatures().length > 0 && (
        <div className="geometry-metrics-card">
          <Ruler size={16} />
          <span>
            {geometryMetrics.areaHectares == null ? "Geometria pontual" : `${geometryMetrics.areaHectares.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ha`}
          </span>
          {geometryMetrics.perimeterMeters != null && (
            <span>{geometryMetrics.perimeterMeters.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} m</span>
          )}
          <span>{geometryMetrics.vertices} vértice{geometryMetrics.vertices === 1 ? "" : "s"}</span>
        </div>
      )}

      {importingVector && <div className="map-operation-feedback">Importando e convertendo arquivo vetorial…</div>}
      {importError && <div className="map-operation-feedback error">{importError}</div>}

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

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {identifyCandidateHistoryRef.current.length > 1 && (
                <button
                  onClick={returnToIdentifyCandidates}
                  aria-label="Voltar às feições encontradas"
                  title="Voltar às feições encontradas"
                >
                  <ArrowLeft size={18} />
                </button>
              )}

              <button
                onClick={clearIdentifiedFeature}
                aria-label="Fechar informações"
              >
                <X size={18} />
              </button>
            </div>
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
