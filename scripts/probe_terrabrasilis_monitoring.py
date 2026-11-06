"""Discover official PRODES/DETER WFS layers without downloading features.

Execute on the VPS: python3 scripts/probe_terrabrasilis_monitoring.py
"""
from pathlib import Path
import sys

# Running directly as a standalone script may use only standard library.
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

BASE = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
PARAMS = {"service": "WFS", "version": "1.0.0", "request": "GetCapabilities"}


def main():
    url = BASE + "?" + urlencode(PARAMS)
    req = Request(url, headers={"User-Agent": "Amazonika-Geoespacial/1.0"})
    try:
        with urlopen(req, timeout=30) as response:
            body = response.read(3_145_729)
            print("HTTP:", response.status, "Content-Type:", response.headers.get("Content-Type"))
    except Exception as exc:
        print("TER RABRASILIS_INDISPONIVEL:", type(exc).__name__, str(exc)[:240])
        sys.exit(2)
    if len(body) > 3_145_728:
        print("XML muito grande, não processado")
        sys.exit(2)
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        print("Não é XML válido; prefixo:", body[:100].decode(errors="replace"))
        sys.exit(2)
    layers = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "FeatureType":
            continue
        child = {node.tag.rsplit("}", 1)[-1]: (node.text or "").strip()
                 for node in el}
        name, title = child.get("Name", ""), child.get("Title", "")
        if "prodes" in (name + title).lower() or "deter" in (name + title).lower():
            layers.append((name, title))
    print("Camadas PRODES/DETER publicadas:", len(layers))
    for name, title in layers[:80]:
        print("  ", name, "|", title[:95])
    if len(layers) > 80:
        print("... Outras", len(layers)-80, "camadas omitidas da saída")
    if not layers:
        print("Nenhuma camada encontrada; não ativar indicadores até confirmar serviço.")


if __name__ == "__main__":
    main()
