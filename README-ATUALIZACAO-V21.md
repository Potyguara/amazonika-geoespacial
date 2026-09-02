# Atualização v21 — ANM, alertas e análise vetorial

Esta atualização é cumulativa e inclui:

- card oficial **ANM — Poligonais de processos minerários**;
- WMS do SIGMINE somente para referência visual;
- vetores oficiais da ANM obtidos pelo ArcGIS REST sob demanda, conforme a área visível ou analisada;
- atributos de processo, fase, titular, substância, uso, área e UF disponíveis na identificação e no relatório;
- alertas reais de disponibilidade das fontes, atualizados a cada cinco minutos;
- análise espacial em segundo plano com PostGIS;
- relatório técnico imprimível em PDF, com fontes efetivamente analisadas, advertências e feições intersectadas;
- URL da API preparada para proxy HTTPS no futuro VPS.

## Instalação no Mac

Encerre o Vite com `Ctrl+C`. Depois execute, sem copiar linhas iniciadas por `#`:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-anm-analise-v21.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.configure_incra_wms
docker compose exec api python -m app.configure_official_sources
until curl -f http://localhost:8000/health; do sleep 2; done
npm run dev -- --host 0.0.0.0 --force
```

Abra `http://localhost:8000/health` e confirme `status: ok`. Em seguida recarregue o painel sem cache.

## Verificação

1. Em **Fontes de dados**, confirme o card `Poligonais de processos minerários` com `WMS + ArcGIS REST sob demanda`.
2. Na **Visão geográfica**, ligue ANM e aproxime o mapa até pelo menos o zoom 7.
3. Use **Identificar** sobre uma poligonal; os atributos devem vir do vetor oficial, não da imagem WMS.
4. Desenhe ou importe uma geometria pequena e clique **Executar análise**.
5. Após a conclusão, clique **Criar relatório** e use `Salvar / imprimir PDF`.

ANM, SICAR e INCRA sob demanda não exigem download manual por UF. O backend consulta somente o envelope necessário, grava uma versão vetorial rastreável e faz a interseção exata no PostGIS.

## Futuro VPS

Publique a API atrás do mesmo domínio HTTPS do painel, encaminhando `/api/v1` para o container `api:8000`. Se frontend e API forem separados, configure `NEXT_PUBLIC_API_URL` e `CORS_ORIGINS` antes do build.
