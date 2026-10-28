"""Behaviour of the seed entrypoint (_seed/woow_seed.sh), without Home Assistant.

Each test builds a fake /config and a small fake seed, runs the real entrypoint
with a stand-in python that stops where Home Assistant would start, and checks
which component folders end up in /config/custom_components.

Run from the repository root:  python -m unittest discover -s tests
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "_seed" / "woow_seed.sh"
SH = shutil.which("sh") or shutil.which("bash")
sys.path.insert(0, str(ROOT / "_seed"))
import seed_groups  # noqa: E402

# Runs seed_groups.py with os.rename failing for the folders named in
# WOOW_TEST_FAIL: "<name>>out" fails moving it out of custom_components,
# "<name>>in" fails moving it back in, and "<name>>out>kill" kills the script
# instead of that move ("<group>>out>kill" stops before the group is marked .done).
FAULT_SHIM = """
import os, runpy, sys
from pathlib import Path
faults = set(os.environ["WOOW_TEST_FAIL"].split(","))
real_rename = os.rename
def rename(src, dst):
    way = "in" if Path(dst).parent.name == "custom_components" else "out"
    if f"{Path(src).name}>{way}>kill" in faults:
        os._exit(137)
    if f"{Path(src).name}>{way}" in faults:
        raise OSError(f"injected failure moving {Path(src).name} {way}")
    return real_rename(src, dst)
os.rename = rename
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""

NEW = ["ha_permission_manager", "woow_ha_records", "woow_multi_protocol"]
OTHER = ["hacs", "localtuya"]
GROUP_OLD = {
    "permission": ["ha_permission_manager", "ha_area_control", "ha_label_control"],
    "records": ["ha_finance", "ha_asset_record", "ha_health_record", "ha_note_record"],
    "protocol": ["woow_dmx", "woow_knx", "woow_modbus"],
}
GROUP_NEW = {
    "permission": "ha_permission_manager",
    "records": "woow_ha_records",
    "protocol": "woow_multi_protocol",
}
OLD = [d for names in GROUP_OLD.values() for d in names]


def component(path, version, marker="seed"):
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps({"domain": path.name, "version": version}))
    (path / "marker").write_text(marker)


class SeedTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.seed = tmp / "seed"
        self.config = tmp / "config"
        self.cc = self.config / "custom_components"
        component(self.seed / "custom_components" / "ha_permission_manager", "2.0.15")
        component(self.seed / "custom_components" / "woow_ha_records", "3.0.0")
        component(self.seed / "custom_components" / "woow_multi_protocol", "3.0.0")
        for name in OTHER:
            component(self.seed / "custom_components" / name, "1.0.0")
        self.config.mkdir()
        self.python = tmp / "python"
        self.shim = tmp / "fault_shim.py"
        self.shim.write_text(FAULT_SHIM)
        self.faults = ""
        self.fake_python()

    def fake_python(self, fail_groups=False):
        real = Path(sys.executable).as_posix()
        groups = 'case "$1" in *seed_groups.py) exit 3;; esac\n' if fail_groups else ""
        shim = self.shim.as_posix()
        self.python.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-m" ] && [ "$2" = "homeassistant" ]; then\n'
            '  echo "[test] homeassistant started"; exit 0\n'
            "fi\n" + groups
            + f'if [ -n "${{WOOW_TEST_FAIL:-}}" ]; then exec "{real}" "{shim}" "$@"; fi\n'
            + f'exec "{real}" "$@"\n',
            newline="\n",
        )
        self.python.chmod(0o755)  # Linux needs the execute bit; Windows ignores it

    # --- arrange helpers -------------------------------------------------

    def install_old(self, names=OLD):
        for name in names:
            version = "1.0.3" if name == "ha_permission_manager" else "2.1.1"
            component(self.cc / name, version, marker="old")

    def config_entries(self, *domains):
        storage = self.config / ".storage"
        storage.mkdir(exist_ok=True)
        entries = [{"entry_id": str(i), "domain": d} for i, d in enumerate(domains)]
        (storage / "core.config_entries").write_text(
            json.dumps({"version": 1, "minor_version": 5, "key": "core.config_entries",
                        "data": {"entries": entries}}))

    # --- act / assert helpers --------------------------------------------

    def run_seed(self):
        env = dict(os.environ,
                   WOOW_SEED_DIR=self.seed.as_posix(),
                   WOOW_SEED_CONFIG_DIR=self.config.as_posix(),
                   WOOW_SEED_PYTHON=self.python.as_posix(),
                   WOOW_TEST_FAIL=self.faults)
        result = subprocess.run([SH, SCRIPT.as_posix()], env=env, capture_output=True, encoding="utf-8", errors="replace",
                                timeout=60)
        self.log = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, self.log)
        self.assertIn("[test] homeassistant started", self.log)

    def present(self):
        return sorted(p.name for p in self.cc.iterdir()) if self.cc.exists() else []

    def marker(self, name):
        return (self.cc / name / "marker").read_text()

    # --- tests -----------------------------------------------------------

    def test_fresh_install_gets_the_new_layout(self):
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertNotIn("removed", self.log)

    def test_factory_state_installed_but_unused_is_replaced(self):
        # Box 4 as shipped: all 10 old folders, no config entries.
        self.install_old()
        self.config_entries("sun", "backup")
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "seed")
        for name in OLD:
            self.assertIn(f"removed old component: {name}", self.log)

    def assert_only_group_kept(self, kept, reason):
        present = self.present()
        for group, old in GROUP_OLD.items():
            if group == kept:
                for name in old:
                    self.assertIn(name, present)
                    self.assertEqual(self.marker(name), "old")
                if GROUP_NEW[group] not in old:
                    self.assertNotIn(GROUP_NEW[group], present)
            else:
                self.assertEqual(sorted(set(old) & set(present) - {GROUP_NEW[group]}), [])
                self.assertEqual(self.marker(GROUP_NEW[group]), "seed")
        self.assertIn(f"kept the old {kept} components: in use ({reason}", self.log)

    def reset_config(self):
        shutil.rmtree(self.config)
        self.config.mkdir()

    def storage_file(self, name):
        (self.config / ".storage").mkdir(exist_ok=True)
        (self.config / ".storage" / name).write_text("{}")

    def yaml_key(self, domain):
        (self.config / "configuration.yaml").write_text(
            f"default_config:\n\n{domain}:\n  some: value\n")

    def data_dir(self, name):
        (self.config / name).mkdir()
        (self.config / name / "devices.yaml").write_text("[]")

    def test_group_in_use_is_kept(self):
        # (group, expected reason, arrange, arg): each of the four "in use" signals.
        cases = [("permission", "config entry ha_label_control",
                  self.config_entries, "ha_label_control"),
                 ("permission", ".storage/ha_permission_manager",
                  self.storage_file, "ha_permission_manager"),
                 ("records", ".storage/ha_health_record_member1",
                  self.storage_file, "ha_health_record_member1")]
        for group, old in GROUP_OLD.items():
            domain = old[-1]
            cases += [(group, f"config entry {domain}", self.config_entries, domain),
                      (group, f".storage/{domain}", self.storage_file, domain),
                      (group, f"configuration.yaml key {domain}", self.yaml_key, domain)]
        for name in ("dmx", "knx", "modbus"):
            cases.append(("protocol", f"/config/{name} not empty", self.data_dir, name))
        for group, reason, arrange, arg in cases:
            with self.subTest(group=group, reason=reason):
                self.reset_config()
                self.install_old()
                arrange(arg)
                self.run_seed()
                self.assert_only_group_kept(group, reason)

    def test_successor_signals_do_not_hold_a_leftover_old_component(self):
        # A 2.x permission manager writes the same entry and storage key as 1.x.
        component(self.cc / "ha_permission_manager", "2.0.15", marker="user")
        self.install_old(["ha_label_control"])
        self.config_entries("ha_permission_manager")
        self.storage_file("ha_permission_manager")
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertIn("removed old component: ha_label_control", self.log)

    def test_old_permission_manager_signals_count_without_the_successor(self):
        # No permission manager folder at all: its 1.x entry still means in use.
        self.install_old(["ha_area_control", "ha_label_control"])
        self.config_entries("ha_permission_manager")
        self.run_seed()
        self.assertEqual(self.present(),
                         sorted(OTHER + ["ha_area_control", "ha_label_control",
                                         "woow_ha_records", "woow_multi_protocol"]))
        self.assertIn("kept the old permission components: in use "
                      "(config entry ha_permission_manager", self.log)

    def test_configuration_yaml_key_variants(self):
        variants = {"spaces before colon": "ha_finance :\n",
                    "byte order mark": "﻿ha_finance:\n",
                    "double quoted": '"ha_finance": {}\n',
                    "single quoted": "'ha_finance': {}\n"}
        for label, text in variants.items():
            with self.subTest(label):
                self.reset_config()
                self.install_old()
                (self.config / "configuration.yaml").write_text(text, encoding="utf-8")
                self.run_seed()
                self.assert_only_group_kept("records", "configuration.yaml key ha_finance")
        with self.subTest("indented key is not top level"):
            self.reset_config()
            self.install_old()
            (self.config / "configuration.yaml").write_text("homeassistant:\n  ha_finance:\n")
            self.run_seed()
            self.assertEqual(self.present(), sorted(NEW + OTHER))

    def test_failed_undo_keeps_the_group_and_other_groups_are_still_seeded(self):
        self.install_old()
        # ha_finance moves out, ha_asset_record fails, moving ha_finance back fails.
        self.faults = "ha_asset_record>out,ha_finance>in"
        self.run_seed()
        present = self.present()
        self.assertEqual(self.marker("ha_permission_manager"), "seed")
        self.assertIn("woow_multi_protocol", present)
        self.assertNotIn("woow_ha_records", present)
        self.assertNotIn("ha_finance", present)
        # Next start: ha_finance comes back before anything else happens.
        self.faults = "ha_finance>out"
        self.run_seed()
        present = self.present()
        for name in GROUP_OLD["records"]:
            self.assertEqual(self.marker(name), "old")
        self.assertNotIn("woow_ha_records", present)

    def test_shell_fallback_lists_the_same_groups(self):
        table = re.search(r'^COMPONENT_GROUPS="([^"]*)"', SCRIPT.read_text(encoding="utf-8"), re.M).group(1)
        rows = [line.split() for line in table.strip().splitlines()]
        self.assertEqual(rows, [[g.name, g.successor, *g.old_domains] for g in seed_groups.GROUPS])

    def test_killed_check_with_one_group_moved_out_does_not_seed_its_successor(self):
        # Only the permission group is present; the script dies with its folders in the trash.
        self.install_old(GROUP_OLD["permission"])
        self.faults = "permission>out>kill"
        self.run_seed()
        self.assertEqual(self.present(),
                         sorted(OTHER + ["woow_ha_records", "woow_multi_protocol"]))
        # Next start: the folders come back and the unused group is replaced.
        self.faults = ""
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "seed")
        self.assertNotIn("kept the old", self.log)
        self.assertEqual(list((self.config / seed_groups.TRASH).iterdir()), [])

    def test_killed_check_seeds_the_successor_of_a_group_already_replaced(self):
        # Permission is replaced, then the script dies moving the records group out.
        self.install_old(GROUP_OLD["permission"] + GROUP_OLD["records"])
        self.faults = "ha_finance>out>kill"
        self.run_seed()
        self.assertEqual(self.present(),
                         sorted(OTHER + GROUP_OLD["records"]
                                + ["ha_permission_manager", "woow_multi_protocol"]))
        self.assertEqual(self.marker("ha_permission_manager"), "seed")
        self.assertIn("kept the old records components", self.log)
        self.faults = ""
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))

    def trash(self, folder, names):
        for name in names:
            component(self.config / seed_groups.TRASH / folder / name, "2.1.1", marker="old")

    def test_leftover_done_folder_is_deleted_and_the_successor_seeded(self):
        self.trash("records.done", ["ha_finance", "ha_asset_record"])
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertEqual(list((self.config / seed_groups.TRASH).iterdir()), [])

    def test_pending_folder_is_restored_then_the_group_is_judged(self):
        for label, entries, expected in (
                ("not in use", (), sorted(NEW + OTHER)),
                ("in use", ("ha_finance",),
                 sorted(OTHER + GROUP_OLD["records"]
                        + ["ha_permission_manager", "woow_multi_protocol"]))):
            with self.subTest(label):
                self.reset_config()
                self.trash("records", ["ha_finance", "ha_asset_record"])
                self.install_old(["ha_health_record", "ha_note_record"])
                self.config_entries(*entries)
                self.run_seed()
                self.assertIn("restored ha_finance after an interrupted removal", self.log)
                self.assertEqual(self.present(), expected)
                self.assertEqual(list((self.config / seed_groups.TRASH).iterdir()), [])

    def test_restore_name_collision_keeps_the_group(self):
        self.trash("records", ["ha_finance"])
        component(self.cc / "ha_finance", "2.1.1", marker="user")
        self.run_seed()
        self.assertEqual(self.marker("ha_finance"), "user")
        self.assertNotIn("woow_ha_records", self.present())
        self.assertTrue((self.config / seed_groups.TRASH / "records" / "ha_finance").is_dir())
        self.assertIn("could not restore ha_finance", self.log)
        self.assertIn("kept the old records components", self.log)

    def test_unreadable_permission_manager_manifest_keeps_the_group(self):
        component(self.cc / "ha_permission_manager", "2.0.15", marker="user")
        (self.cc / "ha_permission_manager" / "manifest.json").write_text('{"version": ')
        self.install_old(["ha_area_control"])
        self.run_seed()
        self.assertEqual(self.marker("ha_permission_manager"), "user")
        self.assertIn("ha_area_control", self.present())
        self.assertIn("kept the old permission components", self.log)
        self.assertIn("custom_components/ha_permission_manager/manifest.json cannot be read",
                      self.log)
        self.assertIn("Check or replace custom_components/ha_permission_manager.", self.log)
        self.assertEqual(self.marker("woow_ha_records"), "seed")

    def test_failing_group_check_on_a_fresh_install_still_seeds_the_successors(self):
        self.fake_python(fail_groups=True)
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))

    def test_partly_removed_old_group_is_still_replaced(self):
        self.install_old(["ha_finance", "woow_knx"])
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))

    def test_existing_successor_is_not_overwritten(self):
        self.install_old()
        component(self.cc / "woow_ha_records", "3.0.1", marker="user")
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("woow_ha_records"), "user")

    def test_newer_permission_manager_is_not_an_old_component(self):
        component(self.cc / "ha_permission_manager", "2.1.0", marker="user")
        self.install_old(["ha_area_control"])
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "user")
        self.assertNotIn("removed old component: ha_permission_manager", self.log)

    def test_unreadable_config_entries_keep_every_group(self):
        self.install_old()
        (self.config / ".storage").mkdir()
        (self.config / ".storage" / "core.config_entries").write_text('{"data": {"entr')
        self.run_seed()
        self.assertEqual(self.present(), sorted(OLD + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "old")
        self.assertEqual(self.log.count("could not check"), 3)

    def test_failing_group_check_keeps_everything_and_starts_ha(self):
        self.fake_python(fail_groups=True)
        self.install_old()
        self.run_seed()
        self.assertEqual(self.present(), sorted(OLD + OTHER))
        self.assertIn("component group check failed", self.log)

    def test_failing_group_check_on_a_migrated_instance_keeps_nothing(self):
        # Only the successors (2.x permission manager) and others are present.
        for name in NEW + OTHER:
            component(self.cc / name, "2.0.15", marker="user")
        self.fake_python(fail_groups=True)
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertNotIn("kept the old", self.log)

    def test_failing_group_check_keeps_an_old_permission_manager_alone(self):
        # Only ha_permission_manager 1.x, no area/label folders and nothing moved out.
        self.install_old(["ha_permission_manager"])
        self.fake_python(fail_groups=True)
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "old")
        self.assertIn("kept the old permission components: component group check failed",
                      self.log)
        self.assertNotIn("kept the old records", self.log)
        self.assertEqual(self.marker("woow_ha_records"), "seed")

    def test_failing_group_check_keeps_an_unreadable_permission_manager(self):
        component(self.cc / "ha_permission_manager", "2.0.15", marker="user")
        (self.cc / "ha_permission_manager" / "manifest.json").write_text('{"version": ')
        self.fake_python(fail_groups=True)
        self.run_seed()
        self.assertEqual(self.marker("ha_permission_manager"), "user")
        self.assertIn("kept the old permission components: component group check failed",
                      self.log)
        self.assertEqual(self.marker("woow_ha_records"), "seed")

    def test_in_use_signal_without_old_folders_seeds_the_successor(self):
        # The permission manager keeps its storage key across 1.x -> 2.x, so a
        # 2.x user also has .storage/ha_permission_manager.
        self.config_entries("ha_permission_manager", "ha_finance")
        self.run_seed()
        self.assertEqual(self.present(), sorted(NEW + OTHER))
        self.assertNotIn("kept the old", self.log)


if __name__ == "__main__":
    unittest.main()
