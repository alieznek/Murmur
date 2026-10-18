import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from screen_translator.resources import MODEL_FILES, app_icon_path, ocr_parameters  # noqa: E402
from screen_translator.services.config import SettingsStore  # noqa: E402
from screen_translator.services.ocr import RapidOcrService  # noqa: E402
from screen_translator.services.offline_resources import resource_directory  # noqa: E402
from screen_translator.ui.design_tokens import DARK, LIGHT  # noqa: E402
from screen_translator.ui.main_window import MainWindow, create_application  # noqa: E402


ICONS = Path(__file__).resolve().parents[1] / "app-icon"
ICO_SIZES = {(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
             (48, 48), (64, 64), (128, 128), (256, 256)}


def contrast(first, second):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + .05) / (low + .05)


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_export_uses_files_beside_script_from_another_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="translator icon ") as temporary:
            working_directory = Path(temporary)
            icon_directory = working_directory / "app icon resources"
            icon_directory.mkdir()
            for filename in ("translator.svg", "export.py"):
                shutil.copy2(ICONS / filename, icon_directory / filename)
            result = subprocess.run(
                [sys.executable, str(icon_directory / "export.py")],
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for filename in ("translator.png", "translator.ico", "preview.png"):
                with self.subTest(filename=filename):
                    with Image.open(icon_directory / filename) as image:
                        image.verify()

    def test_ico_contains_required_sizes_and_loads_in_qt(self):
        with Image.open(ICONS / "translator.ico") as ico:
            self.assertEqual(ico.ico.sizes(), ICO_SIZES)
            for size in ICO_SIZES:
                frame = ico.ico.getimage(size)
                self.assertEqual(frame.size, size)
                self.assertEqual(frame.getpixel((0, 0))[3], 0)
        icon = QIcon(str(ICONS / "translator.ico"))
        self.assertFalse(icon.isNull())
        for width, height in ICO_SIZES:
            with self.subTest(size=width):
                pixmap = icon.pixmap(width, height)
                self.assertFalse(pixmap.isNull())
                self.assertEqual((pixmap.width(), pixmap.height()), (width, height))


class PackagedResourceTests(unittest.TestCase):
    def test_development_resources_use_explicit_repository_paths(self):
        self.assertTrue(app_icon_path().is_file())
        root = Path(__file__).resolve().parents[1]
        with patch("pathlib.Path.is_file", return_value=True):
            parameters = ocr_parameters()
        self.assertEqual(parameters["Rec.model_path"], str(root / "models/ocr" / MODEL_FILES["Rec"]))
        self.assertEqual(resource_directory(), root / "models/argos")

    def test_bundle_missing_models_fails_locally_instead_of_downloading(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "_MEIPASS", temporary, create=True
        ), patch("rapidocr.RapidOCR") as engine:
            with self.assertRaisesRegex(RuntimeError, "离线 OCR 模型不完整"):
                RapidOcrService().recognize(object())
            engine.assert_not_called()

    def test_bundle_has_explicit_model_paths_and_icon(self):
        with tempfile.TemporaryDirectory() as temporary:
            models = Path(temporary) / "resources/models"
            models.mkdir(parents=True)
            for filename in MODEL_FILES.values():
                (models / filename).touch()
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", temporary, create=True):
                parameters = ocr_parameters()
                self.assertEqual(parameters["Rec.model_path"], str(models / MODEL_FILES["Rec"]))
                self.assertEqual(app_icon_path(), Path(temporary) / "resources/app-icon/translator.ico")
                self.assertEqual(resource_directory(), Path(temporary) / "resources/argos")
                with patch("rapidocr.RapidOCR") as engine:
                    engine.return_value.return_value.boxes = None
                    engine.return_value.return_value.txts = None
                    self.assertEqual(RapidOcrService().recognize(object()), [])
                    engine.assert_called_once_with(params=parameters)


class UiPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_themes_have_readable_contrast_and_window_icon(self):
        with tempfile.TemporaryDirectory() as temporary:
            window = MainWindow(SettingsStore(Path(temporary) / "settings.json"))
            try:
                for theme in (LIGHT, DARK):
                    for foreground, background in ((theme.text, theme.panel), (theme.muted, theme.panel),
                                                  (theme.muted, theme.canvas), ("#ffffff", theme.action)):
                        self.assertGreaterEqual(contrast(foreground, background), 4.5)
                self.assertFalse(window.windowIcon().isNull())
            finally:
                window.shutdown()
                window.deleteLater()

    def test_create_application_reuses_existing_qapplication(self):
        self.assertIs(create_application(), self.app)


if __name__ == "__main__":
    unittest.main()
