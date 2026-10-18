"""Render and open the real native project UI, isolated from personal configuration."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--native", action="store_true")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--view", choices=("chat", "scroll", "fonts", "platforms", "ocr", "ocr-settings", "dock"), default="chat")
args = parser.parse_args()
if not args.native:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPainter, QPixmap, QShortcut
from screen_translator.core.text_blocks import TextBlock
from screen_translator.services.config import SettingsStore
from screen_translator.ui.main_window import MainWindow, create_application


class PreviewCredentials:
    def __init__(self):
        self.entries = {}

    def get(self, key):
        return self.entries.get(key)

    def set(self, key, value):
        self.entries[key] = value

    def delete(self, key):
        self.entries.pop(key, None)


def seed(window):
    conversation = window.current_conversation()
    conversation["title"] = "一句关于生活的话"
    conversation["messages"] = [{"id": "native-review", "source": "我想慢一点，走远一点。",
                                  "translation": "I want to slow down,\nso I can go further.", "target": "英语",
                                  "provider": "本地 · Argos", "status": "complete"}]
    if args.view == "scroll":
        conversation["title"] = "长段落与滚轮浏览"
        conversation["messages"] = [{"id": f"scroll-review-{index}",
            "source": f"第 {index + 1} 段 · 阅读长段翻译，窗口不需要拉伸。",
            "translation": (("This is the Murmur translation workspace. "
                            "You can read the entire translation by scrolling through the conversation. "
                            "The input area stays in place, and the copy action follows the final line.\n\n") * 3).strip(),
            "target": "英语", "provider": "本地 · Argos", "status": "complete"}
            for index in range(3)]
    window.render_conversation(scroll=False)
    window.target_combo.setCurrentText("English")
    window.status_label.setText("原生界面验收 · 示例内容")
    image = QPixmap(680, 420)
    image.fill(QColor("#fffdf8"))
    painter = QPainter(image)
    painter.setPen(QColor("#54443c"))
    painter.setFont(QFont("Segoe UI", 23))
    lines = ["Welcome to Tokyo!", "Next stop: Shinjuku Station.", "Please keep your ticket with you.", "Enjoy your journey."]
    for index, line in enumerate(lines):
        painter.drawText(36, index * 76 + 75, line)
    painter.end()
    window.candidate_pixmap = image
    window.blocks = [TextBlock(str(index), line, ((30, index * 76 + 33), (650, index * 76 + 33),
                                                (650, index * 76 + 83), (30, index * 76 + 83)))
                     for index, line in enumerate(lines)]
    window._capture_active = True
    window._show_selection_state()
    window.recognition_window.hide()
    if args.view == "scroll":
        window.render_conversation()


def main():
    args.output.mkdir(parents=True, exist_ok=True)
    app = create_application()
    # Offscreen Qt does not enumerate the system font service in the restricted runtime.
    # Read the same installed Windows fonts used by the real desktop window.
    for name in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc", "msyhbd.ttc", "georgia.ttf", "georgiai.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    store = SettingsStore(args.output / "isolated-settings.json", PreviewCredentials())
    window = MainWindow(store)
    window.setWindowTitle("Murmur（译语） 原生界面验收" + (" · " + args.view if args.view != "chat" else ""))
    window.resize(674, 844)
    window.show()
    seed(window)
    exit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), window)
    exit_shortcut.activated.connect(app.quit)
    if args.native:
        if args.view in ("fonts", "platforms", "ocr-settings"):
            window.open_settings()
            window.settings_dialog.select_page("ocr" if args.view == "ocr-settings" else args.view)
            if args.view == "platforms":
                window.settings_dialog.provider_combo.setCurrentIndex(window.settings_dialog.provider_combo.findData("tencent_tokenhub"))
        elif args.view == "ocr":
            window.show_recognition()
        elif args.view == "dock":
            # Computer Use enumerates ordinary windows, not taskbar-free Qt tools.
            # Exercise the actual icon widget and handlers in a targetable window.
            window.edge_dock.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                                            Qt.WindowType.WindowStaysOnTopHint)
            window.edge_dock.setWindowTitle("译语 · 浮动图标验收")
            window.close()
        def save_native_view():
            surface = window.edge_dock if args.view == "dock" else window.settings_dialog if args.view in ("fonts", "platforms", "ocr-settings") else window.recognition_window if args.view == "ocr" else window
            surface.grab().save(str(args.output / (args.view + "-native.png")))
        QTimer.singleShot(1200, save_native_view)
        app.exec()
    else:
        for _ in range(4):
            app.processEvents()
        window.grab().save(str(args.output / "chat-light.png"))
        window.show_recognition()
        app.processEvents()
        window.recognition_window.grab().save(str(args.output / "ocr-light.png"))
        window.recognition_window.hide()
        window.open_settings()
        app.processEvents()
        window.settings_dialog.grab().save(str(args.output / "fonts-light.png"))
        window.settings_dialog.select_page("platforms")
        window.settings_dialog.provider_combo.setCurrentIndex(window.settings_dialog.provider_combo.findData("tencent_tokenhub"))
        app.processEvents()
        window.settings_dialog.grab().save(str(args.output / "platforms-light.png"))
        window.settings_dialog.select_page("ocr")
        app.processEvents()
        window.settings_dialog.grab().save(str(args.output / "ocr-settings-light.png"))
        window.settings_dialog.reject()
        window.theme_combo.setCurrentIndex(1)
        app.processEvents()
        window.grab().save(str(args.output / "chat-dark.png"))
        window.close()
        app.processEvents()
        window.edge_dock.grab().save(str(args.output / "dock-dark.png"))
        window.show_panel()
        window.theme_combo.setCurrentIndex(0)
        window.resize(460, 380)
        app.processEvents()
        window.grab().save(str(args.output / "chat-compact.png"))
    window.shutdown()


if __name__ == "__main__":
    main()
