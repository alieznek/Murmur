from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QThreadPool, QTimer, Qt, Slot
from PySide6.QtGui import QGuiApplication, QImage, QPixmap, QKeySequence, QShortcut, QCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QLabel, QListWidgetItem, QMainWindow, QMenu, QStyle, QSystemTrayIcon, QVBoxLayout,
)

from screen_translator.core.text_blocks import TextBlock
from screen_translator.core.ocr_text import selected_ocr_text
from screen_translator.services.argos_translator import ArgosTranslator
from screen_translator.services.ocr import RapidOcrService
from screen_translator.services.config import DEFAULT_APPEARANCE, SettingsStore, ConfigurationError
from screen_translator.services.history import HistoryError, HistoryStore
from screen_translator.services.provider_translators import create_translator
from screen_translator.services.providers import PROVIDERS, get_provider
from screen_translator.services.languages import CHOICE_VALUES, language_choices, language_code
from screen_translator.services.translator import TranslationError
from screen_translator.ui.capture_overlay import CaptureOverlay
from screen_translator.ui.settings_dialog import SettingsDialog
from screen_translator.ui.tasks import FunctionWorker
from screen_translator.ui.theme import fit_window, stylesheet, work_area
from screen_translator.ui.translation_workspace import build_translation_workspace
from screen_translator.ui.qt_controls import ThemedComboBox, app_mark_icon, palette_for, refresh_icons
from screen_translator.ui.notice import QMessageBox


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsStore | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Murmur（译语）")
        self.setWindowIcon(app_mark_icon())
        self.resize(674, 844)
        self.read_size = 27
        self.reading_mode = 2
        self.compact_reading_mode = 0
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.pool = QThreadPool.globalInstance()
        self._workers: set[FunctionWorker] = set()
        self.ocr = RapidOcrService()
        self.settings = settings or SettingsStore()
        self.history_store = HistoryStore(self.settings.path.with_name("history.json"))
        self.history_writable = True
        self.conversations = []
        self.active_conversation = ""
        self._chat_request = None
        self._compose_image = QPixmap()
        self.appearance = dict(DEFAULT_APPEARANCE)
        self.settings_dialog: SettingsDialog | None = None
        self.translator = None
        self.local_translator = ArgosTranslator()
        self.translation_mode = "offline"
        self.source_version = 0
        self.translate_task = 0
        self.translation_running = False
        self.capture_generation = 0
        self.blocks: list[TextBlock] = []
        self.candidate_pixmap = QPixmap()
        self.retained_pixmap = QPixmap()
        self.retained_blocks: list[TextBlock] = []
        self.retained_selected_ids: set[str] = set()
        self.overlay: CaptureOverlay | None = None
        self._capture_active = False
        self._capture_screen = None
        self._ocr_worker: FunctionWorker | None = None
        self._shutting_down = False
        self.capture_timer = QTimer(self)
        self.capture_timer.setSingleShot(True)
        self.capture_timer.setInterval(260)
        self.capture_timer.timeout.connect(self._show_capture_overlay)

        self._build_ui()
        self._load_history()
        self._setup_tray()
        self.refresh_appearance()
        self.reload_configuration()
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(120_000)
        self.idle_timer.timeout.connect(self.local_translator.close)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.translate_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.translate_shortcut.activated.connect(self.translate)
        self.history_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.history_shortcut.activated.connect(lambda: self.toggle_history(True))
        self.new_chat_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.new_chat_shortcut.activated.connect(self.new_conversation)
        self.cancel_capture_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.cancel_capture_shortcut.activated.connect(self.cancel_selection)
        self.capture_button.setToolTip("Ctrl+Alt+S · 在鼠标所在显示器取词")
        self._update_reading_layout()
        fit_window(self)
        self.dock_geometry_timer = QTimer(self)
        self.dock_geometry_timer.setInterval(1000)
        self.dock_geometry_timer.timeout.connect(self._update_dock_geometry)

    def _load_history(self) -> None:
        try:
            self.conversations = self.history_store.load()
        except HistoryError as error:
            self.history_writable = False
            self.history_save_label.setText("历史保存暂不可用")
            self.history_save_label.setToolTip(str(error))
        if self.conversations:
            self.active_conversation = max(self.conversations, key=lambda c: c["updated"])["id"]
        else:
            self._create_conversation()
        self.render_conversation(scroll=False)

    def _create_conversation(self) -> dict:
        conversation = {"id": uuid.uuid4().hex, "title": "新的翻译", "updated": datetime.now().astimezone().isoformat(), "messages": []}
        self.conversations.append(conversation)
        self.active_conversation = conversation["id"]
        return conversation

    def current_conversation(self) -> dict:
        return next((c for c in self.conversations if c["id"] == self.active_conversation), None) or self._create_conversation()

    def save_history(self) -> None:
        if not self.history_writable:
            return
        try:
            self.history_store.save([c for c in self.conversations if c["messages"]])
        except HistoryError as error:
            self.history_save_label.setText("保存失败 · 可导出记录")
            self.history_save_label.setToolTip(str(error))
        else:
            self.history_save_label.setText("已保存到本地")
            self.history_save_label.setToolTip("原文、译文和截图缩略图保存在本机")

    def render_conversation(self, *, scroll=True) -> None:
        conversation = self.current_conversation()
        self.session_title.setText(conversation["title"])
        self.chat_view.render(conversation["messages"], self.appearance, self.appearance["theme"], scroll=scroll)
        self.cancel_translation_button.setVisible(self.translation_running)
        self.refresh_history()

    def refresh_history(self, *_args) -> None:
        self.history_pane.render(self.conversations, self.active_conversation)

    def toggle_history(self, visible=None) -> None:
        visible = not self.history_button.isChecked() if visible is None else visible
        self.history_button.setChecked(bool(visible))
        self.body_pages.setCurrentIndex(1 if visible else 0)
        if visible:
            self.refresh_history()
            self.history_pane.search.setFocus()
        else:
            self.source_edit.setFocus()

    def new_conversation(self) -> None:
        if self.translation_running:
            self.cancel_translation()
        if self.current_conversation()["messages"]:
            empty = next((c for c in self.conversations if not c["messages"]), None)
            if empty:
                self.active_conversation = empty["id"]
            else:
                self._create_conversation()
        self.source_edit.clear()
        self.translation_edit.clear()
        self.remove_attachment()
        self.render_conversation()
        self.toggle_history(False)

    def open_conversation(self, conversation_id: str) -> None:
        if not any(c["id"] == conversation_id for c in self.conversations):
            return
        if self.translation_running:
            self.cancel_translation()
        self.active_conversation = conversation_id
        self.source_edit.clear()
        self.remove_attachment()
        messages = self.current_conversation()["messages"]
        self.translation_edit.setPlainText(next((m["translation"] for m in reversed(messages) if m["status"] == "complete"), ""))
        self.copy_button.setEnabled(bool(self.translation_edit.toPlainText()))
        self.render_conversation()
        self.toggle_history(False)

    def delete_conversation(self, conversation_id: str) -> None:
        if conversation_id == self.active_conversation and self.translation_running:
            self.cancel_translation()
        self.conversations = [c for c in self.conversations if c["id"] != conversation_id]
        if not any(c["id"] == self.active_conversation for c in self.conversations):
            self.active_conversation = self.conversations[-1]["id"] if self.conversations else self._create_conversation()["id"]
            self.source_edit.clear()
            self.translation_edit.clear()
            self.copy_button.setEnabled(False)
            self.remove_attachment()
        self.save_history()
        self.render_conversation()

    def _record_request(self, source, target, task_id) -> None:
        conversation = self.current_conversation()
        if not conversation["messages"]:
            conversation["title"] = source[:16].replace("\n", " ") + ("…" if len(source) > 16 else "")
        message = {"id": uuid.uuid4().hex, "source": source, "translation": "", "target": "英语" if target == "English" else target,
                   "provider": self.provider_combo.currentText(), "status": "pending"}
        if not self._compose_image.isNull():
            thumbnail = self._compose_image.scaled(360, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            thumbnail.save(buffer, "PNG")
            message["image"] = bytes(buffer.data().toBase64()).decode("ascii")
        conversation["messages"].append(message)
        conversation["updated"] = datetime.now().astimezone().isoformat()
        self._chat_request = {"task": task_id, "conversation": conversation["id"], "message": message}
        self.save_history()
        self.render_conversation()

    def _finish_request(self, translation="", *, error="", interrupted=False) -> None:
        request = self._chat_request
        if request is None:
            return
        message = request["message"]
        message.update(translation=translation, status="interrupted" if interrupted else "failed" if error else "complete")
        if error:
            message["error"] = error
        self._chat_request = None
        self.save_history()
        self.render_conversation()

    def copy_message(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.status_label.setText("✓  译文已复制")

    def retry_message(self, text: str) -> None:
        self.source_edit.setPlainText(text)
        self.source_edit.setFocus()
        self.status_label.setText("原文已放回输入框，确认后重新翻译")

    def _refresh_provider_choices(self) -> None:
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        self.provider_combo.addItem("本地 · Argos", "offline")
        try:
            profiles = self.settings._read()["providers"]
            active = self.settings.active_provider
        except ConfigurationError:
            profiles, active = {}, ""
        for provider in PROVIDERS.values():
            model = profiles.get(provider.id, {}).get("options", {}).get("model")
            if not model:
                model = next((field.default for field in provider.fields if field.key == "model"), "")
            self.provider_combo.addItem(provider.name + (" · " + model if model else ""), provider.id)
        wanted = "offline" if self.translation_mode == "offline" else active
        index = self.provider_combo.findData(wanted)
        if index < 0:
            self.provider_combo.addItem("配置待更新", "unavailable")
            index = self.provider_combo.count() - 1
        self.provider_combo.setCurrentIndex(index)
        self.provider_combo.setToolTip(self.provider_combo.currentText())
        self.provider_combo.blockSignals(False)
        self._refresh_language_choices()

    def _refresh_language_choices(self) -> None:
        provider_id = self.provider_combo.currentData()
        changed = False
        for combo, is_source in ((self.source_combo, True), (self.target_combo, False)):
            before = combo.currentData()
            wanted = language_code(before) if before else ("auto" if is_source else "zh")
            combo.blockSignals(True)
            combo.clear()
            choices = language_choices(provider_id, source=is_source)
            for language in choices:
                combo.addItem(language.name, CHOICE_VALUES.get(language.code, language.code))
            index = next((i for i, language in enumerate(choices) if language.code == wanted), 0)
            combo.setCurrentIndex(index)
            combo.setToolTip(("源语言" if is_source else "目标语言") + " · 可搜索名称或语言代码")
            combo.blockSignals(False)
            changed |= before != combo.currentData()
        if changed:
            self.invalidate_translation()

    def choose_provider(self, *_args) -> None:
        chosen = self.provider_combo.currentData()
        if not chosen or chosen == "unavailable":
            return
        try:
            if chosen == "offline":
                self.settings.set_translation_mode("offline")
            else:
                self.settings.activate(chosen)
        except (ConfigurationError, TranslationError) as error:
            self.status_label.setText("请先配置所选平台")
            self.open_settings()
            self.settings_dialog.select_page("platforms")
            self.settings_dialog.provider_combo.setCurrentIndex(self.settings_dialog.provider_combo.findData(chosen))
            self.settings_dialog.feedback.setText(str(error))
            self._refresh_provider_choices()
            return
        self.reload_configuration()

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "添加需要识别的图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        try:
            if Path(path).stat().st_size > 15 * 1024 * 1024:
                self.status_label.setText("请选择小于 15 MB 的图片")
                return
        except OSError:
            self.status_label.setText("图片无法读取，请重新选择")
            return
        image = QImage(path)
        if image.isNull():
            self.status_label.setText("图片格式无效，请重新选择")
            return
        self.recognize_image(image)

    def recognize_image(self, image: QImage) -> None:
        if self._shutting_down or self._ocr_worker is not None or self.overlay is not None or self.capture_timer.isActive():
            self.status_label.setText("请先完成当前识别")
            return
        if self.translation_running:
            self.cancel_translation()
        self.capture_generation += 1
        self._capture_active = True
        self.blocks = []
        pixmap = QPixmap.fromImage(image)
        self._capture_selected(pixmap, pixmap.rect(), self.capture_generation)

    def remove_attachment(self) -> None:
        self._compose_image = QPixmap()
        self.attachment_frame.hide()

    def _update_attachment(self) -> None:
        self._compose_image = self.retained_pixmap
        self.attachment_thumbnail.setPixmap(self._compose_image.scaled(43, 31, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.attachment_frame.show()

    def view_history_image(self, data: str) -> None:
        from screen_translator.ui.chrome import TitleBar, shell_for
        from screen_translator.ui.qt_controls import decorate_button
        from PySide6.QtWidgets import QHBoxLayout, QToolButton
        image = QPixmap()
        image.loadFromData(QByteArray.fromBase64(data.encode()))
        if image.isNull():
            return
        dialog = QDialog(self, Qt.WindowType.Window)
        dialog.setWindowTitle("译语 · 来源截图")
        dialog.resize(600, 420)
        shell = shell_for(dialog)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(shell)
        layout = QVBoxLayout(shell.face)
        layout.setContentsMargins(23, 15, 23, 24)
        bar = TitleBar(dialog)
        row = QHBoxLayout(bar)
        row.addWidget(QLabel("来源截图"), 1)
        close = QToolButton()
        decorate_button(close, "close", "关闭来源截图", icon_only=True)
        close.clicked.connect(dialog.reject)
        row.addWidget(close)
        layout.addWidget(bar)
        label = QLabel()
        label.setPixmap(image.scaled(530, 310, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label, 1)
        dialog.setStyleSheet(stylesheet(theme=self.appearance["theme"]))
        shell.face.theme = self.appearance["theme"]
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._image_dialog = dialog
        dialog.show()

    def export_history(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出翻译记录", "译语-翻译记录.json", "JSON (*.json)")
        if path:
            try:
                Path(path).write_text(json.dumps({"schema": 1, "conversations": self.conversations}, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                self.status_label.setText("导出失败，请检查保存位置")

    def shutdown_and_quit(self) -> None:
        self.shutdown()
        QApplication.quit()

    def _start_worker(self, worker: FunctionWorker) -> None:
        # Keep the Python signals and callback receivers alive until delivery.
        self._workers.add(worker)
        worker.signals.finished.connect(self._worker_finished, Qt.ConnectionType.QueuedConnection)
        self.pool.start(worker)

    @Slot(object)
    def _worker_finished(self, worker: FunctionWorker) -> None:
        self._workers.discard(worker)
        if worker is self._ocr_worker:
            self._ocr_worker = None
            if not self._shutting_down:
                self.capture_button.setEnabled(True)
                self.recapture_button.setEnabled(True)

    def _build_ui(self) -> None:
        build_translation_workspace(self)

    def _setup_tray(self) -> None:
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.addAction("显示面板", self.show_panel)
        menu.addAction("屏幕取词 · Ctrl+Alt+S", self.begin_capture)
        menu.addAction("翻译平台设置", self.open_settings)
        self.pin_action = menu.addAction("窗口置顶")
        self.pin_action.setCheckable(True)
        self.pin_action.setChecked(True)
        self.pin_action.toggled.connect(self._set_pin)
        menu.addSeparator()
        menu.addAction("退出", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_panel()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _apply_style(self) -> None:
        compact = self.height() < 520
        self._compact_style = compact
        theme = self.appearance["theme"]
        self.setStyleSheet(stylesheet(self.read_size, theme, compact) + f"\nQWidget {{font-family:'{self.appearance['ui_font']}', 'Microsoft YaHei UI';}}")
        self.setPalette(palette_for(theme))
        self.surface.theme = theme
        self.surface.update()
        self.source_edit.setStyleSheet(f"font-family:'{self.appearance['source_font']}';font-size:{self.appearance['source_size']}px;border:0;background:transparent;")
        for combo in self.findChildren(ThemedComboBox):
            combo.setProperty("theme", theme)
            combo.update()
        refresh_icons(self, theme)
        self._update_reading_layout()
        self.render_conversation(scroll=False)

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()
        if not self._shutting_down:
            self._update_dock_geometry()
            self.edge_dock.show()
            self.dock_geometry_timer.start()

    def _update_dock_geometry(self) -> None:
        try:
            side = self.settings.dock_side
            position = self.settings.dock_position
        except ConfigurationError:
            side, position = "right", None
        self.edge_dock.position_in(work_area(self), side, position)

    def _save_dock_position(self, position) -> None:
        try:
            self.settings.set_dock_position(position.x(), position.y())
        except ConfigurationError as error:
            self.status_label.setText(str(error))
            self.edge_dock.handle.setToolTip("位置仅在本次运行保留；" + str(error))
        else:
            self.edge_dock.handle.setToolTip("按住拖动 · 双击打开译语")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        fit_window(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "chat_view"):
            self._update_reading_layout()
            compact = self.height() < 520
            if getattr(self, "_compact_style", None) != compact:
                self._apply_style()

    def set_reading_mode(self, mode: int) -> None:
        self.reading_mode = mode
        if mode != 2:
            self.compact_reading_mode = mode
        self._update_reading_layout()

    def _update_reading_layout(self) -> None:
        if not hasattr(self, "chat_view"):
            return
        compact = self.width() < 520 or self.height() < 500
        self.header_widget.setFixedHeight(64 if compact else 78)
        self.header_widget.layout().setContentsMargins(14 if compact else 24, 10, 14 if compact else 22, 10)
        self.brand_subtitle.setVisible(not compact)
        self.workspace_menu_button.setVisible(self.width() >= 430)
        self.history_button.setText("历史" if self.width() >= 500 else "")
        self.theme_button.setVisible(self.width() >= 520)
        self.session_hint.setVisible(self.width() >= 480 and not compact)
        self.source_edit.setFixedHeight(48 if self.height() < 520 else 62)
        self.body_pages.widget(0).layout().setSpacing(10 if self.height() < 520 else 15)
        self.body_pages.widget(0).layout().setContentsMargins(20 if compact else 28, 11 if compact else 17,
                                                          20 if compact else 28, 14 if compact else 20)

    def change_reading_size(self) -> None:
        self.read_size = self.font_combo.currentData()
        if self.read_size is not None:
            try:
                self.settings.set_appearance(result_size=self.read_size)
            except ConfigurationError as error:
                self.status_label.setText(str(error))
            self.refresh_appearance()

    def change_theme(self) -> None:
        theme = self.theme_combo.currentData()
        try:
            self.settings.set_appearance(theme=theme)
        except ConfigurationError as error:
            self.status_label.setText(str(error))
        self.refresh_appearance()

    def toggle_theme(self) -> None:
        self.theme_combo.setCurrentIndex(0 if self.appearance["theme"] == "dark" else 1)

    def refresh_appearance(self) -> None:
        try:
            self.appearance = self.settings.appearance
        except ConfigurationError:
            self.appearance = dict(DEFAULT_APPEARANCE)
        self.read_size = self.appearance["result_size"]
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.appearance["theme"]))
        self.theme_combo.blockSignals(False)
        self.font_combo.blockSignals(True)
        index = self.font_combo.findData(self.read_size)
        if index < 0:
            self.font_combo.addItem(f"{self.read_size}px", self.read_size)
            index = self.font_combo.findData(self.read_size)
        self.font_combo.setCurrentIndex(index)
        self.font_combo.blockSignals(False)
        self._apply_style()
        self.recognition_window.apply_theme(self.appearance["theme"])
        self.edge_dock.apply_theme(self.appearance["theme"])
        if self.settings_dialog is not None:
            self.settings_dialog.apply_theme(self.appearance["theme"])
        if hasattr(self, "dock_geometry_timer"):
            self._update_dock_geometry()

    def show_recognition(self) -> None:
        if self._shutting_down or self.capture_timer.isActive() or self.overlay is not None:
            return
        self.recognition_window.showNormal()
        fit_window(self.recognition_window)
        self.recognition_window.raise_()
        self.recognition_window.activateWindow()

    def arrange_workspaces(self, area: QRect | None = None) -> None:
        area = area if area is not None else work_area(self)
        self.show_panel()
        self.showNormal()
        self.recognition_window.showNormal()
        if area.width() >= 1100:
            left_width = int(area.width() * .4)
            self.recognition_window.resize(left_width - 24, area.height() - 70)
            self.recognition_window.move(area.left() + 8, area.top() + 8)
            self.resize(area.width() - left_width - 24, area.height() - 70)
            self.move(area.left() + left_width + 8, area.top() + 8)
        else:
            self.resize(area.width() - 24, area.height() - 60)
            self.move(area.left() + 8, area.top() + 8)
            self.recognition_window.resize(area.width() - 24, area.height() - 60)
            self.recognition_window.move(area.left() + 8, area.top() + 8)
        fit_window(self, area)
        fit_window(self.recognition_window, area)
        self.recognition_window.raise_()
        self.recognition_window.activateWindow()

    def show_panel(self) -> None:
        if self._shutting_down or self.capture_timer.isActive():
            return
        if self.overlay is not None:
            self.overlay.raise_()
            self.overlay.activateWindow()
            return
        self.edge_dock.hide()
        self.dock_geometry_timer.stop()
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        fit_window(self)
        self.raise_()
        self.activateWindow()

    def toggle_pin(self) -> None:
        self._set_pin(self.pin_button.isChecked())

    def _set_pin(self, pinned: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        recognition_visible = self.recognition_window.isVisible()
        self.recognition_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
        self.pin_button.setChecked(pinned)
        self.pin_action.setChecked(pinned)
        if visible:
            self.show()
        if recognition_visible:
            self.recognition_window.show()
        self.status_label.setText("●  已置顶" if pinned else "●  已取消置顶")

    def on_source_changed(self) -> None:
        self.source_version += 1
        self.translation_edit.clear()
        self.copy_button.setEnabled(False)
        self.translate_button.setEnabled(bool(self.source_edit.toPlainText().strip()) and not self.translation_running)
        if self.translation_running and isinstance(self.translator, ArgosTranslator):
            self.cancel_translation()

    def invalidate_translation(self) -> None:
        self.source_version += 1
        self.translation_edit.clear()
        self.copy_button.setEnabled(False)
        if self.translation_running and isinstance(self.translator, ArgosTranslator):
            self.cancel_translation()

    def cancel_translation(self) -> None:
        self.translate_task += 1
        self.local_translator.close()
        self.translation_running = False
        self.cancel_translation_button.setEnabled(False)
        self.translate_button.setToolTip("翻译 · Enter 或 Ctrl+Enter")
        self.translate_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
        self.status_label.setText("●  已取消翻译，可以重试")
        self._finish_request(error="已取消翻译，可以重新发送。", interrupted=True)

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        if self._chat_request is not None:
            self._chat_request["message"]["status"] = "interrupted"
            self._chat_request = None
        self.save_history()
        self.dock_geometry_timer.stop()
        self.edge_dock.hide()
        self.recognition_window.hide()
        self.hide()
        self.capture_generation += 1
        self._capture_active = False
        self.capture_timer.stop()
        self._close_overlay()
        self.translate_task += 1
        self.idle_timer.stop()
        self.local_translator.close()
        if self.settings_dialog is not None:
            self.settings_dialog.cancel_pending_verification()
            self.settings_dialog.hide()
        self.tray.hide()

    def change_mode(self) -> None:
        try:
            self.settings.set_translation_mode(self.mode_combo.currentData())
        except ConfigurationError as error:
            QMessageBox.warning(self, "模式保存失败", str(error))
        self.reload_configuration()

    def open_settings(self) -> None:
        if self._shutting_down or self.capture_timer.isActive() or self.overlay is not None:
            return
        self.edge_dock.hide()
        self.dock_geometry_timer.stop()
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.settings, self)
            self.settings_dialog.configuration_changed.connect(self.reload_configuration)
            self.settings_dialog.appearance_changed.connect(self.refresh_appearance)
            self.settings_dialog.finished.connect(self._settings_closed)
        self.settings_dialog.apply_theme(self.appearance["theme"])
        self.settings_dialog.showNormal()
        fit_window(self.settings_dialog)
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _settings_closed(self) -> None:
        if not self.isVisible() and not self._shutting_down:
            self.edge_dock.show()
            self._update_dock_geometry()
            self.dock_geometry_timer.start()

    def reload_configuration(self) -> None:
        # Invalidate in-flight results before replacing the adapter. Capture the
        # adapter in each worker so queued work cannot accidentally use new keys.
        if self._chat_request is not None:
            self._finish_request(error="翻译平台已更改，请重新发送。", interrupted=True)
        self.translate_task += 1
        self.local_translator.close()
        self.invalidate_translation()
        self.translation_running = False
        self.cancel_translation_button.setEnabled(False)
        self.translate_button.setToolTip("翻译 · Enter 或 Ctrl+Enter")
        self.translate_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
        self.translator = None
        try:
            self.translation_mode = self.settings.translation_mode
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.translation_mode))
            self.mode_combo.blockSignals(False)
            if self.translation_mode == "offline":
                self.provider_label.setText("中英基础体验 · 无需 API · 原文留在本机")
                self.translator = self.local_translator
            else:
                provider_id = self.settings.active_provider
                provider = get_provider(provider_id)
                self.provider_label.setText("当前平台：" + provider.name)
                self.translator = create_translator(provider_id, self.settings.values(provider_id))
        except (ConfigurationError, TranslationError) as error:
            self.status_label.setText("●  请打开平台设置完成配置")
            self.configuration_error = str(error)
            self.provider_label.setText("当前平台：配置待更新")
            if not self.provider_label.text():
                self.provider_label.setText("当前平台：配置不可用")
        else:
            self.configuration_error = ""
            self.status_label.setText("●  准备就绪")
        self._refresh_provider_choices()
        self.render_conversation(scroll=False)

    def translate(self) -> None:
        source = self.source_edit.toPlainText().strip()
        if self._shutting_down or not source or self.translation_running:
            return
        if self.translator is None:
            QMessageBox.warning(self, "请配置翻译平台", self.configuration_error)
            self.open_settings()
            return
        self.translate_task += 1
        task_id = self.translate_task
        version = self.source_version
        target = self.target_combo.currentData() or self.target_combo.currentText()
        source_language = self.source_combo.currentData() or self.source_combo.currentText()
        self.translation_running = True
        self.translate_button.setToolTip("正在翻译")
        self.translate_button.setEnabled(False)
        self.cancel_translation_button.setEnabled(True)
        self.idle_timer.stop()
        self.status_label.setText("●  正在本机翻译，首次需加载模型…" if self.translation_mode == "offline"
                                  else "●  正在连接翻译服务…")
        self._record_request(source, self.target_combo.currentText(), task_id)
        translator = self.translator
        if isinstance(translator, ArgosTranslator):
            ticket = translator.ticket()
            worker = FunctionWorker(lambda: translator.translate(source, target, source_language, ticket=ticket), (task_id, version),
                                    failure_message="翻译组件发生异常，请检查配置后主动重试。")
        else:
            worker = FunctionWorker(lambda: translator.translate(source, target, source_language), (task_id, version),
                                    failure_message="翻译组件发生异常，请检查配置后主动重试。")
        worker.signals.result.connect(self._translation_ready, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(self._translation_failed, Qt.ConnectionType.QueuedConnection)
        self._start_worker(worker)

    @Slot(object, object)
    def _translation_ready(self, context: tuple[int, int], translation: str) -> None:
        task_id, version = context
        if task_id != self.translate_task:
            return
        self.translation_running = False
        self.cancel_translation_button.setEnabled(False)
        if self.translation_mode == "offline":
            self.idle_timer.start()
        self.translate_button.setToolTip("翻译 · Enter 或 Ctrl+Enter")
        self.translate_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
        original = self._chat_request["message"]["source"] if self._chat_request else self.source_edit.toPlainText().strip()
        self._finish_request(translation)
        if version != self.source_version:
            self.status_label.setText("●  原文已修改，请重新翻译")
            return
        self.translation_edit.setPlainText(translation)
        self.compact_reading_mode = 1
        self._update_reading_layout()
        self.copy_button.setEnabled(True)
        self.status_label.setText("●  源语言与目标相同，已保留原文" if self.translation_mode == "offline" and translation == original
                                  else "●  翻译完成")
        if self.source_edit.toPlainText().strip() == original:
            self.source_edit.blockSignals(True)
            self.source_edit.clear()
            self.source_edit.blockSignals(False)
            self.source_count_label.setText("0 字符")
            self.remove_attachment()
            self.translate_button.setEnabled(False)

    @Slot(object, str)
    def _translation_failed(self, context: tuple[int, int], message: str) -> None:
        task_id, version = context
        if task_id != self.translate_task:
            return
        self.translation_running = False
        self.cancel_translation_button.setEnabled(False)
        self.translate_button.setToolTip("翻译 · Enter 或 Ctrl+Enter")
        self.translate_button.setEnabled(bool(self.source_edit.toPlainText().strip()))
        self._finish_request(error=message)
        if version != self.source_version:
            self.status_label.setText("●  内容已更改，请重新翻译")
            return
        self.status_label.setText("●  翻译失败，可重试")
        QMessageBox.warning(self, "翻译未完成", message)

    def copy_translation(self) -> None:
        text = self.translation_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("●  译文已复制")

    def begin_capture(self) -> None:
        if self._shutting_down or self.capture_timer.isActive() or self.overlay is not None:
            return
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.status_label.setText("●  请先关闭平台设置，再取词")
            return
        if self._ocr_worker is not None:
            self.status_label.setText("●  上一次识别正在收尾，请稍后重新取词")
            return
        self.capture_generation += 1
        if not self._capture_active:
            if self.translation_running:
                self.cancel_translation()
        self._capture_active = True
        self._capture_screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.blocks = []
        self.selection_frame.hide()
        self.edge_dock.hide()
        self.dock_geometry_timer.stop()
        self.hide()
        self.capture_timer.start()

    def _show_capture_overlay(self) -> None:
        if self._shutting_down or not self._capture_active:
            return
        screen = self._capture_screen
        if screen is None or screen not in QGuiApplication.screens():
            self._capture_cancelled()
            self.status_label.setText("●  找不到可用屏幕")
            return
        screenshot = screen.grabWindow(0)
        if screenshot.isNull():
            self._capture_cancelled()
            self.status_label.setText("●  屏幕截图失败，请重试")
            return
        self.overlay = CaptureOverlay(screen.geometry(), screenshot)
        self.overlay.winId()
        self.overlay.windowHandle().setScreen(screen)
        self.overlay.setGeometry(screen.geometry())
        generation = self.capture_generation
        self.overlay.selected.connect(lambda rect: self._capture_selected(screenshot, rect, generation))
        self.overlay.cancelled.connect(lambda: self._capture_cancelled(generation))
        self.overlay.show()
        self.overlay.activateWindow()
        self.overlay.setFocus()

    def _close_overlay(self) -> None:
        if self.overlay:
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None

    def _capture_selected(self, screenshot: QPixmap, rect: QRect, generation: int | None = None) -> None:
        if self._shutting_down or (generation is not None and generation != self.capture_generation):
            return
        if self._ocr_worker is not None:
            return
        self._close_overlay()
        self.candidate_pixmap = screenshot.copy(rect)
        self.status_label.setText("●  正在本机识别文字…")
        self.recognition_window.status_label.setText("正在本机识别文字…可取消或返回翻译台编辑")
        self.block_list.clear()
        self.recognition_window.set_review("")
        self.recognition_window.review_edit.setReadOnly(True)
        self.confirm_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.selection_preview.pixmap = self.candidate_pixmap
        self.selection_preview.blocks = []
        self.selection_preview.selected = set()
        self.selection_preview.update()
        self.show_recognition()
        self.capture_button.setEnabled(False)
        self.recapture_button.setEnabled(False)
        generation = self.capture_generation
        image = self.candidate_pixmap.toImage().copy()
        worker = FunctionWorker(lambda: self.ocr.recognize(self._qimage_to_array(image)), generation,
                                failure_message="OCR 组件发生异常，请重新取词；仍失败时重新解压完整包。")
        worker.signals.result.connect(self._ocr_ready, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(self._ocr_failed, Qt.ConnectionType.QueuedConnection)
        self._ocr_worker = worker
        self._start_worker(worker)

    @staticmethod
    def _qimage_to_array(image: QImage):
        import numpy as np
        image = image.convertToFormat(QImage.Format.Format_BGR888)
        pixels = np.frombuffer(image.constBits(), np.uint8, count=image.sizeInBytes())
        # Qt aligns rows to four bytes; RapidOCR expects tightly packed BGR.
        rows = pixels.reshape((image.height(), image.bytesPerLine()))
        return rows[:, :image.width() * 3].reshape((image.height(), image.width(), 3)).copy()

    def _capture_cancelled(self, generation: int | None = None) -> None:
        if generation is None or generation == self.capture_generation:
            self.cancel_selection()

    @Slot(object, object)
    def _ocr_ready(self, generation: int, blocks: list[TextBlock]) -> None:
        if generation != self.capture_generation:
            return
        if not blocks:
            self.blocks = []
            self.status_label.setText("●  未识别到文字，请重新框选")
            self._show_selection_state(empty=True)
            return
        self.blocks = blocks
        self._show_selection_state()
        self.status_label.setText(f"●  识别到 {len(blocks)} 行文字")
        self.recognition_window.status_label.setText("识别完成，可校对文字后放入输入框")

    @Slot(object, str)
    def _ocr_failed(self, generation: int, message: str) -> None:
        if generation != self.capture_generation:
            return
        self.status_label.setText("●  OCR 失败")
        self.recognition_window.status_label.setText("OCR 失败；可重新框选或取消")
        self.recognition_window.review_edit.setReadOnly(False)
        QMessageBox.warning(self, "文字识别失败", message)

    def _show_selection_state(self, empty: bool = False) -> None:
        self.selection_frame.show()
        fit_window(self.selection_frame)
        self.selection_frame.raise_()
        self.selection_frame.activateWindow()
        self.selection_title.setText("截图识字")
        if empty:
            self.recognition_window.status_label.setText("未识别到文字，请重新框选")
        self.block_list.blockSignals(True)
        self.block_list.clear()
        self.selection_preview.pixmap = self.candidate_pixmap
        self.selection_preview.blocks = self.blocks
        self.selection_preview.selected = set()
        self.selection_preview.update()
        self.recognition_window.set_view(0)
        for block in self.blocks:
            item = QListWidgetItem(block.text)
            item.setData(Qt.ItemDataRole.UserRole, block.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(f"截图坐标：{block.bounds}")
            self.block_list.addItem(item)
        self.block_list.blockSignals(False)
        self.recognition_window.review_edit.setReadOnly(False)
        self.recognition_window.set_review(selected_ocr_text(self.blocks, self._selected_ids()))
        self._update_confirm_enabled()
        self.select_all_button.setEnabled(bool(self.blocks))
        self.recapture_button.setText("重新框选")
        self.cancel_selection_button.setText("取消")

    def _update_confirm_enabled(self, *_args) -> None:
        selected = any(
            self.block_list.item(index).checkState() == Qt.CheckState.Checked
            for index in range(self.block_list.count())
        )
        if not self.recognition_window.review_edited and self._capture_active:
            self.recognition_window.set_review(selected_ocr_text(self.blocks, self._selected_ids()))
        text = self.recognition_window.review_edit.toPlainText().strip()
        self.confirm_button.setEnabled(bool(text) and self._capture_active)
        selected_ids = self._selected_ids()
        self.selection_preview.selected = selected_ids
        self.selection_preview.update()
        self.recognition_window.count_label.setText(f"已选 {len(selected_ids)} / {self.block_list.count()}")

    def _selected_ids(self) -> set[str]:
        return {self.block_list.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(self.block_list.count())
                if self.block_list.item(index).checkState() == Qt.CheckState.Checked}

    def toggle_block(self, block_id: str) -> None:
        for index in range(self.block_list.count()):
            item = self.block_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == block_id:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
                                   else Qt.CheckState.Checked)

    def select_image_blocks(self, selected_ids: set[str]) -> None:
        for index in range(self.block_list.count()):
            item = self.block_list.item(index)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in selected_ids
                               else Qt.CheckState.Unchecked)

    def select_all_blocks(self) -> None:
        self.recognition_window.review_edited = False
        for index in range(self.block_list.count()):
            self.block_list.item(index).setCheckState(Qt.CheckState.Checked)
        self._update_confirm_enabled()

    def confirm_selection(self) -> None:
        if not self._capture_active:
            return
        selected_ids = {
            self.block_list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.block_list.count())
            if self.block_list.item(index).checkState() == Qt.CheckState.Checked
        }
        text = (self.recognition_window.review_edit.toPlainText().strip() if self.recognition_window.review_edited
                else selected_ocr_text(self.blocks, selected_ids))
        if not text:
            return
        self.source_edit.setPlainText(text)
        self.translation_edit.clear()
        self.retained_pixmap = self.candidate_pixmap
        self.retained_blocks = list(self.blocks)
        self.retained_selected_ids = selected_ids
        self.screenshot_toggle.setEnabled(True)
        self.screenshot_toggle.show()
        self._update_attachment()
        self.selection_frame.hide()
        self._capture_active = False
        self.capture_generation += 1
        self.confirm_button.setEnabled(False)
        self.show_panel()
        self.set_reading_mode(2)
        self.compact_reading_mode = 0
        self._update_reading_layout()
        self.status_label.setText("●  已回填原文，可以编辑后翻译")

    def cancel_selection(self) -> None:
        if self._shutting_down or not self._capture_active:
            return
        self.capture_generation += 1
        self._capture_active = False
        self.capture_timer.stop()
        self._close_overlay()
        self.selection_frame.hide()
        self.blocks = []
        self.candidate_pixmap = QPixmap()
        self.block_list.clear()
        self.confirm_button.setEnabled(False)
        self.selection_preview.pixmap = QPixmap()
        self.selection_preview.blocks = []
        self.selection_preview.selected = set()
        self.selection_preview.update()
        # Capture does not edit either text field before confirmation. Keep any
        # edits or newer translations made while OCR was running as they are.
        self.show_panel()
        self.status_label.setText("●  已取消，原文保持不变")

    def toggle_screenshot(self) -> None:
        if self.retained_pixmap.isNull() or self._capture_active:
            return
        self.selection_preview.pixmap = self.retained_pixmap
        self.selection_preview.blocks = self.retained_blocks
        self.selection_preview.selected = set(self.retained_selected_ids)
        self.selection_preview.update()
        self.block_list.clear()
        for block in self.retained_blocks:
            item = QListWidgetItem(block.text)
            item.setData(Qt.ItemDataRole.UserRole, block.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if block.id in self.retained_selected_ids else Qt.CheckState.Unchecked)
            self.block_list.addItem(item)
        self._update_confirm_enabled()
        self.recognition_window.selection_title.setText("识别来源截图")
        self.recognition_window.status_label.setText("查看已提交的来源；重新框选可开始新的识文")
        self.recognition_window.set_view(1)
        self.show_recognition()


def create_application() -> QApplication:
    QApplication.setQuitOnLastWindowClosed(False)
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
        instance.setStyle("Fusion")
        instance.setWindowIcon(app_mark_icon())
        return instance
    if not isinstance(instance, QApplication):
        raise RuntimeError("A QCoreApplication already exists; a QApplication is required.")
    instance.setWindowIcon(app_mark_icon())
    return instance
