import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screen_translator.ui.capture_overlay import CaptureOverlay  # noqa: E402


class CaptureOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        screenshot = QPixmap(400, 200)
        screenshot.fill(Qt.GlobalColor.white)
        self.overlay = CaptureOverlay(QRect(0, 0, 200, 100), screenshot)

    def tearDown(self):
        self.overlay.deleteLater()
        self.app.processEvents()

    def test_named_overlay_emits_selected_region_in_image_pixels(self):
        self.assertEqual(self.overlay.windowTitle(), "框选文字")
        regions = []
        self.overlay.selected.connect(regions.append)
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(60, 40))
        self.assertEqual(regions, [QRect(20, 20, 102, 62)])

    def test_escape_cancels_without_returning_a_region(self):
        cancelled = []
        regions = []
        self.overlay.cancelled.connect(lambda: cancelled.append(True))
        self.overlay.selected.connect(regions.append)
        QTest.keyClick(self.overlay, Qt.Key.Key_Escape)
        self.assertEqual(cancelled, [True])
        self.assertEqual(regions, [])

    def test_negative_screen_origin_fractional_dpi_and_outside_drag_are_clamped(self):
        for scale in (1, 1.5, 2):
            with self.subTest(scale=scale):
                screenshot = QPixmap(round(200 * scale), round(100 * scale))
                screenshot.setDevicePixelRatio(scale)
                overlay = CaptureOverlay(QRect(-200, -100, 200, 100), screenshot)
                try:
                    self.assertEqual(overlay.geometry(), QRect(-200, -100, 200, 100))
                    self.assertEqual(overlay._pixmap_rect(QRect(-10, -10, 220, 120)),
                                     QRect(0, 0, screenshot.width(), screenshot.height()))
                    rect = overlay._pixmap_rect(QRect(11, 13, 61, 31))
                    self.assertEqual(rect.x() + rect.width(), round(72 * scale))
                    self.assertEqual(rect.y() + rect.height(), round(44 * scale))
                finally:
                    overlay.deleteLater()


if __name__ == "__main__":
    unittest.main()
