import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from screen_translator.services.config import ConfigurationError, SettingsStore, SystemCredentialStore


class MemoryCredentials:
    def __init__(self):
        self.entries = {}

    def get(self, name):
        return self.entries.get(name)

    def set(self, name, value):
        self.entries[name] = value

    def delete(self, name):
        self.entries.pop(name, None)


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "settings.json"
        self.credentials = MemoryCredentials()
        self.store = SettingsStore(self.path, self.credentials)
        self.addCleanup(patch.stopall)

    def test_save_restart_switch_and_delete_keep_platforms_isolated(self):
        self.store.save("baidu", {"app_id": "private-app", "secret_key": "private-baidu"}, activate=True)
        self.store.save("tencent_tokenhub", {"api_key": "private-tokenhub", "model": "hy-mt2-plus"})
        fresh = SettingsStore(self.path, self.credentials)
        self.assertEqual(fresh.active_provider, "baidu")
        fresh.activate("tencent_tokenhub")
        fresh.clear("baidu")
        self.assertEqual(fresh.values("tencent_tokenhub")["api_key"], "private-tokenhub")
        self.assertEqual(fresh.values("tencent_tokenhub")["model"], "hy-mt2-plus")
        self.assertEqual(fresh.values("baidu")["secret_key"], "")
        text = self.path.read_text(encoding="utf-8")
        for secret in ("private-app", "private-baidu", "private-tokenhub", "api_key", "secret_key"):
            self.assertNotIn(secret, text)
        self.assertEqual(len(self.credentials.entries), 1)

    def test_failed_configuration_write_preserves_previous_credential_and_active_platform(self):
        self.store.save("baidu", {"app_id": "old", "secret_key": "old"}, activate=True)
        before = self.path.read_bytes()
        with patch("os.replace", side_effect=OSError("PRIVATE")):
            with self.assertRaisesRegex(ConfigurationError, "保存失败"):
                self.store.save("baidu", {"app_id": "new", "secret_key": "new"}, activate=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.values("baidu")["secret_key"], "old")
        self.assertEqual(len(self.credentials.entries), 1)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_clear_failure_rolls_back_credentials_and_config(self):
        self.store.save("tencent_tokenhub", {"api_key": "old"}, activate=True)
        before = self.path.read_bytes()
        with patch("os.replace", side_effect=OSError("PRIVATE")):
            with self.assertRaises(ConfigurationError):
                self.store.clear("tencent_tokenhub")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.values("tencent_tokenhub")["api_key"], "old")

    def test_backend_failure_never_writes_plaintext_or_successful_config(self):
        with patch.object(self.credentials, "set", side_effect=ConfigurationError("系统凭据存储不可用")):
            with self.assertRaises(ConfigurationError):
                self.store.save("tencent_tokenhub", {"api_key": "PRIVATE"}, activate=True)
        self.assertFalse(self.path.exists())
        backend = SystemCredentialStore()
        with patch.object(backend, "_backend", side_effect=RuntimeError("PRIVATE")):
            for operation in (lambda: backend.get("test"), lambda: backend.set("test", "PRIVATE"), lambda: backend.delete("test")):
                with self.assertRaises(ConfigurationError) as raised:
                    operation()
                self.assertNotIn("PRIVATE", str(raised.exception))

    def test_corrupt_or_unsupported_config_is_not_overwritten(self):
        for text in ("{broken", '{"schema":99}', '{"schema":1,"active_provider":"tencent_tokenhub","providers":[]}'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ConfigurationError):
                    self.store.save("tencent_tokenhub", {"api_key": "PRIVATE"})
                self.assertEqual(self.path.read_text(), text)
                self.assertFalse(self.credentials.entries)

    def test_missing_system_entry_is_recoverable(self):
        self.store.save("tencent_tokenhub", {"api_key": "saved-key"})
        self.credentials.entries.clear()
        with self.assertRaisesRegex(ConfigurationError, "凭据已丢失"):
            self.store.values("tencent_tokenhub")

    def test_floating_icon_position_survives_restart_and_side_selection_resets_it(self):
        self.store.set_dock_position(-320, 180)
        fresh = SettingsStore(self.path, self.credentials)
        self.assertEqual(fresh.dock_position, [-320, 180])
        fresh.set_dock_side("left")
        self.assertIsNone(fresh.dock_position)
        self.assertEqual(fresh.dock_side, "left")

    def test_unknown_profiles_are_discarded_without_reading_credentials(self):
        self.store.save("baidu", {"app_id": "app", "secret_key": "key"}, activate=True)
        data = self.store._read()
        data["active_provider"] = "unsupported-provider"
        data["providers"]["unsupported-provider"] = {"credential_id": "unsupported-provider:private"}
        self.store._write(data)
        with patch.object(self.credentials, "get", side_effect=AssertionError("unexpected credential read")):
            self.assertEqual(self.store.translation_mode, "offline")
            self.assertEqual(set(self.store._read()["providers"]), {"baidu"})
            self.store.set_appearance(result_size=30)
        self.assertEqual(set(json.loads(self.path.read_text())["providers"]), {"baidu"})
        self.assertEqual(self.store.values("baidu")["secret_key"], "key")

    def test_cross_platform_credential_reference_is_rejected(self):
        self.path.write_text(json.dumps({"schema": 1, "active_provider": "baidu", "providers": {
            "baidu": {"options": {}, "credential_id": "niutrans:private"}}}))
        before = self.path.read_bytes()
        with self.assertRaises(ConfigurationError):
            self.store.save("baidu", {"app_id": "app", "secret_key": "key"})
        self.assertEqual(self.path.read_bytes(), before)

    def test_replacing_credentials_removes_previous_entry(self):
        self.store.save("tencent_tokenhub", {"api_key": "old"})
        self.store.save("tencent_tokenhub", {"api_key": "new"})
        self.assertEqual(len(self.credentials.entries), 1)
        self.assertEqual(self.store.values("tencent_tokenhub")["api_key"], "new")

    def test_cleanup_failure_is_reported_without_claiming_save_failed(self):
        self.store.save("tencent_tokenhub", {"api_key": "old"})
        with patch.object(self.credentials, "delete", side_effect=ConfigurationError("cannot delete")):
            self.store.save("tencent_tokenhub", {"api_key": "new"})
        self.assertEqual(self.store.values("tencent_tokenhub")["api_key"], "new")
        self.assertIn("旧凭据", self.store.cleanup_warning)


@unittest.skipUnless(os.name == "nt", "Windows credential integration")
class WindowsCredentialTests(unittest.TestCase):
    def test_native_credential_roundtrip_across_store_instances(self):
        import uuid

        reference = "alpha-integration-test:" + uuid.uuid4().hex
        store = SystemCredentialStore()
        try:
            store.set(reference, "synthetic-test-value")
            self.assertEqual(SystemCredentialStore().get(reference), "synthetic-test-value")
        finally:
            store.delete(reference)
        self.assertIsNone(SystemCredentialStore().get(reference))
