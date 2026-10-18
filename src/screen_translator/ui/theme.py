"""Shared Murmur styling, painted surfaces and window geometry."""
from __future__ import annotations
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget
from screen_translator.ui.design_tokens import LIGHT, theme_for

TEXT, MUTED, ACCENT, SURFACE = LIGHT.text, LIGHT.muted, LIGHT.action, LIGHT.panel

def stylesheet(read_size: int = 27, theme: str = "light", compact: bool = False) -> str:
    t = theme_for(theme)
    return f"""
        QWidget {{ color: {t.text}; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; background: transparent; }}
        QMainWindow, QDialog, QFrame, QLabel {{ background: transparent; border: 0; }}
        QLabel#brand {{ font-size: 19px; font-weight: 400; }}
        QLabel#wordmark {{ font-family: Georgia; font-size: 27px; font-style: italic; }}
        QLabel#eyebrow, QLabel#muted {{ color: {t.muted}; font-size: 11px; }}
        QLabel#small {{ color: {t.muted}; font-size: 10px; }}
        QLabel#pageTitle {{ font-size: 23px; font-weight: 400; }}
        QFrame#divider {{ background: {t.border}; max-height: 1px; }}
        QFrame#composer {{ background: {t.panel}; border: 1px solid {t.control_border}; border-radius: 19px; }}
        QFrame#replyCard {{ background: {t.panel}; border: 1px solid {t.border}; border-top-left-radius: 4px; border-top-right-radius: 20px; border-bottom-left-radius: 20px; border-bottom-right-radius: 20px; }}
        QFrame#userBubble {{ background: {t.soft}; border: 0; border-top-left-radius: 17px; border-top-right-radius: 17px; border-bottom-left-radius: 17px; border-bottom-right-radius: 3px; }}
        QFrame#card, QFrame#settingsCard {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 10px; }}
        QFrame#fontPreview, QFrame#attachment {{ background: {t.soft}; border: 1px solid {t.control_border}; border-radius: 10px; }}
        QWidget#settingsNav {{ background: {t.soft}; border: 0; }}
        QWidget#historyItem {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 12px; }}
        QWidget#historyItem[active="true"] {{ background: {t.soft}; border-color: {t.accent}; }}
        QTextEdit, QTextBrowser {{ background: transparent; border: 0; padding: 0; selection-background-color: {t.selection}; selection-color: {t.text}; }}
        QTextEdit#sourceEditor {{ font-size: 14px; }}
        QListWidget {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 10px; padding: 6px; selection-background-color: {t.selection}; }}
        QListWidget::item {{ padding: 12px 10px; border-bottom: 1px solid {t.border}; }}
        QListWidget::item:selected, QListWidget::item:hover {{ background: {t.soft}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {{ color: {t.text}; background: {t.panel}; border: 1px solid {t.control_border}; border-radius: 7px; padding: 6px 9px; min-height: 20px; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {t.accent}; }}
        QComboBox QAbstractItemView {{ color: {t.text}; background: {t.panel}; border: 1px solid {t.border}; selection-background-color: {t.soft}; padding: 5px; }}
        QComboBox QAbstractItemView::item {{ min-height: 28px; }}
        QPushButton, QToolButton {{ color: {t.muted}; background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 5px 9px; min-height: 18px; }}
        QPushButton:hover, QToolButton:hover {{ background: {t.hover}; color: {t.accent}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {t.selection}; }}
        QPushButton:checked, QToolButton:checked {{ background: {t.soft}; color: {t.accent}; }}
        QPushButton:focus, QToolButton:focus {{ border-color: {t.accent}; }}
        QPushButton[variant="outline"], QToolButton[variant="outline"] {{ border-color: {t.control_border}; background: {t.panel}; border-radius: 15px; }}
        QPushButton#primary {{ color: white; background: {t.action}; border-color: {t.action}; border-radius: 8px; padding: 7px 14px; }}
        QPushButton#primary:hover, QPushButton#send:hover {{ background: {t.action_hover}; }}
        QPushButton#send {{ color: white; background: {t.action}; border: 0; border-radius: 17px; padding: 0; min-height: 0; }}
        QPushButton#newChat {{ background: {t.soft}; border-radius: 15px; padding: 0; min-height: 0; }}
        QToolButton#brandMark {{ color: white; background: {t.accent}; border: 0; border-radius: 17px; padding: 0; min-height: 0; }}
        QPushButton#navItem {{ text-align: left; padding: 11px 12px; border-radius: 7px; }}
        QPushButton#navItem:checked {{ background: {t.hover}; color: {t.text}; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {t.disabled_text}; background: transparent; }}
        QPushButton#send:disabled, QPushButton#primary:disabled {{ background: {t.disabled}; color: {t.disabled_text}; }}
        QToolButton::menu-indicator {{ image: none; width: 0; height: 0; }}
        QCheckBox {{ spacing: 8px; }}
        QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid {t.control_border}; background: {t.panel}; }}
        QCheckBox::indicator:checked {{ background: {t.action}; border-color: {t.action}; }}
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
        QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {t.control_border}; min-height: 26px; border-radius: 3px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QSlider::groove:horizontal {{ height: 3px; background: {t.border}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: {t.accent}; border: 0; width: 13px; height: 13px; margin: -5px 0; border-radius: 6px; }}
        QMenu {{ color: {t.text}; background: {t.panel}; border: 1px solid {t.border}; padding: 7px; }}
        QMenu::item {{ padding: 8px 24px 8px 12px; border-radius: 5px; }}
        QMenu::item:selected {{ background: {t.soft}; }}
        QMenu::separator {{ height: 1px; background: {t.border}; margin: 5px; }}
        QPushButton#dockHandle {{ background: {t.action}; border: 0; border-radius: 24px; padding: 0; }}
    """

class WindowSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = "light"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        tokens = theme_for(self.theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(tokens.border), .8))
        painter.setBrush(QColor(tokens.canvas))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 24, 24)

def work_area(window: QWidget) -> QRect:
    screen = window.screen() or QGuiApplication.primaryScreen()
    return screen.availableGeometry()

def fit_window(window: QWidget, area: QRect | None = None) -> None:
    area = area if area is not None else work_area(window)
    frame = window.frameGeometry()
    extra_width = max(0, frame.width() - window.width())
    extra_height = max(0, frame.height() - window.height())
    width, height = max(1, area.width() - extra_width), max(1, area.height() - extra_height)
    window.setMinimumSize(min(360, width), min(300, height))
    window.resize(min(window.width(), width), min(window.height(), height))
    frame = window.frameGeometry()
    window.move(max(area.left(), min(frame.left(), area.right() - frame.width() + 1)),
                max(area.top(), min(frame.top(), area.bottom() - frame.height() + 1)))

def toggle_expanded(window: QWidget) -> None:
    if window.isMaximized():
        window.showNormal()
        fit_window(window)
    else:
        window.showMaximized()
