# Amazônika Geoespacial

MVP web para catalogar bases territoriais, importar dados vetoriais, sincronizar WFS oficiais e executar análises de sobreposição em PostGIS.

## Componentes

- painel web React/Vinext com OpenLayers;
- desenho de ponto e polígono e importação de KML/GeoJSON;
- API FastAPI documentada em `/docs`;
- PostgreSQL 16 com PostGIS;
- importação versionada de GeoPackage;
- sincronização WFS com histórico de versões;
- sincronização paginada de serviços ArcGIS FeatureServer;
- painel de gestão das fontes oficiais, com situação, feições, configuração do serviço e atualização manual de contingência;
- exibição das feições oficiais por extensão visível do mapa (BBOX);
- identificação das feições no mapa com painel completo de atributos e escolha entre feições sobrepostas;
- gerenciador de camadas para ativar ou desativar fontes no mapa, na identificação e na análise;
- módulo SIGEF com carga mensal de GeoPackage, histórico e reativação de versões;
- análise por camadas ativas, com área, percentual, feições atingidas e distância mais próxima.

## Execução local

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m app.seed
npm install
npm run dev -- --host 0.0.0.0
```

Abra o endereço exibido pelo Vite. A API fica em `http://localhost:8000` e sua documentação em `http://localhost:8000/docs`.

Para acessar o painel por outro equipamento na mesma rede, defina no `.env`:

```env
NEXT_PUBLIC_API_URL=http://IP_DO_MAC:8000/api/v1
CORS_ORIGINS=http://localhost:3000,http://IP_DO_MAC:3000
```

## Primeira sincronização oficial

O catálogo inicial já contém a configuração do WFS de Unidades de Conservação Federais do ICMBio. Depois de executar o seed:

```bash
docker compose exec api python -m app.sync_source icmbio-ucs
```

O comando cria uma nova versão, importa as feições em SIRGAS 2000 (EPSG:4674) e só a marca como atual depois da carga completa.

O menu **Fontes de dados** também permite executar as sincronizações pelo painel. As integrações configuradas nesta etapa são:

- Unidades de conservação federais — ICMBio/WFS;
- Áreas embargadas — IBAMA/CENIMA via PAMGIA FeatureServer;
- Oito temas do Acervo Fundiário do INCRA — WMS público por UF.

As respostas ArcGIS são paginadas automaticamente em blocos de 2.000 registros. Para atualizar por terminal:

```bash
docker compose exec api python -m app.sync_source ibama-embargos
docker compose exec api python -m app.configure_incra_wms
```

### Contingência de cada fonte

Use o ícone de engrenagem no cartão da fonte para alterar o tipo de serviço, o endereço WFS/FeatureServer, a camada e a frequência. No mesmo painel é possível importar manualmente uma cópia em GeoPackage, KML, GeoJSON ou Shapefile compactado em ZIP. A versão anterior só deixa de ser ativa depois que a nova carga for validada e concluída.

No mapa, **Gerenciar todas as fontes** controla quais camadas são exibidas e participam da identificação e da análise. Quando o clique atingir mais de uma feição, o sistema apresenta as opções antes de abrir os atributos completos.

### Fontes do INCRA por UF

O login gov.br é necessário apenas quando o portal oficial exigir autenticação para mostrar ou copiar os endereços. Depois de conhecida a URL, o WMS do i3Geo é consultado sem autenticação. O backend atua como proxy restrito ao domínio `acervofundiario.incra.gov.br`, evitando conteúdo misto no navegador e mantendo a exceção legada isolada do restante do sistema.

O seletor **UF das camadas INCRA** monta automaticamente os oito temas oficiais para qualquer uma das 27 UFs. Apenas a UF escolhida é requisitada. O WMS serve para visualização atual; identificação, cálculos espaciais e relatórios usam a cópia vetorial importada e versionada.

Na configuração de cada fonte, o botão **Testar conexão WMS do Amapá** executa uma consulta `GetCapabilities` em WMS 1.1.1 e confirma se a camada esperada foi publicada. URLs específicas fornecidas pelo INCRA podem ser armazenadas por UF e prevalecem sobre o endereço calculado automaticamente.

Uma base vetorial sem carga ou com data de referência superior a 15 dias recebe indicador vermelho. Shapefiles compactados em ZIP são extraídos e validados pelo sistema; o pacote deve conter ao menos `.shp`, `.dbf` e `.shx`. Se houver vários Shapefiles no mesmo ZIP, informe o nome da camada interna.

## Atualização mensal do SIGEF interno

Abra **Módulo SIGEF** no menu lateral, informe a data de referência e selecione o `.gpkg`. A versão anterior permanece armazenada e deixa de ser a versão corrente somente após uma importação bem-sucedida. O histórico permite reativar uma carga anterior sem excluir as demais.

## Verificação

```bash
docker compose ps
curl http://localhost:8000/health
npm run build
```

Não armazene tokens, certificados digitais ou credenciais do gov.br no repositório. A estratégia atual usa apenas serviços públicos e cargas internas autorizadas.
