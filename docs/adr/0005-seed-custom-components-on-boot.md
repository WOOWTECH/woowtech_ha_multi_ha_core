# Seed custom components into /config on boot

*Written after the fact on 2026-10-28. It records the decision made in commit
`122f2ee` (v2.3.0, 2026-07-30), whose message and code cited this ADR before it
was committed.*

Before 2.3.0 every instance started brand-only with zero custom components. 2.3.0
reverses that for a vetted set: the curated components are vendored at the refs in
`_seed/seed-manifest.tsv` (some were `HEAD` until 2026-10-22, when they were
pinned to the seed-lock commits) into `_seed/custom_components/` (`scripts/vendor-components.sh`, recorded in
`_seed/seed-manifest.tsv` and `_seed/seed-lock.tsv`), and `scripts/sync-seed.sh`
copies `_seed/` into each add-on's `rootfs/opt/woow_seed`, because Home Assistant
builds each add-on only from its own folder. The image's entrypoint,
`woow_seed.sh`, runs on every boot before Home Assistant and copies a component
into `/config/custom_components` only if nothing exists at that path yet. It
never overwrites an existing file or folder. Default configuration files are seeded only on a
fresh instance (no `configuration.yaml` yet).

The sources do not record why seed-if-missing was chosen over overwriting or
updating on boot, beyond never touching user edits.

## Consequences

- A user's edits to a seeded folder survive every boot and add-on update. A
  seeded folder the user deletes comes back on the next boot.
- An update to a component that is already seeded does not reach existing
  instances; only a missing folder gets the new version.
- `_seed/` is the single source of truth; the five `rootfs` copies are
  generated and must be re-synced whenever `_seed/` changes.
- Seed-if-missing never removes anything, so removing or replacing an
  already-seeded component needs an exception to this policy; see
  [ADR 0006](0006-replace-unused-old-component-groups.md).
