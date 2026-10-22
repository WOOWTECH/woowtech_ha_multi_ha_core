#!/usr/bin/env bash
# Remove component development leftovers from vendored custom components.
# Upstream repos keep .devcontainer/, tests/ and docs/ inside the component folder
# (climate_template, woow_cover_entity, ...); none of it is read by Home Assistant,
# and the shipping pipeline treats it as a wrong shipping state (pipeline issue unattended-pipeline/79).
# vendor-components.sh calls this for every component. Run by hand on a seed with:
#   bash scripts/strip-dev-leftovers.sh _seed/custom_components/*
set -euo pipefail

for comp in "$@"; do
  [ -d "${comp}" ] || continue
  # Any depth: editor/VCS/devcontainer folders and files, shell histories, bytecode.
  # `_history` matches whole names only, so foo_history.py stays.
  find "${comp}" -depth \( -name .devcontainer -o -name .git -o -name .github \
    -o -name .DS_Store -o -name '.vscode*' -o -name '*_history' -o -name '*.pyc' \) \
    -exec rm -rf {} +
  # Only the component's own top-level tests/ and docs/.
  rm -rf "${comp:?}/tests" "${comp:?}/docs"
done
