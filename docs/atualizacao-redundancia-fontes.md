# Atualização — redundância das fontes e identificação sobreposta

Esta atualização não apaga nem exige nova importação das bases existentes no PostGIS.

## Instalação no Mac

Pare o servidor web com `Control + C` e execute:

```bash
cd ~/Documents/amazonika-geoespacial
unzip -o ~/Downloads/atualizacao-redundancia-fontes.zip -d .
docker compose up -d --build api
curl http://localhost:8000/health
npm run dev -- --host 0.0.0.0
```

## Configuração ou carga manual

1. Abra **Fontes de dados**.
2. Clique na engrenagem do cartão desejado.
3. Para sincronização automática, configure o tipo, o endereço e a camada do WFS ou FeatureServer.
4. Como contingência, selecione um GeoPackage, KML, GeoJSON ou ZIP contendo o Shapefile.
5. Informe a data de referência e use **Importar e ativar versão**.

A versão corrente permanece disponível se a nova importação falhar.

## Controle das camadas no mapa

1. Abra **Visão geográfica**.
2. Clique em **Gerenciar todas as fontes**.
3. Ative somente as camadas necessárias ou use **Ativar todas** e **Desativar todas**.
4. As mesmas escolhas valem para visualização, identificação e análise espacial.

Com a ferramenta **Identificar** ativa, um clique que alcance várias feições abre uma lista. Selecione a parcela ou feição desejada para consultar todos os atributos armazenados.
