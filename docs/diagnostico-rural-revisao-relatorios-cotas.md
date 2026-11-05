# Diagnóstico Rural — revisão do produto em 05/11/2026

## Contexto e evidências

No navegador da homologação em `127.0.0.1:13002`, o usuário conseguiu
localizar por coordenada `0,5136 / -51,1027` um registro SIGEF
`AMCEL - AMCEL_A_P1` de aproximadamente 130.140,4981 ha. A consulta pelo
código CAR apresentou "Failed to fetch" (sem corpo/status HTTP visível).
Em uma tentativa, MapBiomas sinalizou corretamente GEE desabilitado.
Houve prévia territorial com 0 feições e PDF com 0/0 bases efetivamente
consultadas: **inconclusivo**, jamais resultado negativo de interferência.

Fontes de referência enviadas pelo usuário:
- `RELATORIO_TERRITORIAL_AG-2026-79E8A434.pdf` — três páginas, relatório
  territorial com legenda, mapa de contexto, tabela de bases, resultado
  inconclusivo e verificação.
- `Farm-Scan_Santana_04-11-2026(1).pdf` — 46 páginas, relatório externo de
  referência de apresentação: capa satelital, identificação do CAR,
  sumário, fiscalização, PRODES, alertas antes/depois, sobreposições,
  queimadas, uso do solo, relevo, solo, clima, hidrografia e metodologia.

As informações e os números do Farm Scan são APENAS exemplos de outro
imóvel, não resultados de análises executadas pela Amazonika. Não
reproduzir sua marca/identidade nem copiar material gráfico protegido.

## Separação obrigatória por tipo

A entrada/cadastro do imóvel é compartilhada (coordenadas, CAR oficial
SICAR, SIGEF e importação validada de perímetro). Após a seleção de um
imóvel, cada análise é independente:

1. **SOBREPOSIÇÕES TERRITORIAIS** — polígonos UCs, Terras Indígenas,
   quilombos, assentamentos, SIGEF/SNCI, ANM, embargos quando apropriado
   à natureza da fonte. Uma linha por fonte com estado `analisada_com_
   interferencia`, `analisada_sem_interferencia`, `falha`,
   `indisponivel`, `nao_executada`. Nunca misturar as contagens.
2. **MONITORAMENTO AMBIENTAL** — PRODES/DETER, queimadas, alertas
   georreferenciados. Total de ocorrências, período, fonte e área de
   interseção deduplicada; imagens antes/depois somente quando houver
   imagens autorizadas reais com datas e atribuição.
3. **FISCALIZAÇÃO AMBIENTAL** — autos e embargos IBAMA/ICMBio, registro,
   processo, situação, distância e área de interseção. Não inferir
   responsabilidade do detentor do imóvel sem prova administrativa.
4. **USO E COBERTURA DO SOLO** — MapBiomas por ano/coleção, mapa temático
   raster recortado ao imóvel, classes da legenda oficial, área em ha,
   percentual da área classificada, resolução, divergência entre área
   geométrica e área classificada, e advertência metodológica.
5. **CARACTERIZAÇÃO FÍSICA** — hipsometria, declividade, hidrografia,
   solo e aptidão, somente quando fontes/algoritmos auditáveis estiverem
   prontos.
6. **CLIMA E CONTEXTO REGIONAL** — indicadores regionais com série e
   cobertura temporal documentadas; jamais apresentar projeções
   especulativas como medição do imóvel.

Cada relatório com `report_type` próprio, `source_status_json`,
geometria identificada, unidade, fonte, versão, UTC, metodologia,
limitações, hash/código de rastreio e PDF individual.

**Consolidado** opcional junta apenas seções previamente executadas e
pode resultar em quantidade variável de páginas. Se uma fonte não foi
consultada, deve aparecer como "não executada", e não "sem ocorrência".

## Layout cartográfico e PDF

- Capa distintiva Amazonika: logomarca, nome do imóvel, código CAR
  completo quando presente, município/UF (somente se confirmado),
  área e identificação de consulta; imagem de fundo com licença e fonte.
- Página 2: identificação da geometria, status de cada tema, sumário
  navegado e limitações; opcional mini mapa de localização.
- Cada tema: título, mapa amplo (preferência altura >= 85 mm em A4),
  legenda interpretável com ID da classe e cores corretas, barra de
  escala construída no SRC/escala da carta, seta do norte, fonte, data
  da análise, resolução e tabela quantitativa.
- Página de uso do solo: mapa categórico, histograma em ha e tabela
  área/percentual/classe; classe sem pixels não deve ser inventada.
- Relatório de sobreposição: sem uso do solo ou gráficos de clima,
  a menos que o usuário peça explicitamente um relatório consolidado.
- Preferir mapas projetados cartograficamente (SRC métrico adequado)
  para escala; nunca imagem esticada, grade atrás da legenda ou título
  órfão. Paginação sem páginas em branco; blocos de relatório com
  `KeepTogether`, `PageBreak` condicionais e tamanho de fonte mínimo.
- Rastreabilidade: página final compacta com código e URL de verificação
  real apenas se estiver implantada. Não sugerir QR público funcional
  para relatório provisório sem endpoint correspondente.

## Consulta CAR — diagnóstico antes da correção

A API usa `GET /api/v1/rural-diagnostics/official-car/lookup?car_code=...`
e filtra o WFS oficial `sicar:sicar_imoveis_{uf}` por igualdade exata
`cod_imovel`. O print "Failed to fetch" **não identifica** se falhou
o `fetch` de navegador (CORS/timeout/túnel), o proxy, ou o SICAR. Coletar:
- No Chrome DevTools > Network > request exata: método, caminho,
  status e duração (sem exportar cookies).
- Na VPS, fazer `curl` local à API com cookie de teste e timeout,
  obtendo status HTTP e mensagem sanitizada. Não registrar senha.
- Checar `docker logs` da API de homologação nesse período, apenas
  mensagens relevantes e sem credenciais.
- Classificar resultados: 200 FOUND, 200 NOT_FOUND, 422 código
  malformado, 503 SICAR indisponível, timeout/Failed to fetch de
  comunicação navegador-API. Só depois ajustar API e interface;
  jamais ocultar indisponibilidade com "não encontrado".
- Para CAR com geometria grande, processar por **tiles/blocos** com
  cortes espacialmente conservadores e união/deduplicação, mantendo
  limites de consumo. Não contornar limite financeiro automaticamente.

## Orçamento Earth Engine

Separar orçamento do Earth Engine dos limites de tiles Google Maps e Mapbox:

- Registro `rural_gee_budget`: habilitado NÃO por padrão; limite
  diário de 1 a 5 tentativas administrativas, nunca maior do que
  hard cap do piloto de 5. Flags `GEE_ENABLED` e
  `GEE_INTERNAL_PILOT_ENABLED` permanecem obrigatórias.
- Auditoria `rural_mapbiomas_pilot_runs` conta reservas concluídas
  e falhas. Contagem é UTC e débito da tentativa ocorre antes da
  primeira chamada paga; sem retentativas automáticas da aplicação.
- Painel administrativo: botão habilitar/desabilitar, limite diário,
  usado/restante hoje, eventos `RESERVED/COMPLETED/FAILED`,
  data UTC; alerta 80% e bloqueio 100%.
- **Separar EECU e cobrança reais**: não inferir custo em R$ pelo
  número de solicitações. Google Cloud Monitoring e Billing são
  as fontes de métricas reais de EECU, uso por projeto e custo.
  O painel deve distinguir claramente `cota interna` vs.
  `consumo Google`; integração Google deve ter acesso
  mínimo e limites no projeto Cloud.
- Fluxos não pilotados de MapBiomas (preview/preview-PDF) não podem ser
  ativados sem reserva equivalente de orçamento; `GEE_BROWSER_PREVIEW_ENABLED`
  deve continuar false até esta proteção existir.

## Critérios de aceite

1. Em homologação, autenticação admin/analista e limitação de acesso
   por papel testadas pelo navegador.
2. Consulta por CAR com resposta 200 e feição oficial verificável,
   além de 404/ausência/503/timeout de teste com mensagens claras.
3. PDFs independentes por tema e um consolidado opcional; nenhum PDF
   territorial relata 0 interferências sem bases consultadas.
4. Relatório MapBiomas com mapa real, legenda de códigos, tabela
   quantificada, escala cartográfica, metodologias e paginação.
5. Orçamento GEE default off, GET/PUT somente admin e limitado 1–5;
   429 quando exceder, bloqueio antes de qualquer chamada externa.
6. Testes backend, frontend e testes E2E isolados; não alterar
   produção 18000/13000 nem homologação cartográfica 18001/13001
   até aprovação expressa.

## Status em 05/11/2026

**Implementado em branch, ainda sem testes/deploy dessa revisão**:
orçamento interno da API GEE com proteção adicional e snapshot
administrativo. **Pendente**: frontend do orçamento, tipagem e
reorganização dos relatórios, investigação da consulta CAR real,
geometria em blocos e acabamento do PDF segundo referência.
