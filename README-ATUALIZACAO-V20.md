# Atualização v20 — rolagem de camadas e SICAR/CAR

Esta atualização é cumulativa sobre a versão 19 e inclui:

- rolagem interna no painel **Gerenciar camadas**;
- card oficial **Cadastro Ambiental Rural (CAR)**;
- WMS do SICAR por UF para visualização;
- WFS do SICAR por UF e pela área desenhada, executado sob demanda na análise;
- tratamento de consultas sem sobreposição como resultado válido com zero feições;
- proxy compatível com os domínios oficiais do INCRA, SPU/INDE e SICAR;
- suporte ao nome especial da camada do Distrito Federal no SICAR.

## Instalação

Pare o Vite com `Ctrl+C` e execute no Terminal:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-scroll-sicar-v20.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.configure_incra_wms
docker compose exec api python -m app.configure_official_sources
until curl -f http://localhost:8000/health; do sleep 2; done
npm run dev -- --host 0.0.0.0 --force
```

Depois, recarregue o navegador sem cache. O card do SICAR não exige **Primeira carga**: o vetor necessário é obtido automaticamente quando a análise é executada.

## Verificação rápida

1. Em **Fontes de dados**, confirme o card `Cadastro Ambiental Rural (CAR)` como conectado.
2. Na **Visão geográfica**, selecione a UF correta.
3. Abra **Gerenciar todas as fontes** e role a lista até o SICAR e as camadas adicionais.
4. Ligue o CAR, desenhe uma área pequena e execute a análise.

Para a futura VPS, mantenha a API atrás de HTTPS e preserve a saída da API para os domínios oficiais configurados.
