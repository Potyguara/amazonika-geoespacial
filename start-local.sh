#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="Amazônika Geoespacial"
EXPECTED_BRANCH="integration/geospatial-tools-vps-20261025"
FEATURE_HOMOLOGATION_BRANCH="feat/pecas-tecnicas-fluxo-20261026"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
API_URL="http://127.0.0.1:8000"
READY_URL="${API_URL}/ready"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*" >&2; }
section() { printf "\n\033[1;36m== %s ==\033[0m\n" "$*"; }

die() {
  red "ERRO: $*"
  exit 1
}

cleanup_frontend() {
  :
}
trap cleanup_frontend EXIT

section "Proteção do ambiente"

case "$ROOT_DIR" in
  /opt/amazonika-geoespacial|/opt/amazonika-geoespacial/*)
    die "Este script é exclusivo para homologação local. Execução em /opt/amazonika-geoespacial foi bloqueada."
    ;;
esac

command -v git >/dev/null 2>&1 || die "Git não encontrado."
command -v docker >/dev/null 2>&1 || die "Docker não encontrado. Abra/instale o Docker Desktop."
command -v node >/dev/null 2>&1 || die "Node.js não encontrado."
command -v npm >/dev/null 2>&1 || die "npm não encontrado."
command -v curl >/dev/null 2>&1 || die "curl não encontrado."

docker info >/dev/null 2>&1 || die "Docker Desktop não está em execução."

CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"

# Homologação local: permitir somente a integração validada e esta branch
# isolada de peças técnicas. A restrição de diretório/working tree permanece.
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" && "$CURRENT_BRANCH" != "$FEATURE_HOMOLOGATION_BRANCH" ]]; then
  die "Branch atual: '${CURRENT_BRANCH:-nenhuma}'. Branches de homologação permitidas: '$EXPECTED_BRANCH' ou '$FEATURE_HOMOLOGATION_BRANCH'."
fi

if [[ -n "$(git status --porcelain)" ]]; then
  yellow "ATENÇÃO: existem alterações locais não commitadas:"
  git status --short
  die "Working tree precisa estar limpo antes de iniciar a homologação."
fi

green "Branch: $CURRENT_BRANCH"
green "Commit: $CURRENT_COMMIT"

section "Versões"
node --version
npm --version
docker --version
docker compose version

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
[[ "$NODE_MAJOR" -ge 22 ]] || die "Node.js 22 ou superior é obrigatório."

section "Configuração local"

if [[ ! -f .env ]]; then
  [[ -f .env.example ]] || die ".env.example não encontrado."
  cp .env.example .env
  green ".env criado a partir de .env.example."
else
  green ".env existente preservado."
fi

if grep -q '^OPENAI_API_KEY=$' .env 2>/dev/null; then
  yellow "OPENAI_API_KEY não configurada. Planta/PDF funcionará; a redação por IA usará o fallback determinístico."
fi

section "Dependências frontend"

if [[ ! -d node_modules ]]; then
  npm ci
elif [[ ! -f node_modules/.package-lock.json ]]; then
  npm ci
elif [[ package-lock.json -nt node_modules/.package-lock.json ]]; then
  npm ci
else
  green "node_modules já disponível."
fi

section "PostGIS e API"

docker compose up --build -d db api

printf "Aguardando API"
READY=0
for _ in $(seq 1 60); do
  if curl -fsS "$READY_URL" >/tmp/amazonika-local-ready.json 2>/dev/null; then
    READY=1
    break
  fi
  printf "."
  sleep 2
done
printf "\n"

if [[ "$READY" -ne 1 ]]; then
  docker compose ps
  docker compose logs --tail=120 api
  die "API não ficou pronta."
fi

cat /tmp/amazonika-local-ready.json
rm -f /tmp/amazonika-local-ready.json
green "API e PostGIS prontos."

section "Catálogo inicial"

docker compose exec -T api python -m app.seed
green "Seed idempotente das fontes concluído."

USER_COUNT="$(docker compose exec -T db psql   -U "${POSTGRES_USER:-amazonika}"   -d "${POSTGRES_DB:-amazonika_geo}"   -tAc "SELECT COUNT(*) FROM users;" 2>/dev/null | tr -d '[:space:]' || true)"

if [[ "${USER_COUNT:-0}" == "0" ]]; then
  yellow "A base local ainda não possui usuários. O sistema subirá normalmente, mas o login exigirá criação/restauração de uma conta de homologação."
else
  green "Usuários existentes na base local: $USER_COUNT"
fi

section "Serviços locais"
docker compose ps
printf "\nAPI:       %s\n" "$API_URL"
printf "Docs API:  %s/docs\n" "$API_URL"
printf "Frontend:  http://localhost:%s\n" "$FRONTEND_PORT"

section "Frontend"
green "Iniciando $PROJECT_NAME em http://localhost:$FRONTEND_PORT"
yellow "Para encerrar o frontend, pressione Ctrl+C. DB e API permanecerão ativos para acelerar os próximos testes."
printf "\n"

exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
