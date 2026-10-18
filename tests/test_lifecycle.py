import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QThreadPool
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication

from screen_translator.core.text_blocks import TextBlock
from screen_translator.services.config import SettingsStore
from screen_translator.services.hotkey import GlobalCaptureHotkey
from screen_translator.services.instance import ApplicationInstance
from screen_translator.ui.main_window import MainWindow


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def test_duplicate_launch_only_activates_owner_and_can_restart_after_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            owner = ApplicationInstance(Path(temporary))
            second = ApplicationInstance(Path(temporary))
            activated = []
            owner.activated.connect(lambda: activated.append(True))
            try:
                self.assertTrue(owner.acquire_or_notify())
                code = (
                    "import sys; from pathlib import Path; from PySide6.QtCore import QCoreApplication; "
                    "from screen_translator.services.instance import ApplicationInstance; "
                    "app=QCoreApplication([]); instance=ApplicationInstance(Path(sys.argv[1])); "
                    "result=instance.acquire_or_notify(); instance.close(); sys.exit(1 if result else 0)"
                )
                child = subprocess.Popen([sys.executable, "-c", code, temporary], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    self.wait_for(lambda: child.poll() is not None)
                    stdout, stderr = child.communicate(timeout=1)
                    self.assertEqual(child.returncode, 0, (stdout, stderr))
                    self.wait_for(lambda: bool(activated))
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=3)
                self.assertEqual(activated, [True])
                second.close()
                self.assertTrue(owner.server.isListening())
                owner.close()
                self.assertTrue(second.acquire_or_notify())
            finally:
                owner.close()
                second.close()

    def test_invalid_instance_message_does_not_activate_panel(self):
        with tempfile.TemporaryDirectory() as temporary:
            owner = ApplicationInstance(Path(temporary))
            activated = Mock()
            owner.activated.connect(activated)
            socket = QLocalSocket()
            try:
                self.assertTrue(owner.acquire_or_notify())
                socket.connectToServer(owner.name)
                self.assertTrue(socket.waitForConnected(1000))
                socket.write(b"invalid command\n")
                socket.flush()
                self.wait_for(lambda: socket.state() == QLocalSocket.LocalSocketState.UnconnectedState)
                activated.assert_not_called()
            finally:
                socket.abort()
                owner.close()

    def test_crashed_instance_lock_is_recovered_without_manual_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            code = (
                "import os, sys; from pathlib import Path; from PySide6.QtCore import QCoreApplication; "
                "from screen_translator.services.instance import ApplicationInstance; "
                "app=QCoreApplication([]); instance=ApplicationInstance(Path(sys.argv[1])); "
                "result=instance.acquire_or_notify(); os._exit(0 if result else 1)"
            )
            crashed = subprocess.run([sys.executable, "-c", code, temporary], capture_output=True, timeout=5)
            self.assertEqual(crashed.returncode, 0, crashed.stderr)
            self.assertTrue((Path(temporary) / "application.lock").is_file())
            recovery = ApplicationInstance(Path(temporary))
            try:
                self.assertTrue(recovery.acquire_or_notify())
            finally:
                recovery.close()

    def test_hotkey_conflict_dispatch_and_cleanup(self):
        backend = Mock()
        backend.RegisterHotKey.return_value = False
        callback = Mock()
        hotkey = GlobalCaptureHotkey(self.app, callback, backend=backend)
        self.assertFalse(hotkey.start())
        hotkey.close()
        backend.UnregisterHotKey.assert_not_called()
        backend.RegisterHotKey.return_value = True
        try:
            self.assertTrue(hotkey.start())
            self.assertTrue(hotkey.start())
            event = wintypes.MSG()
            event.message, event.wParam = hotkey.WM_HOTKEY, hotkey.ID
            self.assertEqual(hotkey.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(event)), (True, 0))
            self.app.processEvents()
            callback.assert_called_once()
            event.wParam += 1
            self.assertEqual(hotkey.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(event)), (False, 0))
            backend.RegisterHotKey.assert_called_with(None, hotkey.ID, 0x4003, ord("S"))
        finally:
            hotkey.close()
        hotkey.close()
        backend.UnregisterHotKey.assert_called_once_with(None, hotkey.ID)

    def make_window(self, directory):
        window = MainWindow(SettingsStore(Path(directory) / "settings.json"))
        window.pool = QThreadPool(window)
        window.ocr = Mock()
        window.source_edit.setPlainText("original")
        window.translation_edit.setPlainText("原译文")
        window.copy_button.setEnabled(True)
        return window

    def dispose(self, window):
        window.shutdown()
        window.pool.waitForDone(3000)
        self.app.processEvents()
        window.hide()
        window.deleteLater()
        self.app.processEvents()

    def test_repeated_capture_and_cancel_stop_delayed_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            window = self.make_window(temporary)
            try:
                window.begin_capture()
                generation = window.capture_generation
                window.begin_capture()
                self.assertEqual(window.capture_generation, generation)
                self.assertTrue(window.capture_timer.isActive())
                window.cancel_selection()
                self.assertFalse(window.capture_timer.isActive())
                window._show_capture_overlay()
                self.assertIsNone(window.overlay)
                self.assertEqual(window.source_edit.toPlainText(), "original")
                self.assertEqual(window.translation_edit.toPlainText(), "原译文")
            finally:
                self.dispose(window)

    def test_cancel_during_ocr_discards_late_result_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            window = self.make_window(temporary)
            release = threading.Event()
            started = threading.Event()
            def recognize(_image):
                started.set()
                release.wait(3)
                return [TextBlock("old", "late OCR", ((0, 0), (50, 0), (50, 20), (0, 20)))]
            window.ocr.recognize.side_effect = recognize
            try:
                window.begin_capture()
                window.capture_timer.stop()
                image = QPixmap(100, 40)
                image.fill(QColor("white"))
                window._capture_selected(image, QRect(0, 0, 100, 40), window.capture_generation)
                self.assertTrue(started.wait(1))
                window.cancel_selection()
                window.source_edit.setPlainText("edited while OCR runs")
                window.begin_capture()
                self.assertFalse(window.capture_timer.isActive())
                self.assertIn("收尾", window.status_label.text())
                release.set()
                self.wait_for(lambda: not window._workers)
                self.assertTrue(window.selection_frame.isHidden())
                self.assertEqual(window.source_edit.toPlainText(), "edited while OCR runs")
                self.assertEqual(window.translation_edit.toPlainText(), "")
                self.assertTrue(window.capture_button.isEnabled())
                window.begin_capture()
                self.assertTrue(window.capture_timer.isActive())
            finally:
                release.set()
                self.dispose(window)

    def test_capture_uses_cursor_monitor_and_old_callbacks_cannot_restart_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            window = self.make_window(temporary)
            selected_screen = Mock()
            try:
                with patch("screen_translator.ui.main_window.QGuiApplication.screenAt", return_value=selected_screen):
                    window.begin_capture()
                self.assertIs(window._capture_screen, selected_screen)
                old = window.capture_generation
                window.cancel_selection()
                window.begin_capture()
                window._capture_cancelled(old)
                self.assertTrue(window.capture_timer.isActive())
                window.shutdown()
                window._ocr_ready(old, [])
                window.begin_capture()
                self.assertFalse(window.capture_timer.isActive())
                self.assertTrue(window.selection_frame.isHidden())
            finally:
                self.dispose(window)
