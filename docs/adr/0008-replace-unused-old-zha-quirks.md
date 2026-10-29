# Replace an unused woow_zha_quirks before 1.4; new nodered and pyscript only on new instances

2.4.3 moves three seeded components to their latest upstream releases:
`woow_zha_quirks` 1.2.0 → 1.4.1, `nodered` 4.2.3+ → 4.3.2 and `pyscript` 2.0.1+ →
2.1.0. Each component was decided on its own; the ha-rebrand `armbian-seed` was
a reference, not a target, because aligning to it literally would have moved
`config_editor`, `nodered` and `pyscript` back to older versions.

## A third exception to seed-if-missing

Under seed-if-missing ([ADR 0005](0005-seed-custom-components-on-boot.md)) an
existing instance would keep `woow_zha_quirks` 1.2.0 forever. We make a third
exception, next to unused old component groups
([ADR 0006](0006-replace-unused-old-component-groups.md)) and a hacs without
`hacs_frontend/` ([ADR 0007](0007-replace-hacs-without-frontend.md)): on every
boot, before Home Assistant, `seed_groups.py` removes a
`custom_components/woow_zha_quirks` whose manifest version is 1.x before 1.4 and
that is not **in use**, and the seed-if-missing copy that follows puts the seed's
1.4.1 in its place. The log says so in one line.

It is in use when `.storage/core.config_entries` has a `woow_zha_quirks` entry,
or `configuration.yaml` has a top-level `woow_zha_quirks` key (the same key check
as ADR 0006). An in-use folder is left alone and the log points to the manual
upgrade in the CHANGELOG.

Why this one: upstream 1.4 moved the integration from a `configuration.yaml` key
to a config entry made in the UI, and asks a person to confirm the move (a
repair notification creates the entry). The add-on's default
`configuration.yaml` deliberately has no `woow_zha_quirks:` key, so every
factory instance has 1.2.0 that never loaded; replacing it changes nothing a
user can see, while the one setup path the UI offers needs 1.4. Where the key
was added by hand, the move needs that person, so we do not touch it.

## No general replacement rule

We did not write one rule for "replace an old seeded component". The manifest
version is not reliable (hacs `0.0.0`, scheduler `v0.0.0`, config_editor 5.1.0
still says 5.0.0), and comparing contents with the seed would replace a
component a user upgraded with HACS by our older one. Each exception names its
component and its own safe condition. When a fourth exception comes, we will
look again at whether a general rule is worth it.

## nodered and pyscript only on new instances

Both keep plain seed-if-missing: an existing folder is never replaced. They are
not broken at their old versions, may be in use, and may have been updated with
HACS; replacing them could downgrade a user's own version or change a running
integration without anyone choosing it. The CHANGELOG says how to update them
by hand.

## Consequences

- The default `configuration.yaml` note now points to the UI instead of the
  `woow_zha_quirks:` key; it is still written only on a fresh instance.

- Only the `custom_components/woow_zha_quirks` code folder is ever removed.
  `.storage`, config entries and `configuration.yaml` are never touched, and no
  config entry is created for an instance in use.
- Any doubt keeps the folder: a manifest version that cannot be read, an
  unreadable `core.config_entries` or `configuration.yaml`, or a failing move.
  Home Assistant still starts.
- Nothing is removed unless the seed's own `woow_zha_quirks` is 1.4 or later.
- The folder is moved to `.woow_seed_removed/woow_zha_quirks.done` and then
  deleted, so it is removed whole or not at all; a leftover is deleted on the
  next boot.
- If `seed_groups.py` cannot run, `woow_seed.sh` does not repeat this check: an
  existing `woow_zha_quirks` is then left as it is.
- `tests/test_seed.py` covers the check against a fake `/config`.
