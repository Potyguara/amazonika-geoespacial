# Diagnóstico Rural — piloto cartográfico interno por CAR

## Estado

Implementação em branch de homologação **sem merge e sem deploy**.
O primeiro canário real na VPS comprovou:
- SICAR WFS e geometria oficial do CAR: 1115,1093 ha.
- MapBiomas Brasil Coleção 11 ano 2025: 1115,077 ha classificados.
- Miniatura de pixels reais 640×454 por Earth Engine.
- PDF privado de três páginas com mapa e gráfico.

**A inspeção visual do arquivo PDF de três páginas ainda é obrigatória.**

## API de homologação

Somente usuário autenticado com papel `ADMINISTRADOR` e permissões
`analysis.view`, `analysis.execute`, `analysis.export`.

- `GET /api/v1/rural-diagnostics/mapbiomas/internal-pilot/status`
- `POST /api/v1/rural-diagnostics/mapbiomas/internal-pilot/pdf`

Corpo JSON de geração: `{"car_code":"<CAR VALIDADO>","year":2025}`.
Não aceita geometria nem valores estatísticos fornecidos pelo navegador.
O código CAR é recuperado do SICAR e a área é calculada no servidor.
O mapa resulta de nova consulta de redução estatística e thumbnail real
para o mesmo perímetro, garantindo que a tabela não use dados de outro imóvel.

O endpoint é síncrono para homologação e devolve PDF diretamente por HTTPS,
sem armazenamento persistente e sem PNG. **Não é fila assíncrona**. A implantação
futura para usuários deverá empregar fila e status persistidos, se necessário.

## Política de consumo e auditoria

- `GEE_INTERNAL_PILOT_ENABLED=false` por padrão;
- `GEE_ENABLED=false` por padrão;
- `GEE_BROWSER_PREVIEW_ENABLED=false` por padrão, independentemente
  da habilitação do piloto.
- 1 **tentativa** por administrador por dia UTC; falhas contam;
- 5 tentativas por dia UTC para toda a instalação;
- só uma execução por vez na instalação (PostgreSQL advisory lock);
- imóveis de até 1200 ha, 30000 pixels máximos para redução;
- miniatura até 640 px/lado, 350000 pixels e 3 MB;
- ano 2025 fixo para este piloto;
- dados de auditoria: UUID do usuário, dia UTC, SHA-256 do CAR, status
  reservado/completo/falhou, categoria genérica e tamanho final do PDF;
- não grava CAR em claro na tabela de auditoria;
- **a reserva é transacional e persistida antes da primeira chamada à rede**;
- não há repetição automática após erro, nem liberação automática da quota;
- só a validação do formato do CAR precede a reserva.

O limite conservador **não substitui** budget/quotas configurados no Google Cloud.
Chamadas ao Google podem gerar cobrança. O administrador deverá revisar gastos,
taxas e custos reais antes de liberar o módulo a clientes.

## Antes de qualquer deploy

1. Fazer backup verificado do PostGIS.
2. Confirmar que o container backend contém as dependências (Pillow, pyproj,
   ReportLab e earthengine-api) e permite acesso à conta de serviço como
   arquivo somente-leitura.
3. Manter `GEE_BROWSER_PREVIEW_ENABLED=false`.
4. Executar testes offline:
   ```bash
   cd /tmp/amazonika-rural-homolog
   git fetch origin
   git checkout --detach origin/feat/diagnostico-rural-coordenada-20261104
   docker run --rm --network none -v "$PWD/backend:/app:ro" -w /app \
     --entrypoint python amazonika-api-testes \
     -m pytest -p no:cacheprovider \
     tests/test_rural_mapbiomas_pilot.py \
     tests/test_rural_mapbiomas_cartography.py \
     tests/test_rural_mapbiomas.py -v
   npm run build
   ```
5. Inspecionar o PDF do canário real de três páginas antes de teste E2E.
6. Somente numa **homologação separada**, com backup e migração confirmados,
   configurar explicitamente `GEE_INTERNAL_PILOT_ENABLED=true` e
   `GEE_ENABLED=true`, sem liberar `GEE_BROWSER_PREVIEW_ENABLED`.
7. Testar autenticação real de administrador, usuários sem permissão 403,
   quotas 429 e indisponibilidade de fontes 503.
8. Deixar o deployment público para depois da aprovação de segurança,
   testes de consumo e revisão cartográfica.

## Atenção — banco

O modelo `RuralMapBiomasPilotRun` está registrado no `Base.metadata`.
Ao iniciar a nova aplicação, o `Base.metadata.create_all` criará a tabela
`rural_mapbiomas_pilot_runs` e o índice único diário. Confirmar migração,
permissões do PostGIS e backup **antes** de subir a versão. Não executar DDL
em produção inadvertidamente.

## Reversão

Desabilitar `GEE_INTERNAL_PILOT_ENABLED` e reiniciar apenas o backend
homologado; qualquer rota de geração falhará fechada com HTTP 503.
Preservar as linhas da tabela de auditoria por rastreabilidade.
