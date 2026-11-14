#!/usr/bin/env bash
# GEO86: atualiza EXCLUSIVAMENTE o web da homologação GEO83; banco/API/proxy preservados.
set -Eeuo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd "$(dirname "$0")/../.."
WEB=amazonika-geo83-web
NET=amazonika-geo83-internal
NEW=amazonika-web-topcon:geo86-20261114
OLD=amazonika-web-topcon:geo84-20261114
LABEL=amazonika.geo83.homolog
test -z "$(git status --porcelain)"
docker inspect "$WEB" >/dev/null
test "$(docker inspect "$WEB" --format '{{index .Config.Labels "amazonika.geo83.homolog"}}')" = 1
test "$(docker inspect "$WEB" --format '{{.Config.Image}}')" = "$OLD"
test "$(docker inspect amazonika-geo83-api --format '{{.Config.Image}}')" = amazonika-api-topcon:geo85-20261114
test "$(docker inspect amazonika-geo83-api --format '{{index .Config.Labels "amazonika.geo83.homolog"}}')" = 1
test "$(docker inspect amazonika-geo83-proxy --format '{{index .Config.Labels "amazonika.geo83.homolog"}}')" = 1
test "$(docker inspect "$WEB" --format '{{.State.Running}}')" = true
docker network inspect "$NET" >/dev/null

echo "===== 1. VALIDAR TYPESCRIPT ====="
node_modules/.bin/tsc --noEmit --incremental false --pretty false

echo "===== 2. BUILD GEO84 ====="
docker build --file deploy/topcon/Dockerfile.web-candidate \
  --build-arg BASE_WEB_IMAGE=amazonika-web-candidato:geo44-20261111 \
  --build-arg NEXT_PUBLIC_API_URL=/api/v1 \
  --tag "$NEW" .
docker image inspect "$NEW" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -Fx NEXT_PUBLIC_API_URL=/api/v1
echo "===== 3. SUBSTITUIR APENAS WEB TEMPORARIA ====="
docker rm -f "$WEB" >/dev/null
restore_old() {
  echo "Tentando restaurar web anterior GEO83..."
  docker rm -f "$WEB" >/dev/null 2>&1 || true
  docker run -d --name "$WEB" --label "$LABEL=1" --network "$NET" \
    --memory 768m --cpus 0.5 -e NEXT_PUBLIC_API_URL=/api/v1 "$OLD" >/dev/null || true
}
trap restore_old ERR
docker run -d --name "$WEB" --label "$LABEL=1" --network "$NET" \
  --memory 768m --cpus 0.5 -e NEXT_PUBLIC_API_URL=/api/v1 "$NEW" >/dev/null
for I in {1..40}; do
  code="$(curl --silent --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:13083/ || true)"
  if [[ "$code" == 200 ]]; then break; fi
  sleep 2
done
test "$code" = 200
trap - ERR
echo "===== 4. PROTEGER PRODUCAO ====="
curl -fsS http://127.0.0.1:18000/ready
echo
docker inspect amazonika-geoespacial-web-1 --format 'PRODUCAO={{.Config.Image}} {{.State.Health.Status}}'
docker inspect "$WEB" --format 'HOMOLOG={{.Config.Image}} {{.State.Running}}'
echo "GEO86 WEB HOMOLOG ATIVA — Recarregue http://localhost:13083"
