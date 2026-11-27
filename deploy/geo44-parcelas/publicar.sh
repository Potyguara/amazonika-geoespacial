#!/usr/bin/env bash
# Publica na produção do Geoespacial SÓ o download de parcelas + correções da PR #23,
# sobre o código da web geo44 (/opt/amazonika-geo-detalhamento-stage) e a API geo71.
#
#   ETAPA 1 (padrão): monta e testa as imagens novas. NÃO mexe na produção.
#   ETAPA 2: PUBLICAR=1 TAG=<tag da etapa 1> bash publicar.sh
#            faz backup do banco e troca só os containers api e web.
#   VOLTAR:  VOLTAR=1 bash publicar.sh   (volta para geo71/geo44)
set -euo pipefail

SRC_RAW="https://raw.githubusercontent.com/Potyguara/amazonika-geoespacial/${REV:-claude/project-thread-e1qg31}/deploy/geo44-parcelas"
STAGE=/opt/amazonika-geo-detalhamento-stage
PROD=/opt/amazonika-geoespacial
CMP=/opt/amazonika-geo-relatorio-comparacao
OVR_DIR=$CMP/geo-parcelas
OLD_WEB=amazonika-web-candidato:geo44-20261111
OLD_API=amazonika-api-sigef-geonode:geo71-20261111
ENV_FILE=${ENV_FILE:-$PROD/.env.production}
COMPOSE=(docker compose -p amazonika-geoespacial --project-directory "$PROD" --env-file "$ENV_FILE"
  -f "$PROD/docker-compose.production.yml"
  -f "$CMP/geo73/docker-compose.geo73.yml"
  -f "$CMP/geo47-web-candidato.yml")

# A produção sobe com --env-file .env.production (senha do banco, CORS, URLs).
# Sem ele os containers sobem com variáveis vazias e caem.
checar_env() {
  [ -s "$ENV_FILE" ] || { echo "ERRO: $ENV_FILE não existe; nada foi trocado."; exit 1; }
  for v in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB CORS_ORIGINS PUBLIC_BASE_URL; do
    grep -qE "^$v=." "$ENV_FILE" || { echo "ERRO: $v ausente em $ENV_FILE; nada foi trocado."; exit 1; }
  done
  if "${COMPOSE[@]}" config 2>&1 | grep -q "variable is not set"; then
    "${COMPOSE[@]}" config 2>&1 | grep "variable is not set" | sort -u
    echo "ERRO: variáveis faltando no compose; nada foi trocado."; exit 1
  fi
}

saude() {
  for i in $(seq 1 45); do
    if curl -fsS http://127.0.0.1:18000/ready >/dev/null && curl -fsS http://127.0.0.1:13000/ >/dev/null; then
      echo "OK: API e web respondendo."; return 0; fi
    sleep 4
  done
  echo "ATENÇÃO: API ou web não respondeu em 3 minutos."; return 1
}

if [ "${VOLTAR:-0}" = 1 ]; then
  checar_env
  echo ">> Voltando para $OLD_API e $OLD_WEB"
  "${COMPOSE[@]}" up -d --no-deps --no-build api web
  saude; exit $?
fi

if [ "${PUBLICAR:-0}" = 1 ]; then
  : "${TAG:?informe TAG=<tag mostrada na etapa 1>}"
  docker image inspect "amazonika-web-candidato:$TAG" "amazonika-api-sigef-geonode:$TAG" >/dev/null
  checar_env
  mkdir -p /opt/amazonika-backups "$OVR_DIR"
  BK=/opt/amazonika-backups/geo-antes-$TAG.sql.gz
  echo ">> Backup do banco em $BK"
  docker exec amazonika-geoespacial-db-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fp' | gzip -1 > "$BK"
  [ -s "$BK" ] || { echo "Backup vazio; nada foi trocado."; exit 1; }
  ls -lh "$BK"
  cat > "$OVR_DIR/docker-compose.parcelas.yml" <<YML
services:
  api:
    image: amazonika-api-sigef-geonode:$TAG
  web:
    image: amazonika-web-candidato:$TAG
YML
  echo ">> Trocando api e web"
  "${COMPOSE[@]}" -f "$OVR_DIR/docker-compose.parcelas.yml" up -d --no-deps --no-build api web
  if saude; then
    echo "Publicado. Para voltar: VOLTAR=1 bash publicar.sh"
  else
    echo ">> Falhou; voltando automaticamente"; "${COMPOSE[@]}" up -d --no-deps --no-build api web; saude || true; exit 1
  fi
  exit 0
fi

# ---------------- ETAPA 1: montar e testar ----------------
TAG=geo44p-$(date +%Y%m%d%H%M)
WORK=/opt/amazonika-builds/$TAG
mkdir -p "$WORK/web" "$WORK/api/app/services" "$WORK/api/app/api/routes"
curl -fsSL "$SRC_RAW/aplicar_parcelas_geo44.py" -o "$WORK/aplicar_parcelas_geo44.py"
echo ">> Pasta de trabalho: $WORK"

echo ">> Conferindo se $STAGE corresponde à geo44 (textos da tela presentes no build publicado)"
NEWER=$(find "$STAGE" \( -path '*/node_modules' -o -path '*/dist' -o -path '*/.next' -o -path '*/.git' \) -prune -o -type f \( -name '*.tsx' -o -name '*.ts' -o -name '*.css' \) -newermt '2026-11-11 07:48' -print | head -5)
[ -z "$NEWER" ] || { echo "Arquivos do stage alterados depois do build da geo44:"; echo "$NEWER"; }
grep -ohE '"[^"{}<>$`]{28,90}"' "$STAGE/components/geo-map.tsx" | tr -d '"' | grep ' ' | sort -u | head -60 > "$WORK/textos.txt"
CID=$(docker create "$OLD_WEB"); docker cp "$CID:/app/dist" "$WORK/geo44-dist" >/dev/null; docker rm "$CID" >/dev/null
TOTAL=$(wc -l < "$WORK/textos.txt"); FALTA=0
while IFS= read -r t; do grep -rqF -- "$t" "$WORK/geo44-dist" || FALTA=$((FALTA+1)); done < "$WORK/textos.txt"
echo "   $((TOTAL-FALTA)) de $TOTAL textos do stage estão na geo44."
if [ "$TOTAL" -lt 10 ] || [ $((FALTA*10)) -gt "$TOTAL" ]; then
  echo "O stage não bate com a geo44. Parei aqui; nada foi alterado."; exit 1; fi

echo ">> Web: copiando o stage e aplicando as mudanças"
tar -C "$STAGE" --exclude=./node_modules --exclude=./dist --exclude=./.next --exclude=./.git -cf - . | tar -C "$WORK/web" -xf -
python3 "$WORK/aplicar_parcelas_geo44.py" web "$WORK/web"
DF="$WORK/web/Dockerfile.web.production"; [ -f "$DF" ] || cp "$PROD/Dockerfile.web.production" "$DF"
echo ">> Web: build da imagem (alguns minutos)"
nice -n 15 docker build -q -f "$DF" -t "amazonika-web-candidato:$TAG" \
  --label org.opencontainers.image.revision="geo44+pr23" "$WORK/web"

echo ">> API: copiando arquivos da geo71 e aplicando as mudanças"
CID=$(docker create "$OLD_API")
docker cp "$CID:/app/app/services/geospatial_export.py" "$WORK/api/app/services/"
docker cp "$CID:/app/app/api/routes/tools.py" "$WORK/api/app/api/routes/"
docker rm "$CID" >/dev/null
python3 "$WORK/aplicar_parcelas_geo44.py" api "$WORK/api"
cat > "$WORK/api/Dockerfile" <<DOCKER
FROM $OLD_API
COPY app/services/geospatial_export.py /app/app/services/geospatial_export.py
COPY app/services/parcel_selection_export.py /app/app/services/parcel_selection_export.py
COPY app/api/routes/tools.py /app/app/api/routes/tools.py
RUN python -W error::SyntaxWarning -m py_compile /app/app/services/geospatial_export.py /app/app/services/parcel_selection_export.py /app/app/api/routes/tools.py
LABEL amazonika.release=geo71-parcelas-pr23
DOCKER
nice -n 15 docker build -q -t "amazonika-api-sigef-geonode:$TAG" "$WORK/api"

echo ">> API: teste sem rede"
docker run --rm --network none --entrypoint python "amazonika-api-sigef-geonode:$TAG" -c '
from app.services.geospatial_export import export_polygon
from app.services.parcel_selection_export import export_parcels
import app.api.routes.tools as t
g={"type":"Polygon","coordinates":[[[-51,0.1,5],[-51,0.2,5],[-50.9,0.2,5],[-51,0.1,5]]]}
for f in ("txt","kml","shp"): assert export_polygon(geometry=g,filename="t",format=f)[0]
p=[{"name":"A","layer":"SIGEF","geometry":g,"properties":{"codigo":"1"}}]
for f in ("kml","shp"): assert export_parcels(parcels=p,filename="t",format=f)[0]
assert any(getattr(r,"path","").endswith("/export-parcels") for r in t.router.routes)
print("   testes OK")'

echo
echo "ETAPA 1 concluída. Produção NÃO foi alterada."
echo "Para publicar:  PUBLICAR=1 TAG=$TAG bash <(curl -fsSL $SRC_RAW/publicar.sh)"
