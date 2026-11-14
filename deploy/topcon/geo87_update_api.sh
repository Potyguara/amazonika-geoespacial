#!/usr/bin/env bash
# GEO-87: atualiza exclusivamente API no ambiente GEO83 de homologacao.
set -Eeuo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd "$(dirname "$0")/../.."
LABEL=amazonika.geo83.homolog
API=amazonika-geo83-api
DB=amazonika-geo83-db
WEB=amazonika-geo83-web
PROXY=amazonika-geo83-proxy
NET=amazonika-geo83-internal
OLD=amazonika-api-topcon:geo85-20261114
NEW=amazonika-api-topcon:geo87-20261114
DBURL=postgresql+psycopg://geo83:geo83_local_only@amazonika-geo83-db:5432/geo83_test

test -z "$(git status --porcelain)"
for C in "$DB" "$API" "$WEB" "$PROXY"; do
  docker inspect "$C" >/dev/null
  test "$(docker inspect "$C" --format '{{index .Config.Labels "amazonika.geo83.homolog"}}')" = 1
  test "$(docker inspect "$C" --format '{{.State.Running}}')" = true
done
test "$(docker inspect "$API" --format '{{.Config.Image}}')" = "$OLD"
test "$(docker inspect "$DB" --format '{{.Config.Image}}')" = postgis/postgis:16-3.4
test "$(docker inspect "$API" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^DATABASE_URL=')" = "DATABASE_URL=$DBURL"
docker network inspect "$NET" >/dev/null
test "$(docker network inspect "$NET" --format '{{index .Labels "amazonika.geo83.homolog"}}')" = 1
docker image inspect "$OLD" >/dev/null

echo "===== 1. COMPILAR IMPORTADOR GEO87 ====="
docker build -f deploy/topcon/Dockerfile.api-geo87 \
  --build-arg BASE_API_IMAGE="$OLD" -t "$NEW" .

echo "===== 2. VALIDAR TESTES DO MOTOR PA2 SEM REDE ====="
docker run --rm --network none --memory 512m --cpus 0.5 \
  -v "$PWD/backend/tests/test_pa2_intersection.py:/tmp/test_pa2_intersection.py:ro" \
  -e PYTHONPATH=/app --workdir /app \
  --entrypoint python "$NEW" -B /tmp/test_pa2_intersection.py

echo "===== 3. SUBSTITUIR SOMENTE API GEO83 ====="
start_api() {
  local image="$1"
  docker run -d --name "$API" --label "$LABEL=1" --network "$NET" \
    --memory 1536m --cpus 0.75 --tmpfs /tmp:rw,size=128m \
    -e DATABASE_URL="$DBURL" \
    -e CORS_ORIGINS=http://localhost:13083 \
    -e STORAGE_DIR=/tmp/uploads \
    -e PUBLIC_BASE_URL=http://localhost:13083 \
    -e GOOGLE_MAP_TILES_ENABLED=false \
    -e MAPBOX_SATELLITE_ENABLED=false \
    "$image" >/dev/null
}
rollback() {
  echo "Falha na nova API. Restaurando somente API GEO80..."
  docker logs --tail 80 "$API" 2>&1 || true
  docker rm -f "$API" >/dev/null 2>&1 || true
  start_api "$OLD" || true
}
docker rm -f "$API" >/dev/null
trap rollback ERR
start_api "$NEW"
READY=0
for I in {1..45}; do
  if docker exec "$API" curl -fsS --max-time 3 http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
test "$READY" = 1
curl -fsS --max-time 8 http://127.0.0.1:13083/ready
echo
trap - ERR
echo "===== 4. VALIDAR ROTA PA2 ====="
docker exec "$API" sh -c 'curl -fsS http://127.0.0.1:8000/openapi.json | grep -q "topcon/pa2-intersection"'
echo "===== 5. CONFERIR AMBIENTE OFICIAL ====="
curl -fsS http://127.0.0.1:18000/ready
echo
docker inspect amazonika-geoespacial-api-1 \
  --format 'PRODUCAO API={{.Config.Image}} {{.State.Health.Status}}'
docker inspect amazonika-geoespacial-web-1 \
  --format 'PRODUCAO WEB={{.Config.Image}} {{.State.Health.Status}}'
docker inspect "$API" --format 'HOMOLOG API={{.Config.Image}} running={{.State.Running}}'
echo "===== GEO87 HOMOLOG ATIVA — REIMPORTE O PDF NO NAVEGADOR ====="
