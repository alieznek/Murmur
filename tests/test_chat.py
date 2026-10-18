import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidget, QPushButton, QStyle
from screen_translator.services.config import ConfigurationError, SettingsStore
from screen_translator.services.history import HistoryError, HistoryStore
from screen_translator.ui.main_window import MainWindow
from test_settings_store import MemoryCredentials


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "history.json"
        self.store = HistoryStore(self.path)
        self.conversation = {"id": "chat", "title": "Hello", "updated": "2026-10-10T01:00:00+08:00", "messages": [
            {"id": "entry", "source": "Hello", "translation": "你好", "target": "中文", "provider": "本地 · Argos", "status": "complete"}]}

    def test_history_reopens_and_interrupted_requests_do_not_stay_pending(self):
        self.store.save([self.conversation])
        self.assertEqual(HistoryStore(self.path).load(), [self.conversation])
        self.conversation["messages"][0]["status"] = "pending"
        self.store.save([self.conversation])
        self.assertEqual(self.store.load()[0]["messages"][0]["status"], "interrupted")

    def test_failed_atomic_save_preserves_existing_history(self):
        self.store.save([self.conversation])
        before = self.path.read_bytes()
        with patch("os.replace", side_effect=OSError("disk failure")), self.assertRaises(HistoryError):
            self.store.save([])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("history-*.tmp")), [])

    def test_malformed_history_is_reported_without_overwriting_it(self):
        self.path.write_text('{"schema":1,"conversations":[{"id":"broken"}]}', encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(HistoryError):
            self.store.load()
        self.assertEqual(self.path.read_bytes(), before)


class ChatUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.credentials = MemoryCredentials()
        self.store = SettingsStore(Path(self.temporary.name) / "settings.json", self.credentials)
        self.window = MainWindow(self.store)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.shutdown()
        self.window.deleteLater()
        self.app.processEvents()

    def test_native_windows_share_frameless_translucent_chrome(self):
        from screen_translator.ui.notice import NoticeDialog, QMessageBox
        self.window.open_settings()
        notice = NoticeDialog(self.window, "提示", "合成提示内容", QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)
        self.addCleanup(notice.deleteLater)
        for window in (self.window, self.window.recognition_window, self.window.settings_dialog, notice):
            self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
            self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))

    def test_font_preferences_persist_and_do_not_replace_task_or_text(self):
        self.window.source_edit.setPlainText("Keep this draft")
        self.window.translation_edit.setPlainText("保留这段译文")
        task, version = self.window.translate_task, self.window.source_version
        self.window.open_settings()
        dialog = self.window.settings_dialog
        with patch("httpx.post") as request:
            dialog.font_controls["result_font"].setCurrentFont(QFont("Consolas"))
            dialog.size_controls["result_size"].setValue(31)
            self.assertEqual(self.store.appearance["result_font"], "Consolas")
            self.assertEqual(self.window.appearance["result_size"], 31)
            request.assert_not_called()
        self.assertEqual((self.window.translate_task, self.window.source_version), (task, version))
        self.assertEqual(self.window.source_edit.toPlainText(), "Keep this draft")
        self.assertEqual(self.window.translation_edit.toPlainText(), "保留这段译文")
        self.assertEqual(SettingsStore(self.store.path, self.credentials).appearance["result_size"], 31)

    def test_invalid_font_preferences_do_not_replace_saved_configuration(self):
        self.store.set_appearance(result_size=30)
        before = self.store.path.read_bytes()
        with self.assertRaises(ConfigurationError):
            self.store.set_appearance(result_size=100)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_chat_history_preserves_request_snapshot_and_can_be_reopened(self):
        self.window.source_edit.setPlainText("A first sentence")
        self.window._record_request("A first sentence", "English", 1)
        first = self.window.active_conversation
        self.window._finish_request("The first translation")
        self.window.new_conversation()
        self.window._record_request("A second sentence", "中文", 2)
        self.window._finish_request("第二句译文")
        self.window.open_conversation(first)
        self.assertEqual(self.window.current_conversation()["messages"][0]["source"], "A first sentence")
        self.assertEqual(self.window.translation_edit.toPlainText(), "The first translation")
        self.assertEqual(len(HistoryStore(self.store.path.with_name("history.json")).load()), 2)
        self.window.delete_conversation(first)
        self.assertEqual(len(HistoryStore(self.store.path.with_name("history.json")).load()), 1)

    def test_failed_translation_can_be_put_back_into_the_composer(self):
        self.window._record_request("Keep this original", "中文", 1)
        self.window._finish_request(error="网络不可用")
        self.assertEqual(self.window.current_conversation()["messages"][0]["status"], "failed")
        self.window.retry_message("Keep this original")
        self.assertEqual(self.window.source_edit.toPlainText(), "Keep this original")

    def test_long_translations_scroll_over_text_and_keep_actions_below_it(self):
        from screen_translator.ui.chat import AutoText
        conversation = self.window.current_conversation()
        conversation["messages"] = [{"source": "A long source sentence " * 30,
            "translation": "A long translation with several wrapped lines. " * 70,
            "target": "English", "provider": "本地 · Argos", "status": "complete"}]
        self.window.resize(530, 560)
        self.window.render_conversation()
        for _ in range(10):
            self.app.processEvents()
        view = self.window.chat_view
        scrollbar = view.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), view.viewport().height())
        output = next(text for text in view.findChildren(AutoText) if text.accessibleName() == "译文")
        card = output.parentWidget()
        copy = next(button for button in card.findChildren(QPushButton) if button.text() == "复制译文")
        self.assertGreater(copy.mapTo(card, QPoint()).y(), output.geometry().bottom())
        self.assertGreaterEqual(output.viewport().height(), output.document().size().height())
        point = output.viewport().mapTo(self.window, QPoint(40, output.viewport().height() - 10))
        before = scrollbar.value()
        QTest.wheelEvent(self.window.windowHandle(), point, QPoint(0, 120))
        self.app.processEvents()
        self.assertLess(scrollbar.value(), before)
        self.assertEqual(output.verticalScrollBar().value(), 0)
        previous = scrollbar.value()
        self.window.render_conversation(scroll=False)
        for _ in range(10):
            self.app.processEvents()
        self.assertEqual(scrollbar.value(), previous)
        self.window.resize(460, 420)
        for _ in range(10):
            self.app.processEvents()
        output = next(text for text in view.findChildren(AutoText) if text.isVisible() and text.accessibleName() == "译文")
        self.assertGreaterEqual(output.viewport().height(), output.document().size().height())

    def test_combo_popup_remains_a_themed_keyboard_operable_list(self):
        combo = self.window.source_combo
        combo.showPopup()
        self.app.processEvents()
        self.assertEqual(combo.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup), 0)
        popup = combo.language_popup
        self.assertTrue(popup.windowFlags() & Qt.WindowType.FramelessWindowHint)
        rows = popup.findChild(QListWidget)
        QTest.keyClick(rows, Qt.Key.Key_Down)
        QTest.keyClick(rows, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(combo.currentData(), "中文")

    def test_ocr_settings_has_no_capture_or_upload_actions(self):
        self.window.open_settings()
        dialog = self.window.settings_dialog
        dialog.select_page("ocr")
        page = dialog.pages.currentWidget()
        self.assertFalse(page.findChildren(QPushButton))

    def test_screenshot_review_can_be_edited_before_explicit_confirmation(self):
        from PySide6.QtGui import QPixmap
        from screen_translator.core.text_blocks import TextBlock
        self.window._capture_active = True
        self.window.candidate_pixmap = QPixmap(100, 30)
        self.window._ocr_ready(self.window.capture_generation, [TextBlock("line", "Incorrect word", ((0, 0), (100, 0), (100, 30), (0, 30)))])
        self.window.recognition_window.review_edit.setPlainText("Corrected word")
        self.assertTrue(self.window.confirm_button.isEnabled())
        self.assertEqual(self.window.source_edit.toPlainText(), "")
        self.window.confirm_selection()
        self.assertEqual(self.window.source_edit.toPlainText(), "Corrected word")
        self.assertTrue(self.window.attachment_frame.isVisible())

    def test_pasted_image_uses_the_existing_local_ocr_flow(self):
        from PySide6.QtCore import QMimeData
        mime = QMimeData()
        image = QImage(40, 20, QImage.Format.Format_RGB888)
        image.fill(Qt.GlobalColor.white)
        mime.setImageData(image)
        with patch.object(self.window, "_capture_selected") as capture:
            self.window.source_edit.insertFromMimeData(mime)
        capture.assert_called_once()
        self.assertTrue(self.window._capture_active)

    def test_unconfigured_provider_opens_settings_without_sending_text(self):
        with patch("httpx.post") as request:
            self.window.provider_combo.setCurrentIndex(self.window.provider_combo.findData("tencent_tokenhub"))
            self.assertTrue(self.window.settings_dialog.isVisible())
            self.assertEqual(self.window.settings_dialog.provider_combo.currentData(), "tencent_tokenhub")
            self.assertEqual(self.store.translation_mode, "offline")
            request.assert_not_called()
