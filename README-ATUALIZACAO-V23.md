# Amazônika Geoespacial — correção da estabilidade da análise (v23)

Esta versão impede que o cálculo de proximidade percorra e transforme todas as
geometrias de bases grandes, situação que podia esgotar os recursos do PostGIS
e interromper temporariamente a comunicação da API.

## Alterações

- seleção da feição mais próxima pelo índice espacial GiST/KNN;
- distância métrica exata calculada apenas para a candidata selecionada;
- limite seguro de 20 segundos por fonte;
- isolamento da consulta de cada fonte por savepoint;
- persistência incremental dos resultados, mantendo o painel responsivo;
- uma fonte lenta gera aviso no relatório e não cancela toda a análise.

## Instalação da correção

Descompacte `correcao-estabilidade-analise-v23.zip` na raiz do projeto,
substituindo o arquivo indicado, e execute:

```bash
cd ~/Documents/amazonika-geoespacial
docker compose up -d --build api
docker compose ps
curl http://localhost:8000/health
```

Não é necessário apagar o banco, recriar as fontes nem importar os vetores
novamente.
