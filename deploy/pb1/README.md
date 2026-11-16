# GEO91 — PB1: índice de articulação da Base Cartográfica do Amapá

**Método INCRA:** PB1 (base cartográfica com precisão conhecida). PS3 é laser scanner aerotransportado; PS4 é sensores orbitais.

A geometria `Articulação_25K_Blocos_WGS84.zip` enviada pelo usuário foi inspecionada:
410 folhas, 5 blocos, EPSG:4326, atributos INOM/MI_1/Blocos.

## Instalação sem criar novo ambiente
1. Criar `deploy/pb1` no **worktree de homologação existente**.
2. Copiar `articulacao_amapa_25k_pb1.geojson` gerado a partir do ZIP para
   `deploy/pb1/articulacao_amapa_25k_pb1.geojson` (aprox. 180 KB).
3. Somente **depois** do arquivo existir, validar a montagem do
   `docker-compose.ps4.homolog.yml`.
4. Reutilizar o serviço `api` e frontend já existentes. Nunca subir novos
   containers de banco ou criar outra homologação para PB1.
5. Com autenticação, `POST /api/v1/technical-pieces/pb1/sheets/lookup` com
   `{"geometry":{"type":"Polygon","coordinates":[[[lon,lat],...]]}}`.
6. Testar um imóvel que cruza duas folhas, outro que toca borda e outro fora do índice.

## Limitações de conformidade
- O índice apenas identifica folhas. É necessário comprovar fonte, edição,
  classe PEC, metadados de acurácia, datum, fidelidade das feições e compatibilidade
  com o tipo do limite antes de classificar como PB1.
- **Não preencher sigmas horizontais com valores fixos 4,25/4,50 m.**
  O valor efetivo precisa de justificativa técnica, e a precisão planimétrica
  do limite natural é 3,00 m (não 7,50 m, reservado ao inacessível).
- MDT Color pode ser raster de visualização (RGB), incapaz de fornecer
  elevação numérica ou posicionamento da margem. Para h elipsoidal a partir
  de alturas normais HN é necessário fator de separação adequado ao datum
  vertical e modelo empregado; não usar automaticamente HN+N.
- A análise deve preservar origem, folha, data, nome do produto, hash e
  responsabilidade técnica; geração oficial ODS permanece bloqueada.

## Disco
Os 180 KB de índice substituem centenas de imagens utilizadas apenas para
consulta do mosaico. Os próprios produtos raster recortados devem ter política
de retenção e armazenamento privado, não serem duplicados em novas homologações.
Não execute `docker system prune --volumes`: pode apagar dados necessários.
