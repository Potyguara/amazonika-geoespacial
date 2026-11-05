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

1. Habilitar previamente o projeto do Google Cloud e credenciar o projeto para Earth Engine conforme as regras atuais do Google. Acesso não comercial gratuito não deve ser presumido válido para um produto comercial.
2. Criar uma conta de serviço exclusiva com as permissões mínimas de processamento em Earth Engine, conforme documentação Google.
3. Guardar o JSON da credencial **fora do repositório e fora do diretório público**, sem incluir no Git, backups compartilhados ou logs. Permissões restritas de leitura.
4. Montar o arquivo no contêiner API como volume **somente leitura**. Exemplo de caminho interno: `/run/secrets/gee-service-account.json`.
5. No ambiente do contêiner API, definir:
   - `GEE_PROJECT_ID=<id-do-projeto>`
   - `GEE_SERVICE_ACCOUNT_EMAIL=<conta-de-servico>@<projeto>.iam.gserviceaccount.com`
   - `GEE_SERVICE_ACCOUNT_KEY_FILE=/run/secrets/gee-service-account.json`
6. Instalar as dependências do `backend/requirements.txt` no contêiner da branch.
7. Consultar `GET /api/v1/rural-diagnostics/mapbiomas/status` usando sessão autenticada.
8. Testar imóvel pequeno e o ano 2025 antes de expandir a operação.

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
