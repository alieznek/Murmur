import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from screen_translator.core.offline_text import numeric_values_agree, translate_preserving_literals, validate_request
from screen_translator.core.ocr_text import selected_ocr_text
from screen_translator.core.text_blocks import TextBlock
from screen_translator.services.argos_translator import ArgosTranslator
from screen_translator.services.offline_resources import verify_resources
from screen_translator.services.translator import TranslationError
from screen_translator.services.worker_process import start_process


class OfflineTextTests(unittest.TestCase):
    def test_direction_detection_manual_override_and_identity(self):
        self.assertEqual(validate_request("Hello world", "中文"), ("en", "zh"))
        self.assertEqual(validate_request("请重试。", "English"), ("zh", "en"))
        self.assertEqual(validate_request("Settings 设置", "en", "中文"), ("zh", "en"))
        self.assertEqual(ArgosTranslator().translate("中文", "中文", "中文"), "中文")
        for text in ("A", "123", "Settings 设置", "", "x" * 2001):
            with self.subTest(text=text[:20]), self.assertRaises(TranslationError):
                validate_request(text, "zh")
        self.assertEqual(validate_request("x" * 2000, "zh"), ("en", "zh"))

    def test_literals_and_manual_paragraphs_are_preserved_without_translating_punctuation(self):
        seen = []
        def model(text):
            seen.append(text)
            return "Translated"
        text = "版本 1.2.3。\n\n打开 `config.json` 文件 C:\\Temp\\demo.txt"
        result = translate_preserving_literals(text, model)
        for token in ("1.2.3", "`config.json`", "C:\\Temp\\demo.txt", "\n\n"):
            self.assertIn(token, result)
        self.assertNotIn("。", seen)
        self.assertTrue(all("1.2.3" not in value and "config.json" not in value for value in seen))
        self.assertEqual(translate_preserving_literals("更新到版本1.2.3。", model), "Translated1.2.3。")

    def test_number_changes_are_rejected_instead_of_guessed(self):
        with self.assertRaisesRegex(TranslationError, "数字"):
            translate_preserving_literals("Wait 10 seconds", lambda _: "等待 12 秒")

    def test_equivalent_number_words_pass_while_different_quantities_fail(self):
        for source, result in (("Wait 10 seconds", "请等十秒再试一次"),
                               ("3 unread messages", "三条未读留言"),
                               ("至少8个字符", "at least eight characters"),
                               ("two minutes", "2分钟")):
            with self.subTest(source=source):
                self.assertTrue(numeric_values_agree(source, result))
                self.assertEqual(translate_preserving_literals(source, lambda _: result), result)
        for source, result in (("10 seconds", "十二秒"), ("3 messages", "four messages"),
                               ("20 messages", "twenty-one messages"), ("编号03", "number three"),
                               ("version 1.2", "version 1.5")):
            with self.subTest(source=source):
                self.assertFalse(numeric_values_agree(source, result))

    def test_ocr_words_rejoin_but_rows_and_columns_remain_separate(self):
        def block(id, text, x, y, width=30):
            return TextBlock(id, text, ((x, y), (x + width, y), (x + width, y + 20), (x, y + 20)))
        boxes = [block("a", "DO", 0, 0), block("b", "NOT", 38, 1),
                 block("c", "DELETE", 76, 0, 65), block("d", "123", 150, 0),
                 block("e", "Next row", 0, 40), block("f", "Other column", 250, 40)]
        self.assertEqual(selected_ocr_text(boxes, {b.id for b in boxes}),
                         "DO NOT DELETE 123\nNext row\nOther column")
        self.assertEqual(selected_ocr_text(boxes, {"a", "d"}), "DO\n123")


class ResourceTests(unittest.TestCase):
    def test_resource_integrity_missing_corrupt_and_manifest_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = []
            for direction, lang in (("en_zh", "en"), ("zh_en", "zh-hans")):
                for name in ("metadata.json", "model/model.bin", f"minisbd/{lang}.onnx"):
                    relative = f"packages/translate-{direction}-1_9/{name}"
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"fixture")
                    files.append({"path": relative, "bytes": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()})
            manifest = {"schema": 1, "model_version": "1.9", "files": files}
            path = root / "resource-manifest.json"
            path.write_text(json.dumps(manifest))
            verify_resources(root)
            (root / files[0]["path"]).write_bytes(b"changed")
            with self.assertRaisesRegex(TranslationError, "不会自动下载"):
                verify_resources(root)
            files[0]["path"] = "../outside"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(TranslationError):
                verify_resources(root)


STUB = '''import json, sys, time
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    r = json.loads(line)
    if r["text"] == "slow": time.sleep(3)
    print(json.dumps({"id": r["id"], "result": "translated"}), flush=True)
'''


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.adapter = ArgosTranslator(timeout=2)
        self.addCleanup(self.adapter.close)
        def stub(_command, environment):
            return start_process([sys.executable, "-u", "-c", STUB], environment)
        self.patch = patch("screen_translator.services.argos_translator.start_process", side_effect=stub)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_serial_process_reuse_close_and_restart(self):
        self.assertIsNone(self.adapter.pid)
        self.assertEqual(self.adapter.translate("Hello", "zh"), "translated")
        pid = self.adapter.pid
        self.adapter.translate("Again", "zh")
        self.assertEqual(self.adapter.pid, pid)
        self.adapter.close()
        self.adapter.translate("Restart", "zh")
        self.assertNotEqual(self.adapter.pid, pid)

    def test_queued_ticket_is_cancelled_before_launch(self):
        ticket = self.adapter.ticket()
        self.adapter.close()
        with self.assertRaisesRegex(TranslationError, "取消"):
            self.adapter.translate("Hello", "zh", ticket=ticket)
        self.assertIsNone(self.adapter.pid)

    def test_crashed_launcher_is_reaped_before_restarting(self):
        self.adapter.translate("Hello", "zh")
        old = self.adapter._process
        old.kill()
        old.wait(timeout=3)
        self.assertEqual(self.adapter.translate("Again", "zh"), "translated")
        self.assertNotEqual(self.adapter.pid, old.pid)

    def test_cancel_rejects_concurrent_inference_and_allows_retry(self):
        errors = []
        def delayed():
            try:
                self.adapter.translate("slow", "zh")
            except TranslationError as error:
                errors.append(str(error))
        thread = threading.Thread(target=delayed)
        thread.start()
        deadline = time.monotonic() + 2
        while self.adapter.pid is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(self.adapter.pid)
        with self.assertRaisesRegex(TranslationError, "收尾"):
            self.adapter.translate("Again", "zh")
        self.adapter.close()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(errors)
        self.assertEqual(self.adapter.translate("Again", "zh"), "translated")

    def test_start_failure_and_timeout_are_recoverable(self):
        with patch("screen_translator.services.argos_translator.start_process", side_effect=OSError("PRIVATE")):
            with self.assertRaisesRegex(TranslationError, "无法启动"):
                self.adapter.translate("Hello", "zh")
        self.adapter.timeout = 0.2
        with self.assertRaisesRegex(TranslationError, "超时"):
            self.adapter.translate("slow", "zh")
        self.assertIsNone(self.adapter.pid)
        self.adapter.timeout = 2
        self.assertEqual(self.adapter.translate("Again", "zh"), "translated")
