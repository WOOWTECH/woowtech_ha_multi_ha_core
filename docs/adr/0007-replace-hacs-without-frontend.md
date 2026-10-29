# Seed HACS from its release asset and replace a hacs without hacs_frontend/

Up to 2.4.1 the seed manifest took every component from a GitHub tarball of its
repository. For HACS that is the source tree: it has no `hacs_frontend/`, which
HACS builds and adds only to its release asset `hacs.zip`, and its version is
`0.0.0`. HACS imports `hacs_frontend` at module level (`__init__.py` imports
`frontend.py`, which imports `.hacs_frontend`), so the seeded hacs cannot even be
imported: the integration fails to load and its config flow cannot open. 2.4.2
seeds HACS 2.0.5 from `hacs.zip`.

## Release assets in the seed manifest

A manifest row whose `srcpath` is `asset:<file>[/<path>]` takes `<path>` (default:
the zip's root) of that asset of the release tagged `<ref>`. The row's fifth
column is the asset's sha256, and vendoring fails without writing anything to
`_seed/` if the download differs: a release asset can be replaced after the tag
is published, so the tag name alone does not pin it. The lock records
`sha256:<hash>` in its `sha` column. The other rows keep the tarball form and
vendor to the same bytes as before.

## A second exception to seed-if-missing

Under seed-if-missing ([ADR 0005](0005-seed-custom-components-on-boot.md)) an
existing instance would keep the broken hacs forever. We make a second exception,
next to unused old component groups ([ADR 0006](0006-replace-unused-old-component-groups.md)):
on every boot, before Home Assistant, `seed_groups.py` removes a
`custom_components/hacs` folder that has no `hacs_frontend/` directory, and the
seed-if-missing copy that follows puts the seed's hacs in its place. The log says
so in one line.

No "in use" check is needed: a hacs without `hacs_frontend/` cannot be imported,
so it never loaded and nobody can have set it up. A hacs that has
`hacs_frontend/` (for example one a user reinstalled, perhaps newer) is left
alone.

## Consequences

- Only the `custom_components/hacs` code folder is ever removed. `.storage`,
  config entries and `configuration.yaml` are never touched.
- Nothing is removed unless the seed's own hacs has `hacs_frontend/`, so a bad
  seed cannot make every boot delete and recopy hacs.
- The folder is first moved to `.woow_seed_removed/hacs.done` and then deleted,
  so it is removed whole or not at all; a leftover `hacs.done` is deleted on the
  next boot. If the move fails, hacs is left as it is, the log says so, and Home
  Assistant still starts.
- If `seed_groups.py` cannot run, `woow_seed.sh` does not repeat this check: an
  existing hacs is then left as it is.
- `hacs_frontend/` makes the seed about 50 MB larger per add-on image.
- `tests/test_seed.py` covers the check against a fake `/config`.
