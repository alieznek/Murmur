import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from screen_translator.core.text_blocks import TextBlock
from screen_translator.diagnostics.runtime import run_self_check


class SelfCheckTests(unittest.TestCase):
    def test_self_check_uses_synthetic_input_and_restores_network_guard(self):
        connect = socket.socket.connect
        block = TextBlock("synthetic", "HELLO WORLD", ((0, 0), (1, 0), (1, 1), (0, 1)))
        with tempfile.TemporaryDirectory() as temporary, patch(
            "screen_translator.services.ocr.RapidOcrService.recognize", return_value=[block]
        ) as recognize, patch("screen_translator.diagnostics.offline.check_offline",
                              side_effect=lambda window, app, checkpoint, report: report.update(offline_passed=True)):
            report_path = Path(temporary) / "report.json"
            self.assertEqual(run_self_check(report_path), 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertTrue(report["online_protocols_mock"]["passed"])
            self.assertTrue(report["lifecycle"]["passed"])
            self.assertTrue(report["lifecycle"]["instance_activation"])
            self.assertTrue(report["lifecycle"]["capture_cancelled"])
            self.assertTrue(report["windows"]["passed"])
            self.assertFalse(report["windows"]["external_machine_verified"])
            self.assertTrue(report["windows"]["last_block_accessible"])
            self.assertEqual(len(report["online_protocols_mock"]["providers"]), 5)
            self.assertEqual(report["stage"], "complete")
            self.assertEqual(recognize.call_args.args[0].shape, (100, 540, 3))
            # Temporary local-channel QObjects must remain safe when the next
            # UI check pumps queued events and when another check follows it.
            self.assertEqual(run_self_check(report_path), 0)
            repeated = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(repeated["lifecycle"]["passed"] and repeated["windows"]["passed"])
        self.assertIs(socket.socket.connect, connect)

    def test_failed_check_preserves_diagnostic_stage_without_user_content(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "screen_translator.services.ocr.RapidOcrService.recognize", side_effect=RuntimeError("PRIVATE")
        ):
            report_path = Path(temporary) / "report.json"
            self.assertEqual(run_self_check(report_path), 1)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["passed"])
            self.assertEqual(report["stage"], "ocr")
            self.assertEqual(report["error_type"], "RuntimeError")
            self.assertNotIn("PRIVATE", report_path.read_text())
