#!/usr/bin/env bash
# Materialize _seed/ into every add-on's build context.
# HA builds each add-on only from its own folder, so the seed must live inside each one.
# Run after vendor-components.sh, or whenever _seed/ changes:
#   bash scripts/sync-seed.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED="${ROOT}/_seed"

for n in 1 2 3 4 5; do
  dest="${ROOT}/woow_ha_core_${n}/rootfs/opt/woow_seed"
  rm -rf "${dest}"
  mkdir -p "${dest}"
  cp -a "${SEED}/custom_components" "${dest}/custom_components"
  cp -a "${SEED}/config_defaults" "${dest}/config_defaults"
  cp -a "${SEED}/woow_seed.sh" "${dest}/woow_seed.sh"
  chmod +x "${dest}/woow_seed.sh"
  echo "synced -> woow_ha_core_${n}/rootfs/opt/woow_seed"
done
