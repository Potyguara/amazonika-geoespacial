"""Read official GeoNode/INCRA WMS capabilities without modifying the database.

Usage: python3 scripts/probe_incra_geonode.py
"""
import ssl
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

ENDPOINT = "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows"


def main():
    parameters = {"service": "WMS", "request": "GetCapabilities", "version": "1.1.1"}
    url = ENDPOINT + "?" + urlencode(parameters)
    req = Request(url, headers={"User-Agent": "Amazonika-Geoespacial/1.0", "Accept": "application/xml,text/xml,*/*"})
    with urlopen(req, timeout=30, context=ssl.create_default_context()) as response:
        data = response.read(6_000_001)
        if len(data) > 6_000_000:
            raise ValueError("Capabilities excedem 6 MB.")
        print("HTTP", response.status, "Content-Type", response.headers.get("Content-Type"))
    root = ElementTree.fromstring(data)
    local_root = root.tag.split("}")[-1]
    if local_root not in {"WMT_MS_Capabilities", "WMS_Capabilities"}:
        raise ValueError("Resposta não é GetCapabilities WMS: " + local_root)
    names = []
    for element in root.iter():
        if element.tag.split("}")[-1] != "Layer":
            continue
        name = next((child.text for child in element if child.tag.split("}")[-1] == "Name" and child.text), None)
        title = next((child.text for child in element if child.tag.split("}")[-1] == "Title" and child.text), None)
        if name:
            names.append((name.strip(), (title or "").strip()))
    print("CAMADAS PUBLICADAS:", len(names))
    for name, title in names[:80]:
        print(f"  LAYERS={name} | {title}")
    if not names:
        raise ValueError("GetCapabilities não informou camadas nomeadas.")
    print("Configure no painel de Fontes o valor exato de LAYERS apresentado acima.")


if __name__ == "__main__":
    main()
