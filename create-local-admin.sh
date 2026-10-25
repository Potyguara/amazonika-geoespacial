#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

EXPECTED_BRANCH="integration/geospatial-tools-vps-20261025"

if [[ "$(git branch --show-current)" != "$EXPECTED_BRANCH" ]]; then
  echo "ERRO: execute este bootstrap somente na branch $EXPECTED_BRANCH." >&2
  exit 1
fi

if ! docker compose ps --status running api | grep -q api; then
  echo "ERRO: a API local não está em execução. Rode primeiro: bash start-local.sh" >&2
  exit 1
fi

printf "E-mail do administrador local [admin.local@amazonika.local]: "
read -r ADMIN_EMAIL
ADMIN_EMAIL="${ADMIN_EMAIL:-admin.local@amazonika.local}"

printf "Nome completo [Administrador Local]: "
read -r ADMIN_NAME
ADMIN_NAME="${ADMIN_NAME:-Administrador Local}"

while true; do
  printf "Senha local (mínimo 12 caracteres): "
  read -rs ADMIN_PASSWORD
  printf "\n"
  if [[ ${#ADMIN_PASSWORD} -ge 12 ]]; then
    break
  fi
  echo "A senha precisa ter pelo menos 12 caracteres."
done

docker compose exec -T   -e LOCAL_ADMIN_EMAIL="$ADMIN_EMAIL"   -e LOCAL_ADMIN_NAME="$ADMIN_NAME"   -e LOCAL_ADMIN_PASSWORD="$ADMIN_PASSWORD"   api   python -m app.bootstrap_local     --email "$ADMIN_EMAIL"     --name "$ADMIN_NAME"     --password "$ADMIN_PASSWORD"

unset ADMIN_PASSWORD

echo
echo "Administrador local pronto."
echo "Frontend: http://localhost:3000"
