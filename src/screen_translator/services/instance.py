from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class ApplicationInstance(QObject):
    """One panel per user; a second launch only asks the owner to show it."""

    activated = Signal()

    def __init__(self, directory: Path | None = None, parent=None):
        super().__init__(parent)
        directory = directory or Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericDataLocation)) / "Murmur"
        directory.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(str(directory.resolve()).casefold().encode()).hexdigest()[:24]
        self.name = "Murmur-" + identity
        self.lock = QLockFile(str(directory / "application.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self._sockets = set()

    def acquire_or_notify(self) -> bool:
        if self.lock.tryLock(0):
            # Only the lock owner may remove a stale endpoint after a crash.
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise RuntimeError("无法创建本机启动通道，请检查配置目录权限后重试。")
            return True
        if self.lock.error() != QLockFile.LockError.LockFailedError:
            raise RuntimeError("无法锁定程序配置目录，请检查目录权限后重试。")
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(1500):
            raise RuntimeError("屏幕翻译器已在运行或正在启动，请从托盘恢复，或稍后重试。")
        socket.write(b"show\n")
        sent = socket.bytesToWrite() == 0 or socket.waitForBytesWritten(1500)
        socket.disconnectFromServer()
        if not sent:
            raise RuntimeError("未能通知已运行的面板，请从托盘恢复。")
        return False

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self._sockets.add(socket)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(2000)
            socket.readyRead.connect(lambda socket=socket: self._read(socket))
            socket.disconnected.connect(lambda socket=socket: self._discard(socket))
            self._read(socket)

    def _read(self, socket):
        if socket.bytesAvailable() > 16:
            socket.abort()
        elif socket.canReadLine():
            if bytes(socket.readLine(16)) == b"show\n":
                self.activated.emit()
            socket.disconnectFromServer()

    def _discard(self, socket):
        self._sockets.discard(socket)
        socket.deleteLater()

    def close(self):
        for socket in tuple(self._sockets):
            socket.abort()
        self.server.close()
        self.lock.unlock()
