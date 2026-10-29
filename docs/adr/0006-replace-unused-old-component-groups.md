# Replace unused old component groups with their consolidated successors

Upstream merged ten split components into three (`ha_permission_manager` 2.x,
`woow_ha_records`, `woow_multi_protocol`), and 2.4.1 seeds only the three. Under
seed-if-missing ([ADR 0005](0005-seed-custom-components-on-boot.md)) an existing
instance would keep the ten old folders and gain the three new ones. We make one exception: on every boot, before Home Assistant,
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
  Once the successor is present in `custom_components`, the entry and storage
  key it shares with 1.x no longer count as the group being in use. A
  `ha_permission_manager` folder whose manifest version cannot be read counts
  as in use.
- A missing `core.config_entries` means Home Assistant never ran with the old
  components, so it does not count as in use.
- A group's old folders are first moved out of `custom_components` together
  and only then deleted; if a move fails, the moves are undone. A move back
  that fails, or a boot interrupted mid-move, is undone on the next boot
  before anything else, so the group is normally whole again after that boot.
  Until it is, the group stays split and its successor is not seeded. A folder
  left in `.woow_seed_removed` that cannot be moved back (a folder of that
  name is in `custom_components` again, or the move keeps failing) is neither
  restored nor deleted: the group stays split, and its successor is not
  seeded, until someone removes the colliding folder or fixes the cause; the
  log says so on every boot.
- Each group is checked on its own: an error in one keeps only that group.
  If `seed_groups.py` cannot run, or is killed, `woow_seed.sh` does not
  seed the successor of any group that still has an old folder in
  `custom_components` or a folder in `.woow_seed_removed`, and seeds the
  rest as usual (a fresh instance gets all three). So a group already
  replaced is not left without its successor, and a successor never takes
  the place a folder must be moved back to. A folder named after the
  successor (`ha_permission_manager`) counts as old unless its manifest
  shows version 2 or higher, as in `is_successor()`; a manifest that cannot
  be read counts as old, so a 1.x-only permission group is kept and logged.
- A user in use migrates by hand (2.4.1 CHANGELOG). Once they delete the old
  folders the successor is seeded on the next boot, whatever data the old
  components left behind.
- `tests/test_seed.py` runs the real entrypoint against a fake `/config`.
