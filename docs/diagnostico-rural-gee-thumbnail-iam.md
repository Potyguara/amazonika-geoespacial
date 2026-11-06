# Diagnóstico IAM: Earth Engine thumbnail Permission (05/11/2026)

**Evidência na VPS:** `reduceRegion` sobre o CAR de 1.115,1093 ha
concluiu e gerou PDF estatístico. No caminho cartográfico,
`getThumbURL` rejeitou duas tentativas, ambas com
`EE_GET_THUMB_URL categoria=EEException marcadores=Permission`.
A origem exata do Permission denied (permissão, projeto, ativo, política
organizacional ou conta) **não está confirmada**. Não repetir cobrança
sem inspecionar IAM.

**Documentação oficial**: `projects.thumbnails.create` requer
`earthengine.thumbnails.create` no projeto pai. O papel predefinido
`roles/earthengine.viewer` permite `earthengine.computations.create`
e `earthengine.thumbnails.get`, mas **não**
`earthengine.thumbnails.create`. Os papéis
`roles/earthengine.writer` e `roles/earthengine.editor`
incluem `earthengine.thumbnails.create`, junto com permissões muito
mais abrangentes de mutação de assets; **evitar Admin, Owner ou Editor
genérico apenas para esse teste**. Preferir papel customizado de
privilégio mínimo se viável e permitido pela organização.

Referências oficiais:
- https://developers.google.com/earth-engine/reference/rest/v1alpha/projects.thumbnails/create
- https://docs.cloud.google.com/iam/docs/roles-permissions/earthengine
- https://developers.google.com/earth-engine/guides/access_control

## Verificar sem nova solicitação Earth Engine

Na VPS:

```bash
GEE_EMAIL=$(python3 -c 'import json;print(json.load(open("/root/amazonika-secrets/gee-service-account.json"))["client_email"])')
if command -v gcloud >/dev/null 2>&1; then
  gcloud projects get-iam-policy amazonika-geoespacial \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:$GEE_EMAIL" \
    --format="table(bindings.role)"
else
  echo "gcloud ausente; consultar Google Cloud Console > IAM e administrador"
fi
```

Essa consulta precisa de permissão Cloud IAM para leitura; se `gcloud`
pedir autenticação, usar sessão autorizada no Console em vez de introduzir
a chave do Earth Engine em comandos de autenticação de administrador.

Atribuições IAM podem ser verificadas no
`Google Cloud Console > IAM e administrador > IAM` do projeto
`amazonika-geoespacial`, procurando o principal pela
`client_email` do JSON. Verifique os papéis e possíveis condições IAM.

Uma alternativa de menor privilégio é acrescentar ao principal somente
`earthengine.thumbnails.create` em papel customizado no projeto, além
das permissões existentes; a permissão de leitura de miniatura também pode
ser necessária (`earthengine.thumbnails.get`). A criação/atribuição
do papel deve ser aprovada pelo administrador da nuvem. Não confundir
papel IAM da conta com políticas de cobrança/quota do Earth Engine.

Depois da alteração de IAM, aguardar propagação e executar **uma** nova
tentativa do canário cartográfico, sem desativar TLS ou publicar
`GEE_BROWSER_PREVIEW_ENABLED`.
