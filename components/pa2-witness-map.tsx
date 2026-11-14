"use client";

import { useEffect, useRef } from "react";
import Map from "ol/Map";
import View from "ol/View";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import OSM from "ol/source/OSM";
import { fromLonLat } from "ol/proj";
import { Circle as CircleStyle, Fill, Stroke, Style, Text as TextStyle } from "ol/style";

export type Pa2MapWitness = {
  name: string;
  latitude: number | null;
  longitude: number | null;
};
type Props = {
  points: Pa2MapWitness[];
  selected: string[];
  intersection?: { latitude: number | null; longitude: number | null } | null;
  onPick: (name: string) => void;
};

/** Mapa de apoio PA2: clique nos dois testemunhos de cada alinhamento. */
export function Pa2WitnessMap({ points, selected, intersection, onPick }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const sourceRef = useRef(new VectorSource());
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const stateKey = JSON.stringify([points, selected, intersection]);

  useEffect(() => {
    if (!container.current) return;
    const source = sourceRef.current;
    const map = new Map({
      target: container.current,
      layers: [
        new TileLayer({ source: new OSM() }),
        new VectorLayer({
          source,
          style: (feature) => {
            const isLine = feature.getGeometry() instanceof LineString;
            const isV = Boolean(feature.get("virtual"));
            const chosen = Boolean(feature.get("chosen"));
            return new Style({
              stroke: new Stroke({ color: isLine ? "#f97316" : "#0e7490", width: 3 }),
              image: new CircleStyle({
                radius: isV ? 9 : chosen ? 8 : 6,
                fill: new Fill({ color: isV ? "#f97316" : chosen ? "#0e7490" : "#ffffff" }),
                stroke: new Stroke({ color: "#064e3b", width: 2 }),
              }),
              text: new TextStyle({
                text: String(feature.get("label") || ""),
                offsetY: -18, font: "bold 12px sans-serif",
                fill: new Fill({ color: "#064e3b" }),
                stroke: new Stroke({ color: "#ffffff", width: 4 }),
              }),
            });
          },
        }),
      ],
      view: new View({ center: fromLonLat([-51, 0]), zoom: 8, maxZoom: 20 }),
      controls: [],
    });
    mapRef.current = map;
    const handler = (event: { pixel: number[] }) => {
      const feature = map.forEachFeatureAtPixel(event.pixel, (candidate) => candidate, {
        hitTolerance: 12,
      });
      if (feature && typeof feature.get("pointName") === "string") {
        pickRef.current(feature.get("pointName") as string);
      }
    };
    map.on("singleclick", handler);
    return () => {
      map.un("singleclick", handler);
      map.setTarget(undefined);
      mapRef.current = null;
      source.clear();
    };
  }, []);

  useEffect(() => {
    const source = sourceRef.current;
    source.clear();
    const positions = new globalThis.Map<string, number[]>();
    for (const point of points) {
      if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) continue;
      const coordinate = fromLonLat([point.longitude as number, point.latitude as number]);
      positions.set(point.name, coordinate);
      const feature = new Feature({ geometry: new Point(coordinate) });
      feature.set("label", point.name);
      feature.set("pointName", point.name);
      feature.set("chosen", selected.includes(point.name));
      source.addFeature(feature);
    }
    for (let i = 0; i + 1 < selected.length && i < 4; i += 2) {
      const a = positions.get(selected[i]);
      const b = positions.get(selected[i + 1]);
      if (a && b) source.addFeature(new Feature({
        geometry: new LineString([a, b]),
        label: i === 0 ? "Reta A" : "Reta B",
      }));
    }
    if (intersection && Number.isFinite(intersection.longitude)
        && Number.isFinite(intersection.latitude)) {
      const point = new Feature({
        geometry: new Point(fromLonLat([
          intersection.longitude as number, intersection.latitude as number,
        ])),
      });
      point.set("label", "V (pré-cálculo)");
      point.set("virtual", true);
      source.addFeature(point);
    }
    const map = mapRef.current;
    if (map && positions.size) {
      map.updateSize();
      const extent = source.getExtent();
      if (extent.every(Number.isFinite)) map.getView().fit(extent, {
        padding: [55, 50, 55, 50], maxZoom: 17, duration: 200,
      });
    }
  }, [stateKey]);

  return <div>
    <div ref={container} style={{ height: 340, width: "100%", borderRadius: 9,
      border: "1px solid #9ca3af", overflow: "hidden" }} aria-label="Mapa de apoio à interseção de retas PA2" />
    <p style={{ fontSize: 12, marginTop: 8 }}>
      Clique em quatro marcos: dois definem a reta A, e outros dois a reta B.
      A posição V é a interseção calculada, não um clique arbitrário no mapa.
    </p>
  </div>;
}
