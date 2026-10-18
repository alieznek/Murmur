"""Native conversation and history surfaces for the Murmur desktop interface."""
from __future__ import annotations

import math
from PySide6.QtCore import QByteArray, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPixmap, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QTextEdit, QVBoxLayout, QWidget,
)
from screen_translator.ui.design_tokens import theme_for
from screen_translator.ui.qt_controls import decorate_button, line_icon


class SourceEditor(QTextEdit):
    submitted = Signal()
    image_pasted = Signal(QImage)

    def __init__(self):
        super().__init__()
        self.composing = False
        self.setAcceptRichText(False)
        self.setObjectName("sourceEditor")
        self.setAccessibleName("翻译输入框；Enter 翻译，Shift+Enter 换行，Ctrl+V 粘贴截图")
        self.setMinimumSize(1, 1)

    def inputMethodEvent(self, event):  # noqa: N802
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.composing and not event.modifiers():
            self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def insertFromMimeData(self, source):  # noqa: N802
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QPixmap):
                image = image.toImage()
            if isinstance(image, QImage) and not image.isNull():
                self.image_pasted.emit(image)
                return
        super().insertFromMimeData(source)


class AutoText(QTextEdit):
    """Selectable message text whose height follows its wrapped document."""
    def __init__(self, text: str, family: str, size: int, line_height: float):
        super().__init__()
        self._sizing = False
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(1)
        self.document().setDocumentMargin(0)
        self.setStyleSheet(f"font-family: '{family}', 'Microsoft YaHei UI'; font-size: {size}px; background: transparent; border: 0; padding: 0;")
        self.setPlainText(text)
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        formatting = QTextBlockFormat()
        formatting.setLineHeight(line_height * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.mergeBlockFormat(formatting)
        self.document().documentLayout().documentSizeChanged.connect(self._update_height)
        QTimer.singleShot(0, self._update_height)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(1, 1)

    def _update_height(self, *_args):
        if self._sizing:
            return
        self._sizing = True
        self.document().setTextWidth(max(1, self.viewport().width()))
        self.setFixedHeight(max(self.fontMetrics().height() + 5, math.ceil(self.document().size().height()) + 7))
        self._sizing = False

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._update_height()

    def wheelEvent(self, event):  # noqa: N802
        # Messages expand to their full document height. Scroll the conversation,
        # even when the pointer is over selectable source or translation text.
        event.ignore()


def caption(text, name="small"):
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class ConversationView(QScrollArea):
    capture_requested = Signal()
    upload_requested = Signal()
    copy_requested = Signal(str)
    retry_requested = Signal(str)
    source_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAccessibleName("翻译聊天记录")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setMinimumSize(1, 1)
        self.setWidget(self.content)
        self.layout = QVBoxLayout(self.content)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.layout.setContentsMargins(0, 7, 0, 8)
        self.layout.setSpacing(25)
        self.bubbles = []
        self._follow_bottom = True
        self._render_generation = 0
        self._restoring_position = False
        self._restore_value = None
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.verticalScrollBar().valueChanged.connect(self._position_changed)

    def _position_changed(self, value):
        if not self._restoring_position:
            self._restore_value = None
            self._follow_bottom = value >= self.verticalScrollBar().maximum() - 2

    def _set_position(self, value):
        restoring = self._restoring_position
        self._restoring_position = True
        self.verticalScrollBar().setValue(value)
        self._restoring_position = restoring

    def _range_changed(self, _minimum, maximum):
        if self._restore_value is not None:
            self._set_position(self._restore_value)
        elif self._follow_bottom:
            self._set_position(maximum)

    def render(self, messages, appearance, theme="light", *, scroll=True):
        previous = self.verticalScrollBar().value()
        self._render_generation += 1
        generation = self._render_generation
        self._restoring_position = True
        self._restore_value = None if scroll else previous
        self._follow_bottom = scroll
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.bubbles = []
        tokens = theme_for(theme)
        if not messages:
            self._welcome(tokens)
        else:
            day = caption("—   翻译记录   —")
            day.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(day)
            for message in messages:
                self._message(message, appearance, tokens)
            self.layout.addStretch(1)
        def restore_position():
            if generation != self._render_generation:
                return
            self._set_position(self.verticalScrollBar().maximum() if scroll else previous)
            self._follow_bottom = scroll
            self._restoring_position = False
        # Message widths settle first, then their document heights update the
        # outer layout. Restore after both passes rather than a transient range.
        QTimer.singleShot(0, lambda: QTimer.singleShot(0, restore_position))

    def _welcome(self, tokens):
        self.layout.addStretch(1)
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 24, 0, 30)
        mark = QLabel()
        mark.setFixedSize(60, 60)
        mark.setPixmap(line_icon("logo", tokens.accent).pixmap(38, 38))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(f"background:{tokens.soft};border:1px solid {tokens.control_border};border-radius:30px;")
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        tagline = caption("A little room for your words.")
        tagline.setStyleSheet(f"color:{tokens.muted};font-family:Georgia;font-style:italic;font-size:13px;")
        layout.addWidget(tagline, 0, Qt.AlignmentFlag.AlignHCenter)
        title = caption("输入文字，或截取屏幕。", "pageTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        detail = caption("选择目标语言与翻译平台，开始翻译。\n每段记录，都留在这台设备。", "muted")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(detail)
        actions = QHBoxLayout()
        actions.addStretch()
        for text, glyph, callback in (("截图识字", "capture", self.capture_requested), ("添加图片", "image", self.upload_requested)):
            button = QPushButton(text)
            decorate_button(button, glyph, text)
            button.setProperty("variant", "outline")
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.layout.addWidget(welcome)
        self.layout.addStretch(1)

    def _message(self, message, prefs, tokens):
        user = QWidget()
        user_layout = QHBoxLayout(user)
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_layout.addStretch(1)
        bubble = QFrame()
        bubble.setObjectName("userBubble")
        font = QFont(prefs["source_font"])
        font.setPixelSize(prefs["source_size"])
        natural_width = max(QFontMetrics(font).horizontalAdvance(line) for line in message["source"].split("\n")) + 42
        if message.get("image"):
            natural_width = max(245, natural_width)
        bubble.setProperty("naturalWidth", max(105, natural_width))
        bubble.setMaximumWidth(min(max(130, int(self.viewport().width() * .85)), max(105, natural_width)))
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(18, 12, 18, 12)
        bubble_layout.setSpacing(7)
        if message.get("image"):
            image = QPixmap()
            image.loadFromData(QByteArray.fromBase64(message["image"].encode()))
            if not image.isNull():
                thumbnail = QPushButton()
                thumbnail.setIcon(image)
                thumbnail.setIconSize(QSize(200, 105))
                thumbnail.setFixedSize(205, 110)
                thumbnail.setAccessibleName("查看来源截图")
                thumbnail.clicked.connect(lambda _=False, data=message["image"]: self.source_requested.emit(data))
                bubble_layout.addWidget(thumbnail)
                bubble_layout.addWidget(caption("来自截图识字"))
        bubble_layout.addWidget(AutoText(message["source"], prefs["source_font"], prefs["source_size"], prefs["line_height"]))
        user_layout.addWidget(bubble, 4)
        self.bubbles.append(bubble)
        self.layout.addWidget(user)
        reply = QWidget()
        reply_layout = QVBoxLayout(reply)
        reply_layout.setContentsMargins(0, 0, 0, 0)
        reply_layout.setSpacing(10)
        identity = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(line_icon("logo", tokens.accent).pixmap(17, 17))
        mark.setFixedSize(24, 24)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(f"border:1px solid {tokens.control_border};border-radius:12px;")
        identity.addWidget(mark)
        identity.addWidget(caption("译语", "muted"))
        identity.addStretch()
        provider = caption(message["provider"])
        provider.setMaximumWidth(260)
        identity.addWidget(provider)
        reply_layout.addLayout(identity)
        card = QFrame()
        card.setObjectName("replyCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(23, 16, 23, 15)
        card_layout.setSpacing(14)
        metadata = QHBoxLayout()
        metadata.addWidget(caption("•  " + message["target"] + " / TRANSLATION"))
        metadata.addStretch()
        quote = QLabel("“")
        quote.setStyleSheet(f"font-family:Georgia;font-size:37px;color:{tokens.control_border};")
        quote.setFixedHeight(28)
        metadata.addWidget(quote)
        card_layout.addLayout(metadata)
        complete = message["status"] == "complete"
        text = message["translation"] if complete else ("正在翻译…" if message["status"] == "pending" else message.get("error") or "这次翻译未完成，可以重新发送。")
        output = AutoText(text, prefs["result_font"] if complete else prefs["ui_font"], prefs["result_size"] if complete else 14, prefs["line_height"])
        output.setAccessibleName("译文" if complete else "翻译状态")
        card_layout.addWidget(output)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        card_layout.addWidget(divider)
        actions = QHBoxLayout()
        copy = QPushButton("复制译文" if complete else "重新发送")
        decorate_button(copy, "copy" if complete else "send", copy.text(), ghost=True)
        copy.setEnabled(message["status"] != "pending")
        copy.clicked.connect(lambda _=False, text=message["translation"] if complete else message["source"], done=complete:
                             self.copy_requested.emit(text) if done else self.retry_requested.emit(text))
        actions.addWidget(copy)
        actions.addStretch()
        actions.addWidget(caption("已保存到本地" if complete else "原文已保留"))
        card_layout.addLayout(actions)
        reply_layout.addWidget(card)
        self.layout.addWidget(reply)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        for bubble in self.bubbles:
            bubble.setMaximumWidth(min(max(130, int(self.viewport().width() * .85)), bubble.property("naturalWidth")))


class HistoryPane(QWidget):
    opened = Signal(str)
    deleted = Signal(str)

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 25, 28, 23)
        root.setSpacing(17)
        root.addWidget(caption("聊过的，都在。", "pageTitle"))
        root.addWidget(caption("保存过的翻译，随时可以继续。", "muted"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索翻译记录")
        self.search.setAccessibleName("搜索本地翻译历史")
        root.addWidget(self.search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.listing = QWidget()
        self.rows = QVBoxLayout(self.listing)
        self.rows.setContentsMargins(0, 3, 0, 3)
        self.rows.setSpacing(9)
        scroll.setWidget(self.listing)
        root.addWidget(scroll, 1)
        note = caption("只存这台设备，关掉也会记得。\n原文、译文和截图缩略图均保存在本地。", "muted")
        note.setWordWrap(True)
        root.addWidget(note)

    def render(self, conversations, active):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        query = self.search.text().strip().casefold()
        for conversation in sorted(conversations, key=lambda c: c["updated"], reverse=True):
            if query and query not in (conversation["title"] + " ".join(m["source"] + m["translation"] for m in conversation["messages"])).casefold():
                continue
            row = QWidget()
            row.setObjectName("historyItem")
            row.setProperty("active", conversation["id"] == active)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 8, 6, 8)
            button = QPushButton(conversation["title"])
            button.setStyleSheet("text-align:left;")
            decorate_button(button, "history", conversation["title"], ghost=True)
            button.clicked.connect(lambda _=False, id=conversation["id"]: self.opened.emit(id))
            layout.addWidget(button, 1)
            delete = QPushButton()
            decorate_button(delete, "close", "删除这段翻译记录", ghost=True, icon_only=True)
            delete.clicked.connect(lambda _=False, id=conversation["id"]: self.deleted.emit(id))
            layout.addWidget(delete)
            self.rows.addWidget(row)
        self.rows.addStretch(1)
