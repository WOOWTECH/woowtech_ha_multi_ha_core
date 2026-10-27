"""Replace unused old split components with their consolidated upstream successor.

Called by woow_seed.sh before the seed-if-missing copy. For each component group
whose old folders are present in /config/custom_components:

- not in use: delete the group's old folders, so the copy that follows seeds the
  new component;
- in use (or the check could not be made): leave the group alone and print the
  new component's name on stdout, so the copy skips it.

Only component code folders are ever deleted; config entries, .storage and YAML
are never touched. Log lines go to stderr. See the 2.4.0 CHANGELOG entry.

Usage: python seed_groups.py <config_dir>
"""

import json
import shutil
import sys
from pathlib import Path

PREFIX = "[woow_seed]"


class Group:
    def __init__(self, name, old, new):
        self.name = name
        self.old = old
        self.new = new


GROUPS = [
    Group("permission", ["ha_permission_manager", "ha_area_control", "ha_label_control"],
          "ha_permission_manager"),
    Group("records", ["ha_finance", "ha_asset_record", "ha_health_record", "ha_note_record"],
          "woow_ha_records"),
    Group("protocol", ["woow_dmx", "woow_knx", "woow_modbus"], "woow_multi_protocol"),
]


def log(message):
    print(f"{PREFIX} {message}", file=sys.stderr, flush=True)


def is_successor(path):
    """ha_permission_manager keeps its domain: 2.x is the successor, 1.x is old."""
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        return int(str(manifest["version"]).split(".")[0]) >= 2
    except (OSError, ValueError, KeyError, TypeError):
        return False


def old_folders(group, custom_components):
    """The group's old folders present in custom_components."""
    return [name for name in group.old
            if (custom_components / name).is_dir()
            and not (name == group.new and is_successor(custom_components / name))]


def in_use(group, config):
    """Why the group counts as in use, or None. Raises when that cannot be told.

    Any one of these counts: a config entry of an old domain; a .storage file
    named after an old domain; for the protocol group, a non-empty old data
    directory; a top-level configuration.yaml key that is an old domain.
    """
    storage = config / ".storage"
    entries_file = storage / "core.config_entries"
    if entries_file.exists():
        entries = json.loads(entries_file.read_text(encoding="utf-8"))["data"]["entries"]
        for entry in entries:
            if entry.get("domain") in group.old:
                return f"config entry {entry['domain']}"

    if storage.is_dir():
        for path in sorted(storage.iterdir()):
            if path.name.startswith(tuple(group.old)):
                return f".storage/{path.name}"

    if group.name == "protocol":
        # woow_dmx/knx/modbus 2.x keep their YAML here, not under their domain name.
        for name in ("dmx", "knx", "modbus"):
            path = config / name
            if path.is_dir() and any(path.iterdir()) or path.is_file() and path.stat().st_size:
                return f"/config/{name} not empty"

    configuration = config / "configuration.yaml"
    if configuration.exists():
        for line in configuration.read_text(encoding="utf-8").splitlines():
            key = line.split(":", 1)[0]
            if key in group.old and ":" in line:
                return f"configuration.yaml key {key}"
    return None


def main(config):
    custom_components = config / "custom_components"
    for group in GROUPS:
        present = old_folders(group, custom_components)
        if not present:
            continue
        try:
            reason = in_use(group, config)
        except Exception as err:  # noqa: BLE001 - any doubt keeps the group
            reason = f"could not check ({err})"
        if reason:
            log(f"kept the old {group.name} components: in use ({reason}); "
                f"{group.new} not seeded. Migrate by hand, see CHANGELOG 2.4.0.")
            print(group.new)
            continue
        for name in present:
            try:
                shutil.rmtree(custom_components / name)
            except OSError as err:
                log(f"could not remove old component {name} ({err}); {group.new} not seeded")
                print(group.new)
                break
            log(f"removed old component: {name} ({group.name} group not in use)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
