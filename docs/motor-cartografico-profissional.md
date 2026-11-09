# Motor cartográfico profissional — Amazônika

Branch: `feat/motor-cartografico-templates-20261109`

## Templates (A2 ou A1, retrato)

| Identificador | Composição | Referência fornecida |
|---|---|---|
| `classic_lateral` | Mapa grande, coluna técnica direita e coordenadas em três colunas na faixa inferior | modelo-1-classico-lateral.pdf |
| `cartographic_frame` | Moldura cartográfica ampla, painéis sobrepostos à esquerda e tabela inferior | modelo-2-moldura-cartografica.pdf |
| `modern_lateral` | Mapa à esquerda, quadro de coordenadas vertical à direita e quadros técnicos abaixo do mapa | modelo-3-moderno-quadro-lateral.pdf |

`lateral` e `inferior` continuam disponíveis por compatibilidade.

## Política cartográfica

- Todos os modelos usam **os mesmos objetos Parcel** e o mesmo pipeline de projeção SIRGAS 2000 / UTM.
- A escala é calculada fisicamente (`72 / (0.0254 * denominador)` pontos por metro) e rejeitada quando a geometria não cabe na área cartográfica.
- Os nomes de vértices, altitudes e confrontantes vêm dos dados de origem. O renderizador não cria dados ausentes.
- Em caso de excesso de linhas, o quadro de coordenadas continua em páginas adicionais; **não perde vértices**.
- As fontes são instaladas a partir de pacotes livres `fonts-dejavu-core` e `fonts-liberation2`. O ReportLab as incorpora ao PDF; a fonte Helvetica de reserva só é usada se os pacotes faltarem.
- O documento gerado não equivale a certificação fundiária; os avisos existentes são preservados.

## Testes de execução (VPS SIS, branch isolada)

```bash
python3 -m py_compile backend/app/services/plant_template_engine.py \
  backend/app/services/plant_memorial_v3.py backend/app/api/routes/tools.py
docker build -f backend/Dockerfile.production \
  -t amazonika-cartografia-profissional:qa backend
docker run --rm --entrypoint python amazonika-cartografia-profissional:qa \
  -m unittest discover -s tests -p 'test_professional_plant_engine.py' -v
docker run --rm --entrypoint python amazonika-cartografia-profissional:qa \
  -m unittest discover -s tests -p 'test_plant_layout_templates.py' -v
npm ci --no-audit --no-fund
./node_modules/.bin/tsc -p tsconfig.ci.json --noEmit
npm run build
```

## Aceite visual obrigatório

1. Importar o ODS real no ambiente de homologação.
2. Gerar **um PDF por template** em A2 retrato e comparar visualmente com os três modelos originais, sem alteração de números.
3. Verificar presença de **todos os 61 vértices** no quadro, campos de altitude, azimutes e distâncias.
4. Conferir se não há sobreposição entre tabela, legenda, croqui e confrontantes.
5. Conferir se o memorial começa a descrição na página correta, sem páginas vazias e sem texto sobre o rodapé.
6. Confirmar separadamente o controle dos rótulos da Planta de Situação e os rótulos da planta principal.
7. Homologar o PDF somente depois da comparação visual; a compilação não é aceite cartográfico.
