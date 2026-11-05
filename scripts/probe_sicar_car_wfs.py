"""Read-only SICAR WFS capability and field probe using standard TLS validation.

No authenticated data, no CAR number and no statewide feature downloads.
Run: python3 scripts/probe_sicar_car_wfs.py
"""
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

URL = "https://geoserver.car.gov.br/geoserver/sicar/ows"
LAYER = "sicar:sicar_imoveis_ap"
QUERIES = (
    ("Capabilities", {
        "SERVICE": "WFS", "VERSION": "1.0.0", "REQUEST": "GetCapabilities",
    }),
    ("Campos Amapá", {
        "SERVICE": "WFS", "VERSION": "1.0.0", "REQUEST": "DescribeFeatureType",
        "TYPENAME": LAYER,
    }),
)


def main():
    for name, params in QUERIES:
        url = URL + "?" + urlencode(params)
        print("\n", name)
        try:
            request = Request(url, headers={"User-Agent": "Amazonika-Geoespacial/1.0"})
            with urlopen(request, timeout=25) as response:
                content_type = response.headers.get("Content-Type")
                payload = response.read(1_000_001)
                print("HTTP:", response.status, "Content-Type:", content_type)
            if len(payload) > 1_000_000:
                print("ERRO: XML excedeu 1MB")
                continue
            root = ET.fromstring(payload)
            exceptions = [node.text for node in root.iter()
                          if node.tag.split("}")[-1] in ("ServiceException", "ExceptionText")
                          and node.text]
            if exceptions:
                print("ERRO OGC:", exceptions[0][:350])
                continue
            if name == "Capabilities":
                layers = [node.text for node in root.iter()
                          if node.tag.split("}")[-1] == "Name" and node.text]
                print("Camada AP publicada:", LAYER in layers)
                print("Quantidade de nomes publicados:", len(layers))
            else:
                fields = [node.attrib.get("name") for node in root.iter()
                          if node.tag.split("}")[-1] == "element" and node.attrib.get("name")]
                print("Campos:", ", ".join(fields[:55]))
                print("Campo cod_imovel:", "cod_imovel" in fields)
        except (HTTPError, URLError, TimeoutError, ET.ParseError) as exc:
            print("INACESSÍVEL:", type(exc).__name__, str(exc)[:240])
            print("Não desabilite a verificação TLS em produção.")
    print("\nVerifique GetFeature exato com um código CAR de teste antes de liberar o fluxo.")


if __name__ == "__main__":
    main()
