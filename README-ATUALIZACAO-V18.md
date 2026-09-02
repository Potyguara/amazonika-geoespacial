# Amazônika Geoespacial — atualização v18

Atualização cumulativa que inclui:

- análise espacial executada em segundo plano, adequada a uma futura VPS;
- acompanhamento do processamento sem manter uma requisição HTTP longa;
- relatório técnico HTML imprimível em PDF;
- correção das geometrias 3D do IPHAN;
- fonte oficial **Imóveis da União — SPU**, com WMS do GeoPortal-SPU;
- seção **Vetores adicionais por UF** para GeoPackage, KML, GeoJSON e Shapefile ZIP;
- categorias para assentamentos estaduais/municipais, UCs estaduais/municipais e outras feições regionais;
- novas camadas adicionais ligadas por padrão no mapa e na análise da UF escolhida.

## Instalação local

Execute no Terminal, sem copiar linhas iniciadas por `#`:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-spu-camadas-adicionais-v18.zip -d .
docker compose up -d --build api
docker compose exec api python -m app.configure_incra_wms
docker compose exec api python -m app.configure_official_sources
until curl -f http://localhost:8000/health; do sleep 2; done
npm run dev -- --host 0.0.0.0 --force
```

Depois, faça uma atualização forçada no navegador (`Command + Shift + R`).

## Uso das camadas adicionais

Em **Fontes de dados**, acesse **Vetores adicionais por UF**, escolha a categoria e a UF, selecione o arquivo e clique em **Adicionar camada ligada**. O backend converte a geometria para SIRGAS 2000 (EPSG:4674), cria uma versão analisável e ativa a camada. No mapa, a camada aparece apenas quando a UF correspondente estiver selecionada.

## SPU

A fonte **Imóveis da União** usa o WMS público do GeoPortal-SPU para referência visual. O serviço público atualmente não expõe o WFS dessa camada de forma anônima; portanto, o sistema não trata a imagem WMS como vetor. Enquanto a SPU não liberar o WFS, um arquivo vetorial oficial pode ser versionado pela configuração da fonte para participar do cálculo de sobreposição.

## Preparação para VPS

No frontend de produção, defina `NEXT_PUBLIC_API_URL` com o endereço HTTPS público da API, por exemplo:

```env
NEXT_PUBLIC_API_URL=https://geo.seudominio.com/api/v1
```

No backend, inclua o domínio público do frontend em `CORS_ORIGINS`. Para produção, recomenda-se Nginx ou Caddy como proxy HTTPS e um worker persistente para as análises. A v18 já remove a dependência de uma requisição HTTP longa; uma etapa futura pode substituir `BackgroundTasks` por Celery/RQ para sobreviver a reinícios do container.
