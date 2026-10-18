from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QListWidget, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget, QTextEdit, QApplication, QBoxLayout,
)

from screen_translator.ui.theme import fit_window, stylesheet
from screen_translator.ui.design_tokens import theme_for
from screen_translator.ui.qt_controls import app_mark_icon, decorate_button, palette_for, refresh_icons


class BlockList(QListWidget):
    """Click or drag whole rows to check them; native keyboard checking remains available."""
    def mousePressEvent(self, event):  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        self._drag_start = self.row(item) if item else -1
        if event.button() == Qt.MouseButton.LeftButton and item:
            self._drag_state = (Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
                                else Qt.CheckState.Checked)
            self.setCurrentItem(item)
            item.setCheckState(self._drag_state)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        if event.buttons() & Qt.MouseButton.LeftButton and getattr(self, "_drag_start", -1) >= 0:
            if item:
                first, last = sorted((self._drag_start, self.row(item)))
                for index in range(first, last + 1):
                    self.item(index).setCheckState(self._drag_state)
            if event.position().y() > self.viewport().height() - 24:
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() + 24)
            elif event.position().y() < 24:
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - 24)
            event.accept()
        else:
            super().mouseMoveEvent(event)


class ScreenshotView(QWidget):
    block_clicked = Signal(str)
    blocks_dragged = Signal(object)

    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self.blocks = []
        self.selected = set()
        self._drag_origin = None
        self.setAccessibleName("来源截图；文字块也可在识别文字列表中用键盘选择")
        self.setMinimumSize(1, 1)

    def image_rect(self):
        if self.pixmap.isNull():
            return QRectF()
        bounds = self.rect().adjusted(12, 12, -12, -12)
        scale = min(bounds.width() / self.pixmap.width(), bounds.height() / self.pixmap.height())
        size = self.pixmap.size() * max(.001, scale)
        return QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                      size.width(), size.height())

    def block_rect(self, block):
        image = self.image_rect()
        x, y, right, bottom = block.bounds
        return QRectF(image.x() + x * image.width() / self.pixmap.width(),
                      image.y() + y * image.height() / self.pixmap.height(),
                      (right - x) * image.width() / self.pixmap.width(), (bottom - y) * image.height() / self.pixmap.height())

    def paintEvent(self, event):  # noqa: N802
        tokens = theme_for(getattr(self.window().surface, "theme", "light"))
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(tokens.panel))
        painter.setPen(QColor(tokens.muted))
        if self.pixmap.isNull():
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "截图后在这里对照来源")
            return
        painter.drawPixmap(self.image_rect(), self.pixmap, QRectF(self.pixmap.rect()))
        for block in self.blocks:
            rect = self.block_rect(block)
            if block.id in self.selected:
                fill = QColor(tokens.accent)
                fill.setAlpha(60)
                painter.fillRect(rect, fill)
            painter.setPen(QPen(QColor(tokens.accent), 2 if block.id in self.selected else 1))
            painter.drawRect(rect)
        if self._drag_origin is not None:
            painter.drawRect(QRectF(self._drag_origin, self._drag_end).normalized())

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self.pixmap.isNull():
            self._drag_origin = self._drag_end = event.position()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_origin is not None:
            self._drag_end = event.position()
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._drag_origin is None:
            return
        selection = QRectF(self._drag_origin, event.position()).normalized()
        if selection.width() + selection.height() < 8:
            for block in self.blocks:
                if self.block_rect(block).contains(event.position()):
                    self.block_clicked.emit(block.id)
                    break
        else:
            self.blocks_dragged.emit({block.id for block in self.blocks
                                      if self.block_rect(block).intersects(selection)})
        self._drag_origin = None
        self.update()


class RecognitionWindow(QDialog):
    cancelled = Signal()
    confirmed = Signal()
    recapture = Signal()
    translation_requested = Signal()
    review_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        from screen_translator.ui.chrome import TitleBar, shell_for
        from screen_translator.ui.chat import caption
        from screen_translator.ui.translation_workspace import divider
        self.setWindowTitle("译语 · 截图识字")
        self.setWindowIcon(app_mark_icon())
        self.resize(884, 634)
        shell = shell_for(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(shell)
        self.surface = shell.face
        root = QVBoxLayout(self.surface)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header_widget = TitleBar(self)
        self.header_widget.setFixedHeight(67)
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(24, 13, 22, 13)
        self.selection_title = caption("截图识字", "brand")
        header.addWidget(self.selection_title, 1)
        switch = QToolButton()
        decorate_button(switch, "back", "回到翻译小窗", ghost=True, icon_only=True)
        switch.clicked.connect(self.translation_requested)
        header.addWidget(switch)
        close = QToolButton()
        decorate_button(close, "close", "关闭截图识字", ghost=True, icon_only=True)
        close.clicked.connect(self.close)
        header.addWidget(close)
        root.addWidget(self.header_widget)
        root.addWidget(divider())
        self.status_label = caption("框选文字，识别后校对，再放入输入框。", "muted")
        self.status_label.setContentsMargins(24, 13, 24, 7)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("文字识别状态")
        root.addWidget(self.status_label)
        body = QWidget()
        self.body_layout = QHBoxLayout(body)
        self.body_layout.setContentsMargins(24, 12, 24, 17)
        self.body_layout.setSpacing(21)
        self.source_card = QFrame()
        self.source_card.setObjectName("settingsCard")
        source = QVBoxLayout(self.source_card)
        source.setContentsMargins(12, 12, 12, 12)
        source.addWidget(caption("来源截图", "muted"))
        self.selection_preview = ScreenshotView()
        source.addWidget(self.selection_preview, 1)
        source.addWidget(caption("点击或拖动框选文字块，可调整需要使用的内容。"))
        self.body_layout.addWidget(self.source_card, 1)
        right = QWidget()
        result = QVBoxLayout(right)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(11)
        tools = QHBoxLayout()
        self.text_button = QPushButton("识别结果")
        self.image_button = QPushButton("文字块")
        for button in (self.text_button, self.image_button):
            button.setCheckable(True)
            button.setProperty("variant", "ghost")
            tools.addWidget(button)
        tools.addStretch()
        tools.addWidget(caption("中英识别"))
        self.text_button.clicked.connect(lambda: self.set_view(0))
        self.image_button.clicked.connect(lambda: self.set_view(1))
        result.addLayout(tools)
        self.pages = QStackedWidget()
        self.pages.setMinimumSize(1, 1)
        self.review_edit = QTextEdit()
        self.review_edit.setAcceptRichText(False)
        self.review_edit.setMinimumSize(1, 1)
        self.review_edit.setPlaceholderText("识别后的文字会出现在这里。\n可以校对、编辑后再使用。")
        self.review_edit.setAccessibleName("可编辑的文字识别结果")
        self.review_edit.setStyleSheet("QTextEdit{border:1px solid #dfcfbd;border-radius:9px;padding:12px;font-size:14px;}")
        self.review_edit.textChanged.connect(self._review_edited)
        self.review_edited = False
        self.pages.addWidget(self.review_edit)
        self.block_list = BlockList()
        self.block_list.setAccessibleName("识别文字块；空格选择，方向键移动")
        self.block_list.setWordWrap(True)
        self.block_list.setMinimumSize(1, 1)
        self.block_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.pages.addWidget(self.block_list)
        result.addWidget(self.pages, 1)
        helpers = QHBoxLayout()
        self.count_label = caption("已选 0 / 0")
        helpers.addWidget(self.count_label, 1)
        self.select_all_button = QPushButton("全部文字")
        helpers.addWidget(self.select_all_button)
        copy = QPushButton("复制文字")
        decorate_button(copy, "copy", "复制识别文字", ghost=True)
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.review_edit.toPlainText()))
        helpers.addWidget(copy)
        result.addLayout(helpers)
        self.body_layout.addWidget(right, 1)
        root.addWidget(body, 1)
        root.addWidget(divider())
        footer = QWidget()
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(23, 13, 23, 18)
        self.recapture_button = QPushButton("重新截图")
        decorate_button(self.recapture_button, "capture", "重新框选屏幕", ghost=True)
        self.recapture_button.clicked.connect(self.recapture)
        actions.addWidget(self.recapture_button)
        actions.addStretch(1)
        self.cancel_selection_button = QPushButton("取消")
        self.cancel_selection_button.clicked.connect(self.close)
        actions.addWidget(self.cancel_selection_button)
        self.confirm_button = QPushButton("放入输入框")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.confirmed)
        actions.addWidget(self.confirm_button)
        root.addWidget(footer)
        self.confirm_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.confirm_shortcut.activated.connect(lambda: self.confirmed.emit() if self.confirm_button.isEnabled() else None)
        self.cancel_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.cancel_shortcut.activated.connect(self.close)
        self.set_view(0)
        self._compact_style = None
        self.apply_theme("light")

    def _review_edited(self):
        self.review_edited = True
        self.review_changed.emit()

    def set_review(self, text):
        self.review_edit.blockSignals(True)
        self.review_edit.setPlainText(text)
        self.review_edit.blockSignals(False)
        self.review_edited = False

    def apply_theme(self, theme):
        self._compact_style = self.height() < 520
        self.surface.theme = theme
        self.surface.update()
        self.setPalette(palette_for(theme))
        self.setStyleSheet(stylesheet(theme=theme, compact=self.height() < 520))
        tokens = theme_for(theme)
        prefs = getattr(self.parent(), "appearance", {})
        self.review_edit.setStyleSheet(f"QTextEdit{{background:{tokens.panel};color:{tokens.text};border:1px solid {tokens.control_border};border-radius:9px;padding:12px;font-family:'{prefs.get('source_font', 'Microsoft YaHei UI')}';font-size:{prefs.get('source_size', 14)}px;}}")
        self.selection_preview.update()
        refresh_icons(self, theme)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "body_layout"):
            narrow = self.width() < 680
            self.body_layout.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
            self.source_card.setVisible(not (narrow and self.height() < 550))
            self.source_card.setMaximumHeight(180 if narrow else 16777215)

    def set_view(self, index):
        self.pages.setCurrentIndex(index)
        self.text_button.setChecked(index == 0)
        self.image_button.setChecked(index == 1)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        fit_window(self)

    def closeEvent(self, event):  # noqa: N802
        self.hide()
        self.cancelled.emit()
        event.accept()

    def reject(self):
        self.close()
