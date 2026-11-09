#!/usr/bin/env bash
# QA isolado: NÃO publica nem reinicia produção ou homologação.
set -euo pipefail

test "$(hostname)" = "SIS"
test -f backend/app/services/plant_template_engine.py
test -f backend/app/services/plant_memorial_v3.py

echo "===== VERSÃO ====="
git log -1 --oneline

echo "===== SINTAXE BACKEND ====="
python3 -m py_compile \
  backend/app/services/plant_template_engine.py \
  backend/app/services/plant_memorial_v3.py \
  backend/app/api/routes/tools.py

echo "===== BUILD API ISOLADA ====="
docker build -f backend/Dockerfile.production \
  -t amazonika-refino-cartografico-api:qa backend

echo "===== TESTES DO MOTOR ====="
for testfile in \
  test_professional_plant_refinement.py \
  test_professional_plant_engine.py \
  test_plant_layout_templates.py \
  test_technical_import.py
do
  echo "---- $testfile ----"
  docker run --rm --entrypoint python amazonika-refino-cartografico-api:qa \
    -m unittest discover -s tests -p "$testfile" -v
done

echo "===== TYPESCRIPT ====="
npm ci --no-audit --no-fund
./node_modules/.bin/tsc -p tsconfig.ci.json --noEmit

echo "===== BUILD VINEXT ====="
npm run build
rm -f tsconfig.ci.tsbuildinfo

echo "===== BUILD FRONTEND DE HOMOLOGAÇÃO ====="
docker build -f Dockerfile.web.production \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:18020/api/v1 \
  -t amazonika-refino-cartografico-web:qa .

echo "===== IMAGENS PRONTAS PARA HOMOLOGAÇÃO ====="
docker image inspect amazonika-refino-cartografico-api:qa \
  amazonika-refino-cartografico-web:qa \
  --format '{{.RepoTags}} {{.Id}}'

echo "===== PRODUÇÃO NÃO ALTERADA ====="
docker ps --filter name=amazonika-geoespacial \
  --format 'table {{.Names}}\\t{{.Status}}'

git diff --check
echo "QA FINALIZADO. NENHUM CONTÊINER FOI REINICIADO."
