# Diagnóstico Territorial Rural — MapBiomas Coleção 11

## Estado

Implementação experimental na branch `feat/diagnostico-rural-coordenada-20261104`.

**Não habilitar em produção até confirmar a autorização do projeto Google Earth Engine, a modalidade de uso (inclusive comercial, quando aplicável), custos/quotas e passar os testes de homologação.** A versão de desenvolvimento fica indisponível com erro explícito até a configuração.

## Fonte

- Instituição: Rede MapBiomas Brasil.
- Produto: uso e cobertura da terra anual 30 m, **Coleção 11**.
- Asset (conforme página oficial MapBiomas):
  `projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3`
- Período: 1985–2025.
- Bandas: `classification_<ano>`.
- Resolução nominal: 30 m.
- Referência institucional: https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/
- Lista oficial de códigos e cores: https://brasil.mapbiomas.org/downloads/codigos-de-legenda/

### Como é calculada a área

`ee.Image.pixelArea().divide(10000)` (hectares) é combinado com a banda categórica de classificação; `ee.Reducer.sum().group(groupField=1)` soma a área de pixels **dentro da geometria selecionada** por código da classe.

É uma estimativa de cobertura por pixels. A área classificada pode diferir da área geométrica calculada por PostGIS em função de resolução, máscara e bordas.

Não rotular códigos desconhecidos com categorias presumidas. Identificá-los numericamente e consultar a legenda oficial da Coleção 11. O sistema não afirma conformidade ambiental.

## Configuração segura da VPS

1. Projeto `amazonika-geoespacial` já foi registrado pelo operador para Earth Engine comercial no plano Limitado (evidenciado na tela de configuração de 05/11/2026). Verificar em **APIs e serviços** que a Earth Engine API está habilitada e em **Faturamento** que existe conta ativa. O plano Limitado é cobrado por consumo, não equivale a serviço gratuito.
2. Criar uma conta de serviço exclusiva, sugerida `amazonika-gee-rural`, com `roles/earthengine.viewer` e `roles/serviceusage.serviceUsageConsumer` no projeto. Não conceder Editor/Owner para as consultas somente leitura. Consultar os requisitos oficiais caso a API informe alguma permissão adicional.
3. Guardar o JSON da credencial **fora do repositório e fora do diretório público**, sem incluir no Git, backups compartilhados ou logs. Permissões restritas de leitura.
4. Montar o arquivo no contêiner API como volume **somente leitura**. Exemplo de caminho interno: `/run/secrets/gee-service-account.json`.
5. No ambiente do contêiner API, definir (apenas no arquivo privado da VPS):
   - `GEE_ENABLED=false` inicialmente; mudar para `true` **somente após homologar**
   - `GEE_PROJECT_ID=amazonika-geoespacial`
   - `GEE_SERVICE_ACCOUNT_EMAIL=<conta-de-servico>@<projeto>.iam.gserviceaccount.com`
   - `GEE_SERVICE_ACCOUNT_KEY_FILE=/run/secrets/gee-service-account.json`
6. Utilizar `docker-compose.gee.optional.yml` apenas como overlay opcional da API quando a chave estiver guardada em caminho absoluto fora do repositório. Configurar `GEE_SERVICE_ACCOUNT_KEY_HOST_PATH=/caminho/absoluto/seguro/chave.json` no `.env.production` privado. Não inserir a chave no Dockerfile.
7. Instalar as dependências do `backend/requirements.txt` no contêiner da branch e executar `python scripts/probe_earth_engine_mapbiomas.py` no contêiner de homologação com a chave montada para verificar somente a autenticação e a existência do asset.
8. Consultar `GET /api/v1/rural-diagnostics/mapbiomas/status` usando sessão autenticada após habilitar `GEE_ENABLED=true` em homologação.
9. Testar imóvel pequeno e o ano 2025 antes de expandir a operação, com orçamentos e alertas em Google Cloud Billing e limite diário de EECU. Os alertas de orçamento normalmente não bloqueiam gastos automaticamente; não tratar orçamento como teto técnico.

**Atenção:** o arquivo não é transferido por API, não é incorporado ao PDF e não deve jamais ser exposto no frontend.

## Endpoints

- `GET /api/v1/rural-diagnostics/mapbiomas/status`: disponibilidade e metadados de coleta (não revela credenciais).
- `POST /api/v1/rural-diagnostics/mapbiomas/preview`: polígono GeoJSON + `year`; permissão `analysis.execute`.
- `POST /api/v1/rural-diagnostics/mapbiomas/preview-pdf`: referência verificada do imóvel + ano; permissão `analysis.export`. Reexecuta o processamento remoto e entrega o PDF preliminar sem armazená-lo na VPS.

## Validação

```bash
cd /tmp/amazonika-rural-homolog
git fetch origin
git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104
docker run --rm --network none -v "$PWD/backend:/app:ro" -w /app --entrypoint python amazonika-api-testes -m pytest -p no:cacheprovider tests/test_rural_mapbiomas.py -v
npm run build
```

O ambiente de testes `amazonika-api-testes` precisa conter as dependências atualizadas para o teste de integração de EE; os testes MapBiomas com mocks não realizam autenticação, rede nem downloads.

**Limites iniciais:** geometria válida com no máximo 25 mil vértices; envelope de até 0,8° por eixo; no máximo 15 milhões de pixels por redução, `bestEffort=False`, para não mudar resolução silenciosamente. Imóveis maiores demandam lote assíncrono ou particionamento.

Nenhuma integração MapBiomas foi ainda homologada com uma conta GEE real. Não prometer valor de cobertura final até o sucesso do teste end-to-end.

## Fonte de preços e IAM (2026)

- https://cloud.google.com/earth-engine/pricing?hl=pt : plano Limitado sem mensalidade fixa de plataforma, com cobrança de processamento utilizado e sem créditos incluídos.
- https://developers.google.com/earth-engine/guides/access_control : papéis `roles/earthengine.viewer` e `roles/serviceusage.serviceUsageConsumer` para uso somente leitura.
- https://developers.google.com/earth-engine/guides/service_account : autenticação por conta de serviço; proteger a chave JSON.

**Atenção**: o registro comercial do projeto não comprova, por si só, que a conta de serviço foi criada, que a API está habilitada ou que os testes passaram.


## Homologação de um imóvel real (não publica o serviço)

Com a chave privada já instalada em `/root/amazonika-secrets/gee-service-account.json` e após conferir alertas de consumo, o operador poderá usar `scripts/probe_mapbiomas_real_property.py` dentro da imagem `amazonika-gee-homolog` criada na worktree. Aceita **um** CAR público ou uma coordenada SIGEF que produza **exatamente uma** parcela; o código CAR e a geometria não são impressos nem armazenados. O programa bloqueia processamento para polígonos com área superior a 100 hectares por padrão (limite configurável, máximo absoluto de 200 hectares).

Exemplo com CAR (substituir pela inscrição real; não incluir código real em logs compartilhados):

```bash
cd /tmp/amazonika-rural-homolog
GEE_EMAIL=$(python3 -c 'import json;print(json.load(open("/root/amazonika-secrets/gee-service-account.json"))["client_email"])')
docker run --rm --memory=1536m --cpus=1 --security-opt no-new-privileges:true \
  --mount type=bind,source=/root/amazonika-secrets/gee-service-account.json,target=/run/secrets/gee-service-account.json,readonly \
  --mount type=bind,source="$PWD/scripts/probe_mapbiomas_real_property.py",target=/tmp/probe_mapbiomas_real_property.py,readonly \
  -e GEE_ENABLED=true \
  -e GEE_PROJECT_ID=amazonika-geoespacial \
  -e GEE_SERVICE_ACCOUNT_EMAIL="$GEE_EMAIL" \
  -e GEE_SERVICE_ACCOUNT_KEY_FILE=/run/secrets/gee-service-account.json \
  -e GEE_ALLOW_REAL_PROPERTY_TEST=yes \
  --entrypoint python amazonika-gee-homolog \
  /tmp/probe_mapbiomas_real_property.py --car-code "INSCRICAO-CAR" --year 2025
```

**Atenção:** se o serviço SICAR não responder, a execução falha sem iniciar a redução. Se o CAR tiver mais de 100 ha, nenhum processamento é executado; selecionar um imóvel menor ou dividir em blocos em implementação futura. O parâmetro `GEE_ENABLED=true` vale **somente para este contêiner descartável de teste**, não habilita a API em produção. O processamento poderá gerar cobrança no plano Limitado.

Teste offline: `tests/test_gee_real_property_probe.py`.


## Homologação adicional: CAR de 1.115,1093 ha

Na VPS, o CAR de teste retornou pelo serviço SICAR oficial uma geometria de
**1.115,1093 ha e 63 vértices**, e os **28 testes de código vigentes passaram**
em 05/11/2026. Esse perímetro não pode ser consultado com a proteção inicial
de 100 ha. A proteção foi ampliada de forma opt-in apenas no script isolado:

- Padrão: máximo 100 ha; até 200 ha com a autorização habitual.
- Acima de 200 ha: **exige também** `GEE_ALLOW_LARGE_PROPERTY_TEST=yes`.
- Teto absoluto de homologação: 1.500 ha.
- Redução remota: um ano, uma consulta, escala fixa de 30 m,
  `maxPixels=30000`, `bestEffort=False`.
- A estimativa de pixels é usada apenas como limite preliminar; 1.115,1093 ha
  equivale aproximadamente a 12.391 pixels de 30 m. A contagem real e o custo
  podem variar conforme projeção e geometria.
- No Docker de teste passar `PYTHONPATH=/app`, pois o script montado em
  `/tmp` importa pacotes de `/app`.
- **Não** configurar `GEE_ALLOW_LARGE_PROPERTY_TEST` nos serviços
  de produção; esta flag serve apenas para execução pontual isolada.
- O processamento é cobrado segundo as condições comerciais do Earth Engine;
  não inferir preço exato do número de pixels sem métricas de EECU.

Exemplo: atualizar a worktree, executar os testes offline e então executar
o script do imóvel real no contêiner descartável (variável `CAR_TESTE`
definida no shell):

```bash
docker run --rm --network bridge --memory=1536m --cpus=1 \
  --security-opt no-new-privileges:true \
  --mount type=bind,source=/root/amazonika-secrets/gee-service-account.json,target=/run/secrets/gee-service-account.json,readonly \
  --mount type=bind,source="$PWD/backend",target=/app,readonly \
  --mount type=bind,source="$PWD/scripts/probe_mapbiomas_real_property.py",target=/tmp/probe_mapbiomas_real_property.py,readonly \
  -e PYTHONPATH=/app \
  -e GEE_ENABLED=true \
  -e GEE_PROJECT_ID=amazonika-geoespacial \
  -e GEE_SERVICE_ACCOUNT_EMAIL="$GEE_EMAIL" \
  -e GEE_SERVICE_ACCOUNT_KEY_FILE=/run/secrets/gee-service-account.json \
  -e GEE_ALLOW_REAL_PROPERTY_TEST=yes \
  -e GEE_ALLOW_LARGE_PROPERTY_TEST=yes \
  --entrypoint python amazonika-gee-homolog \
  /tmp/probe_mapbiomas_real_property.py \
  --car-code "$CAR_TESTE" --year 2025 --max-hectares 1200
```

Importante: o parâmetro `--max-hectares 1200` é suficiente para o imóvel
testado e não permite analisar áreas maiores. Nada é persistido.


## Resultado real da homologação — 05/11/2026

A VPS executou com sucesso a redução remota do MapBiomas Coleção 11, ano
2025, sobre **um perímetro CAR real** recuperado pelo SICAR. Os números abaixo
foram obtidos da saída operacional do contêiner de homologação:

- Área geométrica SICAR: **1.115,1093 ha**, **63 vértices**.
- Área classificada pelo Earth Engine: **1.115,0770 ha**.
- Diferença geométrica/classificada: **0,0323 ha**, sem concluir sua causa
  exata sem inspecionar pixels e máscara.
- Limite configurado no teste: **1.200 ha**, **30.000 pixels**; pixels nominais
  estimados pelo script: **12.391**.
- Sem arquivo raster exportado ou armazenado.
- Testes offline executados antes da redução: **30 aprovados**, build de
  frontend aprovado em execução anterior.

| Código | Classe da legenda oficial | Área classificada (ha) | Percentual |
|---|---|---:|---:|
| 11 | Campo Alagado e Área Pantanosa | 870,7678 | 78,09% |
| 6 | Floresta Alagável | 215,6480 | 19,34% |
| 3 | Formação Florestal | 18,1312 | 1,63% |
| 9 | Silvicultura | 8,0247 | 0,72% |
| 33 | Rio, Lago e Oceano | 1,3431 | 0,12% |
| 21 | Mosaico de Usos | 1,1622 | 0,10% |
| **Total** | | **1.115,0770** | **100%** |

Legenda e códigos verificados na fonte oficial:
https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/

**Limitação fundamental:** classes de uso/cobertura mapeadas por satélite
não equivalem, isoladamente, às categorias jurídicas de APP, Reserva Legal,
área de supressão ou regularidade ambiental. O CAR é autodeclaratório e
não comprova domínio. O relatório deverá distinguir área geométrica
cadastral e área raster classificada, indicando ano, resolução, coleção,
fontes e data da consulta.

A consulta foi bem-sucedida no **contêiner descartável** de homologação,
não na API publicada ao público. Não habilitar processamento comercial
irrestrito antes de implementar quotas, auditoria e limitação de chamadas.
