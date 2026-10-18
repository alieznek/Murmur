import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from screen_translator.services.config import SettingsStore
from screen_translator.ui.design_tokens import DARK, LIGHT
from screen_translator.ui.main_window import MainWindow
from test_settings_store import MemoryCredentials


class WorkspaceControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.window = MainWindow(SettingsStore(Path(self.temporary.name) / "settings.json", MemoryCredentials()))
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        self.app.processEvents()

    def test_character_counts_and_text_survive_font_and_mode_changes(self):
        self.window.source_edit.setPlainText("A readable original")
        self.window.translation_edit.setPlainText("一段译文")
        self.app.processEvents()
        self.assertEqual(self.window.source_count_label.text(), "19 字符")
        self.assertEqual(self.window.translation_count_label.text(), "4 字符")
        self.window.set_reading_mode(1)
        self.window.font_combo.setCurrentIndex(3)
        self.assertEqual(self.window.source_edit.toPlainText(), "A readable original")
        self.assertEqual(self.window.translation_edit.toPlainText(), "一段译文")

    def test_native_combo_keyboard_selection_still_invalidates_the_translation(self):
        self.window.source_edit.setPlainText("original")
        self.window.translation_edit.setPlainText("translation")
        version = self.window.source_version
        self.window.source_combo.setFocus()
        QTest.keyClick(self.window.source_combo, Qt.Key.Key_Down)
        self.assertEqual(self.window.source_combo.currentText(), "中文")
        self.assertGreater(self.window.source_version, version)
        self.assertEqual(self.window.translation_edit.toPlainText(), "")

    def test_theme_is_shared_by_all_windows_and_new_provider_fields_without_requests(self):
        self.window.open_settings()
        task, version = self.window.translate_task, self.window.source_version
        with patch("httpx.post") as http:
            for index, theme in ((1, DARK), (0, LIGHT)):
                self.window.theme_combo.setCurrentIndex(index)
                settings = self.window.settings_dialog
                settings.provider_combo.setCurrentIndex(settings.provider_combo.findData("tencent_tokenhub"))
                self.app.processEvents()
                self.assertEqual(settings.fields["model"].palette().color(QPalette.ColorRole.Text).name(), theme.text)
                for window in (self.window, settings, self.window.recognition_window, self.window.edge_dock):
                    self.assertEqual(window.palette().color(QPalette.ColorRole.WindowText).name(), theme.text)
                self.assertEqual(self.window.source_version, version)
                self.assertEqual(self.window.translate_task, task)
            http.assert_not_called()

    def test_secondary_actions_and_settings_details_remain_available(self):
        self.assertTrue(self.window.settings_button.accessibleName())
        self.assertTrue(self.window.pin_button.accessibleName())
        self.assertTrue(self.window.workspace_menu_button.accessibleName())
        actions = {action.text(): action for action in self.window.workspace_menu_button.menu().actions()}
        actions["查看识别来源"].trigger()
        self.assertTrue(self.window.recognition_window.isVisible())
        self.window.open_settings()
        settings = self.window.settings_dialog
        settings.select_page("platforms")
        self.assertFalse(settings.provider_note.isVisible())
        settings.help_toggle.setChecked(True)
        self.assertTrue(settings.provider_note.isVisible())
        self.assertFalse(settings.clear_button.isVisible())
        settings.advanced_toggle.setChecked(True)
        self.assertTrue(settings.clear_button.isVisible())

    def test_primary_action_is_enabled_only_when_input_is_present(self):
        self.window.source_edit.clear()
        self.app.processEvents()
        button = self.window.translate_button
        self.assertFalse(button.isEnabled())
        self.window.source_edit.setPlainText("Hello")
        self.assertTrue(button.isEnabled())
        self.window.source_edit.clear()
        self.assertFalse(button.isEnabled())
