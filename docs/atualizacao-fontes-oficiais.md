# Atualização — IBAMA e assentamentos INCRA

Esta atualização preserva todas as versões e parcelas SIGEF existentes no volume PostGIS.

## Aplicação no Mac

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-fontes-oficiais.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.seed
npm run dev -- --host 0.0.0.0
```

## Primeiras sincronizações

1. Abra o menu **Fontes de dados**.
2. Em **Áreas embargadas**, clique em **Primeira sincronização**.
3. Aguarde a confirmação antes de iniciar outra fonte.
4. Em **Assentamentos rurais**, clique em **Primeira sincronização**.
5. Volte à **Visão geográfica** para conferir as camadas e usar **Identificar**.

As fontes nacionais possuem milhares de registros e cada primeira sincronização pode levar alguns minutos. O serviço é consultado em páginas de 2.000 feições, e a versão anterior somente é substituída depois da conclusão integral.
