#!/usr/bin/env sh
# Woowtech HA Core — seed curated custom components + defaults into /config, then start HA.
# Runs as the container entrypoint, before Home Assistant.
# Policy: seed-if-missing, per component folder. Never overwrites an existing folder or user edits;
# the one exception, unused old component groups, is handled by seed_groups.py.
# See docs/adr/0005-seed-custom-components-on-boot.md and 0006-replace-unused-old-component-groups.md
set -eu

# The WOOW_SEED_* overrides exist for tests/test_seed.py; the image never sets them.
SEED_DIR="${WOOW_SEED_DIR:-/opt/woow_seed}"
CONFIG_DIR="${WOOW_SEED_CONFIG_DIR:-/config}"
PYTHON="${WOOW_SEED_PYTHON:-/usr/local/bin/python}"

mkdir -p "${CONFIG_DIR}/custom_components"

# One exception to seed-if-missing: an old split component group that is installed
# but not in use is removed, so its consolidated successor gets seeded below.
# seed_groups.py prints the successors to skip (groups in use). If the check itself
# fails on an instance that already has components, every group is kept and no
# successor is seeded; a fresh instance is seeded as usual. HA must still start.
SUCCESSORS="ha_permission_manager woow_ha_records woow_multi_protocol"
if ! skip="$("${PYTHON}" "$(dirname "$0")/seed_groups.py" "${CONFIG_DIR}")"; then
  skip=""
  if [ -n "$(ls -A "${CONFIG_DIR}/custom_components")" ]; then
    echo "[woow_seed] component group check failed; kept old components, not seeding: ${SUCCESSORS}"
    skip="${SUCCESSORS}"
  fi
fi
# Unquoted on purpose: word splitting turns the lines into one space-separated list.
skip=" $(echo ${skip} | tr -d '\r') "

# Seed each managed custom component only when its folder is absent.
if [ -d "${SEED_DIR}/custom_components" ]; then
  for src in "${SEED_DIR}/custom_components/"*/; do
    [ -d "${src}" ] || continue
    name="$(basename "${src}")"
    case "${skip}" in *" ${name} "*) continue ;; esac
    dest="${CONFIG_DIR}/custom_components/${name}"
    if [ ! -e "${dest}" ]; then
      cp -a "${src}" "${dest}"
      echo "[woow_seed] seeded custom_component: ${name}"
    fi
  done
fi

# Seed default configuration files only on a fresh instance (no configuration.yaml yet).
if [ ! -e "${CONFIG_DIR}/configuration.yaml" ] && [ -d "${SEED_DIR}/config_defaults" ]; then
  for f in "${SEED_DIR}/config_defaults/"*; do
    [ -e "${f}" ] || continue
    bn="$(basename "${f}")"
    if [ ! -e "${CONFIG_DIR}/${bn}" ]; then
      cp -a "${f}" "${CONFIG_DIR}/${bn}"
      echo "[woow_seed] seeded default: ${bn}"
    fi
  done
fi

cd "${CONFIG_DIR}"
exec "${PYTHON}" -m homeassistant --config "${CONFIG_DIR}"
