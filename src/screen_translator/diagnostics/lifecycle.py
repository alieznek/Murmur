"""Synthetic lifecycle lifecycle checks; never capture the user's screen or load keys."""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path


def check_lifecycle(window, app, directory: Path) -> dict:
    from PySide6.QtNetwork import QLocalSocket
    from screen_translator.services.hotkey import GlobalCaptureHotkey
    from screen_translator.services.instance import ApplicationInstance

    result = {"kind": "synthetic_lifecycle_no_user_data"}

    def wait_for(predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if not predicate():
            raise RuntimeError("Application lifecycle deadline exceeded")

    owner = ApplicationInstance(directory / "instance", parent=app)
    activated = []
    owner.activated.connect(lambda: activated.append(True))
    socket = QLocalSocket(app)
    try:
        result["instance_owner"] = owner.acquire_or_notify()
        socket.connectToServer(owner.name)
        if not socket.waitForConnected(1000):
            raise RuntimeError("Application activation channel failed")
        socket.write(b"show\n")
        socket.flush()
        wait_for(lambda: bool(activated))
        result["instance_activation"] = activated == [True]
    finally:
        socket.abort()
        socket.deleteLater()
        owner.close()
        owner.deleteLater()

    hotkey_calls = []
    hotkey = GlobalCaptureHotkey(app, lambda: hotkey_calls.append(True))
    try:
        registered = hotkey.start()
        result["hotkey_registered"] = registered
        if registered and sys.platform == "win32":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentThreadId.restype = wintypes.DWORD
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.PostThreadMessageW.restype = wintypes.BOOL
            if not user.PostThreadMessageW(kernel.GetCurrentThreadId(), hotkey.WM_HOTKEY, hotkey.ID, 0):
                raise RuntimeError("Application hotkey dispatch failed")
            wait_for(lambda: bool(hotkey_calls))
            result["hotkey_dispatch"] = hotkey_calls == [True]
        else:
            result["hotkey_dispatch"] = "not_run_shortcut_unavailable"
    finally:
        hotkey.close()
    result["hotkey_released"] = not hotkey.registered

    window.source_edit.setPlainText("Synthetic lifecycle original")
    window.translation_edit.setPlainText("合成生命周期 译文")
    window.begin_capture()
    old = window.capture_generation
    window.begin_capture()
    result["capture_coalesced"] = old == window.capture_generation
    window.cancel_selection()
    window._show_capture_overlay()
    window._ocr_ready(old, [])
    result["capture_cancelled"] = not window.capture_timer.isActive() and window.overlay is None and window.selection_frame.isHidden()
    result["source_preserved"] = window.source_edit.toPlainText() == "Synthetic lifecycle original"
    result["translation_preserved"] = window.translation_edit.toPlainText() == "合成生命周期 译文"
    result["passed"] = all(result[key] for key in ("instance_owner", "instance_activation", "hotkey_released",
        "capture_coalesced", "capture_cancelled", "source_preserved", "translation_preserved")) and result["hotkey_dispatch"] is not False
    return result
