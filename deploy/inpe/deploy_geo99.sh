#!/usr/bin/env bash
# GEO99 - deploy only to isolated GEO83 homology. Never targets production services.
set -Eeuo pipefail
umask 077
cd /opt/amazonika-topcon-stage

API=amazonika-geo83-api
WEB=amazonika-geo83-web
TILES=amazonika-geo90-cog-tiles
API_OLD=amazonika-api-inpe:geo98
WEB_OLD=amazonika-web:geo98
TILES_OLD=amazonika-cog-tiles:geo98-multiscene
API_NEW=amazonika-api-inpe:geo99
WEB_NEW=amazonika-web:geo99
TILES_NEW=amazonika-cog-tiles:geo99-multiscene
API_BACKUP=amazonika-geo83-api-backup-geo99
WEB_BACKUP=amazonika-geo83-web-backup-geo99
TILES_BACKUP=amazonika-geo90-cog-tiles-backup-geo99
INTERNAL=amazonika-geo83-internal
EDGE=amazonika-geo83-edge

echo "===== GEO99: PRE-VALIDACOES ====="
test "$(hostname)" = "SIS"
test -z "$(git status --porcelain)"
test -f deploy/inpe/Dockerfile.api-geo99
docker image inspect "$API_NEW" "$WEB_NEW" "$TILES_NEW" >/dev/null
for entry in "$API:$API_OLD" "$WEB:$WEB_OLD" "$TILES:$TILES_OLD"; do
  name="${entry%%:*}"
  old="${entry#*:}"
  test "$(docker inspect "$name" --format '{{.Config.Image}}')" = "$old"
  test "$(docker inspect "$name" --format '{{.State.Running}}')" = "true"
done
for backup in "$API_BACKUP" "$WEB_BACKUP" "$TILES_BACKUP"; do
  if docker container inspect "$backup" >/dev/null 2>&1; then
    echo "Backup ja existe: $backup. Nenhum servico foi alterado."
    exit 1
  fi
done
test "$(docker network inspect "$INTERNAL" --format '{{.Internal}}')" = "true"
test "$(docker network inspect "$EDGE" --format '{{.Internal}}')" = "false"
curl -fsS http://127.0.0.1:13083/ready && echo
curl -fsS http://127.0.0.1:18000/ready && echo

TMP_GEO99="$(mktemp -d)"
for name in "$API" "$WEB"; do
  docker inspect "$name" | python3 -c '
import json,sys
for key in json.load(sys.stdin)[0]["Config"]["Env"]:
    print(key)
' > "$TMP_GEO99/$name.env"
  chmod 600 "$TMP_GEO99/$name.env"
done

restore() {
  local name="$1" backup="$2"
  if docker container inspect "$backup" >/dev/null 2>&1; then
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker rename "$backup" "$name" || true
    docker start "$name" >/dev/null 2>&1 || true
  fi
}
rollback() {
  trap - ERR INT TERM
  set +e
  echo "===== GEO99: REVERSAO ====="
  restore "$WEB" "$WEB_BACKUP"
  restore "$API" "$API_BACKUP"
  restore "$TILES" "$TILES_BACKUP"
  rm -rf "$TMP_GEO99"
  docker ps --filter name=amazonika-geo83 --filter name=amazonika-geo90 \
    --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
}
trap rollback ERR INT TERM

echo "===== GEO99: RENDERIZADOR ====="
docker stop "$TILES" >/dev/null
docker rename "$TILES" "$TILES_BACKUP"
docker run -d --name "$TILES" \
  --label amazonika.geo90.raster=1 \
  --network "$EDGE" \
  --memory 768m --cpus 0.5 --pids-limit 64 \
  --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --restart no "$TILES_NEW" >/dev/null
docker network connect "$INTERNAL" "$TILES"
ready=0
for i in {1..45}; do
  if docker exec "$TILES" python -c '
import json,urllib.request
with urllib.request.urlopen("http://127.0.0.1:8090/health",timeout=3) as r:
    a=json.load(r); assert a["status"]=="ok"
' >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
if [ "$ready" != 1 ]; then docker logs --tail 100 "$TILES"; false; fi
docker run --rm --network "$INTERNAL" --memory 256m \
  --entrypoint python "$API_NEW" -c '
import json,urllib.request
with urllib.request.urlopen("http://amazonika-geo90-cog-tiles:8090/health",timeout=10) as r:
    a=json.load(r); assert a["status"]=="ok" and a["scene"]=="allowlisted"
'

echo "===== GEO99: API ====="
docker stop "$API" >/dev/null
docker rename "$API" "$API_BACKUP"
docker run -d --name "$API" --network "$INTERNAL" \
  --env-file "$TMP_GEO99/$API.env" \
  --memory 1536m --cpus 0.75 --pids-limit 128 \
  --security-opt no-new-privileges --restart no "$API_NEW" >/dev/null
ready=0
for i in {1..45}; do
  if docker exec "$API" python -c '
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8000/ready",timeout=3) as r:
    assert r.status==200
' >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
if [ "$ready" != 1 ]; then docker logs --tail 100 "$API"; false; fi

echo "===== GEO99: FRONTEND ====="
docker stop "$WEB" >/dev/null
docker rename "$WEB" "$WEB_BACKUP"
docker run -d --name "$WEB" \
  --label amazonika.geo83.homolog=1 --network "$INTERNAL" \
  --env-file "$TMP_GEO99/$WEB.env" \
  --memory 768m --cpus 0.5 --pids-limit 128 \
  --security-opt no-new-privileges --restart no "$WEB_NEW" >/dev/null
ready=0
for i in {1..45}; do
  if docker exec "$WEB" node -e '
fetch("http://127.0.0.1:3000/")
  .then(r=>process.exit(r.ok?0:1))
  .catch(()=>process.exit(1))
' >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
if [ "$ready" != 1 ]; then docker logs --tail 100 "$WEB"; false; fi

echo "===== GEO99: VERIFICACOES FINAIS ====="
curl -fsS http://127.0.0.1:13083/ready && echo
curl -fsS http://127.0.0.1:18000/ready && echo
for entry in "$API:$API_NEW" "$WEB:$WEB_NEW" "$TILES:$TILES_NEW"; do
  name="${entry%%:*}"
  new="${entry#*:}"
  test "$(docker inspect "$name" --format '{{.Config.Image}}')" = "$new"
  test "$(docker inspect "$name" --format '{{.State.Running}}')" = "true"
done
trap - ERR INT TERM
rm -rf "$TMP_GEO99"
echo "===== GEO99: PUBLICADO NA HOMOLOGACAO ====="
docker inspect "$API" "$WEB" "$TILES" \
  --format '{{.Name}} | {{.Config.Image}} | {{.State.Status}}'
echo "Backups GEO98 preservados para reversao."
