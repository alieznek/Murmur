from __future__ import annotations

import json
import os
import platform
import socket
import sys
import tempfile
from pathlib import Path


def run_self_check(report_path: Path) -> int:
    """Exercise the bundled runtime with network access disabled, without user data."""
    from screen_translator import __version__

    report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "python": platform.python_version(), "system": platform.platform(), "passed": False}
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def no_network(*_args, **_kwargs):
        raise RuntimeError("Self-check forbids network access")

    def checkpoint(stage: str):
        report["stage"] = stage
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        checkpoint("runtime")
        socket.socket.connect = no_network
        socket.create_connection = no_network
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QImage, QPainter
        from screen_translator.resources import app_icon_path
        from screen_translator.services.config import SettingsStore, SystemCredentialStore
        from screen_translator.services.ocr import RapidOcrService
        from screen_translator.ui.main_window import MainWindow, create_application
        from screen_translator.ui.settings_dialog import SettingsDialog

        app = create_application()
        if sys.platform == "win32":
            # The offscreen Qt plugin does not enumerate Windows system fonts.
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
            if font_path.is_file():
                QFontDatabase.addApplicationFont(str(font_path))
        checkpoint("qt")
        image = QImage(540, 100, QImage.Format.Format_RGB888)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setPen(QColor("black"))
        painter.setFont(QFont("Arial", 34))
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "HELLO WORLD")
        painter.end()
        checkpoint("ocr")
        blocks = RapidOcrService().recognize(MainWindow._qimage_to_array(image))
        report["offline_ocr"] = any("HELLO" in block.text.upper() for block in blocks)
        report["icon"] = not QIcon(str(app_icon_path())).isNull()
        report["credential_backend"] = type(SystemCredentialStore()._backend()).__name__
        checkpoint("settings")

        # Use an isolated empty config: never load the user's settings or credentials.
        with tempfile.TemporaryDirectory() as temporary:
            store = SettingsStore(Path(temporary) / "settings.json")
            store._write({"schema": 1, "active_provider": "baidu", "providers": {}})
            window = MainWindow(store)
            dialog = SettingsDialog(store, window)
            report["settings_ui"] = dialog.provider_combo.count() == 5 and len(dialog.fields) == 3
            dialog.reject()
            checkpoint("online-protocols-mock")
            from screen_translator.diagnostics.online import check_online_protocols
            report["online_protocols_mock"] = check_online_protocols()
            checkpoint("lifecycle")
            from screen_translator.diagnostics.lifecycle import check_lifecycle
            report["lifecycle"] = check_lifecycle(window, app, Path(temporary))
            checkpoint("windows")
            from screen_translator.diagnostics.windows import check_windows
            report["windows"] = check_windows(window, app)
            checkpoint("offline-translation")
            from screen_translator.diagnostics.offline import check_offline
            check_offline(window, app, checkpoint, report)
            window.shutdown()
            dialog.deleteLater()
            window.deleteLater()
            app.processEvents()
        report["passed"] = all(report[key] for key in ("offline_ocr", "icon", "settings_ui", "offline_passed")) and report["online_protocols_mock"]["passed"] and report["lifecycle"]["passed"] and report["windows"]["passed"]
        report["stage"] = "complete"
    except Exception as error:
        # Self-check uses synthetic input, but still avoid copying dependency messages.
        report["error_type"] = type(error).__name__
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create_connection
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1
