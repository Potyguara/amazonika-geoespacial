"""Run inside cartography-worker: /usr/bin/python3 /srv/smoke.py"""
import json
import urllib.request
import time

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
 "metadata":{"property_name":"Área de homologação", "municipality":"Macapá", "state":"AP", "responsible":"Teste técnico (fictício)"},
 "layers":[
   {"name":"Área de teste", "role":"property","color":"#d02020","geometry":property_polygon},
   {"name":"Classes de uso do solo","role":"theme","color":"#45956e",
    "class_field":"classe",
    "classes":[{"value":"Floresta","label":"Floresta","color":"#238b45"},
               {"value":"Pastagem","label":"Pastagem","color":"#edc36a"}],
    "features":[
      {"type":"Feature","properties":{"classe":"Floresta"},"geometry":theme_polygon},
      {"type":"Feature","properties":{"classe":"Pastagem"},"geometry":{
       "type":"Polygon","coordinates":[[[-51.139,-0.119],[-51.134,-0.119],[-51.134,-0.114],[-51.139,-0.114],[-51.139,-0.119]]]}}
    ]}
 ]
}
request=urllib.request.Request("http://127.0.0.1:8090/render",
 data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
deadline=time.monotonic()+90
while True:
 try:
  with urllib.request.urlopen("http://127.0.0.1:8090/health",timeout=3) as ready:
   if ready.status==200:
    break
 except (OSError,TimeoutError):
  if time.monotonic()>=deadline:
   raise RuntimeError("PyQGIS não iniciou em 90 segundos; consulte docker logs")
  time.sleep(1)
with urllib.request.urlopen(request,timeout=90) as response:
 result=response.read()
assert result.startswith(b"%PDF"), "Saída não é PDF"
assert len(result)>1000, "PDF inesperadamente pequeno"
from pathlib import Path
output=Path("/tmp/amazonika-pyqgis-homologacao.pdf")
output.write_bytes(result)
print("PYQGIS_SMOKE_OK",len(result),"bytes",str(output))

# Validate that oversized legends fail explicitly rather than overlap metadata.
from urllib.error import HTTPError
oversized=json.loads(json.dumps(payload))
theme=oversized["layers"][1]
theme["classes"]=[{"value":f"Classe {i}","label":f"Classe {i}","color":"#238b45"} for i in range(16)]
bad=urllib.request.Request("http://127.0.0.1:8090/render",
 data=json.dumps(oversized).encode(),headers={"Content-Type":"application/json"},method="POST")
try:
 urllib.request.urlopen(bad,timeout=90)
 raise AssertionError("Legenda com 16 classes deveria ser rejeitada")
except HTTPError as exc:
 assert exc.code == 422, f"Erro inesperado: {exc.code}"
print("PYQGIS_LEGEND_LIMIT_OK")
