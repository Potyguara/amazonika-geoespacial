"""Read-only SIGEF WFS diagnostic: formats and OGC exceptions (no parcel data logged).

Run on VPS: python3 scripts/diagnose_sigef_wfs_response.py
Checks representative, small AP window with one feature only.
"""
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from xml.etree import ElementTree as ET
import json

URL = "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows"
BASE = {
    "SERVICE": "WFS", "VERSION": "1.0.0", "REQUEST": "GetFeature",
    "TYPENAME": "sigef_geo", "SRSNAME": "EPSG:4326",
    "BBOX": "-51.2,-0.2,-51.0,0.0", "MAXFEATURES": "1",
}
VARIANTS = [
    ("application/json + UF", {"OUTPUTFORMAT": "application/json", "CQL_FILTER": "uf_id=16"}),
    ("json + UF", {"OUTPUTFORMAT": "json", "CQL_FILTER": "uf_id=16"}),
    ("application/json without UF", {"OUTPUTFORMAT": "application/json"}),
    ("default GML + UF", {"CQL_FILTER": "uf_id=16"}),
]


def main():
    for name, variant in VARIANTS:
        params = {**BASE, **variant}
        req = Request(URL + "?" + urlencode(params), headers={"User-Agent": "Amazonika-Geoespacial/1.0", "Accept": "*/*"})
        print("\nTEST:", name)
        try:
            with urlopen(req, timeout=35) as response:
                data = response.read(60_001)
                print("HTTP:", response.status, "TYPE:", response.headers.get("Content-Type"), "SAMPLE_BYTES:", len(data))
        except HTTPError as exc:
            data = exc.read(60_001)
            print("HTTP ERROR:", exc.code, "TYPE:", exc.headers.get("Content-Type"))
        except Exception as exc:
            print("REQUEST ERROR:", str(exc)[:180])
            continue
        if data.lstrip().startswith((b"{", b"[")):
            try:
                decoded = json.loads(data)
                print("JSON_TYPE:", decoded.get("type"), "FEATURES:", len(decoded.get("features", [])))
                if "features" in decoded:
                    print("UF_IDS:", list({str(f.get("properties", {}).get("uf_id")) for f in decoded["features"]}))
            except json.JSONDecodeError:
                print("JSON response truncated by 60 KB limit")
        elif data.lstrip().startswith(b"<"):
            try:
                root = ET.fromstring(data)
                print("XML_ROOT:", root.tag.split("}")[-1])
                exception = [element.text for element in root.iter() if element.tag.split("}")[-1] in ("ServiceException", "ExceptionText") and element.text]
                for item in exception[:2]:
                    print("OGC_EXCEPTION:", item[:450])
            except ET.ParseError:
                print("XML possibly truncated; prefix:", data[:220].decode(errors="replace"))
        else:
            print("UNEXPECTED_PREFIX:", data[:180].decode(errors="replace"))


if __name__ == "__main__":
    main()
