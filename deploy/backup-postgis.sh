#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_dir="${project_dir}/backups"
mkdir -p "${backup_dir}"
cd "${project_dir}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="${backup_dir}/amazonika_geo-${timestamp}.dump.part"
final="${backup_dir}/amazonika_geo-${timestamp}.dump"
compose=(docker compose --env-file .env.production -f docker-compose.production.yml)

"${compose[@]}" exec -T db pg_dump \
  -U amazonika_geo -d amazonika_geo \
  --format=custom --no-owner --no-acl > "${temporary}"
mv "${temporary}" "${final}"
sha256sum "${final}" > "${final}.sha256"
find "${backup_dir}" -maxdepth 1 -type f -mtime +14 \
  \( -name 'amazonika_geo-*.dump' -o -name 'amazonika_geo-*.dump.sha256' \) -delete

echo "Backup concluído: ${final}"
