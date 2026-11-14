#!/usr/bin/env bash
# GEO-83B: inicia ambiente persistente de HOMOLOGAÇÃO local, sem tocar na produção.
set -Eeuo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
NET=amazonika-geo83-internal
EDGE=amazonika-geo83-edge
DB=amazonika-geo83-db
API=amazonika-geo83-api
WEB=amazonika-geo83-web
PROXY=amazonika-geo83-proxy
LABEL=amazonika.geo83.homolog
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROXY_FILE="$BASE/deploy/topcon/geo83_proxy.cjs"
test -s "$PROXY_FILE"
for IMG in amazonika-api-topcon:geo80-20261114 amazonika-web-topcon:geo83-20261114 postgis/postgis:16-3.4 amazonika-web-candidato:geo44-20261111; do
  docker image inspect "$IMG" >/dev/null
done

echo "===== 1. VERIFICACOES PREVIAS ====="
for C in "$DB" "$API" "$WEB" "$PROXY"; do
  if docker container inspect "$C" >/dev/null 2>&1; then
    echo "O container $C ja existe. Nada foi alterado."
    exit 1
  fi
done
if docker network inspect "$NET" >/dev/null 2>&1; then
  echo "Rede $NET ja existe. Nada foi alterado."
  exit 1
fi
if docker network inspect "$EDGE" >/dev/null 2>&1; then
  echo "Rede $EDGE ja existe. Nada foi alterado."
  exit 1
fi
if ss -ltn | grep -q ':13083 '; then
  echo "Porta 13083 ocupada. Nada foi alterado."
  exit 1
fi

CREATED_NET=0
CREATED_EDGE=0
CREATED_DB=0
CREATED_API=0
CREATED_WEB=0
CREATED_PROXY=0
cleanup_on_failure() {
  status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    echo "===== ERRO: LOGS API / WEB / PROXY ====="
    [[ "$CREATED_API" == 1 ]] && docker logs --tail 60 "$API" 2>&1 || true
    [[ "$CREATED_WEB" == 1 ]] && docker logs --tail 60 "$WEB" 2>&1 || true
    [[ "$CREATED_PROXY" == 1 ]] && docker logs --tail 60 "$PROXY" 2>&1 || true
    [[ "$CREATED_PROXY" == 1 ]] && docker rm -f "$PROXY" >/dev/null 2>&1 || true
    [[ "$CREATED_WEB" == 1 ]] && docker rm -f "$WEB" >/dev/null 2>&1 || true
    [[ "$CREATED_API" == 1 ]] && docker rm -f "$API" >/dev/null 2>&1 || true
    [[ "$CREATED_DB" == 1 ]] && docker rm -f "$DB" >/dev/null 2>&1 || true
    [[ "$CREATED_NET" == 1 ]] && docker network rm "$NET" >/dev/null 2>&1 || true
    [[ "$CREATED_EDGE" == 1 ]] && docker network rm "$EDGE" >/dev/null 2>&1 || true
  fi
}
trap cleanup_on_failure EXIT

echo "===== 2. REDE INTERNA ====="
docker network create --internal --label "$LABEL=1" "$NET" >/dev/null
CREATED_NET=1
docker network create --label "$LABEL=1" "$EDGE" >/dev/null
CREATED_EDGE=1

echo "===== 3. POSTGIS DESCARTAVEL ====="
docker run -d --name "$DB" --label "$LABEL=1" --network "$NET" \
  --memory 1g --cpus 0.5 \
  --tmpfs /var/lib/postgresql/data:rw,size=512m \
  -e PGDATA=/var/lib/postgresql/data/pgdata \
  -e POSTGRES_DB=geo83_test \
  -e POSTGRES_USER=geo83 \
  -e POSTGRES_PASSWORD=geo83_local_only \
  postgis/postgis:16-3.4 >/dev/null
CREATED_DB=1
READY=0
for I in {1..45}; do
  if docker exec "$DB" pg_isready -U geo83 -d geo83_test >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "PostGIS nao iniciou"; exit 1; }

echo "===== 4. API TOPCON GEO80 ====="
docker run -d --name "$API" --label "$LABEL=1" --network "$NET" \
  --memory 1536m --cpus 0.75 --tmpfs /tmp:rw,size=128m \
  -e DATABASE_URL="postgresql+psycopg://geo83:geo83_local_only@amazonika-geo83-db:5432/geo83_test" \
  -e CORS_ORIGINS=http://localhost:13083 \
  -e STORAGE_DIR=/tmp/uploads \
  -e PUBLIC_BASE_URL=http://localhost:13083 \
  -e GOOGLE_MAP_TILES_ENABLED=false \
  -e MAPBOX_SATELLITE_ENABLED=false \
  amazonika-api-topcon:geo80-20261114 >/dev/null
CREATED_API=1
READY=0
for I in {1..45}; do
  if docker exec "$API" curl -fsS --max-time 3 http://127.0.0.1:8000/ready >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
[[ "$READY" == 1 ]] || { echo "API de homologacao nao iniciou"; exit 1; }

echo "===== 5. USUARIO TEMPORARIO DE TESTE ====="
docker exec -i "$API" python -B - <<'PY'
import secrets
from sqlalchemy.engine import make_url
from app.core.config import get_settings
url = make_url(get_settings().database_url)
assert (url.host, url.database, url.username) == ("amazonika-geo83-db", "geo83_test", "geo83")
from app.db.session import SessionLocal
from app.models.auth import Permission, Role, User
from app.core.security import hash_password
password = secrets.token_urlsafe(18)
email = "geo83-homolog@example.com"
with SessionLocal() as db:
    perm = Permission(code="analysis.execute", name="Executar análise", module="analysis")
    role = Role(code="ADMINISTRADOR", name="Admin homologação")
    role.permissions.append(perm)
    user = User(email=email, full_name="Teste GEO83", password_hash=hash_password(password), is_active=True)
    user.roles.append(role)
    db.add(user)
    db.commit()
print("USUARIO TEMPORARIO:", email)
print("SENHA TEMPORARIA:", password)
print("OBS: banco exclusivamente de teste; anotá-la antes de fechar o terminal")
PY

echo "===== 6. FRONTEND GEO83 ====="
docker run -d --name "$WEB" --label "$LABEL=1" --network "$NET" \
  --memory 768m --cpus 0.5 \
  -e NEXT_PUBLIC_API_URL=/api/v1 \
  amazonika-web-topcon:geo83-20261114 >/dev/null
CREATED_WEB=1

echo "===== 7. PROXY LOCAL, SEM EXPOSICAO PUBLICA ====="
docker run -d --name "$PROXY" --label "$LABEL=1" --network "$EDGE" \
  --memory 160m --cpus 0.25 \
  -p 127.0.0.1:13083:8080 \
  -v "$PROXY_FILE:/tmp/geo83_proxy.cjs:ro" \
  --entrypoint node amazonika-web-candidato:geo44-20261111 \
  /tmp/geo83_proxy.cjs >/dev/null
CREATED_PROXY=1
docker network connect "$NET" "$PROXY"

echo "===== 8. TESTAR URL HOMOLOG ====="
READY=0
for I in {1..35}; do
  CODE="$(curl --silent --max-time 4 --output /dev/null --write-out '%{http_code}' http://127.0.0.1:13083/ || true)"
  if [[ "$CODE" == 200 ]]; then READY=1; break; fi
  if (( I == 1 || I % 5 == 0 )); then echo "Tentativa $I: HTTP ${CODE:-sem_resposta}"; fi
  sleep 2
done
if [[ "$READY" != 1 ]]; then
  echo "Frontend de homologacao nao respondeu HTTP 200"
  echo "===== DIAGNOSTICO DE PROXY ====="
  docker exec "$PROXY" node -e '
const http=require("http");
for(const h of ["amazonika-geo83-web:3000","amazonika-geo83-api:8000"]){
  const [host,port]=h.split(":");
  http.get({hostname:host,port:Number(port),path:port==="8000"?"/ready":"/",timeout:3000},r=>{
    console.log(h,"status",r.statusCode);
    r.resume();
  }).on("error",e=>console.log(h,e.message));
}
' || true
  exit 1
fi
curl -fsS http://127.0.0.1:13083/ready
echo
curl -fsS http://127.0.0.1:18000/ready
echo
echo "===== 9. PRODUCAO NAO ALTERADA ====="
docker inspect amazonika-geoespacial-api-1 --format 'API produção={{.Config.Image}} | {{.State.Health.Status}}'
docker inspect amazonika-geoespacial-web-1 --format 'WEB produção={{.Config.Image}} | {{.State.Health.Status}}'
echo "===== GEO-83B ATIVA — ACESSE VIA TUNEL SSH localhost:13083 ====="
