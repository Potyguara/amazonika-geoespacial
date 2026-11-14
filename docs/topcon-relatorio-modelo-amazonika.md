# Modelo de relatório Topcon Tools para Amazonika Geoespacial

## Objetivo
Exportar **um relatório HTML do Topcon Tools** que permita extrair coordenadas, precisão, sessões e qualidade dos vetores GNSS. O ODS SIGEF, planta e memorial dependem também da confirmação cadastral e de perímetro; o relatório de processamento não é, sozinho, a planilha SIGEF.

## Configuração no Topcon Tools
1. Concluir processamento e ajustamento; revisar soluções, vínculos à base e qualidade GNSS.
2. Relatório > Configuração Relatório (F9).
3. Usar **Copiar Relatório como** a partir de INCRA ou criar **Novo Relatório**; nomear **AMAZONIKA - GNSS SIGEF**; não substituir relatórios padrão.
4. Selecionar **HTML** como formato principal (o backend aceita .htm/.html). Uma cópia PDF textual é útil para conferência. Excel, quando necessário, deve ser convertido em .xlsx para a importação atual.
5. No quadro de itens disponíveis, incluir os blocos abaixo. A nomenclatura varia por versão/idioma; abrir **Opções** de cada item para selecionar colunas.

| Ordem | Item desejado | Campos essenciais |
| --- | --- | --- |
| 1 | Resumo do projeto | Nome, data, projeção, zona UTM, hemisfério, datum, geóide, ajustamento |
| 2 | Pontos / Resumo de pontos | Nome original, N, E, elevação informada e também latitude/longitude, sempre com CRS explícito |
| 3 | Pontos ajustados / Qualidade dos pontos ajustados | Desvios-padrão N, E, horizontal e vertical; identificação da base |
| 4 | Observações GPS / GPS Obs Qualidade | Base-rover, distância, dN, dE, dHt, sigma/resíduos, tipo solução, órbita, PDOP, HDOP, VDOP |
| 5 | Ocupações GPS / Sessões | Nome ponto, início, fim, duração, método, intervalo e antena |
| 6 | Pontos de controle | Estação-base, coordenadas e condições de controle |
| 7 | Ajustamento / Fechamentos | Resultados de ajustamento, rejeições e verificações de qualidade |

**Se o software disponibilizar coordenadas UTM e geográficas como conjuntos separados, exportar ambos.** Se não permitir ambos num único bloco, adicionar o mesmo item duas vezes com opções distintas, se permitido pela instalação. Não remover a estação base do relatório: ela deve apenas ser excluída do perímetro.

## Colunas prioritárias do item Pontos
- Nome/identificador do ponto
- Grid Northing (N), Grid Easting (E) e Elevation
- Latitude e Longitude
- Desvio padrão Northing/Easting, Horizontal/Vertical
- Indicação expressa do sistema de coordenadas, zona e hemisfério

**Altitude:** o termo 'Elevação' não comprova altura elipsoidal. Ela só pode preencher o campo h do SIGEF após confirmação da referência vertical e do geóide.

## Restrições do importador atual
A rotina `parse_topcon_report` identifica seções `COORDENADAS UTM`, `COORDENADAS GEOGRÁFICAS`, `DESVIO PADRÃO`, `FATOR DE ESCALA`, `DISTÂNCIA, SOLUÇÃO, ÓRBITA E PDOP` e `DURAÇÃO E INTERVALO`. Ela não interpreta automaticamente todo formato de relatório personalizado do Topcon. **Antes de considerar o modelo definitivo, salvar um HTML real e verificar que esses títulos e tabelas são extraídos corretamente.** Se a configuração gerar cabeçalhos diferentes, ajustar o parser e acrescentar teste com o exemplo (sem dados pessoais).

## Pré-validação já integrada
O painel em Peças Técnicas importa .htm, .html, .xlsx e .pdf textual; lista os pontos e permite selecionar e ordenar vértices. A rota `POST /api/v1/technical-pieces/topcon/perimeter-review` verifica fecho, geometrias, sentido, vértice inicial ao norte e preenchimento técnico explícito.

## Dados que o Topcon não consegue preencher com segurança
- Código de vértice SIGEF e classe M/P/V
- Identificação dos imóveis e confrontantes
- Tipo de limite do segmento e método SIGEF confirmado
- Dados do proprietário/imóvel, CNS, matrícula e RT
- Altura elipsoidal quando o relatório fornece só 'elevação'

## Critério de aceite para gerar ODS/Planta/Memorial
1. HTML real processado e pontos conferidos com as coordenadas originais;
2. Perímetro revisado, ordenado e sem estação base;
3. Datum/época, tipo de altura e precisões confirmados;
4. Código de vértice, método, tipo limite e confrontante preenchidos;
5. ODS gerado por transformação **sem inventar dados**, usando o modelo oficial;
6. Planta e memorial derivados exatamente da mesma geometria aprovada.

Fontes de navegação: manual de referência Topcon Tools, capítulos Report Configuration/Customized Reports; guia de customização Topcon Tools; tutorial Métrica TOPO de modelo personalizado (apenas referência de navegação, não padrão de dados Amazonika).
