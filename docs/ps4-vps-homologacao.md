# GEO90/PS4 — pré-homologação e publicação controlada

**Situação:** PR #14 em rascunho. Este documento **não** autoriza publicação automática ou emissão SIGEF.

## 1. Pré-verificação na VPS (somente leitura)

No host `SIS`:

```bash
cd /opt/amazonika-geoespacial
git status --short
git branch --show-current
git rev-parse --short HEAD
df -h /
free -h
docker compose --env-file .env.production -f docker-compose.production.yml ps
curl --fail --max-time 10 http://127.0.0.1:18000/ready
```

Quando o script estiver disponível no checkout, executar
`bash scripts/ps4_vps_preflight.sh`. O script não publica nem reinicia serviços.
Conferir a saída real (não presumir que o PR já foi implantado).

## 2. Proxy e upload

O backend limita arquivos a **256 MiB GeoTIFF** e **25 MiB PDF**.
O proxy que encaminha `/api` precisa aceitar corpo superior ao limite do
GeoTIFF, considerando overhead multipart. Exemplo de **configuração candidata**
a validar no bloco `server`/ `location` efetivo do host:

```nginx
client_max_body_size 270m;
client_body_timeout 120s;
proxy_read_timeout 180s;
proxy_send_timeout 180s;
```

Não sobrescrever a configuração real sem inspecionar `nginx -T`. Aplicar
somente após backup, revisão e `nginx -t` com sucesso. Um 413 indica limite
de corpo no proxy; um 504 pode indicar timeout ou serviço indisponível.
Recortes CBERS automáticos **não exigem upload de 256 MiB pelo navegador**
porque são processados pelo worker.

## 3. Recursos e armazenamento

- O `package-worker` existente executa recortes PS4 serialmente, aproveitando
  `uploads_data:/data/uploads` compartilhado com API.
- A preparação exige pelo menos **2 GiB livres** antes de acessar o COG.
- Os temporários GDAL de preparação são criados no mesmo volume e eliminados
  ao final do processamento normal.
- A fila JSON fica em `.ps4_inpe_jobs`; jobs finais anteriores a 90 dias têm
  apenas os **metadados de status** removidos no início do worker.
- A rotina de retenção **não apaga** imagens, XML ou relatórios. Limpeza de
  evidências definitivas precisa de política separada e conferência no banco.
- Verificar `docker stats --no-stream`, `df -h` e logs do worker durante ensaio.

## 4. Critérios de homologação ponta a ponta

1. Salvar uma peça de teste com poligonal e permissões apropriadas.
2. Selecionar cena L4 ou RGB no catálogo do INPE e inspecionar metadados.
3. Solicitar recorte e confirmar resposta **HTTP 202 + job ID**.
4. Consultar job `QUEUED → PROCESSING → READY`; reiniciar o browser no meio
   para verificar recuperação do progresso sem duplicação.
5. Verificar se GeoTIFF e metadados XML são associados à **mesma peça e cena**,
   se o EPSG está correto e se a ortoimagem é renderizada no OpenLayers.
6. Confirmar que não há criação de V fora da cobertura, sem pixel válido, ou
   sem relatório técnico anexado.
7. Confirmar bloqueio de revisão RT até o relatório, parâmetros de precisão e
   checagens exigidos; GSD não é comprovação da precisão absoluta.
8. Trocar a cena com importação pendente e provar que o job anterior não
   sobrescreve a imagem nem conserva a aprovação.
9. Testar `NOT_APPLICABLE` quando não existirem V adicionais.
10. Provar que ODS SIGEF preenchida permanece bloqueada se houver ausência de
    altura elipsoidal confirmada, sigmas ou precisão horizontal em V.
11. Revisar normal/ortométrica versus elipsoidal no memorial; a aprovação
    horizontal PS4 **não resolve** a altimetria por si só.

## 5. Critérios de interrupção

Não aprovar nem publicar se ocorrer qualquer um destes eventos:

- Proxy recusa anexos dentro dos limites definidos.
- COG inacessível, recorte falha ou SRC inesperado.
- Worker consome recursos incompatíveis com os outros serviços.
- Arquivo de cena antiga substitui imagem nova ou status perde persistência.
- Sistema libera ODS SIGEF sem campos obrigatórios.
- Divergência entre memorial, geometria e alturas de referência.

## 6. Rollback

Antes de qualquer deploy: anotar commit/base ativos, efetuar backup do banco e
do volume de evidências, e preservar configuração Nginx original. Publicar
somente a branch homologada em janela controlada. Se houver falha, voltar ao
commit/imagens Docker anteriores e revalidar saúde da API, web e worker.
**Não remover volumes nem executar `docker compose down -v`.**

Não há acesso SSH automático a partir deste PR. Execução/resultado na VPS
devem ser confirmados por operador autorizado.
