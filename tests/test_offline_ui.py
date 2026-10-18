import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication
from screen_translator.services.config import SettingsStore
from screen_translator.ui.main_window import MainWindow
from test_settings_store import MemoryCredentials


class OfflineUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SettingsStore(Path(self.temporary.name) / "settings.json", MemoryCredentials())
        self.window = MainWindow(self.store)
        self.window.pool = QThreadPool(self.window)

    def tearDown(self):
        self.window.shutdown()
        self.window.pool.waitForDone(3000)
        self.app.processEvents()
        self.window.deleteLater()
        self.app.processEvents()

    def wait(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_new_user_local_mode_does_not_read_credentials_or_send_http(self):
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.window.source_edit.isVisible())
        self.assertIn("翻译输入框", self.window.source_edit.accessibleName())
        with patch.object(self.store.credentials, "get") as credential, patch("httpx.post") as http:
            self.window.reload_configuration()
            self.assertIs(self.window.translator, self.window.local_translator)
            self.assertIsNone(self.window.local_translator.pid)
            self.window.source_edit.setPlainText("Hello")
            with patch.object(self.window.local_translator, "translate", return_value="你好") as translate:
                self.window.translate()
                self.wait(lambda: not self.window.translation_running)
            self.assertEqual(translate.call_args.args, ("Hello", "中文", "自动识别"))
            self.window.copy_translation()
            self.assertEqual(self.app.clipboard().text(), "你好")
            credential.assert_not_called()
            http.assert_not_called()

    def test_online_preference_and_local_switch_survive_restart_without_changing_keys(self):
        self.store.save("tencent_tokenhub", {"api_key": "draft-key"})
        self.window.reload_configuration()
        self.assertEqual(self.window.translation_mode, "offline")
        self.store.save("tencent_tokenhub", {"api_key": "key"}, activate=True)
        self.window.reload_configuration()
        self.assertEqual(self.window.translation_mode, "online")
        self.window.mode_combo.setCurrentIndex(0)
        restarted = SettingsStore(self.store.path, self.store.credentials)
        self.assertEqual(restarted.translation_mode, "offline")
        self.assertEqual(restarted.active_provider, "tencent_tokenhub")
        self.assertEqual(restarted.values("tencent_tokenhub")["api_key"], "key")
        self.window.mode_combo.setCurrentIndex(1)
        self.assertEqual(self.window.translation_mode, "online")

    def test_legacy_online_configuration_and_mode_write_failure_keep_preference(self):
        self.store._write({"schema": 1, "active_provider": "tencent_tokenhub", "providers": {}})
        self.window.reload_configuration()
        self.assertEqual(self.window.translation_mode, "online")
        self.assertIsNone(self.window.translator)
        before = self.store.path.read_bytes()
        with patch("os.replace", side_effect=OSError("write failure")), patch(
            "screen_translator.ui.main_window.QMessageBox.warning"
        ) as warning:
            self.window.mode_combo.setCurrentIndex(0)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.window.mode_combo.currentData(), "online")
        warning.assert_called_once()

    def test_edit_cancel_language_and_switch_discard_late_results_and_errors(self):
        for action in (lambda: self.window.source_edit.setPlainText("Changed"),
                       lambda: self.window.source_combo.setCurrentText("English"),
                       self.window.cancel_translation,
                       lambda: self.window.mode_combo.setCurrentIndex(1)):
            with self.subTest(action=action), patch("screen_translator.ui.main_window.QMessageBox.warning") as warning:
                self.store.set_translation_mode("offline")
                self.window.reload_configuration()
                released = threading.Event()
                entered = threading.Event()
                def slow(*args, **kwargs):
                    entered.set()
                    released.wait(2)
                    raise RuntimeError("Old error")
                self.window.source_combo.setCurrentText("自动识别")
                self.window.source_edit.setPlainText("Hello")
                with patch.object(self.window.local_translator, "translate", side_effect=slow):
                    self.window.translate()
                    self.wait(entered.is_set)
                    self.window.translate()  # No second inference while busy.
                    action()
                    released.set()
                    self.wait(lambda: not self.window._workers)
                self.assertEqual(self.window.translation_edit.toPlainText(), "")
                warning.assert_not_called()
