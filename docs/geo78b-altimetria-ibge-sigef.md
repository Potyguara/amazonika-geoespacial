# GEO-78B — altitude elipsoidal SIGEF e altitudes físicas IBGE

## Decisão técnica fundamentada
O manual do SIGEF especifica que a coluna **h** é altitude elipsoidal e que o campo **Sigma h** representa a incerteza dessa altura. Não exportar altitude normal nem ortométrica para a coluna h.

Referência SIGEF: https://sigef.incra.gov.br/documentos/manual/
Referência FAQ SIGEF: https://sigef.incra.gov.br/sobre/faq/

## Conversão altimétrica
Para o sistema altimétrico REALT2018, o modelo **hgeoHNOR2020** do IBGE fornece o fator η, de modo que:

- **HN = h − η** (altitude normal).
- Na situação em que se utiliza um modelo de ondulação geoidal **N**, como MAPGEO2015, **H ortométrica ≈ h − N**, observadas as limitações e referências do modelo adotado.

Essas duas grandezas e os respectivos fatores não são intercambiáveis, especialmente no Amapá onde o datum vertical de Santana deve ser considerado.

Fontes oficiais:
- https://www.ibge.gov.br/geociencias/informacoes-sobre-posicionamento-geodesico/servicos-para-posicionamento-geodesico/31283-hgeohnor2020-modeloconversaoaltitudesgeometricasgnss-datumverticalsgb.html
- https://www.ibge.gov.br/geociencias/informacoes-sobre-posicionamento-geodesico/servicos-para-posicionamento-geodesico/10855-modelo-de-ondulacao-geoidal.html

## Forma de obtenção
O IBGE oferece cálculo on-line e grades oficiais para uso local. Não foi identificado nesta etapa um contrato documentado de API REST pública e estável para consultar individualmente cada coordenada. **Não inventar endpoint nem automatizar acesso por raspagem da página.**

Primeira versão: usuário informa η ou N por ponto, a origem, modelo e confirma o referencial de h. O backend calcula a altitude física e conserva h original.

Versão seguinte: interpolador local sobre **grades hgeoHNOR2020** oficiais, identificadas por versão, checksum e abrangência espacial. Validar numericamente contra valores de referência do IBGE e limitar extrapolações.

## Campos do contrato
POST `/api/v1/technical-pieces/topcon/vertical-conversion`

Entrada:
```json
{
  "model": "hgeoHNOR2020",
  "points": [{
    "name": "M001",
    "latitude": 0.25,
    "longitude": -51.3,
    "ellipsoidal_height_m": 20.4,
    "height_reference_confirmed": true,
    "conversion_factor_m": 13.2,
    "factor_origin": "IBGE hgeoHNOR2020, calculado em DD/MM/AAAA",
    "sigma_h_m": 0.03
  }]
}
```

Saída: `normal_height_m = 7.2`, `sigef_h_m = 20.4`, proveniência do fator e aviso de que as coordenadas não foram alteradas. Se o referencial não estiver confirmado, o cálculo será bloqueado.

## Falha GEO-78A
O teste da ODS retornou 48 vértices para 6 pretendidos. A linha modelo tem atributo ODF `table:number-rows-repeated`, que deve ser eliminado antes de duplicar as linhas de vértices. O exportador foi corrigido e ganhou regressão específica. A correção precisa passar no teste com o arquivo ODS real da VPS antes da publicação.

## Limites
- A checagem local não certifica o imóvel e não substitui SIGEF/INCRA.
- Não usar elevação Topcon como h sem identificar referência vertical.
- Não calcular sigma H por soma simples de incertezas sem tratamento estatístico apropriado.
- Não substituir automaticamente h ou coordenadas por deslocamentos cartográficos.
