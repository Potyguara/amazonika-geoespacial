# Primeiro marco executável — Relatório Consolidado da Fazenda

**Não substituir o relatório territorial de sobreposições existente na produção.**
Esta nova função foi concebida como um produto distinto, com evolução gradual
até alcançar o nível de detalhamento do modelo de 46 páginas.

## Estado do código

- `POST /api/v1/rural-consolidated/analyses/{analysis_id}` aceita opcionalmente
  `{"monitoring_layer_name":"<nome WFS exato do catálogo TerraBrasilis>"}`.
  Sem nome selecionado, **PRODES/DETER não é executado**.
- `GET /api/v1/rural-consolidated/jobs/{job_id}` expõe estado, percentuais,
  fontes/seções e disponibilidade do PDF.
- `GET /api/v1/rural-consolidated/jobs/{job_id}/pdf` retorna PDF somente ao
  criador do job ou administrador, com permissão export.
- `rural_consolidated_jobs` é independente de `report_emissions`; nenhum
  documento territorial existente é alterado.
- BackgroundTasks persiste estados e snapshot no PostgreSQL; os processos
  podem ficar em `PROCESSING` após reinício da API. **Ainda não é um
  worker durável nem tem recuperação automática.**
- O PDF desta etapa é `PRELIMINARY_PARTIAL`: identificação e hash da
  geometria, quadro de 18 temas, evidências de base territorial existente,
  embargos IBAMA oficiais (quando a consulta completar), PRODES/DETER oficial
  (somente camada escolhida e validada) e metodologia.
- **Não inclui ainda:** imagem satelital de capa, cartografia temática,
  coleção completa de análises, clima, solo, hidrografia, mineração,
  MapBiomas computado, fotos antes/depois ou emissão com QR.
- Falhas externas resultam em `UNAVAILABLE`; 0/0 fontes não é "sem
  sobreposições". Não há qualquer acesso ao Google Earth Engine por este
  processo.

## Validar código offline sem executar serviços externos

Na homologação isolada, atualizar worktree com `git fetch` e checkout
da branch sem modificar produção. Usar imagem de testes já disponível:

```bash
cd /tmp/amazonika-rural-homolog
git fetch origin
git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104
git rev-parse --short HEAD

docker run --rm --network none --memory=768m --cpus=1 \
  -e GEE_ENABLED=false -e GEE_INTERNAL_PILOT_ENABLED=false \
  -v "$PWD/backend:/app:ro" -w /app \
  --entrypoint python amazonika-api-testes \
  -m pytest -p no:cacheprovider \
  tests/test_rural_consolidated_contract.py \
  tests/test_rural_consolidated_pdf.py -v
```

**Não executar `docker compose up` com `--build` nesta etapa**.
O stack isolado da porta 18002 só deverá ser atualizado após revisão dos
resultados dos testes e confirmação de que o módulo está pronto para
homologação. A imagem de testes existente pode não conter `pytest`;
se isso ocorrer, ajustar exclusivamente o contêiner descartável de testes.

## Próximo estágio de implementação

1. Fila/worker durável com recuperação e cancellation auditada.
2. Seleção explícita de fontes/anos e cache com proveniência.
3. Serviços de consulta de CAR robustos com resposta 503 quando upstream
   indisponível, em vez de 500.
4. Mapa cartográfico por seção em CRS métrico, com legenda e fontes.
5. MapBiomas 2025 com quota e orçamento aprovados, somente por opt-in.
6. Demais seções segundo o modelo de 46 páginas, cada uma com fonte real.
7. Frontend `Relatório Consolidado da Fazenda` separado do botão
   `Analisar imóvel`, com status e histórico de jobs.
8. Testes integrados e PDFs examinados visualmente antes de merge/deploy.
