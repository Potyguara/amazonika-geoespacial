#!/usr/bin/env bash
# Limpeza do disco da VPS do Geoespacial.
#   bash limpar.sh              -> só mostra o que seria removido (não apaga nada)
#   CONFIRMO=1 bash limpar.sh   -> apaga
# Preserva: tudo que está rodando (produção geo, homologação ps4/peças técnicas,
# rural, openwa, egress INPE), as imagens de volta da produção (geo71/geo44) e da
# homologação ps4, o backup do banco de hoje e todos os volumes de dados.
set -uo pipefail
GO=${CONFIRMO:-0}
run() { if [ "$GO" = 1 ]; then "$@"; else echo "   [simulação] $*"; fi; }
echo ">> Antes:"; df -h / | tail -1

echo ">> Containers parados a remover"
mapfile -t OLD < <(docker ps -a --filter status=exited --filter status=created --format '{{.Names}}' \
  | grep -E '^amazonika-' | grep -vE '^amazonika-(geoespacial|ps4-homolog|rural-homolog)-')
mapfile -t CARTO < <(docker ps -a --format '{{.Names}}' | grep -E '^amazonika-cartografia-homolog-')
printf '   %s\n' "${OLD[@]}" "${CARTO[@]}" | sort -u
[ ${#OLD[@]} -gt 0 ] && run docker rm -f "${OLD[@]}"
[ ${#CARTO[@]} -gt 0 ] && run docker rm -f "${CARTO[@]}"

echo ">> Fixando as imagens de volta (container parado 'pin' impede a remoção)"
PINS=(amazonika-api-sigef-geonode:geo71-20261111 amazonika-web-candidato:geo44-20261111)
ROLL=/opt/amazonika-geo90-ps4-homolog/.env.ps4.homolog.pre-geo125-dc5b3ad
[ -f "$ROLL" ] && mapfile -t -O ${#PINS[@]} PINS < <(grep -E '^PS4_(WEB_)?IMAGE=' "$ROLL" | cut -d= -f2-)
i=0
for img in "${PINS[@]}"; do
  docker image inspect "$img" >/dev/null 2>&1 || { echo "   (não existe) $img"; continue; }
  i=$((i+1)); echo "   $img"
  docker ps -a --format '{{.Names}}' | grep -qx "amazonika-pin-rollback-$i" \
    || run docker create --name "amazonika-pin-rollback-$i" "$img" true
done

echo ">> Imagens sem uso (todas as não usadas por nenhum container)"
if [ "$GO" = 1 ]; then docker image prune -af | tail -1; else
  used=$(docker ps -a --format '{{.Image}}' | sort -u)
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -vxF "$used" | grep -v '<none>' | sed 's/^/   /' | head -80
fi

echo ">> Cache de build, logs e sobras de hoje"
run docker builder prune -af
run journalctl --vacuum-size=50M
for t in 202611271158 202611271406 202611271435; do run rm -f /opt/amazonika-backups/geo-antes-geo44p-$t.sql.gz; done
run rm -rf /opt/amazonika-builds/geo44p-*

echo ">> Backups antigos (só com BACKUPS_BAIXADOS=1, depois de baixar no PC)"
for b in 20261109-160002 pre-mapbox-20261028-004147 pre-limpeza-sigef-20261109-234056 anm-20261108; do
  if [ "${BACKUPS_BAIXADOS:-0}" = 1 ]; then run rm -rf "/opt/amazonika-backups/$b"; else echo "   mantido: $b"; fi
done
if [ "${BACKUPS_BAIXADOS:-0}" = 1 ]; then run rm -rf /opt/amazonika-backups/ambientes-*; fi

echo ">> Depois:"; df -h / | tail -1
