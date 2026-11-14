#!/usr/bin/env bash
# GEO-81E: Homologação HTTP end-to-end, rede e PostGIS descartáveis.
set -Eeuo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

NET="amazonika-geo81-isolada"
DB="amazonika-geo81-db"
API="amazonika-geo81-api"
API_IMAGE="amazonika-api-topcon:geo80-20261114"
DB_IMAGE="postgis/postgis:16-3.4"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/deploy/topcon/geo81_http_smoke.py"
test -s "$SCRIPT"

echo "===== 1. VERIFICAR IMAGENS E RESÍDUOS ====="
docker image inspect "$API_IMAGE" "$DB_IMAGE" >/dev/null
for NAME in "$DB" "$API"; do
  if docker container inspect "$NAME" >/dev/null 2>&1; then
    echo "Container $NAME já existe: nenhuma alteração foi feita."
    exit 1
  fi
done
if docker network inspect "$NET" >/dev/null 2>&1; then
  echo "Rede $NET já existe: nenhuma alteração foi feita."
  exit 1
fi

# O trap só é instalado após verificar que nenhum recurso preexistia.
# A limpeza opera exclusivamente sobre recursos comprovadamente criados nesta execução.
CREATED_NET=0
CREATED_DB=0
CREATED_API=0
cleanup() {
  status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    echo "===== LOGS DE HOMOLOGAÇÃO (falha) ====="
    if [[ "$CREATED_API" -eq 1 ]]; then
      docker logs --tail 80 "$API" 2>&1 || true
    fi
    if [[ "$CREATED_DB" -eq 1 ]]; then
      docker logs --tail 50 "$DB" 2>&1 || true
    fi
  fi
  echo "===== REMOVENDO SOMENTE RECURSOS CRIADOS NESTA EXECUÇÃO ====="
  if [[ "$CREATED_API" -eq 1 ]]; then
    docker rm -f "$API" >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_DB" -eq 1 ]]; then
    docker rm -f "$DB" >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_NET" -eq 1 ]]; then
    docker network rm "$NET" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "===== 2. REDE DOCKER INTERNA ====="
docker network create --internal "$NET" >/dev/null
CREATED_NET=1

echo "===== 3. POSTGIS DESCARTÁVEL ====="
docker run -d --name "$DB" --network "$NET" \
  --memory 1g --cpus 0.5 \
  --tmpfs /var/lib/postgresql/data:rw,size=512m \
  -e PGDATA=/var/lib/postgresql/data/pgdata \
  -e POSTGRES_DB=geo81_test \
  -e POSTGRES_USER=geo81 \
  -e POSTGRES_PASSWORD=geo81_local_only \
  "$DB_IMAGE" >/dev/null
CREATED_DB=1

DB_READY=0
for ATTEMPT in {1..40}; do
  if docker exec "$DB" pg_isready -U geo81 -d geo81_test >/dev/null 2>&1; then
    DB_READY=1
    break
  fi
  sleep 2
done
if [[ "$DB_READY" -ne 1 ]]; then
  echo "PostGIS temporário não ficou pronto."
  exit 1
fi

echo "===== 4. API CANDIDATA ISOLADA ====="
docker run -d --name "$API" --network "$NET" \
  --memory 1536m --cpus 0.75 \
  --tmpfs /tmp:rw,size=128m \
  -e DATABASE_URL="postgresql+psycopg://geo81:geo81_local_only@amazonika-geo81-db:5432/geo81_test" \
  -e CORS_ORIGINS=http://localhost:3000 \
  -e STORAGE_DIR=/tmp/uploads \
  -e PUBLIC_BASE_URL=http://localhost:3000 \
  -e GOOGLE_MAP_TILES_ENABLED=false \
  -e MAPBOX_SATELLITE_ENABLED=false \
  "$API_IMAGE" >/dev/null
CREATED_API=1

API_READY=0
for ATTEMPT in {1..40}; do
  if docker exec "$API" curl --silent --show-error --fail --max-time 3 \
    http://127.0.0.1:8000/ready >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  sleep 2
done
if [[ "$API_READY" -ne 1 ]]; then
  echo "API não iniciou."
  exit 1
fi

echo "===== 5. TESTES HTTP REAIS COM SESSÃO TEMPORÁRIA ====="
docker run --rm --network "$NET" --memory 512m --cpus 0.5 \
  --volume "$SCRIPT:/tmp/geo81_http_smoke.py:ro" \
  --env PYTHONPATH=/app \
  --workdir /app \
  --env GEO81_API_URL=http://amazonika-geo81-api:8000 \
  --env DATABASE_URL="postgresql+psycopg://geo81:geo81_local_only@amazonika-geo81-db:5432/geo81_test" \
  --entrypoint python "$API_IMAGE" -B /tmp/geo81_http_smoke.py

echo "===== 6. CONFERIR PRODUÇÃO (LEITURA) ====="
curl --silent --show-error --fail http://127.0.0.1:18000/ready
echo
docker inspect amazonika-geoespacial-api-1 \
  --format 'API produção: {{.Config.Image}} | {{.State.Health.Status}}'
docker inspect amazonika-geoespacial-web-1 \
  --format 'WEB produção: {{.Config.Image}} | {{.State.Health.Status}}'

echo "===== GEO-81E APROVADA ====="
