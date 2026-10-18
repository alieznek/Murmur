from __future__ import annotations

import sys
import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from screen_translator.ui.main_window import MainWindow, create_application


def main() -> int:
    parser = argparse.ArgumentParser(description="屏幕翻译器")
    parser.add_argument("--self-check", type=Path, metavar="REPORT_JSON", help="运行离线资源自检并写入报告后退出")
    parser.add_argument("--profile-dir", type=Path, help="使用独立的配置和会话目录（用于本机界面实测）")
    args = parser.parse_args()
    if args.self_check:
        from screen_translator.diagnostics.runtime import run_self_check
        return run_self_check(args.self_check)
    app = create_application()
    if not QApplication.platformName() and sys.platform != "win32":
        QMessageBox.warning(None, "屏幕翻译器", "当前桌面环境无法创建图形界面。")
        return 1
    from screen_translator.services.instance import ApplicationInstance
    from screen_translator.services.hotkey import GlobalCaptureHotkey

    try:
        instance = ApplicationInstance(directory=args.profile_dir, parent=app)
        if not instance.acquire_or_notify():
            return 0
    except (OSError, RuntimeError) as error:
        QMessageBox.warning(None, "启动未完成", str(error))
        return 1
    try:
        from screen_translator.services.config import SettingsStore
        store = SettingsStore(args.profile_dir / "settings.json") if args.profile_dir else None
        window = MainWindow(store)
        instance.activated.connect(window.show_panel)
        hotkey = GlobalCaptureHotkey(app, window.begin_capture)
        if not hotkey.start():
            window.capture_button.setToolTip("Ctrl+Alt+S 注册失败，可能被其他程序占用；仍可点击取词或使用托盘菜单。")
            window.status_label.setText("●  Ctrl+Alt+S 不可用，可点击取词或使用托盘菜单")
        app.aboutToQuit.connect(hotkey.close)
        window.show()
        return app.exec()
    finally:
        if "hotkey" in locals():
            hotkey.close()
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
