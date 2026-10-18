import json
import unittest
from unittest.mock import patch

import httpx

from screen_translator.services.provider_translators import (
    HuaweiTranslator, NiutransTranslator, TokenHubTranslator, create_translator,
    huawei_signed_headers, niutrans_signature,
)
from screen_translator.services.providers import PROVIDERS
from screen_translator.services.translator import TranslationError


def tokenhub_response(content="你好", finish="stop", **message):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": content, **message,
    }}]}


class ProviderProtocolTests(unittest.TestCase):
    def test_only_five_online_factories_and_unconfigured_requests_are_rejected(self):
        self.assertEqual(set(PROVIDERS), {"baidu", "aliyun", "tencent_tokenhub", "huawei", "niutrans"})
        with patch("httpx.post") as post:
            with self.assertRaises(TranslationError):
                create_translator("unsupported-provider", {})
            with self.assertRaises(TranslationError):
                create_translator("tencent_tokenhub", {})
            post.assert_not_called()

    def test_tokenhub_dedicated_endpoint_and_language_snapshot(self):
        for source in ("auto", "English"):
            with patch("httpx.post", return_value=httpx.Response(200, json=tokenhub_response())) as post:
                self.assertEqual(TokenHubTranslator("test-key", "hy-mt2-plus").translate("hello + v1.2.3", "中文", source), "你好")
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.args[0], TokenHubTranslator.ENDPOINT)
            args = post.call_args.kwargs
            self.assertFalse(args["follow_redirects"])
            self.assertEqual(args["headers"]["Authorization"], "Bearer test-key")
            body = args["json"]
            self.assertEqual(body["model"], "hy-mt2-plus")
            self.assertEqual(body["text"], "hello + v1.2.3")
            self.assertEqual(body["target"], "zh")
            self.assertFalse(body["stream"])
            self.assertEqual(body.get("source"), None if source == "auto" else "en")

    def test_tokenhub_rejects_truncation_explanations_and_reasoning(self):
        cases = [tokenhub_response(finish="length"), tokenhub_response(finish="sensitive"),
                 tokenhub_response("译文：你好"), tokenhub_response("Translation: Hello"),
                 tokenhub_response("```text\n你好\n```"), tokenhub_response("<think>PRIVATE</think>你好"),
                 tokenhub_response(reasoning_content="PRIVATE"), tokenhub_response(refusal="PRIVATE"),
                 tokenhub_response(""), tokenhub_response(role="user"), {"choices": [None]},
                 {"choices": tokenhub_response()["choices"] * 2}]
        for payload in cases:
            with self.subTest(payload=payload), patch("httpx.post", return_value=httpx.Response(200, json=payload)) as post:
                with self.assertRaises(TranslationError) as error:
                    TokenHubTranslator("key").translate("hello", "中文")
                self.assertNotIn("PRIVATE", str(error.exception))
                self.assertEqual(post.call_count, 1)
        with patch("httpx.post", return_value=httpx.Response(200, json=tokenhub_response("错误：请重试。"))):
            self.assertEqual(TokenHubTranslator("key").translate("Error: Please try again.", "中文"), "错误：请重试。")

    def test_huawei_signature_matches_independent_official_sdk_vector(self):
        # Vector generated with Huawei's public Signer (2026-10-07), not this helper.
        # Reference source SHA256: 4fb6f24a221714f3b751a1834d28cb6a1173c76511b7fa53a4f7d25ef20b301e.
        body = '{"text":"你好 + &","from":"zh","to":"en","scene":"common"}'.encode()
        headers = huawei_signed_headers(HuaweiTranslator.HOST,
                                        "/v1/" + "a" * 32 + "/machine-translation/text-translation",
                                        body, "test-ak", "test-sk", "20261007T010203Z")
        self.assertEqual(headers["Authorization"],
                         "SDK-HMAC-SHA256 Access=test-ak, SignedHeaders=content-type;host;x-sdk-date, "
                         "Signature=c3f21c918d56ba04836a27cce99d7b5a8a5282d9fa860c05ab547a3391a33902")

    def test_huawei_auto_source_is_local_and_mixed_input_can_be_corrected(self):
        adapter = HuaweiTranslator("ak", "sk", "a" * 32)
        for text, source, expected in (("Hello world", "auto", "en"), ("欢迎使用翻译", "auto", "zh"),
                                       ("保存 API Key", "中文", "zh")):
            with patch("httpx.post", return_value=httpx.Response(200, json={"translated_text": "result"})) as post:
                self.assertEqual(adapter.translate(text, "English", source), "result")
            self.assertEqual(post.call_count, 1)
            self.assertEqual(json.loads(post.call_args.kwargs["content"]),
                             {"text": text, "from": expected, "to": "en", "scene": "common"})
            self.assertTrue(post.call_args.kwargs["headers"]["Authorization"].startswith("SDK-HMAC-SHA256 Access=ak"))
        with patch("httpx.post") as post:
            with self.assertRaisesRegex(TranslationError, "手动"):
                adapter.translate("保存 API Key", "中文")
            with self.assertRaisesRegex(TranslationError, "项目 ID"):
                HuaweiTranslator("ak", "sk", "../private").translate("Hello", "中文")
            post.assert_not_called()

    def test_niutrans_v2_signature_preserves_raw_text_and_milliseconds(self):
        text = "你好 + &\ntimestamp=not a parameter"
        params = {"appId": "test-app", "from": "zh", "to": "en", "srcText": text, "timestamp": "1791334923000"}
        self.assertEqual(niutrans_signature({**params, "authStr": "ignored", "empty": ""}, "test-key"),
                         "77edb44bae053bfc0a7a833f2817bd45")
        with patch("httpx.post", return_value=httpx.Response(200, json={"tgtText": "Hello"})) as post, patch(
            "screen_translator.services.provider_translators.time.time", return_value=1791334923
        ):
            self.assertEqual(NiutransTranslator("test-app", "test-key").translate(text, "English", "中文"), "Hello")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], "https://api.niutrans.com/v2/text/translate")
        self.assertEqual(post.call_args.kwargs["json"], {**params, "authStr": "77edb44bae053bfc0a7a833f2817bd45"})
        self.assertNotIn("test-key", json.dumps(post.call_args.kwargs))
        for field in ("errorCode", "error_code"):
            with patch("httpx.post", return_value=httpx.Response(200, json={field: "20001", "errorMsg": "PRIVATE"})):
                with self.assertRaisesRegex(TranslationError, "鉴权") as error:
                    NiutransTranslator("app", "key").translate("Hello", "中文")
                self.assertNotIn("PRIVATE", str(error.exception))
