# API Amazônika Geoespacial

## Execução local

Na raiz do projeto:

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m app.seed
```

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Saúde: `http://localhost:8000/health`

O motor usa SIRGAS 2000 (EPSG:4674) no armazenamento e `geography` do PostGIS para áreas e distâncias. Cada carga cria uma versão imutável da fonte; apenas uma versão fica marcada como corrente.
