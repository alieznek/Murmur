"""Synthetic end-to-end check of the actual UI, OCR and offline adapter."""
from __future__ import annotations

import json
import time
from pathlib import Path


def check_offline(window, app, checkpoint, report):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from screen_translator.ui.notice import QMessageBox
    from screen_translator.core.ocr_text import selected_ocr_text
    from screen_translator.services.argos_translator import ArgosTranslator

    def wait_for(predicate):
        deadline = time.monotonic() + 90
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if not predicate():
            raise RuntimeError("Offline UI deadline exceeded")

    def translate(text, source, target):
        window.source_combo.setCurrentText(source)
        window.target_combo.setCurrentText(target)
        window.source_edit.setPlainText(text)
        start = time.perf_counter()
        window.translate()
        wait_for(lambda: not window.translation_running)
        result = window.translation_edit.toPlainText()
        if not result:
            raise RuntimeError("Offline UI did not return a result")
        report.setdefault("translations", []).append({"source": text, "result": result,
                                                       "seconds": time.perf_counter() - start})
        window.copy_translation()
        if QApplication.clipboard().text() != result:
            raise RuntimeError("Offline copy failed")
        return result

    # Every input in this report is public synthetic test data.
    window.settings.set_translation_mode("offline")
    window.reload_configuration()
    report["argos_loaded_in_ui"] = "argostranslate.translate" in __import__("sys").modules
    report["lazy_worker"] = window.local_translator.pid is None
    original_warning = QMessageBox.warning
    report["ui_errors"] = []
    QMessageBox.warning = lambda _parent, _title, message: report["ui_errors"].append(message)
    try:
        checkpoint("offline-first-direction")
        result = translate("Do not delete this file.", "自动识别", "中文")
        report["negation"] = "不" in result
        checkpoint("offline-both-directions")
        result = translate("请更新到版本 1.2.3。", "中文", "English")
        report["version_preserved"] = "1.2.3" in result and "1.5.3" not in result
        translate("打开 `config.json` 文件。", "中文", "English")
        checkpoint("offline-ocr")
        image = QImage(640, 100, QImage.Format.Format_RGB888)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setPen(QColor("black"))
        painter.setFont(QFont("Arial", 32))
        painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "DO NOT DELETE 123")
        painter.end()
        blocks = window.ocr.recognize(window._qimage_to_array(image))
        joined = selected_ocr_text(blocks, {block.id for block in blocks})
        report["ocr_joined"] = joined
        result = translate(joined, "English", "中文")
        report["ocr_negation"] = "不" in result and "123" in result
        # Re-run the fixed isolation corpus through the product policies.
        corpus = Path(__file__).with_name("offline-cases.json")
        report["corpus"] = []
        if corpus.is_file():
            from screen_translator.services.translator import TranslationError
            for case in json.loads(corpus.read_text(encoding="utf-8")):
                try:
                    result = window.local_translator.translate(case["text"], case["target"], case["source"])
                    report["corpus"].append({**case, "result": result})
                except TranslationError as error:
                    report["corpus"].append({**case, "rejected": str(error)})
        checkpoint("offline-release")
        # Corpus number rejection may have unloaded the preceding process.
        # Ensure this measures releasing a live, successfully used worker.
        translate("Hello release.", "English", "中文")
        pid = window.local_translator.pid
        window.local_translator.close()
        wait_for(lambda: not window._workers)
        report["released_pid"] = pid
        report["released"] = window.local_translator.pid is None
        time.sleep(0.2)
        checkpoint("offline-restart")
        translate("Hello world.", "English", "中文")
        report["restart"] = window.local_translator.pid != pid
        # Missing models must be a recoverable, local error with a fixed hint.
        missing = ArgosTranslator(resources=window.settings.path.parent / "missing-resources")
        try:
            missing.translate("Hello.", "中文")
            report["missing_resources_rejected"] = False
        except Exception as error:
            report["missing_resources_rejected"] = "不会自动下载" in str(error)
        finally:
            missing.close()
        # Actual UI cancellation suppresses callbacks and tears down the worker.
        checkpoint("offline-cancel")
        window.source_edit.setPlainText("Please do not delete this file. " * 40)
        window.translate()
        window.cancel_translation()
        wait_for(lambda: not window._workers)
        report["cancel"] = not window.translation_running and not window.translation_edit.toPlainText()
        checkpoint("offline-recovery")
        translate("Hello again.", "English", "中文")
        window.settings.set_translation_mode("online")
        window.reload_configuration()
        report["online_release"] = window.local_translator.pid is None
        report["offline_passed"] = all(report[key] for key in
            ("lazy_worker", "negation", "version_preserved", "ocr_negation", "released", "restart",
             "missing_resources_rejected", "cancel", "online_release")) and not report["argos_loaded_in_ui"]
    finally:
        QMessageBox.warning = original_warning
        window.shutdown()
