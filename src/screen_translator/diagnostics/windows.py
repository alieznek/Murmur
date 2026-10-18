"""Small frozen-runtime UI check using synthetic data and existing shared services."""
from __future__ import annotations


def check_windows(window, app) -> dict:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QPixmap
    from screen_translator.core.text_blocks import TextBlock

    result = {"kind": "synthetic_qt_ui_no_user_data", "external_machine_verified": False}
    window.show_panel()
    window.source_edit.setPlainText("Synthetic window input")
    window.translation_edit.setPlainText("合成窗口 译文")
    window._capture_active = True
    image = QPixmap(400, 1280)
    image.fill(QColor("white"))
    window.candidate_pixmap = image
    blocks = [TextBlock(str(index), f"Synthetic block {index}", ((0, index * 40), (380, index * 40),
                                                              (380, index * 40 + 30), (0, index * 40 + 30)))
              for index in range(32)]
    window._ocr_ready(window.capture_generation, blocks)
    app.processEvents()
    result["independent_windows"] = window.block_list.window() is window.recognition_window and window.recognition_window.isWindow()
    window.select_image_blocks({"1", "31"})
    result["selection_synchronized"] = window.selection_preview.selected == {"1", "31"}
    result["pending_preserves_input"] = window.source_edit.toPlainText() == "Synthetic window input"
    window.recognition_window.resize(500, 344)
    window.resize(500, 344)
    app.processEvents()
    window.recognition_window.set_view(1)
    window.block_list.scrollToBottom()
    app.processEvents()
    last = window.block_list.visualItemRect(window.block_list.item(31))
    result["last_block_accessible"] = window.block_list.viewport().rect().intersects(last)
    result["compact_actions_visible"] = all(button.isVisible() and button.geometry().bottom() <= button.parentWidget().height()
                                            for button in (window.confirm_button, window.translate_button, window.capture_button))
    generation = window.capture_generation
    window.recognition_window.close()
    window._ocr_ready(generation, blocks)
    result["close_discards_late_ocr"] = window.recognition_window.isHidden() and window.source_edit.toPlainText() == "Synthetic window input"
    window.close()
    result["edge_entry"] = window.edge_dock.isVisible()
    area = QRect(-512, -100, 512, 384)
    for side in ("left", "right"):
        window.edge_dock.position_in(area, side)
        result[f"edge_{side}_inside_workarea"] = area.contains(window.edge_dock.geometry())
    window.show_panel()
    result["restore_preserves_content"] = window.source_edit.toPlainText() == "Synthetic window input" and window.translation_edit.toPlainText() == "合成窗口 译文"
    result["passed"] = all(value for key, value in result.items() if key not in ("kind", "external_machine_verified"))
    return result
