# Replace unused old component groups with their consolidated successors

Upstream merged ten split components into three (`ha_permission_manager` 2.x,
`woow_ha_records`, `woow_multi_protocol`), and 2.4.0 seeds only the three. Under
seed-if-missing ([ADR 0005](0005-seed-custom-components-on-boot.md)) an existing instance would keep the ten old folders and
gain the three new ones. We make one exception: on every boot, before Home Assistant,
`seed_groups.py` checks each **component group** whose old folders are present; if
the group is not **in use**, its old folders are deleted so the successor gets
seeded. A group in use is left exactly as it is and its successor is not seeded;
the log says why.

We did not keep pure seed-if-missing because the two layouts cannot sit side by
side: `woow_ha_records` reuses the old records panels' `url_path`s
(`ha-finance`, ...), so once both are set up the second one fails to register its
panel, and upstream does not support the old `ha_area_control` and
`ha_label_control` next to `ha_permission_manager` 2.x. Upstream is a clean break
(new domains, no data import), so there is nothing to migrate automatically. And
the shipped boxes have the old components installed but never set up, so
replacing unused groups changes nothing a user can see.

## Consequences

- Only code folders in `custom_components` are ever deleted. Config entries,
  `.storage` and YAML are never touched; any doubt (an unreadable
  `core.config_entries`, a failing check) counts as in use.
- For the protocol group, a non-empty `/config/dmx`, `/config/knx` or
  `/config/modbus` counts as in use, whether it is a folder or a regular file.
- `ha_permission_manager` keeps its domain, so a 2.x folder counts as the
  successor and is never deleted or overwritten; only a 1.x folder is old.
  Once the successor is installed, the entry and storage key it shares with
  1.x no longer count as the group being in use.
- A missing `core.config_entries` means Home Assistant never ran with the old
  components, so it does not count as in use.
- A group's old folders are first moved out of `custom_components` together
  and only then deleted; if a move fails, the moves are undone. A group is
  either fully replaced or untouched. They are moved into
  `/config/.woow_seed_removed`, which is deleted on every boot; it only ever
  holds old code folders.
- If the check fails outright, an instance that already has components keeps
  every group; a fresh instance is seeded as usual.
- A user in use migrates by hand (2.4.0 CHANGELOG). Once they delete the old
  folders the successor is seeded on the next boot, whatever data the old
  components left behind.
- `tests/test_seed.py` runs the real entrypoint against a fake `/config`.
