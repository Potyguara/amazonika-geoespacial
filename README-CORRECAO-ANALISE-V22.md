# Correção v22 — execução da análise espacial

Corrige o erro `Geometry SRID (4674) does not match column SRID (4326)` ao clicar em **Executar análise**.

A geometria continua armazenada e intersectada em SIRGAS 2000 (`EPSG:4674`). Somente os cálculos geodésicos de área e distância são transformados explicitamente para `EPSG:4326/geography`. Geometrias KML ou GeoJSON com altitude também são convertidas para 2D antes da gravação.

## Instalação

Encerre o Vite com `Ctrl+C` e execute:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/correcao-analise-srid-v22.zip -d .
docker compose up -d --build api
until curl -f http://localhost:8000/health; do sleep 2; done
npm run dev -- --host 0.0.0.0 --force
```

Depois recarregue o navegador sem cache, mantenha inicialmente uma área pequena e clique em **Executar análise**.
