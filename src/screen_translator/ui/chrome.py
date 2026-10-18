"""Integrated paper-colored chrome, with native dragging and resizing."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget
from screen_translator.ui.theme import WindowSurface, toggle_expanded


class WindowShell(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.face = WindowSurface()
        self.face.setMouseTracking(True)
        self.face.setObjectName("paperSurface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 15)
        layout.setSpacing(0)
        layout.addWidget(self.face)
        self.controller = ResizeController(window, self)

    @property
    def theme(self):
        return self.face.theme

    @theme.setter
    def theme(self, value):
        self.face.theme = value
        self.face.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bounds = QRectF(self.face.geometry()).translated(0, 4)
        for distance in range(11, 0, -1):
            shade = QColor("#583c29")
            shade.setAlpha(max(1, 13 - distance))
            painter.setPen(QPen(shade, 1.7))
            painter.drawRoundedRect(bounds.adjusted(-distance, -distance, distance, distance),
                                    25 + distance, 25 + distance)


class ResizeController(QObject):
    def __init__(self, window, shell):
        super().__init__(window)
        self.window, self.origin, self.geometry = window, None, None
        self.edges = Qt.Edge(0)
        for widget in (window, shell, shell.face):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def edge_at(self, point):
        if self.window.isMaximized():
            return Qt.Edge(0)
        edges = Qt.Edge(0)
        if point.x() < 14:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= self.window.width() - 14:
            edges |= Qt.Edge.RightEdge
        if point.y() < 10:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= self.window.height() - 15:
            edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            return False
        edges = self.edge_at(self.window.mapFromGlobal(event.globalPosition().toPoint()))
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton and edges:
            handle = self.window.windowHandle()
            if handle and handle.startSystemResize(edges):
                return True
            self.origin, self.geometry, self.edges = event.globalPosition().toPoint(), self.window.geometry(), edges
            return True
        if event.type() == QEvent.Type.MouseMove:
            if self.origin is not None:
                delta, rect = event.globalPosition().toPoint() - self.origin, self.geometry.adjusted(0, 0, 0, 0)
                if self.edges & Qt.Edge.LeftEdge:
                    rect.setLeft(min(rect.right() - self.window.minimumWidth() + 1, rect.left() + delta.x()))
                if self.edges & Qt.Edge.RightEdge:
                    rect.setRight(max(rect.left() + self.window.minimumWidth() - 1, rect.right() + delta.x()))
                if self.edges & Qt.Edge.TopEdge:
                    rect.setTop(min(rect.bottom() - self.window.minimumHeight() + 1, rect.top() + delta.y()))
                if self.edges & Qt.Edge.BottomEdge:
                    rect.setBottom(max(rect.top() + self.window.minimumHeight() - 1, rect.bottom() + delta.y()))
                self.window.setGeometry(rect)
                return True
            diagonal = (edges & Qt.Edge.LeftEdge and edges & Qt.Edge.TopEdge) or (edges & Qt.Edge.RightEdge and edges & Qt.Edge.BottomEdge)
            other = (edges & Qt.Edge.RightEdge and edges & Qt.Edge.TopEdge) or (edges & Qt.Edge.LeftEdge and edges & Qt.Edge.BottomEdge)
            cursor = (Qt.CursorShape.SizeFDiagCursor if diagonal else Qt.CursorShape.SizeBDiagCursor if other
                      else Qt.CursorShape.SizeHorCursor if edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
                      else Qt.CursorShape.SizeVerCursor if edges else Qt.CursorShape.ArrowCursor)
            watched.setCursor(cursor)
        if event.type() == QEvent.Type.MouseButtonRelease:
            self.origin = None
        return False


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__()
        self.owner, self.origin = window, None
        self.setObjectName("titleBar")

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.owner.windowHandle()
            if not handle or not handle.startSystemMove():
                self.origin = event.globalPosition().toPoint() - self.owner.pos()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self.origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.owner.move(event.globalPosition().toPoint() - self.origin)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self.origin = None

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            toggle_expanded(self.owner)


def shell_for(window):
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    window.setAutoFillBackground(False)
    return WindowShell(window)
