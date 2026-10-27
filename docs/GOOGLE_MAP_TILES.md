# Google Map Tiles — implantação controlada (Amazônika Geoespacial)

## Escopo
Integração oficial **2D Satélite** somente para visualização online no mapa
OpenLayers principal. Não utiliza URL não documentada de imagens Google.

- Fluxo: browser autenticado -> backend FastAPI -> Map Tiles API Google.
- Segredo presente **somente no ambiente do backend**.
- Sessão criada via `POST /v1/createSession`, reutilizada até vencer;
  imagens via `GET /v1/2dtiles/{z}/{x}/{y}`.
- Direitos autorais dinâmicos obtidos do endpoint `viewport`.
- Nenhum cache persistente próprio, armazenamento de Google tiles, análise de
  imagens, screenshot ou exportação Google para PDF nesta integração.
- Em caso de indisponibilidade, usar OpenStreetMap/Esri existentes.

## Pré-requisitos Google Cloud
1. Conta de faturamento do projeto correta.
2. **Map Tiles API** habilitada no projeto (não confundir com Maps JavaScript API).
3. Chave de API restrita à **Map Tiles API** e à(s) origem(ns) de IP do backend.
4. Monitoramento de uso, orçamento, quotas e alertas de gastos.

**Não coloque o segredo no GitHub, capturas ou chat.**

## Local: .env (arquivo existente, não versionar)
Adicionar as linhas abaixo, com uma chave real somente no seu computador:

```dotenv
GOOGLE_MAPS_API_KEY=SUBSTITUIR_SOMENTE_NO_ARQUIVO_LOCAL
GOOGLE_MAP_TILES_ENABLED=true
```

``docker compose up -d --build api`` reconstrói o backend com as variáveis.
O navegador usa sessão autenticada já existente e exibirá **Google Satélite
(visualização)** no painel Mapa base. Não é necessária variável pública/Vite.

Para verificar sem revelar segredo:

```bash
curl -sS http://127.0.0.1:8000/ready
```

Se o provedor negar a sessão, conferir habilitação da Map Tiles API,
faturamento, restrição de IP e uso do IP de saída do servidor. Não liberar a
chave irrestritamente como solução permanente.

## Produção (posterior à homologação)
Usar as mesmas variáveis em `.env.production` e o Docker Compose de produção;
a opção permanece desativada se a chave ou `GOOGLE_MAP_TILES_ENABLED` não
forem configuradas. Nunca alterar a VPS sem backup e checklist de rollback.

## Restrições desta etapa
- **Somente mapa principal online**. Mapa lateral/Planta de Situação e PDF
  continuam utilizando Esri/OSM.
- Não captura/armazenamento de tiles Google nos documentos.
- Não há geocodificação, Google Places, elevação ou tiles 3D.
- Crédito Google Maps e atribuição de viewport exibidos somente ao visualizar
  a base Google; validar créditos no navegador em cada mudança de zoom/área.
- Monitorar cotas e uso ao habilitar acesso multiusuário.

Fontes oficiais:
- https://developers.google.com/maps/documentation/tile/overview
- https://developers.google.com/maps/documentation/tile/session_tokens
- https://developers.google.com/maps/documentation/tile/policies
