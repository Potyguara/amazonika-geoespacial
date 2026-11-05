# Diagnóstico Rural — teste HTTP e PostgreSQL **descartável**

## Objetivo
Comprovar a integração real entre a rota HTTP autenticada, o mutex advisory
do PostgreSQL, reserva da quota e auditoria persistida. O SICAR e Earth Engine
serão **simulados**, sem consultas ou cobrança Google. Não afeta o banco,
volumes nem portas da produção.

**Atenção:** todos os comandos são executados em /tmp/amazonika-rural-homolog.
Nunca executar este teste apontando para `db`/PostgreSQL de produção.
A suíte recusa DATABASE_URL se não contiver exatamente
`pilot-postgres` e `amazonika_pilot_test`.

## 1. Atualização e testes secos

```bash
cd /tmp/amazonika-rural-homolog
git fetch origin
git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104

docker run --rm --network none -v "$PWD/backend:/app:ro" -w /app \
  --entrypoint python amazonika-api-testes \
  -m pytest -p no:cacheprovider \
  tests/test_rural_mapbiomas_pilot.py tests/test_rural_mapbiomas.py \
  tests/test_rural_mapbiomas_cartography.py -v
npm run build
```

## 2. Preparar PostgreSQL independente e efêmero

```bash
docker network create amazonika-pilot-test-net
docker run -d --name amazonika-pilot-postgres-test \
  --network amazonika-pilot-test-net --network-alias pilot-postgres \
  --memory=512m --cpus=1 \
  -e POSTGRES_DB=amazonika_pilot_test \
  -e POSTGRES_USER=pilot \
  -e POSTGRES_PASSWORD=pilot_password_isolated_only \
  --tmpfs /var/lib/postgresql/data:rw,size=256m \
  postgis/postgis:16-3.4

docker exec amazonika-pilot-postgres-test \
  pg_isready -U pilot -d amazonika_pilot_test
```

Se o `pg_isready` indicar que o banco ainda não está pronto,
execute novamente **somente** o comando `pg_isready` antes de prosseguir.

## 3. Construir imagem de testes HTTP separada

A imagem `amazonika-api-testes` não contém `httpx`, necessário ao
`fastapi.testclient.TestClient`. Não modificar a imagem existente nem
instalar `httpx` na API/web em execução. Criar imagem **independente**
somente para testes, com `httpx==0.28.1` fixado:

```bash
cd /tmp/amazonika-rural-homolog
docker build --network bridge \
  -f backend/Dockerfile.pilot-http-test \
  -t amazonika-api-pilot-http-test backend

docker run --rm --network none \
  --entrypoint python amazonika-api-pilot-http-test \
  -c "import httpx, pytest, sqlalchemy, psycopg; print('DEPENDENCIAS_HTTP_OK', httpx.__version__)"
```

Se o build falhar por indisponibilidade de PyPI, pare e informe a saída;
não instale dependências diretamente na VPS nem na produção.

## 3.1. Teste HTTP integrado na rede isolada

```bash
docker run --rm --network amazonika-pilot-test-net \
  --memory=768m --cpus=1 \
  -e DATABASE_URL=postgresql+psycopg://pilot:pilot_password_isolated_only@pilot-postgres:5432/amazonika_pilot_test \
  -e AMAZONIKA_TEST_PG_INTEGRATION=yes \
  -e GEE_ENABLED=false \
  -e GEE_INTERNAL_PILOT_ENABLED=false \
  -e GEE_BROWSER_PREVIEW_ENABLED=false \
  -v "$PWD/backend:/app:ro" -w /app \
  --entrypoint python amazonika-api-pilot-http-test \
  -m pytest -p no:cacheprovider tests/test_rural_pilot_postgres_http.py -v
```

O teste seleciona a rota HTTP autenticada com `ADMINISTRADOR` e testa
`ANALISTA=403`, primeira execução `200/application/pdf`,
segunda no mesmo dia `429`; registro persistente `COMPLETED`
de apenas uma tentativa. Todos os serviços externos são simulados.

## 4. Limpeza

```bash
docker rm -f amazonika-pilot-postgres-test
docker network rm amazonika-pilot-test-net
docker image rm amazonika-api-pilot-http-test
curl -fsS http://127.0.0.1:18000/ready
```

Nenhum contêiner, serviço, porta ou volume existente da produção é alterado.
Se houver erro durante qualquer fase, executar a limpeza e devolver logs,
sem ativar GEE interno nem fazer deploy.
