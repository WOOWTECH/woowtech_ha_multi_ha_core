#!/usr/bin/env bash
# Vendor the curated custom components listed in _seed/seed-manifest.tsv into
# _seed/custom_components/ at their pinned refs. The folder is rebuilt from scratch,
# so a component dropped from the manifest disappears from the seed.
# This is the reproducible source of truth for ADR 0005.
# Uses GitHub tarballs (via gh, authenticated) — fast and works for private repos.
# A component whose srcpath is asset:<file>[/<path>] comes instead from that asset of
# the release tagged <ref> (a zip); its sha256 in the fifth column must match, or
# nothing is written. _seed/ only changes when every component was fetched.
# Requires: gh (authenticated), tar, unzip, sha256sum. Run from anywhere:
#   bash scripts/vendor-components.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${ROOT}/_seed/seed-manifest.tsv"
OUT="${ROOT}/_seed/custom_components"
LOCK="${ROOT}/_seed/seed-lock.tsv"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

STAGE="${TMP}/custom_components"
STAGE_LOCK="${TMP}/seed-lock.tsv"
mkdir -p "${STAGE}"
printf '# name\trepo\tref\tsha\tmanifest_version\n' > "${STAGE_LOCK}"

count=0
while IFS=$'\t' read -r name repo ref srcpath asset_sha256 || [ -n "${name:-}" ]; do
  case "${name}" in ''|'#'*) continue;; esac
  echo "== ${name}  (${repo}@${ref})"

  case "${srcpath}" in
  asset:*)
    spec="${srcpath#asset:}"
    asset="${spec%%/*}"
    inner=""
    case "${spec}" in */*) inner="/${spec#*/}";; esac
    if [ -z "${asset_sha256:-}" ]; then
      echo "  !! ${name}: release asset ${asset} has no sha256 in the fifth column" >&2
      exit 1
    fi
    assetdir="${TMP}/$(echo "${repo}@${ref}@${asset}" | tr '/@' '__')"
    if [ ! -d "${assetdir}" ]; then
      mkdir -p "${assetdir}/unzipped"
      gh release download "${ref}" -R "${repo}" -p "${asset}" -O "${assetdir}/${asset}"
      got="$(sha256sum "${assetdir}/${asset}" | cut -d' ' -f1)"
      if [ "${got}" != "${asset_sha256}" ]; then
        echo "  !! ${name}: ${asset} of release ${ref} has sha256 ${got}; the manifest pins ${asset_sha256}" >&2
        exit 1
      fi
      unzip -q "${assetdir}/${asset}" -d "${assetdir}/unzipped"
    fi
    sha="sha256:${asset_sha256}"
    src="${assetdir}/unzipped${inner}"
    ;;
  *)
    key="$(echo "${repo}@${ref}" | tr '/@' '__')"
    tardir="${TMP}/${key}"
    if [ ! -d "${tardir}" ]; then
      mkdir -p "${tardir}"
      if [ "${ref}" = "HEAD" ]; then
        gh api "repos/${repo}/tarball" > "${tardir}/src.tgz"
      else
        gh api "repos/${repo}/tarball/${ref}" > "${tardir}/src.tgz"
      fi
      tar xzf "${tardir}/src.tgz" -C "${tardir}"
    fi

    top=""
    for d in "${tardir}"/*/; do
      [ -d "${d}" ] && { top="$(basename "${d}")"; break; }
    done
    sha="$(echo "${top}" | sed 's/.*-//')"
    src="${tardir}/${top}/${srcpath}"
    ;;
  esac
  if [ ! -d "${src}" ]; then
    echo "  !! source path missing: ${srcpath}" >&2
    exit 1
  fi

  cp -a "${src}" "${STAGE}/${name}"
  bash "${ROOT}/scripts/strip-dev-leftovers.sh" "${STAGE}/${name}"

  ver="$(grep -m1 '"version"' "${STAGE}/${name}/manifest.json" 2>/dev/null | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')"
  [ -z "${ver}" ] && ver="-"
  printf '%s\t%s\t%s\t%s\t%s\n' "${name}" "${repo}" "${ref}" "${sha}" "${ver}" >> "${STAGE_LOCK}"
  count=$((count + 1))
done < "${MANIFEST}"

rm -rf "${OUT}"
cp -a "${STAGE}" "${OUT}"
cp "${STAGE_LOCK}" "${LOCK}"

echo ""
echo "Vendored ${count} components -> ${OUT}"
echo "Lockfile -> ${LOCK}"
echo "Next: bash scripts/sync-seed.sh"
