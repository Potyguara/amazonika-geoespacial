#!/usr/bin/env bash
# Guarda, antes da limpeza, tudo o que é preciso para recriar os ambientes parados
# (homologação de cartografia, ANM e bancos de teste): bancos (pg_dumpall),
# imagens Docker, configurações e o "docker inspect" de cada container.
# Não apaga nada.
set -uo pipefail
D=/opt/amazonika-backups/ambientes-$(date +%Y%m%d)
mkdir -p "$D"
echo ">> Espaço livre antes:"; df -h / | tail -1

# Containers parados que serão removidos na limpeza (exceto cópias backup/pre-).
mapfile -t CONTAINERS < <(docker ps -a --format '{{.Names}}' | grep -E '^amazonika-(cartografia-homolog-|cartography-test$|anm-|consolidated-postgres-test$|geo83-db$|geo83-proxy$|geo90-cog-tiles$|sigef-api$|sigef-web$|web-homolog-geo45$|web-topcon-geo80-check$)')
printf '   %s\n' "${CONTAINERS[@]}"

echo ">> Configurações"
tar czf "$D/configs.tgz" --exclude=node_modules --exclude=.next --exclude=dist \
  /tmp/amazonika-pyqgis-test /tmp/amazonika-sigef-homolog /opt/amazonika-anm-homolog 2>/dev/null
for c in "${CONTAINERS[@]}"; do docker inspect "$c" > "$D/inspect-$c.json"; done

echo ">> Bancos de dados"
for c in "${CONTAINERS[@]}"; do
  [[ "$(docker inspect -f '{{.Config.Image}}' "$c")" == postgis/* ]] || continue
  running=$(docker inspect -f '{{.State.Running}}' "$c")
  docker start "$c" >/dev/null || { echo "   $c: não iniciou"; continue; }
  for i in $(seq 1 30); do docker exec "$c" sh -c 'pg_isready -U "$POSTGRES_USER"' >/dev/null 2>&1 && break; sleep 2; done
  if docker exec "$c" sh -c 'pg_dumpall -U "$POSTGRES_USER"' | gzip -1 > "$D/banco-$c.sql.gz"; then
    echo "   $c: $(du -h "$D/banco-$c.sql.gz" | cut -f1)"
  else
    echo "   $c: FALHOU o dump"
  fi
  [ "$running" = true ] || docker stop "$c" >/dev/null
done

echo ">> Imagens"
mapfile -t IMAGES < <(for c in "${CONTAINERS[@]}"; do docker inspect -f '{{.Config.Image}}' "$c"; done | grep -v '^postgis/' | sort -u)
printf '   %s\n' "${IMAGES[@]}"
docker save "${IMAGES[@]}" | gzip -1 > "$D/imagens.tar.gz"
docker volume ls --format '{{.Name}}' > "$D/volumes.txt"

echo ">> Pacote pronto"
ls -lh "$D"; du -sh "$D"; df -h / | tail -1
echo
echo "Baixe no PC (PowerShell, numa pasta com espaço):"
echo "  scp -r root@2.24.125.171:$D ."
for b in 20261109-160002 pre-mapbox-20261028-004147 pre-limpeza-sigef-20261109-234056 anm-20261108; do
  echo "  scp -r root@2.24.125.171:/opt/amazonika-backups/$b ."
done
