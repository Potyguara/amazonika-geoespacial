#!/usr/bin/env bash
# GEO90/PS4 — ensaio isolado na VPS.
# Não usa compose, não publica Nginx, não reinicia produção.
set -Eeuo pipefail

REPO=/opt/amazonika-geoespacial
STAGE=/opt/amazonika-geo90-ps4-homolog
REF=origin/feat/geo90-ps4-evidencias-20261115
IMAGE=amazonika-ps4-candidato:homolog-20261116

printf '\n=== Preflight da homologação isolada ===\n'
test -d "$REPO/.git" || { echo "ERRO: checkout Git ausente."; exit 2; }
command -v docker >/dev/null
command -v git >/dev/null
test "$(docker info --format '{{.ServerVersion}}' 2>/dev/null)" != "" || {
  echo "ERRO: Docker indisponível."; exit 2;
}
root_free=$(df -Pk /opt | awk 'NR==2 {print $4}')
test "$root_free" -ge 10485760 || {
  echo "ERRO: menos de 10 GiB livres no volume da VPS."; exit 2;
}

cd "$REPO"
printf 'Produção atual: '
git rev-parse --short HEAD
printf 'Branch atual: '
git branch --show-current

# fetch não realiza checkout nem altera arquivos rastreados da produção
git fetch --no-tags origin feat/geo90-ps4-evidencias-20261115
git rev-parse --verify "$REF^{commit}" >/dev/null

if [ -e "$STAGE" ]; then
  echo "ERRO: staging já existe; não sobrescrever: $STAGE"
  exit 2
fi

printf '\n=== Criar checkout separado de homologação ===\n'
git worktree add --detach "$STAGE" "$REF"

printf '\n=== Verificar isolamento ===\n'
test "$(git -C "$REPO" rev-parse --short HEAD)" = "$(git -C "$REPO" rev-parse --short HEAD)"
git -C "$STAGE" log -1 --format='Commit candidato: %h %s'
git -C "$REPO" status --short

printf '\n=== Compilar imagem candidata independente ===\n'
docker build --pull=false \
  --file "$STAGE/backend/Dockerfile.production" \
  --tag "$IMAGE" "$STAGE/backend"

printf '\n=== Teste PS4 sem rede e sem banco externo ===\n'
# Nenhum diretório de produção é montado; root read-only e temp temporário.
docker run --rm --network none --read-only \
  --security-opt no-new-privileges \
  --cap-drop ALL --pids-limit 128 \
  --memory 1024m --cpus 1 \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m,mode=1777 \
  -e PYTHONPATH=/app \
  "$IMAGE" \
  python -m unittest discover -s tests -p 'test_ps4*.py' -v

printf '\n=== Teste SIGEF ODS sem rede ===\n'
docker run --rm --network none --read-only \
  --security-opt no-new-privileges \
  --cap-drop ALL --pids-limit 128 \
  --memory 1024m --cpus 1 \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m,mode=1777 \
  -e PYTHONPATH=/app \
  "$IMAGE" \
  python -m unittest discover -s tests -p 'test_sigef_ods_reviewed.py' -v

printf '\n=== Produção inalterada ===\n'
git -C "$REPO" rev-parse --short HEAD
docker compose --project-directory "$REPO" \
  --env-file "$REPO/.env.production" \
  -f "$REPO/docker-compose.production.yml" ps
printf '\nHOMOLOGAÇÃO ISOLADA: testes concluídos, SEM DEPLOY.\n'
