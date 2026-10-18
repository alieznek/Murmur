import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

from screen_translator.services.config import ConfigurationError, SettingsStore
from screen_translator.ui.main_window import MainWindow
from screen_translator.ui.settings_dialog import SettingsDialog
from test_settings_store import MemoryCredentials


class SettingsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SettingsStore(Path(self.temporary.name) / "settings.json", MemoryCredentials())
        self.addCleanup(patch.stopall)
        self.window = MainWindow(self.store)
        self.window.pool = QThreadPool(self.window)
        self.dialog = SettingsDialog(self.store, self.window)
        self.dialog.pool = QThreadPool(self.dialog)
        self.dialog.configuration_changed.connect(self.window.reload_configuration)

    def tearDown(self):
        self.dialog.pool.waitForDone(3000)
        self.window.pool.waitForDone(3000)
        self.app.processEvents()
        self.dialog.hide()
        self.window.tray.hide()
        self.window.hide()
        self.dialog.deleteLater()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def choose(self, provider):
        self.dialog.provider_combo.setCurrentIndex(self.dialog.provider_combo.findData(provider))

    def fill_tokenhub(self, key="key"):
        self.choose("tencent_tokenhub")
        self.dialog.fields["api_key"].setText(key)
        self.dialog.fields["model"].setCurrentIndex(1)

    def test_dynamic_fields_mask_credentials_and_keep_drafts_per_platform(self):
        self.assertEqual(set(self.dialog.fields), {"app_id", "secret_key", "edition"})
        self.dialog.fields["app_id"].setText("draft-app")
        self.assertEqual(self.dialog.fields["secret_key"].echoMode(), QLineEdit.EchoMode.Password)
        self.fill_tokenhub()
        self.assertEqual(set(self.dialog.fields), {"api_key", "model"})
        self.dialog.reveal.setChecked(True)
        self.assertEqual(self.dialog.fields["api_key"].echoMode(), QLineEdit.EchoMode.Normal)
        self.choose("baidu")
        self.assertEqual(self.dialog.fields["app_id"].text(), "draft-app")
        self.assertEqual(self.dialog.fields["secret_key"].echoMode(), QLineEdit.EchoMode.Password)

    def test_five_forms_and_platform_changes_preserve_input(self):
        self.assertEqual(self.dialog.provider_combo.count(), 5)
        self.window.source_edit.setPlainText("keep me")
        with patch("httpx.post") as post:
            for provider, fields in (("baidu", {"app_id", "secret_key", "edition"}),
                                     ("aliyun", {"access_key_id", "access_key_secret", "region"}),
                                     ("tencent_tokenhub", {"api_key", "model"}),
                                     ("huawei", {"access_key_id", "secret_access_key", "project_id"}),
                                     ("niutrans", {"app_id", "api_key"})):
                self.choose(provider)
                self.assertEqual(set(self.dialog.fields), fields)
            self.fill_tokenhub()
            self.dialog.activate()
            post.assert_not_called()
        self.assertEqual(self.window.source_edit.toPlainText(), "keep me")
        self.assertEqual(self.store.active_provider, "tencent_tokenhub")
        self.assertEqual(self.store.values("tencent_tokenhub")["api_key"], "key")

    def test_open_and_save_are_local_only_and_activation_uses_visible_draft(self):
        with patch("httpx.post") as post:
            self.fill_tokenhub()
            self.dialog.save()
            self.assertEqual(self.store.active_provider, "baidu")
            self.dialog.fields["api_key"].setText("new-key")
            self.dialog.activate()
            self.assertEqual(self.store.active_provider, "tencent_tokenhub")
            self.assertEqual(self.store.values("tencent_tokenhub")["api_key"], "new-key")
            self.assertIn("TokenHub", self.window.provider_label.text())
            post.assert_not_called()

    def test_active_verification_sends_fixed_text_once_without_saving(self):
        self.fill_tokenhub()
        self.window.source_edit.setPlainText("PRIVATE USER TEXT")
        release = threading.Event()
        self.addCleanup(release.set)
        adapter = Mock()
        adapter.translate.side_effect = lambda *_args: release.wait(3) and "你好"
        with patch("screen_translator.ui.settings_dialog.create_translator", return_value=adapter):
            self.dialog.verify()
            self.dialog.verify()
            self.assertFalse(self.dialog.verify_button.isEnabled())
            release.set()
            self.wait_for(lambda: not self.dialog._workers)
        adapter.translate.assert_called_once_with("Hello.", "中文")
        self.assertIn("成功", self.dialog.feedback.text())
        self.assertFalse(self.store.path.exists())
        self.assertTrue(self.dialog.verify_button.isEnabled())

    def test_verification_error_restores_controls_and_close_discards_late_feedback(self):
        self.fill_tokenhub()
        adapter = Mock()
        adapter.translate.side_effect = RuntimeError("PRIVATE KEY AND USER TEXT")
        with patch("screen_translator.ui.settings_dialog.create_translator", return_value=adapter):
            self.dialog.verify()
            self.wait_for(lambda: not self.dialog._workers)
        self.assertIn("验证组件发生异常", self.dialog.feedback.text())
        self.assertNotIn("PRIVATE", self.dialog.feedback.text())
        self.assertTrue(self.dialog.verify_button.isEnabled())
        release = threading.Event()
        self.addCleanup(release.set)
        adapter.translate.side_effect = lambda *_args: release.wait(3) and "late"
        with patch("screen_translator.ui.settings_dialog.create_translator", return_value=adapter):
            self.dialog.verify()
            self.dialog.reject()
            release.set()
            self.wait_for(lambda: not self.dialog._workers)
        self.assertNotIn("成功", self.dialog.feedback.text())

    def test_configuration_change_discards_old_result_and_error_during_new_request(self):
        for fail in (False, True):
            with self.subTest(old_request_fails=fail):
                old_release, new_release = threading.Event(), threading.Event()
                self.addCleanup(old_release.set)
                self.addCleanup(new_release.set)
                old_adapter = Mock()
                new_adapter = Mock()

                def old_translate(*_args):
                    old_release.wait(3)
                    if fail:
                        raise RuntimeError("old error")
                    return "old result"

                old_adapter.translate.side_effect = old_translate
                new_adapter.translate.side_effect = lambda *_args: new_release.wait(3) and "new result"
                self.window.translator = old_adapter
                self.window.source_edit.setPlainText("source")
                self.window.translate()
                self.fill_tokenhub("modified-key")
                with patch("screen_translator.ui.main_window.create_translator", return_value=new_adapter):
                    self.dialog.activate()
                self.assertEqual(self.window.source_edit.toPlainText(), "source")
                self.assertFalse(self.window.translation_running)
                self.window.translate()
                with patch("screen_translator.ui.main_window.QMessageBox.warning") as warning:
                    old_release.set()
                    self.wait_for(lambda: len(self.window._workers) == 1)
                    self.assertTrue(self.window.translation_running)
                    self.assertEqual(self.window.translation_edit.toPlainText(), "")
                    warning.assert_not_called()
                    new_release.set()
                    self.wait_for(lambda: not self.window._workers)
                self.assertEqual(self.window.translation_edit.toPlainText(), "new result")
                self.assertFalse(self.window.translation_running)
                old_adapter.translate.assert_called_once_with("source", "中文", "自动识别")
                new_adapter.translate.assert_called_once_with("source", "中文", "自动识别")

    def test_failed_save_keeps_current_adapter_and_reports_failure(self):
        self.window.translator = old = Mock()
        self.fill_tokenhub()
        with patch.object(self.store.credentials, "set", side_effect=ConfigurationError("系统凭据不可用")):
            self.dialog.activate()
        self.assertIs(self.window.translator, old)
        self.assertIn("不可用", self.dialog.feedback.text())
        self.assertFalse(self.store.path.exists())

    def test_no_credentials_keeps_local_input_and_opens_settings_without_http(self):
        self.store.set_translation_mode("online")
        self.window.reload_configuration()
        self.window.source_edit.setPlainText("keep me")
        self.assertTrue(self.window.capture_button.isEnabled())
        with patch("httpx.post") as post, patch.object(self.window, "open_settings") as opened, patch(
            "screen_translator.ui.main_window.QMessageBox.warning"
        ):
            self.window.translate()
        post.assert_not_called()
        opened.assert_called_once()
        self.assertEqual(self.window.source_edit.toPlainText(), "keep me")

    def test_clear_platform_removes_masked_fields_and_invalidates_current_adapter(self):
        self.fill_tokenhub()
        self.dialog.activate()
        self.window.source_edit.setPlainText("keep me")
        with patch("screen_translator.ui.settings_dialog.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.dialog.clear()
        self.assertEqual(self.dialog.fields["api_key"].text(), "")
        self.assertIsNone(self.window.translator)
        self.assertEqual(self.window.source_edit.toPlainText(), "keep me")
        self.assertFalse(self.store.credentials.entries)
