"""Native Qt interaction with consistently painted controls and small line icons."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QComboBox, QFrame, QListView, QProxyStyle, QPushButton, QStyle

from screen_translator.ui.design_tokens import COMPONENT, PRIMITIVES, theme_for
from screen_translator.resources import app_icon_path


def line_icon(name: str, color: str) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32):
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size * 2 / 24, size * 2 / 24)
        painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        if name == "capture":
            for points in (((8, 3), (3, 3), (3, 8)), ((16, 3), (21, 3), (21, 8)),
                           ((3, 16), (3, 21), (8, 21)), ((21, 16), (21, 21), (16, 21))):
                path = QPainterPath(QPointF(*points[0]))
                for point in points[1:]:
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)
            painter.drawLine(8, 10, 16, 10)
            painter.drawLine(12, 10, 12, 16)
        elif name == "settings":
            for y, x in ((6, 8), (12, 16), (18, 10)):
                painter.drawLine(3, y, x - 2, y)
                painter.drawLine(x + 2, y, 21, y)
                painter.drawEllipse(QPointF(x, y), 2, 2)
        elif name == "pin":
            painter.drawLine(8, 4, 16, 4)
            painter.drawLine(9, 4, 9, 11)
            painter.drawLine(15, 4, 15, 11)
            painter.drawLine(9, 11, 6, 15)
            painter.drawLine(15, 11, 18, 15)
            painter.drawLine(6, 15, 18, 15)
            painter.drawLine(12, 15, 12, 22)
        elif name == "copy":
            painter.drawRoundedRect(8, 8, 12, 13, 2, 2)
            path = QPainterPath(QPointF(5, 16))
            for point in ((4, 16), (4, 3), (16, 3), (16, 5)):
                path.lineTo(QPointF(*point))
            painter.drawPath(path)
        elif name == "image":
            painter.drawRoundedRect(3, 4, 18, 16, 2, 2)
            painter.drawEllipse(QPointF(8, 9), 1.5, 1.5)
            path = QPainterPath(QPointF(4, 17))
            for point in ((10, 12), (14, 16), (17, 13), (20, 17)):
                path.lineTo(QPointF(*point))
            painter.drawPath(path)
        elif name == "expand":
            for points in (((3, 9), (3, 3), (9, 3)), ((15, 21), (21, 21), (21, 15))):
                path = QPainterPath(QPointF(*points[0]))
                for point in points[1:]:
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)
            painter.drawLine(4, 4, 10, 10)
            painter.drawLine(20, 20, 14, 14)
        elif name == "more":
            painter.setBrush(QColor(color))
            for x in (5, 12, 19):
                painter.drawEllipse(QPointF(x, 12), 1.1, 1.1)
        elif name == "back":
            painter.drawLine(4, 12, 20, 12)
            painter.drawLine(4, 12, 10, 6)
            painter.drawLine(4, 12, 10, 18)
        elif name == "close":
            painter.drawLine(6, 6, 18, 18)
            painter.drawLine(18, 6, 6, 18)
        elif name == "plus":
            painter.drawLine(12, 5, 12, 19)
            painter.drawLine(5, 12, 19, 12)
        elif name == "minus":
            painter.drawLine(6, 12, 18, 12)
        elif name == "send":
            painter.drawLine(12, 19, 12, 5)
            painter.drawLine(12, 5, 6, 11)
            painter.drawLine(12, 5, 18, 11)
        elif name in ("history", "font"):
            if name == "history":
                path = QPainterPath(QPointF(12, 5))
                for point in ((4, 4), (4, 19), (12, 20), (20, 19), (20, 4), (12, 5), (12, 20)):
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)
            else:
                painter.drawLine(4, 19, 10, 4)
                painter.drawLine(10, 4, 16, 19)
                painter.drawLine(6, 14, 14, 14)
        elif name == "plug":
            painter.drawLine(8, 3, 8, 8)
            painter.drawLine(16, 3, 16, 8)
            painter.drawRoundedRect(6, 8, 12, 9, 4, 4)
            painter.drawLine(12, 17, 12, 21)
        elif name == "moon":
            painter.drawArc(4, 4, 16, 16, 40 * 16, 280 * 16)
            painter.drawArc(10, 1, 13, 13, 150 * 16, 185 * 16)
        elif name == "logo":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            for x in (5, 14):
                painter.drawRect(x, 5, 6, 7)
                path = QPainterPath(QPointF(x + 6, 11))
                path.cubicTo(x + 6, 17, x + 4, 19, x, 19)
                path.lineTo(x, 16)
                path.cubicTo(x + 2, 16, x + 3, 15, x + 3, 12)
                path.closeSubpath()
                painter.drawPath(path)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        icon.addPixmap(pixmap)
    return icon


def decorate_button(button, icon_name, name=None, *, ghost=False, icon_only=False):
    button.setProperty("glyph", icon_name)
    button.setIcon(line_icon(icon_name, theme_for().muted))
    button.setIconSize(QSize(COMPONENT["icon"], COMPONENT["icon"]))
    if name:
        button.setAccessibleName(name)
        button.setToolTip(name)
    if ghost:
        button.setProperty("variant", "ghost")
    if icon_only:
        button.setProperty("iconOnly", True)
        button.setText("")
        button.setFixedWidth(COMPONENT["control_height"])
    return button


def app_mark_icon(theme="light"):
    return QIcon(str(app_icon_path()))


def palette_for(theme_name):
    tokens = theme_for(theme_name)
    palette = QPalette()
    for role, value in ((QPalette.ColorRole.Window, tokens.canvas), (QPalette.ColorRole.Base, tokens.panel),
                        (QPalette.ColorRole.AlternateBase, tokens.soft), (QPalette.ColorRole.Text, tokens.text),
                        (QPalette.ColorRole.WindowText, tokens.text), (QPalette.ColorRole.Button, tokens.panel),
                        (QPalette.ColorRole.ButtonText, tokens.text), (QPalette.ColorRole.Highlight, tokens.action),
                        (QPalette.ColorRole.HighlightedText, PRIMITIVES["white"])):
        palette.setColor(role, QColor(value))
    return palette


def refresh_icons(window, theme_name):
    tokens = theme_for(theme_name)
    for button in window.findChildren(QAbstractButton):
        name = button.property("glyph")
        if name:
            color = "#ffffff" if button.objectName() in ("send", "primary", "brandMark", "dockHandle") else tokens.accent if button.isChecked() else tokens.muted
            button.setIcon(line_icon(name, color))


class DropdownStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ComboBox_Popup:
            return 0  # Use a scrolling list, without native menu scroller bands.
        return super().styleHint(hint, option, widget, returnData)


class ThemedComboBox(QComboBox):
    """Keep Qt's popup, keyboard and accessibility; remove Windows bevel artifacts."""
    def __init__(self, parent=None, *, variant="outline"):
        super().__init__(parent)
        self.variant = variant
        self.setMinimumWidth(0)
        popup_style = DropdownStyle("Fusion")
        popup_style.setParent(self)
        self.setStyle(popup_style)
        self.setMaxVisibleItems(10)
        view = QListView(self)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setUniformItemSizes(True)
        self.setView(view)

    def showPopup(self):  # noqa: N802
        inherited = getattr(getattr(self.window(), "surface", None), "theme", "light")
        tokens = theme_for(self.property("theme") or inherited)
        popup = self.view().window()
        popup.setObjectName("comboPopup")
        popup.setPalette(palette_for(self.property("theme") or inherited))
        popup.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        popup.setStyleSheet(f"""
            QFrame#comboPopup {{ background: {tokens.panel}; border: 1px solid {tokens.control_border}; border-radius: 8px; }}
            QListView {{ background: {tokens.panel}; color: {tokens.text}; border: 0; padding: 5px; outline: 0; }}
            QListView::item {{ min-height: 30px; padding: 0 7px; border: 0; border-radius: 4px; }}
            QListView::item:selected, QListView::item:hover {{ background: {tokens.soft}; color: {tokens.accent}; }}
            QScrollBar:vertical {{ background: {tokens.panel}; width: 7px; margin: 4px 1px; }}
            QScrollBar::handle:vertical {{ background: {tokens.control_border}; min-height: 24px; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)
        super().showPopup()

    def minimumSizeHint(self):  # noqa: N802
        return QSize(64, COMPONENT["control_height"])

    def paintEvent(self, event):  # noqa: N802
        inherited = getattr(getattr(self.window(), "surface", None), "theme", "light")
        tokens = theme_for(self.property("theme") or inherited)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        fill = tokens.soft if self.variant == "chip" else tokens.canvas if self.variant == "quiet" else tokens.panel
        if self.underMouse():
            fill = tokens.hover
        border = tokens.accent if self.hasFocus() else tokens.control_border
        if self.variant != "outline" and not self.hasFocus():
            border = fill
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill if self.isEnabled() else tokens.disabled))
        painter.drawRoundedRect(rect, COMPONENT["radius"], COMPONENT["radius"])
        color = tokens.accent if self.variant == "chip" else tokens.text
        painter.setPen(QColor(color if self.isEnabled() else tokens.disabled_text))
        text = painter.fontMetrics().elidedText(self.currentText(), Qt.TextElideMode.ElideRight, max(0, self.width() - 34))
        painter.drawText(self.rect().adjusted(9, 0, -25, 0), Qt.AlignmentFlag.AlignVCenter, text)
        x, y = self.width() - 16, self.height() / 2
        painter.setPen(QPen(QColor(tokens.muted), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x - 3, y - 1), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 3, y - 1))


class FontCombo(ThemedComboBox):
    """System font selection with the same border and caret as other Murmur controls."""
    currentFontChanged = Signal(QFont)

    def __init__(self):
        super().__init__()
        self.addItems(QFontDatabase.families())
        self.currentIndexChanged.connect(lambda: self.currentFontChanged.emit(self.currentFont()))

    def currentFont(self):  # noqa: N802
        return QFont(self.currentText())

    def setCurrentFont(self, font):  # noqa: N802
        index = self.findText(font.family())
        if index < 0:
            self.addItem(font.family())
            index = self.count() - 1
        self.setCurrentIndex(index)


class SendButton(QPushButton):
    """Keep the send affordance circular in every native Windows state."""
    def paintEvent(self, event):  # noqa: N802
        tokens = theme_for(getattr(getattr(self.window(), "surface", None), "theme", "light"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.action_hover if self.isEnabled() and self.underMouse() else tokens.action if self.isEnabled() else tokens.soft))
        painter.drawEllipse(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5))
        line_icon("send", "#ffffff" if self.isEnabled() else tokens.disabled_text).paint(painter, (self.width() - 17) // 2, (self.height() - 17) // 2, 17, 17)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(tokens.accent), 1.5))
            painter.drawEllipse(QRectF(self.rect()).adjusted(2, 2, -2, -2))
