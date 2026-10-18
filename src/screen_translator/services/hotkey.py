from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer


class GlobalCaptureHotkey(QAbstractNativeEventFilter):
    """Register Ctrl+Alt+S on the UI thread without a keyboard hook."""

    ID = 0x5354
    WM_HOTKEY = 0x0312
    MODIFIERS = 0x0001 | 0x0002 | 0x4000  # Alt, Ctrl, no autorepeat

    def __init__(self, app, callback, *, backend=None):
        super().__init__()
        self.app = app
        self.callback = callback
        self.registered = False
        self.backend = backend
        if self.backend is None and sys.platform == "win32":
            self.backend = ctypes.WinDLL("user32", use_last_error=True)
            self.backend.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.backend.RegisterHotKey.restype = wintypes.BOOL
            self.backend.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.backend.UnregisterHotKey.restype = wintypes.BOOL

    def start(self) -> bool:
        if self.registered:
            return True
        if self.backend is None or not self.backend.RegisterHotKey(None, self.ID, self.MODIFIERS, ord("S")):
            return False
        self.registered = True
        self.app.installNativeEventFilter(self)
        return True

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if self.registered and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            event = wintypes.MSG.from_address(int(message))
            if event.message == self.WM_HOTKEY and event.wParam == self.ID:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0

    def close(self):
        if self.registered:
            self.registered = False
            self.app.removeNativeEventFilter(self)
            self.backend.UnregisterHotKey(None, self.ID)
