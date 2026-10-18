from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QLineEdit

from screen_translator.services.config import ConfigurationError, SettingsStore
from screen_translator.services.provider_translators import create_translator
from screen_translator.services.providers import get_provider
from screen_translator.services.translator import TranslationError
from screen_translator.ui.tasks import FunctionWorker
from screen_translator.ui.theme import fit_window, stylesheet
from screen_translator.ui.qt_controls import ThemedComboBox, app_mark_icon, palette_for, refresh_icons
from screen_translator.ui.notice import QMessageBox


class SettingsDialog(QDialog):
    configuration_changed = Signal()
    appearance_changed = Signal()
    VERIFY_TEXT = "Hello."

    def __init__(self, store: SettingsStore, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.store = store
        self.setWindowTitle("译语 · 设置")
        self.setWindowIcon(app_mark_icon())
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.pool = QThreadPool.globalInstance()
        self._workers: set[FunctionWorker] = set()
        self._generation = 0
        self._provider_id = ""
        self._drafts: dict[str, dict[str, str]] = {}
        self.fields: dict[str, QLineEdit | QComboBox] = {}
        from screen_translator.ui.settings_workspace import build_settings_workspace
        build_settings_workspace(self)
        try:
            active = self.store.active_provider
            theme = self.store.appearance["theme"]
        except ConfigurationError:
            active, theme = "baidu", "light"
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(active)))
        if not self.fields:
            self._load_provider()
        self._refresh_current()
        self.apply_theme(theme)
        self.rebuild_font_preview()
        self.resize(944, 790)
        fit_window(self)

    def select_page(self, key):
        self.pages.setCurrentIndex(self.page_indices[key])
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        self.platform_actions.setVisible(key == "platforms")

    def open_provider_link(self, attribute):
        QDesktopServices.openUrl(QUrl(getattr(get_provider(self.provider_combo.currentData()), attribute)))

    def open_config_directory(self):
        directory = self.store.path.absolute().parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.feedback.setText("无法创建配置目录，请检查目录权限后重试。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            self.feedback.setText(f"无法打开配置目录，请手动打开：{directory}")
            return
        self.feedback.setText("已打开配置目录。手动修改设置前请先退出程序，修改后重新启动。")

    def save_appearance(self, key, value):
        try:
            self.store.set_appearance(**{key: value})
        except ConfigurationError as error:
            self.feedback.setText(str(error))
            self.sync_appearance_controls()
            return
        self.feedback.setText("已保存到本地")
        self.sync_appearance_controls()
        self.rebuild_font_preview()
        if key == "theme":
            self.apply_theme(value)
        self.appearance_changed.emit()

    def sync_appearance_controls(self):
        from PySide6.QtGui import QFont
        try:
            prefs = self.store.appearance
        except ConfigurationError:
            return
        for key, control in self.font_controls.items():
            control.blockSignals(True)
            control.setCurrentFont(QFont(prefs[key]))
            control.blockSignals(False)
        for key, control in self.size_controls.items():
            control.blockSignals(True)
            control.setValue(round(prefs[key] * 10) if key == "line_height" else prefs[key])
            control.blockSignals(False)
            self.size_values[key].setText(str(prefs[key]) + ("" if key == "line_height" else " px"))
        self.theme_setting.blockSignals(True)
        self.theme_setting.setCurrentIndex(self.theme_setting.findData(prefs["theme"]))
        self.theme_setting.blockSignals(False)

    def rebuild_font_preview(self):
        from screen_translator.ui.chat import AutoText
        from screen_translator.services.config import DEFAULT_APPEARANCE
        try:
            prefs = self.store.appearance
        except ConfigurationError:
            prefs = DEFAULT_APPEARANCE
        while self.preview_layout.count() > 1:
            item = self.preview_layout.takeAt(1)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.preview_layout.addWidget(AutoText("我想慢一点，走远一点。", prefs["source_font"], prefs["source_size"], prefs["line_height"]))
        self.preview_layout.addWidget(AutoText("I want to slow down, so I can go further.", prefs["result_font"], prefs["result_size"], prefs["line_height"]))

    def reset_fonts(self):
        from screen_translator.services.config import DEFAULT_APPEARANCE
        try:
            self.store.set_appearance(**{key: value for key, value in DEFAULT_APPEARANCE.items() if key != "theme"})
        except ConfigurationError as error:
            self.feedback.setText(str(error))
            return
        self.sync_appearance_controls()
        self.rebuild_font_preview()
        self.appearance_changed.emit()
        self.feedback.setText("字体已恢复默认")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "navigation"):
            compact = self.width() < 500
            self.navigation.setFixedWidth(54 if compact else 146 if self.width() < 700 else 190)
            self.navigation.layout().setContentsMargins(6 if compact else 13, 22, 6 if compact else 13, 19)
            for label in self.navigation.findChildren(QLabel):
                label.setVisible(not compact)
            for button in self.nav_buttons.values():
                button.setText("" if compact else button.accessibleName())

    def apply_theme(self, theme):
        self.surface.theme = theme
        self.surface.update()
        self.setStyleSheet(stylesheet(theme=theme))
        self.setPalette(palette_for(theme))
        for combo in self.findChildren(ThemedComboBox):
            combo.setProperty("theme", theme)
            combo.update()
        refresh_icons(self, theme)
        self.sync_appearance_controls()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        fit_window(self)

    def _save_dock_side(self):
        try:
            self.store.set_dock_side(self.dock_combo.currentData())
        except ConfigurationError as error:
            self.feedback.setText(str(error))
            self.dock_combo.blockSignals(True)
            try:
                self.dock_combo.setCurrentIndex(self.dock_combo.findData(self.store.dock_side))
            except ConfigurationError:
                self.dock_combo.setCurrentIndex(0)
            self.dock_combo.blockSignals(False)
            return
        self.appearance_changed.emit()

    def _refresh_current(self):
        try:
            self.current_label.setText("正在使用：本地 · Argos" if self.store.translation_mode == "offline" else "正在使用：" + get_provider(self.store.active_provider).name)
        except (ConfigurationError, TranslationError) as error:
            self.current_label.setText(str(error))

    def _values(self) -> dict[str, str]:
        return {key: control.currentData() if isinstance(control, QComboBox) else control.text()
                for key, control in self.fields.items()}

    def _load_provider(self, *_args):
        if self._provider_id:
            self._drafts[self._provider_id] = self._values()
        self._generation += 1
        self._provider_id = self.provider_combo.currentData()
        provider = get_provider(self._provider_id)
        self.feedback.clear()
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        values = self._drafts.get(provider.id)
        if values is None:
            try:
                values = self.store.values(provider.id)
            except ConfigurationError as error:
                values = {}
                self.feedback.setText(str(error))
        self.provider_note.setText(f"{provider.status}\n{provider.quota_note}")
        for field in provider.fields:
            if field.choices:
                control = ThemedComboBox()
                for choice in field.choices:
                    labels = {"standard": "标准版", "advanced": "高级版 / 尊享版"}
                    control.addItem(labels.get(choice, choice), choice)
                index = control.findData(values.get(field.key, field.default))
                control.setCurrentIndex(max(index, 0))
            else:
                control = QLineEdit(values.get(field.key, field.default))
                if field.secret:
                    control.setEchoMode(QLineEdit.EchoMode.Password)
            control.setAccessibleName(field.label)
            control.setMinimumHeight(30)
            self.fields[field.key] = control
            label = QLabel(field.label + (" *" if field.required else "（可选）"))
            label.setBuddy(control)
            self.form.addRow(label, control)
            if field.hint:
                hint = QLabel(field.hint)
                hint.setWordWrap(True)
                hint.setObjectName("small")
                self.form.addRow(hint)
        self.reveal.setChecked(False)

    def _toggle_secrets(self, reveal: bool):
        for field in get_provider(self._provider_id).fields:
            control = self.fields[field.key]
            if field.secret and isinstance(control, QLineEdit):
                control.setEchoMode(QLineEdit.EchoMode.Normal if reveal else QLineEdit.EchoMode.Password)

    def _changed(self, message: str):
        self._generation += 1
        self.configuration_changed.emit()
        self._refresh_current()
        self.feedback.setText(message)

    def save(self):
        try:
            self.store.save(self._provider_id, self._values())
        except (ConfigurationError, TranslationError) as error:
            self.feedback.setText(str(error))
            return
        self._changed(self.store.cleanup_warning or "配置已保存到系统凭据存储。可验证连接后设为当前平台。")

    def activate(self):
        try:
            # Save the visible draft atomically with activation; never activate hidden stale values.
            self.store.save(self._provider_id, self._values(), activate=True)
        except (ConfigurationError, TranslationError) as error:
            self.feedback.setText(str(error))
            return
        self._changed(self.store.cleanup_warning or "配置已保存，并设为当前平台。")

    def clear(self):
        answer = QMessageBox.question(self, "清除凭据", "清除该平台的系统凭据？其他平台配置会保留。",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.clear(self._provider_id)
        except ConfigurationError as error:
            self.feedback.setText(str(error))
            return
        self._drafts.pop(self._provider_id, None)
        self._provider_id = ""
        self._load_provider()
        self._changed("该平台凭据已清除，其他平台配置保留。")

    def _set_busy(self, busy: bool):
        for control in (self.provider_combo, self.form_widget, self.save_button, self.activate_button,
                        self.clear_button, self.reveal, self.verify_button):
            control.setEnabled(not busy)
        self.verify_button.setText("验证中…" if busy else "验证连接")

    def verify(self):
        if self._workers:
            return
        try:
            translator = create_translator(self._provider_id, self._values())
        except TranslationError as error:
            self.feedback.setText(str(error))
            return
        self._generation += 1
        generation = self._generation
        self._set_busy(True)
        self.feedback.setText("正在验证连接…")
        worker = FunctionWorker(lambda: translator.translate(self.VERIFY_TEXT, "中文"), generation,
                                failure_message="验证组件发生异常，请检查配置后主动重试。")
        self._workers.add(worker)
        worker.signals.result.connect(self._verified, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(self._verification_failed, Qt.ConnectionType.QueuedConnection)
        worker.signals.finished.connect(self._worker_finished, Qt.ConnectionType.QueuedConnection)
        self.pool.start(worker)

    @Slot(object, object)
    def _verified(self, generation, _translation):
        if generation == self._generation:
            self.feedback.setText("连接验证成功。验证使用当前表单；如有修改，请保存或设为当前平台。")

    @Slot(object, str)
    def _verification_failed(self, generation, message):
        if generation == self._generation:
            self.feedback.setText(message)

    @Slot(object)
    def _worker_finished(self, worker):
        self._workers.discard(worker)
        if not self._workers:
            self._set_busy(False)

    def reject(self):
        self.cancel_pending_verification()
        super().reject()

    def closeEvent(self, event):  # noqa: N802
        self.cancel_pending_verification()
        super().closeEvent(event)

    def cancel_pending_verification(self):
        self._generation += 1
