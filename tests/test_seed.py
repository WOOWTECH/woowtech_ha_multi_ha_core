"""Behaviour of the seed entrypoint (_seed/woow_seed.sh), without Home Assistant.

Each test builds a fake /config and a small fake seed, runs the real entrypoint
with a stand-in python that stops where Home Assistant would start, and checks
which component folders end up in /config/custom_components.

Run from the repository root:  python -m unittest discover -s tests
"""

import json
import os
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

    def test_group_in_use_is_kept(self):
        # (group, signal, arrange) - each of the four "in use" signals.
        storage = lambda name: lambda: (self.config / ".storage").mkdir(exist_ok=True) or \
            (self.config / ".storage" / name).write_text("{}")
        cases = [("permission", "config entry ha_label_control",
                  lambda: self.config_entries("sun", "ha_label_control"))]
        for group, old in GROUP_OLD.items():
            domain = old[-1]
            cases.append((group, f"config entry {domain}", lambda d=domain: self.config_entries(d)))
            cases.append((group, f".storage/{domain}", storage(domain)))
            cases.append((group, "configuration.yaml key " + domain,
                          lambda d=domain: (self.config / "configuration.yaml").write_text(
                              f"default_config:\n\n{d}:\n  some: value\n")))
        cases.append(("records", ".storage/ha_health_record_member1",
                      storage("ha_health_record_member1")))
        cases.append(("permission", ".storage/ha_permission_manager",
                      storage("ha_permission_manager")))
        for protocol in ("dmx", "knx", "modbus"):
            def data_dir(p=protocol):
                (self.config / p).mkdir()
                (self.config / p / "devices.yaml").write_text("[]")
            cases.append(("protocol", f"/config/{protocol} not empty", data_dir))
        for group, reason, arrange in cases:
            with self.subTest(group=group, reason=reason):
                self.reset_config()
                self.install_old()
                arrange()
                self.run_seed()
                self.assert_only_group_kept(group, reason)

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


if __name__ == "__main__":
    unittest.main()
