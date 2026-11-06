# Padrão visual obrigatório — relatório consolidado completo (revisão do usuário, 06/11/2026)

## Diagnóstico da discrepância

**A prévia sintética de 3 páginas foi rejeitada.** O problema não é cor nem tipografia: ela é uma listagem de dados, enquanto a referência `Modelo de Relatorio Consolidado.pdf` (46 páginas, entregue pelo usuário) é um **relatório cartográfico ilustrado**, com hierarquia visual forte, mapas georreferenciados, imagem de satélite, indicadores, quadros temáticos e fichas espaciais.

A capacidade de gerar um PDF em ReportLab e o teste PostGIS de status não significam aprovação visual. Separar claramente **validação de infraestrutura** de **validação de relatório**.

## Referência por página / critério visual

| Referência | Componente novo | Critério de aceite |
|---|---|---|
| 1 | Capa ambiental integral | Imagem satélite licenciada do perímetro real, overlay da geometria, título, dados identificados, escala/atribuição, propriedades, data. Não usar imagem genérica nem mapa inventado. |
| 2 | Resumo técnico do imóvel | Duas colunas de métricas CAR/RL/APP/uso/área com unidades e fonte; quando indisponível, indicar não consultado. |
| 3 | Sumário de conformidade | Linhas compactas por domínio, badges textuais coerentes com consultas REALMENTE executadas, sem 0 falso. |
| 4–9 | Fiscalização e embargos | Fichas de ocorrências com número/processo/área/ano, recorte de mapa da interseção, status individual. |
| 10–17 | Alertas e cenas multitemporais | Visuais antes/depois com datas de captura e licença, somente imagens reais com fonte. |
| 18–21 | Sobreposições | Um tema por mapa/ficha, geometrias projetadas, legenda, áreas, fonte, versão, alertas. |
| 22–27 | PRODES/DETER | Miniaturas cartográficas por ocorrência + metadados geoespaciais e áreas em ha. |
| 28–29 | Queimadas | Mapa, cronologia anual, gráficos e tabela de áreas. |
| 30–35 | Aptidão, outorgas, IPHAN, florestas, infraestrutura | Mapas ou fichas conforme o tipo de dado, não texto sem visual. |
| 36 | Uso/cobertura MapBiomas | Raster classificado recortado, legenda de classes, quadro áreas/percentuais, ano de referência. |
| 37–42 | Relevo, solos e pastagens | Hipsometria/declividade, pedologia e metodologia de classificação; somente dados oficiais/derivados reproduzíveis. |
| 43–45 | Clima | Gráficos temporais de precipitação/temperatura/veranicos com série e estação/fonte. |
| 46 | Fontes e metodologia | Proveniência de cada mapa/indicador, limitações, versões, data da coleta. |

## Layout editorial

- A4 retrato para páginas analíticas; páginas técnicas de mapa podem ser paisagem (A4/A3) somente quando necessário, mantendo índice e paginação coerentes.
- Área de conteúdo projetada primeiro (imagem/mapa/gráfico), texto ao lado ou abaixo; não preencher páginas com listas `NOT_RUN`.
- Paleta Amazonika original; identidade própria, **não copiar logomarca, código visual exato, textos proprietários ou mapas da empresa do modelo**.
- Capa: fundo cartográfico real, polígono transparente e contorno forte, identificação do imóvel e data.
- Páginas analíticas: cabeçalho discreto, módulo, mapa em 40–60% da área, ficha de indicadores, fonte e data em rodapé; grades e tabelas só quando ajudam.
- Cada mapa: geometria real, CRS e escala métrica consistentes, seta norte, legenda ligada aos atributos efetivos, fontes/datas, bounding box e resolução de impressão.
- Fichas repetíveis de ocorrência com imagens/crop, datas, área e tipo; evitar cortes, títulos órfãos e páginas quase vazias.
- Renderização programática desacoplada dos adapters: `SectionData -> SectionFigure -> ReportPage`. Dois testes distintos: validação dos dados e inspeção visual do PDF renderizado.
- Reservar no PDF áreas *não disponíveis* pontualmente no sumário. Não gerar páginas inteiras vazias para fontes não consultadas.
- PDF gerado somente com evidência real na versão de homologação; amostras sintéticas devem ser marcadas em todas as páginas.

## Mudança de implementação exigida

1. **Não investir no polimento de `render_preliminary_consolidated_pdf` como resultado final**. O arquivo é instrumento técnico de regressão, não design alvo.
2. Criar `report_design_system` (margens, grades, tipografia, indicadores, componentes de ficha, mapas e gráficos) e um novo `full_farm_report_renderer` com seções guiadas por `SectionData`.
3. Construir primeiro um protótipo visual de 5 páginas com dados *claramente sintéticos* (capa cartográfica esquemática quando não houver fonte real, resumo executivo, fiscalização, PRODES, MapBiomas), marcado em todas as páginas como demonstração. **Não inventar satélite**; caso não exista imagem licenciada, exibir área de mapa `Imagem satelital não fornecida` para revisão de grid.
4. Aprovar visualmente o protótipo comparando lado a lado com páginas 1, 3, 23, 36 e 43 do modelo antes de integrar ao banco.
5. Com layout aprovado, conectar imagens licenciadas e camadas reais; registrar origem, datas, ano da imagem e custo/quota. Não acionar GEE sem opt-in e orçamento.
6. Testar pixel-level/render/PDF de páginas, principalmente texto sobre imagem, legibilidade, cards, mapa/legenda e paginação.
7. Só oferecer botão `Relatório Consolidado Completo` depois da integração real dos módulos; oferecer `Prévia técnica` separadamente, quando incompleto.

## Critério de rejeição

- PDF predominantemente texto e tabelas: **rejeitado**, mesmo que testes unitários passem.
- Sem mapa do imóvel na capa: **rejeitado** como relatório final.
- Sem mapas/fichas para módulos com feições: **rejeitado**.
- Inferir ausência de embargos/prodes por erro WFS: **rejeitado**.
- Reproduzir imagens/números da fazenda do modelo: **rejeitado**.
- Publicar uma prévia de 3 páginas como equivalente ao relatório completo de 46 páginas: **rejeitado**.

Status: contrato visual definido, **novo renderer não implementado ainda**. Produção e homologação rural ativas preservadas.
