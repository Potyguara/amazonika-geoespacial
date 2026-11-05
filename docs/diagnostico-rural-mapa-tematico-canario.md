# Homologação do mapa temático real — MapBiomas 2025 (Coleção 11)

## O que esta etapa faz

- Reconsulta somente o perímetro CAR pela fonte oficial SICAR.
- Reusa os totais de classe **já homologados em 05/11/2026** sobre o
  mesmo CAR, sem repetir `reduceRegion`. A comparação de área geométrica
  de até 0,1 ha é uma salvaguarda preliminar, mas **não prova a identidade
  integral da geometria**; antes de emissão oficial é necessário versionar e
  comparar o hash do perímetro e a data da base.
- Realiza **uma requisição adicional cobrável ao Earth Engine** para gerar
  apenas uma miniatura raster de pixels MapBiomas de 2025, mascarada pelo
  polígono CAR. Imagem máxima: 640 px por lado, 350 mil pixels e 3 MB,
  limitada a imóvel de 1.500 ha.
- Gera um PDF preliminar privado com dados e tabela, gráficos e **mapa
  temático com pixels reais**, legenda, seta norte e escala gráfica
  **aproximada**. Não é carta georreferenciada, planta de levantamento nem
  laudo de regularidade ambiental.
- Não altera a API, banco, frontend ou relatório antigo.
- O PNG é usado somente em memória para compor o PDF, sem exportação de
  GeoTIFF ou persistência de raster.

## Testes offline obrigatórios

```bash
cd /tmp/amazonika-rural-homolog
git fetch origin
git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104
docker run --rm --network none \
  -v "$PWD/backend:/app:ro" \
  -v "$PWD/scripts:/scripts:ro" \
  -w /app --entrypoint python amazonika-api-testes \
  -m pytest -p no:cacheprovider \
  tests/test_rural_mapbiomas_cartography.py \
  tests/test_rural_mapbiomas.py \
  tests/test_rural_official_car.py \
  tests/test_gee_real_property_probe.py -v
```

Só executar a consulta remota se todos os testes passarem.

## Execução controlada na VPS

```bash
cd /tmp/amazonika-rural-homolog
read -r -p "CAR para mapa temático: " CAR_TESTE
GEE_EMAIL=$(python3 -c 'import json;print(json.load(open("/root/amazonika-secrets/gee-service-account.json"))["client_email"])')
install -d -m 700 /root/amazonika-canary-reports
test ! -e /root/amazonika-canary-reports/amazonika_mapbiomas_mapa_canary_2025.pdf || { echo "Mapa já foi gerado, evitar cobrança repetida"; exit 1; }
docker run --rm --network bridge \
  --memory=1536m --cpus=1 --security-opt no-new-privileges:true \
  --mount type=bind,source=/root/amazonika-secrets/gee-service-account.json,target=/run/secrets/gee-service-account.json,readonly \
  --mount type=bind,source="$PWD/backend",target=/app,readonly \
  --mount type=bind,source="$PWD/scripts",target=/scripts,readonly \
  --mount type=bind,source=/root/amazonika-canary-reports,target=/output \
  -e PYTHONPATH=/app:/scripts \
  -e CAR_TESTE="$CAR_TESTE" \
  -e GEE_ENABLED=true \
  -e GEE_BROWSER_PREVIEW_ENABLED=false \
  -e GEE_PROJECT_ID=amazonika-geoespacial \
  -e GEE_SERVICE_ACCOUNT_EMAIL="$GEE_EMAIL" \
  -e GEE_SERVICE_ACCOUNT_KEY_FILE=/run/secrets/gee-service-account.json \
  -e GEE_ALLOW_REAL_PROPERTY_TEST=yes \
  -e GEE_ALLOW_LARGE_PROPERTY_TEST=yes \
  -e GEE_PRODUCTION_CANARY=yes \
  -e GEE_MAP_CANARY=yes \
  --entrypoint python amazonika-gee-homolog \
  /scripts/run_rural_mapbiomas_map_canary.py
```

## Conferência e próxima decisão

```bash
file /root/amazonika-canary-reports/amazonika_mapbiomas_mapa_canary_2025.pdf
ls -lh /root/amazonika-canary-reports/amazonika_mapbiomas_mapa_canary_2025.pdf
curl -fsS http://127.0.0.1:18000/ready
```

Transfira o PDF com scp e revise a figura, sua correspondência com o
perímetro CAR, cores e classes. O arquivo deve conter ao menos duas páginas.
**Não** confundir escala aproximada com escala cartográfica rigorosa;
não emitir parecer ou planta com base neste canário.

**Não habilitar** `GEE_BROWSER_PREVIEW_ENABLED=true` na produção. Continua
faltando auditoria, controle de concorrência, limites por usuário, revisão
cartográfica, armazenamento autorizado da proveniência e validação E2E web.
