"""Run inside cartography-worker: /usr/bin/python3 /srv/smoke.py"""
import json
import urllib.request

property_polygon={
 "type":"Polygon",
 "coordinates":[[[-51.15,-0.12],[-51.13,-0.12],[-51.13,-0.10],[-51.15,-0.10],[-51.15,-0.12]]]
}
theme_polygon={
 "type":"Polygon",
 "coordinates":[[[-51.148,-0.118],[-51.14,-0.118],[-51.14,-0.11],[-51.148,-0.11],[-51.148,-0.118]]]
}
payload={
 "title":"MAPA TEMÁTICO DE HOMOLOGAÇÃO",
 "subtitle":"Teste automatizado do motor PyQGIS",
 "source":"Geometrias sintéticas de teste, não utilizar em peças oficiais",
 "style":{"grid":"border","context":"balanced"},
 "layers":[
   {"name":"Área de teste", "role":"property","color":"#d02020","geometry":property_polygon},
   {"name":"Classe de exemplo","role":"theme","color":"#45956e","geometry":theme_polygon}
 ]
}
request=urllib.request.Request("http://127.0.0.1:8090/render",
 data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(request,timeout=90) as response:
 result=response.read()
assert result.startswith(b"%PDF"), "Saída não é PDF"
assert len(result)>1000, "PDF inesperadamente pequeno"
from pathlib import Path
output=Path("/tmp/amazonika-pyqgis-homologacao.pdf")
output.write_bytes(result)
print("PYQGIS_SMOKE_OK",len(result),"bytes",str(output))
