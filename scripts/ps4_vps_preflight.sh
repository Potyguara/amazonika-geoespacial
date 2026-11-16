#!/usr/bin/env bash
# Pré-homologação PS4 somente leitura; não implanta, reinicia nem modifica serviços.
set -Eeuo pipefail
cd /opt/amazonika-geoespacial || {
  echo "ERRO: pasta /opt/amazonika-geoespacial não encontrada."; exit 2;
}
printf '\n=== PS4 — BASE DE CÓDIGO ===\n'
git branch --show-current
git rev-parse --short HEAD
printf '\n=== RECURSOS VPS ===\n'
df -h /
free -h
printf '\n=== CONTAINERS ===\n'
docker compose --env-file .env.production -f docker-compose.production.yml ps
printf '\n=== COMPARTILHAMENTO DO VOLUME DE DADOS ===\n'
docker compose --env-file .env.production -f docker-compose.production.yml \
  config --format json | python3 -c '
import json,sys
settings=json.load(sys.stdin)
for name in ("api","package-worker"):
    values=settings["services"][name].get("volumes",[])
    print(name,[(v.get("source"),v.get("target")) for v in values if v.get("target")=="/data/uploads"])
'
printf '\n=== WORKER E FILA PS4 ===\n'
docker compose --env-file .env.production -f docker-compose.production.yml \
  logs --tail=20 package-worker | tail -n 25
printf '\n=== RESERVA DE ARMAZENAMENTO ===\n'
df -h /opt /tmp
printf '\n=== API (somente saúde) ===\n'
curl --max-time 10 --fail --silent --show-error http://127.0.0.1:18000/ready
printf '\n\n=== GDAL NO CONTAINER API ===\n'
docker compose --env-file .env.production -f docker-compose.production.yml \
  exec -T api sh -c 'command -v gdalinfo && command -v gdalwarp && command -v gdal_translate && gdalinfo --version'
printf '\n=== PROXY NGINX — LIMITES DE UPLOAD ===\n'
if command -v nginx >/dev/null 2>&1; then
  nginx -T 2>&1 | grep -n -E 'server_name geo\\.amazonikaengenharia\\.com\\.br|client_max_body_size|proxy_read_timeout|proxy_send_timeout|proxy_request_buffering' || true
  echo "ATENÇÃO: confira o bloco server/location aplicável; grep não determina herança de diretivas."
else
  echo "Nginx não encontrado no host; verifique o proxy externo."
fi
printf '\n=== VERIFICAÇÃO DO LIMITE DO SISTEMA ===\n'
docker compose --env-file .env.production -f docker-compose.production.yml \
  exec -T api python - <<'PY'
from app.services.ps4_assets import MAX_RASTER_BYTES, MAX_REPORT_BYTES
from app.core.config import get_settings
from pathlib import Path
settings = get_settings()
root = Path(settings.storage_dir)
print("GeoTIFF (bytes):", MAX_RASTER_BYTES)
print("PDF (bytes):", MAX_REPORT_BYTES)
print("Diretório de dados existe:", root.exists())
print("Diretório gravável pelo processo:", root.is_dir() and __import__("os").access(root, __import__("os").W_OK))
PY
printf '\nPré-homologação somente leitura concluída. NÃO houve publicação ou reinício.\n'
