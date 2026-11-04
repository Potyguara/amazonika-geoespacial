"""Verify GeoNode SIGEF uf_id against IBGE state codes before enabling CQL.

Run on VPS: python3 scripts/verify_sigef_uf_ids.py
Read-only WFS GetFeature; prints a small sample without personal details.
"""
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows"
# Small geographic windows intentionally inside states; no geometries persisted.
WINDOWS = {
    "AP": {"bbox": "-51.2,-0.2,-51.0,0.0", "expected": 16},
    "PA": {"bbox": "-48.6,-1.6,-48.4,-1.3", "expected": 15},
    "SP": {"bbox": "-46.8,-23.7,-46.5,-23.4", "expected": 35},
}


def main():
    verified = 0
    checked = 0
    for uf, item in WINDOWS.items():
        params = {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typeName": "sigef_geo",
            "outputFormat": "application/json",
            "maxFeatures": 2,
            "bbox": item["bbox"],
        }
        url = URL + "?" + urlencode(params)
        try:
            req = Request(url, headers={"User-Agent": "Amazonika-Geoespacial/1.0", "Accept": "application/json"})
            with urlopen(req, timeout=45) as response:
                body = response.read(400_001)
                content_type = response.headers.get("Content-Type", "")
            if len(body) > 400_000 or "json" not in content_type.lower():
                raise ValueError("WFS não retornou JSON GeoJSON com tamanho aceitável")
            features = json.loads(body).get("features") or []
            values = sorted(set(str(f.get("properties", {}).get("uf_id")) for f in features))
            if not features:
                print(uf, "SEM_FEICOES_NESTA_JANELA — validação inconclusiva")
                continue
            checked += 1
            ok = values == [str(item["expected"])]
            verified += int(ok)
            print(uf, "uf_id=", values, "IBGE_esperado=", item["expected"], "OK" if ok else "DIVERGENTE")
        except Exception as exc:
            print(uf, "ERRO:", str(exc)[:180])
    print("RESULTADO:", verified, "de", checked, "janelas com feições corresponderam aos códigos IBGE.")
    if checked < 2 or verified != checked:
        print("NÃO PUBLICAR FILTRO CQL EM PRODUÇÃO ANTES DE INVESTIGAR OS IDs.")


if __name__ == "__main__":
    main()
