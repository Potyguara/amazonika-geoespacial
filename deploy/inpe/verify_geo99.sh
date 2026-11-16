#!/usr/bin/env bash
# GEO99: only builds and smoke-tests staging images; never replaces active containers.
set -Eeuo pipefail
cd /opt/amazonika-topcon-stage
test "$(hostname)" = "SIS"
test -z "$(git status --porcelain)"
test -f deploy/inpe/Dockerfile.api-geo99
echo "===== GEO99: TYPESCRIPT ====="
node_modules/.bin/tsc --noEmit --incremental false --pretty false
echo "===== GEO99: TESTES FRONTEND ====="
node --test tests/geo97-ps4-quality.test.cjs tests/geo98-altitude-preview.test.cjs
echo "===== GEO99: SINTAXE PYTHON ====="
python3 -m py_compile \
  backend/app/api/routes/technical_pieces.py \
  backend/app/api/routes/inpe_cbers.py \
  backend/app/services/sigef_ods_working.py \
  backend/app/services/topcon_perimeter_review.py \
  backend/app/services/plant_memorial_v2.py \
  backend/app/services/plant_memorial_v3.py \
  deploy/inpe/cog_tiles.py
echo "===== GEO99: BUILD API ====="
docker build -f deploy/inpe/Dockerfile.api-geo99 \
  --build-arg BASE_API_IMAGE=amazonika-api-inpe:geo98 \
  -t amazonika-api-inpe:geo99 .
echo "===== GEO99: TESTES PYTHON NA IMAGEM ====="
docker run --rm --network none --memory 512m \
  -v "$PWD/backend/tests:/tests:ro" \
  --entrypoint python amazonika-api-inpe:geo99 \
  -m unittest discover -s /tests -p 'test_geo99_*.py' -v
echo "===== GEO99: ROTAS DA API ====="
docker run --rm -i --network none --memory 512m \
  --entrypoint python amazonika-api-inpe:geo99 - <<'PY'
from app.main import app
routes={(r.path, next(iter(r.methods or []), "")) for r in app.routes}
paths={path for path,_ in routes}
for path in (
    "/api/v1/technical-pieces/sigef/modelo-ods",
    "/api/v1/technical-pieces/sigef/rascunho-ods",
    "/api/v1/technical-pieces/sigef/reviewed-ods",
    "/api/v1/inpe-cbers/scenes",
):
    assert path in paths, path
    print("ROTA OK:", path)
PY
echo "===== GEO99: BUILD RENDERIZADOR CBERS ====="
docker build -f deploy/inpe/Dockerfile.cog-tiles \
  -t amazonika-cog-tiles:geo99-multiscene .
echo "===== GEO99: BUILD FRONTEND ====="
docker build -f deploy/topcon/Dockerfile.web-candidate \
  --build-arg BASE_WEB_IMAGE=amazonika-web-candidato:geo44-20261111 \
  --build-arg NEXT_PUBLIC_API_URL=/api/v1 \
  -t amazonika-web:geo99 .
echo "===== GEO99: STATUS DOS AMBIENTES ====="
curl -fsS http://127.0.0.1:13083/ready && echo
curl -fsS http://127.0.0.1:18000/ready && echo
echo "===== GEO99: VALIDACOES E IMAGENS CONCLUIDAS, SEM DEPLOY ====="
