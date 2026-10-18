import hashlib
import json
import unittest
from urllib.parse import parse_qs
from unittest.mock import patch

import httpx

from screen_translator.services.provider_translators import (
    AliyunTranslator, BaiduTranslator, TokenHubTranslator, HuaweiTranslator, NiutransTranslator,
    aliyun_signed_headers, create_translator,
)
from screen_translator.services.translator import TranslationError


class ProviderTranslatorTests(unittest.TestCase):
    def adapters(self):
        return [BaiduTranslator("app", "secret"), AliyunTranslator("id", "secret"), TokenHubTranslator("secret"), HuaweiTranslator("id", "key", "a" * 32), NiutransTranslator("app", "key")]

    def test_baidu_signature_uses_raw_utf8_and_keeps_response_lines(self):
        response = httpx.Response(200, json={"trans_result": [{"dst": "你好"}, {"dst": "世界"}]})
        with patch("httpx.post", return_value=response) as post, patch("secrets.token_hex", return_value="123"):
            self.assertEqual(BaiduTranslator("appid", "key").translate("hello + 中文", "中文"), "你好\n世界")
        data = post.call_args.kwargs["data"]
        self.assertEqual(data["sign"], hashlib.md5("appidhello + 中文123key".encode()).hexdigest())
        self.assertEqual((data["from"], data["to"]), ("auto", "zh"))
        self.assertNotIn("?", post.call_args.args[0])

    def test_aliyun_signing_matches_official_acs3_example(self):
        # https://www.alibabacloud.com/help/zh/sdk/product-overview/v3-request-structure-and-signature
        headers = aliyun_signed_headers(
            "ecs.cn-shanghai.aliyuncs.com", "RunInstances", "2014-05-26", b"",
            "YourAccessKeyId", "YourAccessKeySecret", "2023-10-26T10:22:32Z",
            "3156853299f313e23d1673dc12e1703d",
            "ImageId=win2019_1809_x64_dtc_zh-cn_40G_alibase_20230811.vhd&RegionId=cn-shanghai",
        )
        self.assertTrue(headers["Authorization"].endswith(
            "Signature=06563a9e1b43f5dfe96b81484da74bceab24a1d853912eee15083a6f0f3283c0"))

    def test_aliyun_sends_general_form_and_region_endpoint(self):
        response = httpx.Response(200, json={"Code": 200, "Data": {"Translated": "hello"}})
        with patch("httpx.post", return_value=response) as post:
            self.assertEqual(AliyunTranslator("id", "key", "cn-shanghai").translate("你好 +", "English"), "hello")
        self.assertEqual(post.call_args.args[0], "https://mt.aliyuncs.com/")
        body = post.call_args.kwargs["content"]
        self.assertEqual(parse_qs(body.decode()), {
            "FormatType": ["text"], "SourceLanguage": ["auto"], "TargetLanguage": ["en"],
            "SourceText": ["你好 +"], "Scene": ["general"],
        })
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["x-acs-action"], "TranslateGeneral")
        self.assertEqual(headers["x-acs-version"], "2018-10-12")
        self.assertEqual(headers["x-acs-content-sha256"], hashlib.sha256(body).hexdigest())

    def test_platform_specific_boundaries_do_not_silently_truncate(self):
        cases = [(BaiduTranslator("a", "k"), "中" * 1001),
                 (BaiduTranslator("a", "k", "advanced"), "中" * 2001),
                 (AliyunTranslator("a", "k"), "😀" * 5001),
                 (TokenHubTranslator("k"), "😀" * 876),
                 (HuaweiTranslator("a", "k", "a" * 32), "中" * 2001),
                 (NiutransTranslator("a", "k"), "中" * 5001)]
        for adapter, text in cases:
            with self.subTest(adapter=type(adapter).__name__), patch("httpx.post") as post:
                with self.assertRaisesRegex(TranslationError, "最多"):
                    adapter.translate(text, "中文")
                post.assert_not_called()
        for adapter, text, payload in [
            (BaiduTranslator("a", "k"), "中" * 1000, {"trans_result": [{"dst": "ok"}]}),
            (BaiduTranslator("a", "k", "advanced"), "中" * 2000, {"trans_result": [{"dst": "ok"}]}),
            (AliyunTranslator("a", "k"), "😀" * 5000, {"Code": 200, "Data": {"Translated": "ok"}}),
            (TokenHubTranslator("k"), "a" * 3500, {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}),
            (HuaweiTranslator("a", "k", "a" * 32), "中" * 2000, {"translated_text": "ok"}),
            (NiutransTranslator("a", "k"), "中" * 5000, {"tgtText": "ok"}),
        ]:
            with patch("httpx.post", return_value=httpx.Response(200, json=payload)) as post:
                self.assertEqual(adapter.translate(text, "中文"), "ok")
                self.assertEqual(post.call_count, 1)

    def test_empty_missing_credentials_and_unsupported_language_do_not_send_requests(self):
        with patch("httpx.post") as post:
            for adapter in self.adapters():
                for text, target in ((" ", "中文"), ("hi", "unsupported"), ("hi", "auto")):
                    with self.assertRaises(TranslationError):
                        adapter.translate(text, target)
            for provider in ("baidu", "aliyun", "tencent_tokenhub", "huawei", "niutrans"):
                with self.assertRaises(TranslationError):
                    create_translator(provider, {})
            post.assert_not_called()

    def test_multilingual_requests_use_each_platforms_codes(self):
        cases = [
            (BaiduTranslator("app", "key"), "ja", "fr", {"trans_result": [{"dst": "ok"}]}, "fra", "jp"),
            (BaiduTranslator("app", "key"), "ms", "zh-Hant", {"trans_result": [{"dst": "ok"}]}, "cht", "may"),
            (AliyunTranslator("id", "key"), "ja", "ko", {"Code": 200, "Data": {"Translated": "ok"}}, "ko", "ja"),
            (TokenHubTranslator("key"), "ja", "zh-Hant", {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}, "zh-TR", "ja"),
            (NiutransTranslator("app", "key"), "bo", "kk", {"tgtText": "ok"}, "ka", "ti"),
        ]
        for adapter, source, target, payload, expected_target, expected_source in cases:
            with self.subTest(adapter=type(adapter).__name__), patch("httpx.post", return_value=httpx.Response(200, json=payload)) as post:
                self.assertEqual(adapter.translate("sample", target, source), "ok")
                request = post.call_args.kwargs
                if isinstance(adapter, AliyunTranslator):
                    body = parse_qs(request["content"].decode())
                    actual = (body["TargetLanguage"][0], body["SourceLanguage"][0])
                elif isinstance(adapter, TokenHubTranslator):
                    actual = (request["json"]["target"], request["json"]["source"])
                else:
                    body = request.get("data", request.get("json"))
                    actual = (body["to"], body["from"])
                self.assertEqual(actual, (expected_target, expected_source))
        with patch("httpx.post") as post:
            for adapter, target, source in ((HuaweiTranslator("id", "key", "a" * 32), "ja", "auto"),
                                            (AliyunTranslator("id", "key"), "zh-Hant", "zh"),
                                            (BaiduTranslator("app", "key"), "ja", "ja")):
                with self.assertRaises(TranslationError):
                    adapter.translate("sample", target, source)
            post.assert_not_called()

    def test_common_transport_errors_are_sanitized_and_not_retried(self):
        for adapter in self.adapters():
            for status in (401, 403, 429, 500, 302):
                with self.subTest(adapter=type(adapter).__name__, status=status), patch(
                    "httpx.post", return_value=httpx.Response(status, json={"message": "PRIVATE key text"})
                ) as post:
                    with self.assertRaises(TranslationError) as raised:
                        adapter.translate("hello", "中文")
                    self.assertNotIn("PRIVATE", str(raised.exception))
                    self.assertEqual(post.call_count, 1)
            for error in (httpx.ConnectTimeout("PRIVATE"), httpx.ConnectError("PRIVATE")):
                with patch("httpx.post", side_effect=error) as post:
                    with self.assertRaises(TranslationError) as raised:
                        adapter.translate("hello", "中文")
                    self.assertNotIn("PRIVATE", str(raised.exception))
                    self.assertEqual(post.call_count, 1)

    def test_service_auth_activation_quota_and_language_errors(self):
        cases = [
            (BaiduTranslator("a", "k"), {"error_code": "54001"}, "签名"),
            (BaiduTranslator("a", "k"), {"error_code": "58002"}, "开通"),
            (BaiduTranslator("a", "k"), {"error_code": "54004"}, "额度"),
            (BaiduTranslator("a", "k"), {"error_code": "54003"}, "频率"),
            (AliyunTranslator("a", "k"), {"Code": "SignatureDoesNotMatch"}, "鉴权"),
            (AliyunTranslator("a", "k"), {"Code": 10013}, "欠费"),
            (AliyunTranslator("a", "k"), {"Code": 10006}, "识别"),
            (TokenHubTranslator("k"), {"error": {"code": "invalid_api_key"}}, "API Key"),
            (HuaweiTranslator("a", "k", "a" * 32), {"error_code": "NLP.0101"}, "鉴权"),
            (HuaweiTranslator("a", "k", "a" * 32), {"error_code": "ModelArts.4204"}, "开通"),
            (NiutransTranslator("a", "k"), {"errorCode": "20001"}, "鉴权"),
        ]
        for adapter, payload, hint in cases:
            payload["message"] = "PRIVATE"
            with self.subTest(payload=payload), patch("httpx.post", return_value=httpx.Response(200, json=payload)):
                with self.assertRaisesRegex(TranslationError, hint) as raised:
                    adapter.translate("hello", "中文")
                self.assertNotIn("PRIVATE", str(raised.exception))

    def test_malformed_and_empty_response_are_recoverable(self):
        for adapter in self.adapters():
            for payload in (None, {}, [], {"trans_result": [{}]}, [{"translations": []}]):
                with self.subTest(adapter=type(adapter).__name__, payload=payload), patch(
                    "httpx.post", return_value=httpx.Response(200, json=payload)
                ):
                    with self.assertRaises(TranslationError):
                        adapter.translate("hello", "中文")
            with patch("httpx.post", return_value=httpx.Response(200, text="<html>PRIVATE</html>")):
                with self.assertRaises(TranslationError):
                    adapter.translate("hello", "中文")
