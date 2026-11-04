"""Inspect whether INCRA publishes vector fields usable for UF filtering.

Read-only WFS DescribeFeatureType against the official GeoNode endpoint.
Do not assume an 'uf' attribute exists before seeing the schema.
"""
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

URL = "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows"
PARAMS = {
    "service": "WFS",
    "version": "1.1.0",
    "request": "DescribeFeatureType",
    "typeName": "sigef_geo",
}


def main():
    request = Request(
        URL + "?" + urlencode(PARAMS),
        headers={
            "User-Agent": "Amazonika-Geoespacial/1.0",
            "Accept": "application/xml,text/xml,*/*",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read(2_000_001)
            print("WFS HTTP", response.status)
            print("Content-Type", response.headers.get("Content-Type"))
    except (HTTPError, URLError, TimeoutError) as error:
        print("WFS indisponível:", error)
        return
    if len(data) > 2_000_000:
        print("Resposta excede 2 MB.")
        return
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        print("Resposta não é XML:", data[:200].decode(errors="replace"))
        return
    if root.tag.split("}")[-1] != "schema":
        print("DescribeFeatureType não disponibilizado:", root.tag.split("}")[-1])
        print(data[:500].decode(errors="replace"))
        return
    fields = []
    for item in root.iter():
        if item.tag.split("}")[-1] == "element":
            name = item.attrib.get("name")
            kind = item.attrib.get("type")
            if name:
                fields.append((name, kind))
    print("CAMPOS PUBLICADOS:")
    for name, kind in fields:
        print(" ", name, kind or "")
    print("O uso de filtro estadual depende de um atributo de UF confirmado e de testes de GetMap.")


if __name__ == "__main__":
    main()
