# Atualização de desempenho do mapa

Esta atualização não altera nem apaga as cargas existentes no PostGIS.

## Aplicar no Mac

Na pasta do projeto, descompacte o pacote de atualização e reconstrua apenas a API:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-performance-mapa.zip -d .
docker compose up -d --build api
npm run dev -- --host 0.0.0.0
```

Não execute novamente a carga SIGEF.

## Novo comportamento

- Parcelas SIGEF aparecem a partir do zoom 9, quando passam a ser úteis para inspeção.
- Consultas anteriores são canceladas ao mover o mapa ou trocar de módulo.
- A listagem do mapa transporta somente os campos essenciais.
- Os atributos completos são consultados apenas ao clicar em **Identificar**.
- Em áreas densas, o mapa solicita aproximação em vez de tentar desenhar milhares de polígonos de uma vez.
