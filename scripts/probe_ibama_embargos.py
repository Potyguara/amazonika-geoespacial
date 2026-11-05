"""Read-only smoke test of the public IBAMA embargo ArcGIS REST layer.

Verifies layer metadata, field names, bounded spatial count and GeoJSON
support. Does not query by personal identifiers or transfer national files.
Run on the homologation VPS: python3 scripts/probe_ibama_embargos.py
"""
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = (
    "https://pamgia.ibama.gov.br/server/rest/services/"
    "01_Publicacoes_Bases/adm_embargos_ibama_a/MapServer/0"
)
FIELDS = {"objectid", "num_tad", "num_processo", "qtd_area_embargada", "dat_embargo"}


def get_json(path, params, limit=250_000):
    url = BASE + path + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "Amazonika-Geoespacial/1.0"})
    with urlopen(request, timeout=30) as result:
        raw = result.read(limit + 1)
        if len(raw) > limit:
            raise RuntimeError(f"Resposta excedeu {limit} bytes")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("error"):
            raise RuntimeError("ArcGIS retornou exceção: " + str(data.get("error"))[:240])
        return data


def main():
    metadata = get_json("", {"f": "json"})
    fields = {item.get("name") for item in metadata.get("fields", [])}
    print("Camada:", metadata.get("name"))
    print("Referencial:", metadata.get("spatialReference"))
    print("Campos essenciais:", sorted(FIELDS & fields))
    missing = FIELDS - fields
    if missing:
        raise RuntimeError("Campos faltando: " + ", ".join(sorted(missing)))
    if metadata.get("geometryType") != "esriGeometryPolygon":
        raise RuntimeError("Serviço não apresenta a camada poligonal esperada")
    # A test envelope around Macapá; not the user's device or exact location.
    bounds = "-51.15,0.00,-51.14,0.01"
    common = {
        "where": "1=1", "geometry": bounds,
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4674, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
    }
    count = get_json("/query", {**common, "f": "json", "returnCountOnly": "true"})
    print("Polígonos no envelope de teste:", count.get("count"))
    if not isinstance(count.get("count"), int):
        raise RuntimeError("Consulta de contagem inconclusiva")
    sample = get_json("/query", {
        **common, "f": "geojson", "returnGeometry": "true",
        "outFields": "objectid,num_tad,num_processo,qtd_area_embargada",
        "resultRecordCount": 3,
    }, limit=1_000_000)
    print("GeoJSON:", sample.get("type"), "amostras:", len(sample.get("features") or []))
    if sample.get("type") != "FeatureCollection":
        raise RuntimeError("GeoJSON indisponível")
    print("PROBE_OK: integração pública do IBAMA habilitada para homologação")


if __name__ == "__main__":
    main()
