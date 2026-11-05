# Teste real controlado na VPS de produção — Diagnóstico Rural

**Data:** 05/11/2026. Esta rotina usa a infraestrutura real, o SICAR oficial e
o Google Earth Engine comercial do projeto `amazonika-geoespacial`,
mas **não substitui a API/web de produção e não habilita o endpoint público**.
É a primeira etapa antes de um deploy público, não equivalente a testar a UI.

## Pré-requisitos já confirmados

- `/root/amazonika-secrets/gee-service-account.json`: chave privada da
  conta de serviço, modo 0600.
- `amazonika-gee-homolog`: imagem Python com Earth Engine/ReportLab.
- O CAR real da homologação: 1.115,1093 ha, 63 vértices, consulta SICAR OK.
- 30 testes anteriores aprovados e redução MapBiomas de 1.115,0770 ha.
- O comando de nova execução pode gerar cobrança. Executar **apenas uma vez**.

## Passo 1 — atualizar worktree e testar offline

```bash
cd /tmp/amazonika-rural-homolog
git fetch origin
git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104

docker run --rm --network none \
  -v "$PWD/backend:/app:ro" -v "$PWD/scripts:/scripts:ro" \
  -w /app --entrypoint python amazonika-api-testes \
  -m pytest -p no:cacheprovider \
  tests/test_rural_official_car.py \
  tests/test_rural_mapbiomas.py \
  tests/test_gee_real_property_probe.py -v

npm run build
```

Não iniciar o canário se algum teste falhar.

## Passo 2 — autorizar UMA execução no ambiente de produção

Em uma sessão root da VPS, sem registrar a senha/chave nos logs:

```bash
cd /tmp/amazonika-rural-homolog
read -r -p "Código CAR para o teste único: " CAR_TESTE
test -n "$CAR_TESTE" || { echo "CAR vazio"; exit 1; }
GEE_EMAIL=$(python3 -c 'import json;print(json.load(open("/root/amazonika-secrets/gee-service-account.json"))["client_email"])')
install -d -m 700 /root/amazonika-canary-reports
test ! -e /root/amazonika-canary-reports/amazonika_mapbiomas_canary_2025.pdf || { echo "Canário já executado"; exit 1; }
```

A execução é isolada em contêiner efêmero. O resultado ficará em
`/root/amazonika-canary-reports`, que **não** é pasta pública. A API
atual continuará atendendo no localhost:18000 e a web em 13000.

```bash
docker run --rm --network bridge \
  --memory=1536m --cpus=1 \
  --security-opt no-new-privileges:true \
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
  --entrypoint python amazonika-gee-homolog \
  /scripts/run_rural_production_canary.py
```

**Resultado esperado**: `CANARY_PRODUCAO_OK`, uma geometria de cerca
de 1115 ha, aproximadamente 1115 ha classificados e 6 classes, além do PDF.

## Passo 3 — conferir arquivo e contêineres existentes

```bash
file /root/amazonika-canary-reports/amazonika_mapbiomas_canary_2025.pdf
ls -lh /root/amazonika-canary-reports/
curl -fsS http://127.0.0.1:18000/ready
docker compose --env-file /opt/amazonika-geoespacial/.env.production \
  -f /opt/amazonika-geoespacial/docker-compose.production.yml ps
```

O PDF é preliminar, sem certificação e sem mapa temático raster;
a validação visual precisa ser feita antes de qualquer emissão para clientes.

**Rollback:** não houve serviço modificado. Remover apenas o PDF privado
se não for necessário guardar o comprovante de homologação:
`rm -f /root/amazonika-canary-reports/amazonika_mapbiomas_canary_2025.pdf`.

## Liberação da interface em etapa separada

Os endpoints públicos `/mapbiomas/preview` e `/mapbiomas/preview-pdf`
são bloqueados por padrão por `GEE_BROWSER_PREVIEW_ENABLED=false`,
inclusive com credenciais e `GEE_ENABLED=true`. Antes de mudar isso,
implementar limitação transacional de consumo por usuário, controle de
concorrência, quotas e auditoria. Nunca ativar o serviço cobrable
irrestritamente apenas porque o canário foi aprovado.
