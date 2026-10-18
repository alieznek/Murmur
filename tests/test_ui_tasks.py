import gc
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QThread, QThreadPool, Slot, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from screen_translator.core.text_blocks import TextBlock  # noqa: E402
from screen_translator.ui.main_window import MainWindow  # noqa: E402


class RecordingWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.callback_threads = []

    @Slot(object, object)
    def _translation_ready(self, context, translation):
        self.callback_threads.append(QThread.currentThread())
        super()._translation_ready(context, translation)

    @Slot(object, str)
    def _translation_failed(self, context, message):
        self.callback_threads.append(QThread.currentThread())
        super()._translation_failed(context, message)

    @Slot(object, object)
    def _ocr_ready(self, generation, blocks):
        self.callback_threads.append(QThread.currentThread())
        super()._ocr_ready(generation, blocks)

    @Slot(object, str)
    def _ocr_failed(self, generation, message):
        self.callback_threads.append(QThread.currentThread())
        super()._ocr_failed(generation, message)


class UiTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = RecordingWindow()
        self.window.pool = QThreadPool(self.window)
        self.window.translator = Mock()
        self.window.ocr = Mock()
        self.warning = patch("screen_translator.ui.main_window.QMessageBox.warning").start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.window.pool.waitForDone(3000)
        self.app.processEvents()
        self.window.tray.hide()
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate(), "Background task did not update the UI")

    def assert_finished_on_ui_thread(self):
        self.wait_for(lambda: not self.window._workers)
        self.assertTrue(self.window.callback_threads)
        self.assertTrue(all(thread == self.app.thread() for thread in self.window.callback_threads))

    def capture(self, width=101):
        screenshot = QPixmap(width, 40)
        screenshot.fill(QColor("white"))
        self.window._capture_active = True
        self.window._capture_selected(screenshot, QRect(0, 0, width, 40))

    def test_manual_translation_returns_to_ui_and_releases_worker(self):
        self.window.translator.translate.return_value = "你好，世界"
        self.window.source_edit.setPlainText("hello world")
        self.window.show()
        self.window.activateWindow()
        self.window.source_edit.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.source_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        gc.collect()
        self.wait_for(lambda: not self.window.translation_running)
        self.assertEqual(self.window.translation_edit.toPlainText(), "你好，世界")
        self.assertFalse(self.window.translate_button.isEnabled())
        self.assertEqual(self.window.source_edit.toPlainText(), "")
        self.assertEqual(self.window.current_conversation()["messages"][-1]["translation"], "你好，世界")
        self.assertTrue(self.window.copy_button.isEnabled())
        self.assertIn("翻译完成", self.window.status_label.text())
        self.assert_finished_on_ui_thread()

    def test_translation_failure_is_visible_and_can_be_retried(self):
        self.window.translator.translate.side_effect = RuntimeError("UserUnregister")
        self.window.source_edit.setPlainText("hello world")
        self.window.translate()
        self.wait_for(lambda: not self.window.translation_running)
        self.warning.assert_called_once_with(self.window, "翻译未完成", "翻译组件发生异常，请检查配置后主动重试。")
        self.assertTrue(self.window.translate_button.isEnabled())
        self.assertIn("翻译失败", self.window.status_label.text())
        self.assert_finished_on_ui_thread()

        self.window.translator.translate.side_effect = None
        self.window.translator.translate.return_value = "你好，世界"
        self.window.translate()
        self.wait_for(lambda: self.window.translation_edit.toPlainText() == "你好，世界")
        self.assert_finished_on_ui_thread()

    def test_translation_discards_results_after_source_or_target_changes(self):
        for change in (lambda: self.window.source_edit.setPlainText("new text"),
                       lambda: self.window.target_combo.setCurrentText("English")):
            with self.subTest(change=change):
                release = threading.Event()
                self.addCleanup(release.set)

                def delayed_translation(*_args):
                    if not release.wait(3):
                        raise RuntimeError("Test task was not released")
                    return "old result"

                self.window.translator.translate.side_effect = delayed_translation
                self.window.source_edit.setPlainText("hello world")
                self.window.translate()
                change()
                release.set()
                self.wait_for(lambda: not self.window.translation_running)
                self.assertEqual(self.window.translation_edit.toPlainText(), "")
                self.assertTrue(self.window.translate_button.isEnabled())
                self.assert_finished_on_ui_thread()

    def test_ocr_returns_selectable_text_then_fills_source(self):
        self.window.ocr.recognize.return_value = [
            TextBlock("line-1", "hello world", ((0, 0), (100, 0), (100, 30), (0, 30)))
        ]
        self.capture()
        gc.collect()
        # Result and finished are separate queued signals. Recapture is enabled
        # only after the worker has released its resources.
        self.wait_for(lambda: self.window.block_list.count() == 1 and self.window._ocr_worker is None)
        self.assertTrue(self.window.capture_button.isEnabled())
        self.assertFalse(self.window.selection_frame.isHidden())
        self.window.select_all_blocks()
        self.window.confirm_selection()
        self.assertEqual(self.window.source_edit.toPlainText(), "hello world")
        self.assert_finished_on_ui_thread()

    def test_ocr_failure_is_visible_and_capture_can_be_retried(self):
        self.window.ocr.recognize.side_effect = RuntimeError("OCR model failure")
        self.capture()
        self.wait_for(lambda: self.window.capture_button.isEnabled())
        self.warning.assert_called_once_with(self.window, "文字识别失败", "OCR 组件发生异常，请重新取词；仍失败时重新解压完整包。")
        self.assertIn("OCR 失败", self.window.status_label.text())
        self.assert_finished_on_ui_thread()

    def test_empty_ocr_result_finishes_without_waiting_forever(self):
        self.window.ocr.recognize.return_value = []
        self.capture()
        self.wait_for(lambda: self.window.capture_button.isEnabled())
        self.assertIn("未识别到文字", self.window.status_label.text())
        self.assertFalse(self.window.confirm_button.isEnabled())
        self.assert_finished_on_ui_thread()

    def test_qimage_conversion_removes_row_padding_and_returns_owned_bgr_pixels(self):
        for width in (100, 101, 102, 103):
            with self.subTest(width=width):
                image = QImage(width, 2, QImage.Format.Format_RGB888)
                image.fill(QColor(11, 22, 33))
                image.setPixelColor(width - 1, 1, QColor(44, 55, 66))
                array = self.window._qimage_to_array(image)
                self.assertEqual(array.shape, (2, width, 3))
                self.assertEqual(array[0, 0].tolist(), [33, 22, 11])
                self.assertEqual(array[1, width - 1].tolist(), [66, 55, 44])
                self.assertTrue(array.flags.c_contiguous)
                image.fill(QColor("black"))
                self.assertEqual(array[0, 0].tolist(), [33, 22, 11])


if __name__ == "__main__":
    unittest.main()
