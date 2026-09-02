#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${project_dir}/migracao-vps"
mkdir -p "${output_dir}"

cd "${project_dir}"
docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER:-amazonika}" \
  -d "${POSTGRES_DB:-amazonika_geo}" \
  --format=custom --no-owner --no-acl \
  > "${output_dir}/amazonika_geo.dump"

docker compose exec -T api tar -C /data/uploads -czf - . \
  > "${output_dir}/uploads.tar.gz"

shasum -a 256 "${output_dir}/amazonika_geo.dump" "${output_dir}/uploads.tar.gz" \
  > "${output_dir}/SHA256SUMS.txt"

echo "Migração criada em: ${output_dir}"
