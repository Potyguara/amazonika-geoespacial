#!/usr/bin/env bash
# GEO-83B: encerra APENAS os recursos marcados como pertencentes à homologação.
set -Eeuo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
NET=amazonika-geo83-internal
LABEL=amazonika.geo83.homolog
for NAME in amazonika-geo83-proxy amazonika-geo83-web amazonika-geo83-api amazonika-geo83-db; do
  if docker container inspect "$NAME" >/dev/null 2>&1; then
    actual="$(docker inspect "$NAME" --format '{{index .Config.Labels "amazonika.geo83.homolog"}}')"
    if [[ "$actual" != 1 ]]; then
      echo "BLOQUEADO: $NAME nao possui o marcador GEO83."
      exit 1
    fi
  fi
done
if docker network inspect "$NET" >/dev/null 2>&1; then
  actual="$(docker network inspect "$NET" --format '{{index .Labels "amazonika.geo83.homolog"}}')"
  if [[ "$actual" != 1 ]]; then
    echo "BLOQUEADO: rede $NET nao possui o marcador GEO83."
    exit 1
  fi
fi
echo "===== ENCERRANDO HOMOLOGACAO GEO83 ====="
for NAME in amazonika-geo83-proxy amazonika-geo83-web amazonika-geo83-api amazonika-geo83-db; do
  if docker container inspect "$NAME" >/dev/null 2>&1; then
    docker rm -f "$NAME" >/dev/null
    echo "Removido: $NAME"
  fi
done
if docker network inspect "$NET" >/dev/null 2>&1; then
  docker network rm "$NET" >/dev/null
  echo "Rede interna removida: $NET"
fi
echo "===== PRODUCAO ====="
curl -fsS http://127.0.0.1:18000/ready
echo
echo "GEO83 encerrada; nenhuma imagem ou volume oficial removido."
