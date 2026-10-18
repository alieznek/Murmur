from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class CaptureOverlay(QWidget):
    selected = Signal(QRect)
    cancelled = Signal()

    def __init__(self, screen_geometry: QRect, screenshot: QPixmap) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("框选文字")
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._screenshot = screenshot
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._screenshot)
        painter.fillRect(self.rect(), QColor(10, 18, 24, 80))
        painter.setPen(QColor("white"))
        painter.drawText(24, 38, "拖动框选文字区域 · Esc 取消")
        if self._origin is not None and self._current is not None:
            rect = QRect(self._origin, self._current).normalized()
            painter.drawPixmap(rect, self._screenshot, self._pixmap_rect(rect))
            painter.setPen(QPen(QColor("#81c79a"), 2))
            painter.drawRect(rect)

    def _pixmap_rect(self, rect: QRect) -> QRect:
        rect = rect.intersected(self.rect())
        sx = self._screenshot.width() / max(1, self.width())
        sy = self._screenshot.height() / max(1, self.height())
        left, top = round(rect.x() * sx), round(rect.y() * sy)
        right, bottom = round((rect.x() + rect.width()) * sx), round((rect.y() + rect.height()) * sy)
        return QRect(left, top, right - left, bottom - top)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = QRect(self._origin, event.position().toPoint()).normalized().intersected(self.rect())
        self._origin = None
        if rect.width() < 12 or rect.height() < 12:
            self.cancelled.emit()
            return
        self.selected.emit(self._pixmap_rect(rect))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)
