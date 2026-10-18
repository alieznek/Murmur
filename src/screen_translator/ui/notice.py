"""Small confirmation/error windows using the same integrated Murmur chrome."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox as NativeMessageBox, QPushButton, QToolButton, QVBoxLayout
from screen_translator.ui.chrome import TitleBar, shell_for
from screen_translator.ui.theme import fit_window, stylesheet
from screen_translator.ui.qt_controls import decorate_button


class NoticeDialog(QDialog):
    def __init__(self, parent, title, text, buttons, default):
        super().__init__(parent, Qt.WindowType.Dialog)
        self.choice = default
        self.setWindowTitle(title)
        if parent is not None and parent.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        shell = shell_for(self)
        theme = getattr(getattr(parent, "surface", None), "theme", "light")
        shell.face.theme = theme
        self.setStyleSheet(stylesheet(theme=theme))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(shell)
        layout = QVBoxLayout(shell.face)
        layout.setContentsMargins(22, 15, 22, 22)
        layout.setSpacing(16)
        bar = TitleBar(self)
        heading = QHBoxLayout(bar)
        heading.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName("brand")
        label.setTextFormat(Qt.TextFormat.PlainText)
        heading.addWidget(label, 1)
        close = QToolButton()
        decorate_button(close, "close", "关闭提示", ghost=True, icon_only=True)
        close.clicked.connect(self.reject)
        heading.addWidget(close)
        layout.addWidget(bar)
        message = QLabel(text)
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(message, 1)
        actions = QHBoxLayout()
        actions.addStretch()
        for value, name in ((NativeMessageBox.StandardButton.No, "取消"), (NativeMessageBox.StandardButton.Yes, "确认"),
                            (NativeMessageBox.StandardButton.Ok, "知道了")):
            if not buttons & value:
                continue
            button = QPushButton(name)
            if value != NativeMessageBox.StandardButton.No:
                button.setObjectName("primary")
            button.setDefault(value == default)
            button.clicked.connect(lambda _=False, value=value: self.choose(value))
            actions.addWidget(button)
        layout.addLayout(actions)
        self.resize(456, 230)
        fit_window(self)

    def choose(self, value):
        self.choice = value
        self.accept()


class QMessageBox:
    """Preserve the existing task/form call signatures and button enums."""
    StandardButton = NativeMessageBox.StandardButton

    @staticmethod
    def warning(parent, title, message):
        dialog = NoticeDialog(parent, title, message, NativeMessageBox.StandardButton.Ok, NativeMessageBox.StandardButton.Ok)
        dialog.exec()
        return dialog.choice

    @staticmethod
    def question(parent, title, message, buttons=None, default=None):
        buttons = buttons or NativeMessageBox.StandardButton.Yes | NativeMessageBox.StandardButton.No
        default = default or NativeMessageBox.StandardButton.No
        dialog = NoticeDialog(parent, title, message, buttons, default)
        dialog.exec()
        return dialog.choice
