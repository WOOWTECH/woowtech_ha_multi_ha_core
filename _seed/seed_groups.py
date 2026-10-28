"""Replace unused old split components with their consolidated upstream successor.

Called by woow_seed.sh before the seed-if-missing copy. For each component group
whose old folders are present in /config/custom_components:

- not in use: delete the group's old folders, so the copy that follows seeds the
  successor;
- in use (or the check could not be made): leave the group alone and print the
  successor's name on stdout, so the copy skips it.

Only component code folders are ever deleted; config entries, .storage and YAML
are never touched. A missing core.config_entries means Home Assistant never ran
with these components, so it does not count as in use. Log lines go to stderr.
See the 2.4.0 CHANGELOG entry.

Usage: python seed_groups.py <config_dir>
"""

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

PREFIX = "[woow_seed]"
TRASH = ".woow_seed_removed"  # under /config, outside custom_components
# An unindented, optionally quoted key, then a colon: `key:`, `key :`, `"key":`, `'key':`.
TOP_LEVEL_KEY = re.compile(r"""(?P<q>["']?)(?P<key>\w+)(?P=q)[ \t]*:""")


@dataclass(frozen=True)
class Group:
    name: str
    old_domains: tuple
    successor: str
    data_dirs: tuple = ()  # old data directories under /config, not named after a domain

    def signal_domains(self, custom_components):
        """The old domains whose entries, storage and YAML keys count as in use.

        Signals of the successor's own domain belong to the successor once it is installed.
        """
        if self.successor in self.old_domains and is_successor(custom_components / self.successor):
            return tuple(d for d in self.old_domains if d != self.successor)
        return self.old_domains


GROUPS = [
    Group("permission", ("ha_permission_manager", "ha_area_control", "ha_label_control"),
          "ha_permission_manager"),
    Group("records", ("ha_finance", "ha_asset_record", "ha_health_record", "ha_note_record"),
          "woow_ha_records"),
    # woow_dmx/knx/modbus 2.x keep their YAML in /config/<protocol>.
    Group("protocol", ("woow_dmx", "woow_knx", "woow_modbus"), "woow_multi_protocol",
          data_dirs=("dmx", "knx", "modbus")),
]


def log(message):
    print(f"{PREFIX} {message}", file=sys.stderr, flush=True)


def is_successor(path):
    """Whether a folder of the successor's domain is the successor, not an old version.

    Only ha_permission_manager keeps its domain: 2.x is the successor, 1.x is old.
    """
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        return int(str(manifest["version"]).split(".")[0]) >= 2
    except (OSError, ValueError, KeyError, TypeError):
        return False


def old_folders(group, custom_components):
    """The group's old folders present in custom_components."""
    return [name for name in group.old_domains
            if (custom_components / name).is_dir()
            and not (name == group.successor and is_successor(custom_components / name))]


def in_use(group, config, domains):
    """Why the group counts as in use, or None. Raises when that cannot be told.

    Any one of these counts, for the given old domains: a config entry; a .storage
    file named after one; a non-empty old data directory; a top-level
    configuration.yaml key.
    """
    storage = config / ".storage"
    entries_file = storage / "core.config_entries"
    if entries_file.exists():
        entries = json.loads(entries_file.read_text(encoding="utf-8"))["data"]["entries"]
        for entry in entries:
            if entry.get("domain") in domains:
                return f"config entry {entry['domain']}"

    if storage.is_dir():
        for path in sorted(storage.iterdir()):
            if path.name.startswith(domains):
                return f".storage/{path.name}"

    for name in group.data_dirs:
        path = config / name
        if (path.is_dir() and any(path.iterdir())) or (path.is_file() and path.stat().st_size):
            return f"/config/{name} not empty"

    configuration = config / "configuration.yaml"
    if configuration.exists():
        for line in configuration.read_text(encoding="utf-8").splitlines():
            match = TOP_LEVEL_KEY.match(line)
            if match and match["key"] in domains:
                return f"configuration.yaml key {match['key']}"
    return None


def remove(names, custom_components, trash):
    """Move the folders out of custom_components, then delete them.

    The moves are undone if one fails, so a group is either fully removed or
    untouched. Returns whether it was removed.
    """
    trash.mkdir(exist_ok=True)
    moved = []
    try:
        for name in names:
            (custom_components / name).rename(trash / name)
            moved.append(name)
    except OSError as err:
        log(f"could not remove old component {names[len(moved)]} ({err}); kept the group")
        for name in reversed(moved):
            (trash / name).rename(custom_components / name)
        return False
    shutil.rmtree(trash, ignore_errors=True)
    return True


def main(config):
    custom_components = config / "custom_components"
    trash = config / TRASH
    shutil.rmtree(trash, ignore_errors=True)  # left over from an interrupted boot
    for group in GROUPS:
        present = old_folders(group, custom_components)
        if not present:
            continue
        try:
            reason = in_use(group, config, group.signal_domains(custom_components))
        except Exception as err:  # noqa: BLE001 - any doubt keeps the group
            reason = f"could not check ({err})"
        if reason:
            log(f"kept the old {group.name} components: in use ({reason}); "
                f"{group.successor} not seeded. Migrate by hand, see CHANGELOG 2.4.0.")
            print(group.successor)
            continue
        if not remove(present, custom_components, trash):
            print(group.successor)
            continue
        for name in present:
            log(f"removed old component: {name} ({group.name} group not in use)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
