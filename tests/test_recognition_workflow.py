import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QRect, QThreadPool, Qt
from PySide6.QtGui import QColor, QKeySequence, QPixmap, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from screen_translator.core.text_blocks import TextBlock
from screen_translator.services.config import ConfigurationError, SettingsStore
from screen_translator.ui.main_window import MainWindow
from screen_translator.ui.theme import fit_window
from test_settings_store import MemoryCredentials


class RecognitionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = SettingsStore(Path(self.temporary.name) / "settings.json", MemoryCredentials())
        self.window = MainWindow(self.store)
        self.window.pool = QThreadPool(self.window)
        self.window.source_edit.setPlainText("original")
        self.window.translation_edit.setPlainText("原译文")
        self.window.copy_button.setEnabled(True)

    def tearDown(self):
        self.window.shutdown()
        self.window.pool.waitForDone(3000)
        self.app.processEvents()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def recognize(self, count=32):
        self.window._capture_active = True
        image = QPixmap(400, count * 40)
        image.fill(QColor("white"))
        self.window.candidate_pixmap = image
        blocks = [TextBlock(str(index), f"Block {index}: a line of recognized text",
                            ((20, index * 40), (380, index * 40), (380, index * 40 + 25),
                             (20, index * 40 + 25))) for index in range(count)]
        self.window._ocr_ready(self.window.capture_generation, blocks)
        self.app.processEvents()
        return blocks

    def assert_inside(self, control, window):
        rect = QRect(control.mapTo(window, QPoint()), control.size())
        self.assertTrue(window.rect().contains(rect), (rect, window.rect()))
        self.assertTrue(control.isVisible())

    def test_independent_recognition_preserves_input_until_explicit_confirmation(self):
        self.window.show()
        self.recognize(3)
        recognition = self.window.recognition_window
        self.assertTrue(recognition.isWindow())
        self.assertNotEqual(self.window.source_edit.window(), self.window.block_list.window())
        self.window.select_image_blocks({"1", "2"})
        self.assertEqual(self.window.source_edit.toPlainText(), "original")
        self.assertEqual(self.window.translation_edit.toPlainText(), "原译文")
        self.assertEqual(self.window.selection_preview.selected, {"1", "2"})
        self.window.confirm_selection()
        self.assertIn("Block 1", self.window.source_edit.toPlainText())
        self.assertNotIn("Block 0", self.window.source_edit.toPlainText())
        self.assertEqual(self.window.translation_edit.toPlainText(), "")
        self.assertFalse(recognition.isVisible())
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window.confirm_button.isEnabled())
        self.window.toggle_screenshot()
        self.assertEqual(recognition.pages.currentIndex(), 1)
        self.assertFalse(self.window.confirm_button.isEnabled())

    def test_close_cancels_selection_and_late_generation_without_losing_edits(self):
        blocks = self.recognize(2)
        generation = self.window.capture_generation
        self.window.source_edit.setPlainText("edited during recognition")
        self.window.recognition_window.close()
        self.window._ocr_ready(generation, blocks)
        self.assertFalse(self.window._capture_active)
        self.assertFalse(self.window.recognition_window.isVisible())
        self.assertEqual(self.window.source_edit.toPlainText(), "edited during recognition")
        self.assertEqual(self.window.block_list.count(), 0)

    def test_cancel_recapture_restores_retained_source_preview_and_selection(self):
        self.recognize(3)
        self.window.select_image_blocks({"1"})
        self.window.confirm_selection()
        source = self.window.source_edit.toPlainText()
        self.recognize(4)
        self.window.select_all_blocks()
        self.window.recognition_window.close()
        self.window.toggle_screenshot()
        self.assertEqual(self.window.block_list.count(), 3)
        self.assertEqual(self.window.selection_preview.selected, {"1"})
        self.assertEqual(self.window._selected_ids(), {"1"})
        self.assertFalse(self.window.confirm_button.isEnabled())
        self.assertEqual(self.window.source_edit.toPlainText(), source)

    def test_minimize_restore_and_pin_keep_selection_and_hidden_desk_state(self):
        self.window.show()
        self.recognize(3)
        self.window.select_image_blocks({"1"})
        self.window.recognition_window.showMinimized()
        self.window.show_recognition()
        self.assertFalse(self.window.recognition_window.isMinimized())
        self.assertTrue(self.window._capture_active)
        self.assertEqual(self.window._selected_ids(), {"1"})
        self.window.close()
        self.window._set_pin(False)
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window.edge_dock.isVisible())
        self.window.show_panel()
        self.assertEqual(self.window.source_edit.toPlainText(), "original")
        self.assertEqual(self.window.translation_edit.toPlainText(), "原译文")

    def test_close_while_ocr_runs_discards_result_and_reenables_recapture(self):
        release = threading.Event()
        started = threading.Event()
        def recognize(_image):
            started.set()
            release.wait(3)
            return [TextBlock("old", "late", ((0, 0), (90, 0), (90, 20), (0, 20)))]
        self.window.ocr = Mock()
        self.window.ocr.recognize.side_effect = recognize
        image = QPixmap(100, 40)
        image.fill(QColor("white"))
        try:
            self.window._capture_active = True
            self.window._capture_selected(image, QRect(0, 0, 100, 40))
            self.assertTrue(started.wait(1))
            self.assertTrue(self.window.recognition_window.isVisible())
            self.assertFalse(self.window.recapture_button.isEnabled())
            self.window.recognition_window.close()
            release.set()
            self.wait_for(lambda: not self.window._workers)
            self.assertFalse(self.window.recognition_window.isVisible())
            self.assertEqual(self.window.source_edit.toPlainText(), "original")
            self.assertTrue(self.window.recapture_button.isEnabled())
        finally:
            release.set()

    def test_text_click_drag_keyboard_and_screenshot_share_selection(self):
        blocks = self.recognize(4)
        self.window.recognition_window.set_view(1)
        self.window.select_image_blocks(set())
        self.app.processEvents()
        listing = self.window.block_list
        first = listing.visualItemRect(listing.item(0)).center()
        second = listing.visualItemRect(listing.item(1)).center()
        QTest.mousePress(listing.viewport(), Qt.MouseButton.LeftButton, pos=first)
        QTest.mouseMove(listing.viewport(), second)
        QTest.mouseRelease(listing.viewport(), Qt.MouseButton.LeftButton, pos=second)
        self.assertEqual(self.window._selected_ids(), {"0", "1"})
        listing.setCurrentRow(2)
        QTest.keyClick(listing, Qt.Key.Key_Space)
        self.assertIn("2", self.window._selected_ids())
        self.window.recognition_window.set_view(1)
        self.app.processEvents()
        view = self.window.selection_preview
        point = view.block_rect(blocks[3]).center().toPoint()
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(self.window._selected_ids(), {"0", "1", "2", "3"})

    def test_long_text_and_ocr_last_block_scroll_with_fixed_actions_at_small_workareas(self):
        self.window.show()
        self.recognize()
        self.window.recognition_window.set_view(1)
        for width, height in ((1024, 768), (819, 614), (683, 512), (512, 384)):
            with self.subTest(size=(width, height)):
                self.window.resize(width - 10, height - 40)
                self.window.recognition_window.resize(width - 10, height - 40)
                self.app.processEvents()
                for control in (self.window.confirm_button, self.window.recapture_button,
                                self.window.cancel_selection_button):
                    self.assert_inside(control, self.window.recognition_window)
                self.window.block_list.scrollToBottom()
                self.app.processEvents()
                last = self.window.block_list.visualItemRect(self.window.block_list.item(31))
                self.assertTrue(self.window.block_list.viewport().rect().intersects(last))
                for size in (16, 18, 21, 24):
                    self.window.font_combo.setCurrentIndex(self.window.font_combo.findData(size))
                    self.window.source_edit.setPlainText("A readable paragraph\n" * 80 + "LAST SOURCE")
                    self.window.translation_edit.setPlainText("一段可阅读的译文\n" * 80 + "最后一段译文")
                    self.window.source_edit.moveCursor(QTextCursor.MoveOperation.End)
                    self.window.source_edit.ensureCursorVisible()
                    self.assertGreater(self.window.source_edit.viewport().height(), 24)
                    self.assertTrue(self.window.source_edit.viewport().rect().contains(self.window.source_edit.cursorRect()))
                    for control in (self.window.translate_button, self.window.capture_button, self.window.upload_button):
                        self.assert_inside(control, self.window)

    def test_history_drawer_preserves_draft_and_translation_when_window_resizes(self):
        self.window.show()
        self.window.toggle_history(True)
        for size in ((780, 650), (500, 500)):
            self.window.resize(*size)
            self.app.processEvents()
            self.assertEqual(self.window.body_pages.currentIndex(), 1)
            self.assertEqual(self.window.source_edit.toPlainText(), "original")
            self.assertEqual(self.window.translation_edit.toPlainText(), "原译文")
        self.window.toggle_history(False)
        self.assertTrue(self.window.source_edit.isVisible())
        self.assertTrue(self.window.chat_view.isVisible())

    def test_a_single_tall_ocr_block_can_scroll_to_its_end_in_compact_window(self):
        self.recognize(2)
        self.window.recognition_window.set_view(1)
        self.window.recognition_window.resize(500, 344)
        listing = self.window.block_list
        listing.item(1).setText("A long recognized sentence. " * 80 + "LAST WORD")
        self.app.processEvents()
        listing.scrollToBottom()
        self.app.processEvents()
        last = listing.visualItemRect(listing.item(1))
        self.assertGreater(last.height(), listing.viewport().height())
        self.assertLessEqual(last.bottom(), listing.viewport().height())

    def test_theme_and_read_size_do_not_change_task_snapshot_or_send_http(self):
        version, task = self.window.source_version, self.window.translate_task
        with patch("httpx.post") as http, patch.object(self.window.local_translator, "translate") as translator:
            self.window.theme_combo.setCurrentIndex(1)
            self.window.font_combo.setCurrentIndex(3)
            self.window.set_reading_mode(1)
            self.assertEqual(self.window.source_version, version)
            self.assertEqual(self.window.translate_task, task)
            self.assertEqual(self.window.source_edit.toPlainText(), "original")
            self.assertEqual(self.window.translation_edit.toPlainText(), "原译文")
            http.assert_not_called()
            translator.assert_not_called()

    def test_edge_restore_both_sides_and_settings_survive_restart_without_changing_translation(self):
        for side in ("right", "left"):
            self.store.set_dock_side(side)
            self.window.show()
            self.window.close()
            self.app.processEvents()
            dock = self.window.edge_dock
            self.assertTrue(dock.isVisible())
            area = QRect(-1280, -200, 640, 480)
            dock.position_in(area, side)
            self.assertTrue(area.contains(dock.geometry()))
            # Keyboard access works even without pointer hover.
            dock.handle.setFocus()
            QTest.keyClick(dock.handle, Qt.Key.Key_Space)
            self.assertTrue(self.window.isVisible())
            self.assertFalse(dock.isVisible())
            self.window.show_panel()
            self.assertFalse(dock.isVisible())
            self.assertEqual(self.window.source_edit.toPlainText(), "original")
            self.assertEqual(self.window.translation_edit.toPlainText(), "原译文")
            self.assertEqual(SettingsStore(self.store.path, self.store.credentials).dock_side, side)

    def test_settings_nonmodal_actions_stay_visible_and_appearance_does_not_invalidate(self):
        self.window.show()
        task, version = self.window.translate_task, self.window.source_version
        self.window.open_settings()
        settings = self.window.settings_dialog
        self.assertEqual(settings.windowModality(), Qt.WindowModality.NonModal)
        settings.select_page("platforms")
        settings.resize(500, 384)
        self.app.processEvents()
        for control in (settings.save_button, settings.verify_button, settings.activate_button):
            self.assert_inside(control, settings)
        self.assertGreater(settings.content_scroll.verticalScrollBar().maximum(), 0)
        settings.dock_combo.setCurrentIndex(1)
        self.assertEqual(self.window.translate_task, task)
        self.assertEqual(self.window.source_version, version)
        self.assertEqual(self.window.translation_edit.toPlainText(), "原译文")
        with patch("os.replace", side_effect=OSError("write failure")):
            settings.dock_combo.setCurrentIndex(0)
        self.assertEqual(settings.dock_combo.currentData(), "left")
        self.assertEqual(self.store.dock_side, "left")

    def test_capture_hides_all_visible_workspaces_and_dock_without_duplicate_ocr(self):
        self.window.show()
        self.window.show_recognition()
        self.window.close()
        self.window.begin_capture()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.recognition_window.isVisible())
        self.assertFalse(self.window.edge_dock.isVisible())
        self.assertTrue(self.window.capture_timer.isActive())

    def test_arrangement_and_restore_fit_negative_origin_and_small_logical_workarea(self):
        self.window.show()
        for area in (QRect(-1280, -200, 1280, 900), QRect(-512, 0, 512, 384)):
            self.window.arrange_workspaces(area)
            self.app.processEvents()
            self.assertTrue(area.contains(self.window.frameGeometry()))
            self.assertTrue(area.contains(self.window.recognition_window.frameGeometry()))
            if area.width() >= 1100:
                self.assertFalse(self.window.frameGeometry().intersects(self.window.recognition_window.frameGeometry()))

    def test_shutdown_hides_every_window_and_blocks_restore(self):
        self.window.show()
        self.window.show_recognition()
        self.window.open_settings()
        self.window.close()
        self.window.shutdown()
        self.window.show_panel()
        self.window.show_recognition()
        self.window.open_settings()
        self.assertTrue(all(not window.isVisible() for window in (self.window, self.window.recognition_window,
                                                                 self.window.settings_dialog, self.window.edge_dock)))
        self.assertFalse(self.window.dock_geometry_timer.isActive())
