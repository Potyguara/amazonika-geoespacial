# Amazônika Geoespacial — atualização v19

Correções principais: importação de ZIPs gerados no macOS, WFS público CMR/FUNAI para Terras Indígenas, card vetorial da SPU com nove camadas oficiais da INDE e descoberta automática da API pelo IP usado no navegador.

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-funai-spu-zip-v19.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.configure_incra_wms
docker compose exec api python -m app.configure_official_sources
until curl -f http://localhost:8000/health; do sleep 2; done
npm run dev -- --host 0.0.0.0 --force
```

Após iniciar, faça `Command + Shift + R`, execute a primeira carga de Terras Indígenas e da SPU e reenvie o ZIP da FLOTA/AP.
