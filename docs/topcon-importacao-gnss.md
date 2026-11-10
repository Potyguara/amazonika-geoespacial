# Amazonika — processamento GNSS Topcon Tools (etapa 1)

**Branch:** `feat/topcon-importacao-prevalidacao-20261109`

## Implementado nesta entrega
- `POST /api/v1/technical-pieces/import-topcon`, autenticado e protegido por
  `analysis.execute`; arquivo até 12 MB; `.htm`, `.html`, `.xlsx`, `.pdf`
  com texto selecionável; resposta apenas em memória, sem persistir dados.
- Conversão da tabela de coordenadas UTM e geográficas de cada ponto,
  desvios-padrão norte/leste/horizontal/vertical, fator de escala,
  linhas-base, PDOP/HDOP/VDOP e sessões, onde existirem.
- Validação cruzada de coordenadas nas zonas brasileiras SIRGAS2000 UTM
  (18–22N, 18–25S), identificando divergência acima de ~1 m.
- Pré-visualização no primeiro passo de Peças Técnicas, com mensagens
  de erro e ressalvas. A base fica separada dos pontos não classificados.

## Regras de segurança de dados
- Jamais converter a palavra "Elevação" em altura elipsoidal sem que o
  modelo vertical/geóide esteja tecnicamente confirmado.
- A estação-base de controle NÃO entra no perímetro do imóvel.
- Os nomes originais dos pontos são preservados; não são alterados
  automaticamente para códigos de vértice SIGEF.
- Um relatório de processamento **não** é evidência suficiente para
  determinar a sequência da divisa, confrontantes ou tipo de limite.
- Conter a execução aos documentos de processamento com quantidade e
  tamanho limitados, sem requisições externas ou interpretação de macros.

## Aceite de homologação
1. Rodar `test_topcon_import.py` (coordenadas reais do relatório).
2. Executar o QA completo (backend, tsc, build).
3. Carregar o PDF `RELATORIO DE PROCESSAMENTO - TOPCON TOOLS.pdf`.
4. Verificar **cinco** pontos: 0304, 0305, 0306, 0307 e Base.
5. Confirmar UTM 22N, datum SIRGAS, sigma, base como controle.
6. Conferir os valores 0304 N=120268.227, E=513406.376,
   sigma Hz=0.008 e 0305 N=120168.534, E=514407.275.
7. Confirmar que nenhuma ODS certificável, planta ou memorial foi gerada
   automaticamente.

## Planejado para a etapa 2
- Vincular pontos de processamento ao perímetro efetivamente levantado.
- Confirmar os vértices oficiais, método SIGEF e tipo de limite.
- Identificar o datum e época e a altura elipsoidal, sem inferência.
- Compor a área com fecho, sentido horário e vértice inicial ao norte.
- Validar contra o modelo ODS oficial do INCRA **sem mudar seu layout**.
- Inserir campos de confrontantes e dados cadastrais ausentes.
- Exportar ODS somente quando o responsável confirmar campos e
  as validações necessárias passarem; gerar Planta/Memorial pelo motor atual.

O resultado da pré-validação não equivale à certificação do INCRA.
