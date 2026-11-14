# GEO-77: ODS SIGEF multiparcelas e assistente de compatibilização

Referência visual: telas da planilha SIGEF do Métrica TOPO 2026 (3ª edição / Portaria 69 / Amazônia Legal), enviadas em 14/11/2026.

## Objetivo e limites
Gerar **ODS a partir do modelo oficial SIGEF sem alterar sua estrutura**, permitindo múltiplos municípios, parcelas, encravadas e limites confrontantes; produzir Planta e Memorial a partir da mesma versão de geometria confirmada pelo responsável técnico.

A aplicação não afirma que houve validação oficial INCRA. A verificação definitiva ocorre no SIGEF, inclusive confronto com coordenadas existentes e parcelas certificadas. Referências: https://sigef.incra.gov.br/documentos/manual/ e https://sigef.incra.gov.br/sobre/faq/.

## Matriz de situações
| Condição | Entrada | Regras do fluxo |
|---|---|---|
| Imóvel registrado | CNS, matrícula/transcrição, situação | Solicitar documentos e conferir campos obrigatórios |
| Área titulada não registrada | Título e identificação | Não fabricar CNS/matrícula |
| Área não titulada | Identificação e modalidade correspondente | Somente dados efetivamente conhecidos |
| Vários municípios | Nomes/códigos e polígonos municipais IBGE | Um imóvel poderá conter municípios distintos |
| Múltiplas parcelas | Identificação e perímetro separados | Uma aba por perímetro, sem sobreposição interna |
| Área encravada | Perímetro externo + interno | Mesmo número de parcela, lado correspondente |
| Limite compartilhado | Vértices e tipo de limite de cada segmento | Verificar identidade dos vértices comuns |
| SIGEF vizinho certificado | Parcela e metadados oficiais | Conferir compatibilidade com vértices já certificados |
| Fonte vizinha não certificada | Data, instituição, referência | Aviso de caráter informativo |
| Divergência de área | Área geodésica, projeção, método cartográfico | Comparar, não substituir automaticamente |
| Precisão horizontal/vertical | Sigma calculado e natureza da altitude | Não interpretar zero ou campo vazio como medida válida |

## Sobreposição e ajuste proposto
1. Consultar somente fontes com geometria e identificação rastreável.
2. Calcular interseção, área e confrontantes; distinguir contato de fronteira de sobreposição superficial.
3. Mostrar cada conflito, fonte, referência, geometria e data.
4. Calcular pontos de referência e deslocamentos geodésicos; NÃO mudar automaticamente coordenadas.
5. Habilitar proposta de revisão apenas sob ação explícita, preservar origem e versão, registrar quem aprovou e por quê.
6. A aprovação da sugestão não comprova compatibilidade técnica, correção do levantamento, certificação nem ausência de conflito fundiário.
7. Submeter revisões a nova validação integral; se exceder critérios técnicos, exigir reprocessamento/relevantamento.

## Contratos implementados
- `POST /api/v1/technical-pieces/topcon/perimeter-review` — revisa vértices Topcon.
- `POST /api/v1/technical-pieces/sigef/parcels-review` — entrada: `identification`, `parcels` e `neighbors`; saída: pendências, áreas, conflitos e distâncias **meramente referenciais**. Preserva geometrias.
- Nenhum desses endpoints gera ODS certificável ou altera automaticamente o perímetro.

## Etapas seguintes de código
- Desenvolver editor de identificação e perimetros adicionais na interface.
- Mapear códigos e valores admitidos do modelo oficial para cada situação.
- Construir exportador ODS multiabas, preservando o modelo oficial.
- Implementar read-back do ODS gerado e regressões com desmembramentos, áreas encravadas e confrontantes.
- Implementar validador vetorial SIGEF/SNCI baseado em fonte oficial confiável e data de atualização registrada.
- Integrar Planta/Memorial à geometria confirmada; testar convergência dos dados e versões.
- Testar fluxo real na VPS e executar pré-validação oficial no LibreOffice com extensão SIGEF quando aplicável.
