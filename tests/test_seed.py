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

sys.path.insert(0, str(ROOT / "_seed"))
import seed_groups  # noqa: E402


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
        self.fake_python()

    def fake_python(self, fail_groups=False):
        real = Path(sys.executable).as_posix()
        groups = 'case "$1" in *seed_groups.py) exit 3;; esac\n' if fail_groups else ""
        self.python.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-m" ] && [ "$2" = "homeassistant" ]; then\n'
            '  echo "[test] homeassistant started"; exit 0\n'
            "fi\n" + groups + f'exec "{real}" "$@"\n',
            newline="\n",
        )

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
                   WOOW_SEED_PYTHON=self.python.as_posix())
        result = subprocess.run([SH, SCRIPT.as_posix()], env=env, capture_output=True, encoding="utf-8", errors="replace",
                                timeout=60)
        self.log = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, self.log)
        self.assertIn("[test] homeassistant started", self.log)

    def installed(self):
        return sorted(p.name for p in self.cc.iterdir()) if self.cc.exists() else []

    def marker(self, name):
        return (self.cc / name / "marker").read_text()

    # --- tests -----------------------------------------------------------

    def test_fresh_install_gets_the_new_layout(self):
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))
        self.assertNotIn("removed", self.log)

    def test_factory_state_installed_but_unused_is_replaced(self):
        # Box 4 as shipped: all 10 old folders, no config entries.
        self.install_old()
        self.config_entries("sun", "backup")
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "seed")
        for name in OLD:
            self.assertIn(f"removed old component: {name}", self.log)

    def assert_only_group_kept(self, kept, reason):
        installed = self.installed()
        for group, old in GROUP_OLD.items():
            if group == kept:
                for name in old:
                    self.assertIn(name, installed)
                    self.assertEqual(self.marker(name), "old")
                if GROUP_NEW[group] not in old:
                    self.assertNotIn(GROUP_NEW[group], installed)
            else:
                self.assertEqual(sorted(set(old) & set(installed) - {GROUP_NEW[group]}), [])
                self.assertEqual(self.marker(GROUP_NEW[group]), "seed")
        self.assertIn(f"kept the old {kept} components: in use ({reason}", self.log)

    def reset_config(self):
        shutil.rmtree(self.config)
        self.config.mkdir()

    def storage_file(self, name):
        (self.config / ".storage").mkdir(exist_ok=True)
        (self.config / ".storage" / name).write_text("{}")

    def yaml_key(self, domain, key_template="{}:"):
        (self.config / "configuration.yaml").write_text(
            f"default_config:\n\n{key_template.format(domain)}\n  some: value\n")

    def yaml_key_first_after_bom(self, domain):
        # Some Windows editors save a BOM; HA's YAML loader skips it.
        (self.config / "configuration.yaml").write_text(
            f"﻿{domain}:\n  some: value\n", encoding="utf-8")

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
        for key_template in ("{} :", '"{}":', "'{}':", "'{}' :"):
            cases.append(("records", "configuration.yaml key ha_finance",
                          lambda d, t=key_template: self.yaml_key(d, t), "ha_finance"))
        cases.append(("records", "configuration.yaml key ha_finance",
                      self.yaml_key_first_after_bom, "ha_finance"))
        for group, reason, arrange, arg in cases:
            with self.subTest(group=group, reason=reason):
                self.reset_config()
                self.install_old()
                arrange(arg)
                self.run_seed()
                self.assert_only_group_kept(group, reason)

    def test_indented_or_commented_yaml_key_is_not_in_use(self):
        for key_template in ("  {}:", "# {}:", "#{}:"):
            with self.subTest(key_template=key_template):
                self.reset_config()
                self.install_old(["ha_finance"])
                self.yaml_key("ha_finance", key_template)
                self.run_seed()
                self.assertEqual(self.installed(), sorted(NEW + OTHER))
                self.assertIn("removed old component: ha_finance", self.log)

    def test_successor_signals_do_not_hold_a_leftover_old_component(self):
        # A 2.x permission manager writes the same entry and storage key as 1.x.
        component(self.cc / "ha_permission_manager", "2.0.15", marker="user")
        self.install_old(["ha_label_control"])
        self.config_entries("ha_permission_manager")
        self.storage_file("ha_permission_manager")
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))
        self.assertIn("removed old component: ha_label_control", self.log)

    def test_permission_signals_hold_the_group_when_the_old_manager_folder_is_gone(self):
        # 1.x deleted by hand, ha_area_control left: no successor is installed, so
        # the ha_permission_manager entry and storage key still count as in use.
        for reason, arrange in (("config entry ha_permission_manager", self.config_entries),
                                (".storage/ha_permission_manager", self.storage_file)):
            with self.subTest(reason=reason):
                self.reset_config()
                self.install_old(["ha_area_control"])
                arrange("ha_permission_manager")
                self.run_seed()
                self.assertEqual(self.installed(), sorted(
                    ["ha_area_control"] + [n for n in NEW if n != GROUP_NEW["permission"]]
                    + OTHER))
                self.assertEqual(self.marker("ha_area_control"), "old")
                self.assertIn(f"kept the old permission components: in use ({reason}", self.log)

    def test_failing_group_check_on_a_fresh_install_still_seeds_the_successors(self):
        self.fake_python(fail_groups=True)
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))

    def test_partly_removed_old_group_is_still_replaced(self):
        self.install_old(["ha_finance", "woow_knx"])
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))

    def test_existing_successor_is_not_overwritten(self):
        self.install_old()
        component(self.cc / "woow_ha_records", "3.0.1", marker="user")
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("woow_ha_records"), "user")

    def test_newer_permission_manager_is_not_an_old_component(self):
        component(self.cc / "ha_permission_manager", "2.1.0", marker="user")
        self.install_old(["ha_area_control"])
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "user")
        self.assertNotIn("removed old component: ha_permission_manager", self.log)

    def test_unreadable_config_entries_keep_every_group(self):
        self.install_old()
        (self.config / ".storage").mkdir()
        (self.config / ".storage" / "core.config_entries").write_text('{"data": {"entr')
        self.run_seed()
        self.assertEqual(self.installed(), sorted(OLD + OTHER))
        self.assertEqual(self.marker("ha_permission_manager"), "old")
        self.assertEqual(self.log.count("could not check"), 3)

    def test_failing_group_check_keeps_everything_and_starts_ha(self):
        self.fake_python(fail_groups=True)
        self.install_old()
        self.run_seed()
        self.assertEqual(self.installed(), sorted(OLD + OTHER))
        self.assertIn("component group check failed", self.log)

    def test_in_use_signal_without_old_folders_seeds_the_successor(self):
        # The permission manager keeps its storage key across 1.x -> 2.x, so a
        # 2.x user also has .storage/ha_permission_manager.
        self.config_entries("ha_permission_manager", "ha_finance")
        self.run_seed()
        self.assertEqual(self.installed(), sorted(NEW + OTHER))
        self.assertNotIn("kept the old", self.log)



class SuccessorListTest(unittest.TestCase):
    def test_shell_fallback_lists_the_same_successors_as_the_groups(self):
        shell = re.search(r'^SUCCESSORS="([^"]*)"', SCRIPT.read_text(encoding="utf-8"), re.M)
        self.assertEqual(sorted(shell[1].split()),
                         sorted(group.successor for group in seed_groups.GROUPS))


if __name__ == "__main__":
    unittest.main()
