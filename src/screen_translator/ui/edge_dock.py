from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QHBoxLayout, QPushButton, QWidget

from screen_translator.ui.theme import stylesheet
from screen_translator.ui.qt_controls import app_mark_icon, decorate_button, palette_for, refresh_icons


class EdgeDock(QWidget):
    """A floating restore icon: hold to drag, double-click to open."""

    translation_requested = Signal()
    position_changed = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("译语 · 浮动图标")
        self.setWindowIcon(app_mark_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(68, 68)
        self.side = "right"
        self.area = None
        self._floating_position = None
        self._press_position = None
        self._grab_offset = QPoint()
        self._dragging = False
        self._last_release_dragged = False
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        self.handle = QPushButton()
        decorate_button(self.handle, "logo", "按住拖动 · 双击打开译语")
        self.handle.setObjectName("dockHandle")
        self.handle.setFixedSize(48, 48)
        self.handle.setIconSize(QSize(27, 27))
        self.handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.handle.installEventFilter(self)
        # Mouse releases are handled below; keyboard activation remains available.
        self.handle.clicked.connect(self.translation_requested)
        root.addWidget(self.handle)
        shadow = QGraphicsDropShadowEffect(self.handle)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(70, 40, 24, 65))
        self.handle.setGraphicsEffect(shadow)
        self.apply_theme("light")

    def _bounded_position(self, position, area):
        return QPoint(max(area.left(), min(position.x(), area.right() - self.width() + 1)),
                      max(area.top(), min(position.y(), area.bottom() - self.height() + 1)))

    def position_in(self, area, side=None, position=None):
        if self._press_position is not None:
            return  # The work-area timer must never move an icon being dragged.
        side = side or self.side
        if side != self.side:
            self._floating_position = None
        self.side = side
        if self._floating_position is None and position is not None:
            self._floating_position = QPoint(*position)
        if self._floating_position is not None:
            screen = QGuiApplication.screenAt(self._floating_position + self.rect().center())
            area = screen.availableGeometry() if screen else area
            point = self._bounded_position(self._floating_position, area)
            self._floating_position = point
        else:
            point = QPoint(area.left() + 8 if side == "left" else area.right() - self.width() - 7,
                           area.top() + (area.height() - self.height()) // 2)
            point = self._bounded_position(point, area)
        self.area = area
        self.move(point)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.handle:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._press_position = event.globalPosition().toPoint()
                self._grab_offset = self._press_position - self.pos()
                self._dragging = False
                self.handle.setDown(True)
                self.handle.setFocus(Qt.FocusReason.MouseFocusReason)
                self.handle.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.handle.grabMouse()
                return True
            elif event.type() == QEvent.Type.MouseMove and self._press_position is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    cursor = event.globalPosition().toPoint()
                    if (cursor - self._press_position).manhattanLength() >= QApplication.startDragDistance():
                        self._dragging = True
                    if self._dragging:
                        self.handle.setDown(False)
                        screen = QGuiApplication.screenAt(cursor) or self.screen()
                        self.area = screen.availableGeometry()
                        self.move(self._bounded_position(cursor - self._grab_offset, self.area))
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                dragged = self._dragging
                self._last_release_dragged = dragged
                self._end_drag()
                if dragged:
                    self._floating_position = QPoint(self.pos())
                    self.position_changed.emit(self.pos())
                return True  # A click or drag release must not restore the window.
            elif event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                should_open = not self._last_release_dragged
                self._last_release_dragged = False
                self._end_drag()
                if should_open:
                    self.translation_requested.emit()
                return True
        return super().eventFilter(watched, event)

    def _end_drag(self):
        self._press_position = None
        self._dragging = False
        self.handle.setDown(False)
        self.handle.setCursor(Qt.CursorShape.OpenHandCursor)
        if QWidget.mouseGrabber() is self.handle:
            self.handle.releaseMouse()

    def hideEvent(self, event):  # noqa: N802
        self._end_drag()
        super().hideEvent(event)

    def apply_theme(self, theme):
        self.setStyleSheet(stylesheet(theme=theme))
        self.setPalette(palette_for(theme))
        refresh_icons(self, theme)
