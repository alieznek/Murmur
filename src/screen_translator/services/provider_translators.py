from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import quote, urlencode

import httpx

from screen_translator.services.providers import get_provider
from screen_translator.services.languages import provider_language_pair
from screen_translator.services.translator import TranslationError


class Translator(Protocol):
    def translate(self, text: str, target: str, source: str = "auto") -> str: ...


def validate_text(text: str, target: str, source: str, limit: int, unit: str = "字符",
                  *, provider_id: str) -> tuple[str, str]:
    if not text.strip():
        raise TranslationError("待翻译文本不能为空。")
    size = len(text.encode("utf-8")) if unit == "UTF-8 字节" else len(text)
    if size > limit:
        raise TranslationError(f"单次翻译最多 {limit} {unit}，请缩短文本后重试。")
    return provider_language_pair(provider_id, target, source)


def post_json(name: str, endpoint: str, timeout: float, **kwargs):
    try:
        response = httpx.post(endpoint, timeout=timeout, follow_redirects=False, **kwargs)
    except httpx.TimeoutException:
        raise TranslationError(f"{name}请求超时，请检查网络后主动重试。") from None
    except httpx.HTTPError:
        raise TranslationError(f"无法连接{name}，请检查网络后主动重试。") from None
    # Never display response bodies or HTTP exception strings: they may echo secrets/text.
    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None
    return response.status_code, payload


def check_http(status: int, name: str) -> None:
    if status in (401, 403):
        raise TranslationError(f"{name}鉴权或权限检查失败，请检查密钥、地域与服务开通状态。")
    if status == 429:
        raise TranslationError(f"{name}限流或额度耗尽，请检查官方额度并稍后主动重试。")
    if status == 402:
        raise TranslationError(f"{name}余额或额度不足，请检查官方账单后主动重试。")
    if status >= 300:
        raise TranslationError(f"{name}服务返回 HTTP {status}，请检查官方控制台后主动重试。")


def result_text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TranslationError(f"{name}响应格式不正确或返回空结果，请主动重试。")
    return value.strip()


class BaiduTranslator:
    ENDPOINT = "https://fanyi-api.baidu.com/api/trans/vip/translate"

    def __init__(self, app_id: str, secret_key: str, edition: str = "standard", timeout: float = 30):
        self.app_id, self.secret_key, self.edition, self.timeout = app_id, secret_key, edition, timeout

    def translate(self, text: str, target: str, source: str = "auto") -> str:
        get_provider("baidu").validate({"app_id": self.app_id, "secret_key": self.secret_key, "edition": self.edition})
        limit, unit = (1000, "字符") if self.edition == "standard" else (6000, "UTF-8 字节")
        target_code, source_code = validate_text(text, target, source, limit, unit, provider_id="baidu")
        salt = secrets.token_hex(16)
        sign = hashlib.md5((self.app_id + text + salt + self.secret_key).encode("utf-8")).hexdigest()
        status, payload = post_json("百度翻译", self.ENDPOINT, self.timeout, data={
            "q": text, "from": source_code, "to": target_code, "appid": self.app_id, "salt": salt, "sign": sign,
        })
        if isinstance(payload, dict) and "error_code" in payload:
            hints = {
                "52001": "请求超时，请稍后主动重试。",
                "52003": "APP ID 未获授权，请开通通用文本翻译服务。",
                "54001": "签名校验失败，请检查 APP ID 与密钥是否属于同一应用。",
                "54003": "调用频率过高，请稍后主动重试。",
                "54004": "账户额度耗尽或余额不足，请检查官方额度和账单。",
                "54005": "短文本请求频率过高，请稍后主动重试。",
                "58000": "客户端 IP 不在允许范围，请检查官方安全设置。",
                "58001": "语种不支持，请修改目标语言或原文。",
                "58002": "服务未开通或已关闭，请在官方控制台开通服务。",
                "90107": "账号认证未通过或已失效，请检查官方认证状态。",
            }
            raise TranslationError("百度翻译：" + hints.get(str(payload["error_code"]), "调用失败，请检查官方服务状态和配置。"))
        check_http(status, "百度翻译")
        rows = payload.get("trans_result") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            raise TranslationError("百度翻译响应格式不正确，请主动重试。")
        return "\n".join(result_text(row.get("dst") if isinstance(row, dict) else None, "百度翻译") for row in rows)


def aliyun_signed_headers(host: str, action: str, version: str, body: bytes,
                          access_key_id: str, access_key_secret: str, date: str, nonce: str,
                          query: str = "") -> dict[str, str]:
    hashed_body = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-acs-action": action, "x-acs-version": version,
               "x-acs-date": date, "x-acs-signature-nonce": nonce, "x-acs-content-sha256": hashed_body}
    names = sorted(headers)
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in names)
    signed_headers = ";".join(names)
    canonical = f"POST\n/\n{query}\n{canonical_headers}\n{signed_headers}\n{hashed_body}"
    string_to_sign = "ACS3-HMAC-SHA256\n" + hashlib.sha256(canonical.encode()).hexdigest()
    signature = hmac.new(access_key_secret.encode(), string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = f"ACS3-HMAC-SHA256 Credential={access_key_id},SignedHeaders={signed_headers},Signature={signature}"
    return headers


class AliyunTranslator:
    HOSTS = {"cn-hangzhou": "mt.cn-hangzhou.aliyuncs.com", "cn-shanghai": "mt.aliyuncs.com",
             "ap-southeast-1": "mt.ap-southeast-1.aliyuncs.com"}

    def __init__(self, access_key_id: str, access_key_secret: str, region: str = "cn-hangzhou", timeout: float = 30):
        self.access_key_id, self.access_key_secret = access_key_id, access_key_secret
        self.region, self.timeout = region, timeout

    def translate(self, text: str, target: str, source: str = "auto") -> str:
        get_provider("aliyun").validate({"access_key_id": self.access_key_id, "access_key_secret": self.access_key_secret, "region": self.region})
        target_code, source_code = validate_text(text, target, source, 5000, provider_id="aliyun")
        body = urlencode({"FormatType": "text", "SourceLanguage": source_code,
                          "TargetLanguage": target_code, "SourceText": text, "Scene": "general"}).encode()
        host = self.HOSTS[self.region]
        headers = aliyun_signed_headers(host, "TranslateGeneral", "2018-10-12", body,
                                        self.access_key_id, self.access_key_secret,
                                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), uuid.uuid4().hex)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        status, payload = post_json("阿里云机器翻译", f"https://{host}/", self.timeout, content=body, headers=headers)
        code = str(payload.get("Code", "")) if isinstance(payload, dict) else ""
        if code and code != "200":
            if code in ("10009", "Forbidden", "Forbidden.RAM", "InvalidAccessKeyId.NotFound", "SignatureDoesNotMatch"):
                hint = "鉴权或权限失败，请检查 AccessKey 及 RAM 的机器翻译权限。"
            elif code in ("10010", "10013", "ServiceNotOpened"):
                hint = "服务未开通或账号欠费，请开通机器翻译通用版并检查账单。"
            elif "Throttl" in code:
                hint = "调用限流，请稍后主动重试。"
            elif code in ("10005", "10006"):
                hint = "语种不支持或自动识别失败，请检查原文与目标语言。"
            else:
                hint = "调用失败，请检查密钥、服务开通状态、额度和账单后主动重试。"
            raise TranslationError("阿里云机器翻译：" + hint)
        check_http(status, "阿里云机器翻译")
        data = payload.get("Data") if isinstance(payload, dict) else None
        return result_text(data.get("Translated") if isinstance(data, dict) else None, "阿里云机器翻译")


class TokenHubTranslator:
    ENDPOINT = "https://tokenhub.tencentmaas.com/v1/api/translations"

    def __init__(self, api_key: str, model: str = "hy-mt2-lite", timeout: float = 30):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def translate(self, text: str, target: str, source: str = "auto") -> str:
        get_provider("tencent_tokenhub").validate({"api_key": self.api_key, "model": self.model})
        target_code, source_code = validate_text(text, target, source, 3500, "UTF-8 字节", provider_id="tencent_tokenhub")
        body = {"model": self.model, "text": text, "target": target_code, "stream": False}
        if source_code != "auto":
            body["source"] = source_code
        status, payload = post_json("腾讯 TokenHub", self.ENDPOINT, self.timeout, json=body,
                                    headers={"Authorization": "Bearer " + self.api_key})
        check_http(status, "腾讯 TokenHub")
        if isinstance(payload, dict) and payload.get("error"):
            raise TranslationError("腾讯 TokenHub 调用失败，请检查 API Key、广州地域、模型权限、额度与输入 token 限制。")
        try:
            choices = payload["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            if choice["finish_reason"] != "stop":
                raise TranslationError("腾讯 TokenHub 译文未完整结束或未通过审核，已停止回填；请缩短原文或检查控制台。")
            message = choice["message"]
            if message.get("role") != "assistant" or message.get("reasoning_content") or message.get("refusal"):
                raise ValueError
            value = result_text(message["content"], "腾讯 TokenHub")
        except (KeyError, TypeError, ValueError, AttributeError):
            raise TranslationError("腾讯 TokenHub 响应格式异常或包含额外推理，已停止回填；请检查翻译模型。") from None
        # Do not strip or guess a translation out of a model explanation.
        wrapper = r"^(?:(?:译文|翻译结果|以下是[^\n]{0,20}(?:译文|翻译(?:结果)?)|translation|translated text|here (?:is|are) (?:the |your )?translation)\s*[:：]|sure[,!]|of course[,!])"
        if (re.search(r"</?think\b", value, re.I) or
                ("```" in value and "```" not in text) or
                (re.search(wrapper, value, re.I) and not re.search(wrapper, text.strip(), re.I))):
            raise TranslationError("腾讯 TokenHub 返回了说明或格式包装，已停止回填；请检查所选翻译模型后主动重试。")
        return value


def huawei_signed_headers(host: str, path: str, body: bytes, access_key_id: str,
                          secret_access_key: str, date: str) -> dict[str, str]:
    """NLP POST signing per Huawei's SDK-HMAC-SHA256 canonical request."""
    headers = {"content-type": "application/json", "host": host, "x-sdk-date": date}
    names = sorted(headers)
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in names)
    signed = ";".join(names)
    canonical_uri = quote(path.rstrip("/"), safe="/~") + "/"
    canonical = f"POST\n{canonical_uri}\n\n{canonical_headers}\n{signed}\n{hashlib.sha256(body).hexdigest()}"
    to_sign = "SDK-HMAC-SHA256\n" + date + "\n" + hashlib.sha256(canonical.encode()).hexdigest()
    signature = hmac.new(secret_access_key.encode(), to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = f"SDK-HMAC-SHA256 Access={access_key_id}, SignedHeaders={signed}, Signature={signature}"
    return headers


class HuaweiTranslator:
    HOST = "nlp-ext.cn-north-4.myhuaweicloud.com"

    def __init__(self, access_key_id: str, secret_access_key: str, project_id: str, timeout: float = 30):
        self.access_key_id, self.secret_access_key, self.project_id = access_key_id, secret_access_key, project_id
        self.timeout = timeout

    def translate(self, text: str, target: str, source: str = "auto") -> str:
        get_provider("huawei").validate({"access_key_id": self.access_key_id,
                                         "secret_access_key": self.secret_access_key, "project_id": self.project_id})
        target_code, source_code = validate_text(text, target, source, 2000, provider_id="huawei")
        if source_code == "auto":
            from screen_translator.core.offline_text import validate_request
            source_code, _ = validate_request(text, target_code, "auto")
        path = f"/v1/{self.project_id}/machine-translation/text-translation"
        body = json.dumps({"text": text, "from": source_code, "to": target_code, "scene": "common"},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = huawei_signed_headers(self.HOST, path, body, self.access_key_id, self.secret_access_key,
                                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        status, payload = post_json("华为 NLP", "https://" + self.HOST + path, self.timeout, content=body, headers=headers)
        check_http(status, "华为 NLP")
        if isinstance(payload, dict) and payload.get("error_code"):
            code = str(payload["error_code"])
            hints = {"NLP.0101": "鉴权失败，请核对 AK/SK、权限与系统时间。",
                     "ModelArts.4204": "服务未开通，请在北京四开通 NLP 并核对项目 ID。"}
            raise TranslationError("华为 NLP：" + hints.get(code, "调用失败，请检查服务、语言、额度、地域和权限后主动重试。"))
        return result_text(payload.get("translated_text") if isinstance(payload, dict) else None, "华为 NLP")


def niutrans_signature(params: dict[str, str], api_key: str) -> str:
    values = {key: value for key, value in params.items() if value and key not in ("authStr", "apikey")}
    values["apikey"] = api_key
    raw = "&".join(f"{key}={values[key]}" for key in sorted(values))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class NiutransTranslator:
    ENDPOINT = "https://api.niutrans.com/v2/text/translate"

    def __init__(self, app_id: str, api_key: str, timeout: float = 30):
        self.app_id, self.api_key, self.timeout = app_id, api_key, timeout

    def translate(self, text: str, target: str, source: str = "auto") -> str:
        get_provider("niutrans").validate({"app_id": self.app_id, "api_key": self.api_key})
        target_code, source_code = validate_text(text, target, source, 5000, provider_id="niutrans")
        body = {"appId": self.app_id, "from": source_code, "to": target_code,
                "srcText": text, "timestamp": str(int(time.time() * 1000))}
        body["authStr"] = niutrans_signature(body, self.api_key)
        status, payload = post_json("小牛 Flash", self.ENDPOINT, self.timeout, json=body)
        check_http(status, "小牛 Flash")
        if isinstance(payload, dict) and ("errorCode" in payload or "error_code" in payload):
            code = str(payload.get("errorCode", payload.get("error_code")))
            hints = {"20001": "鉴权失败，请核对 appId、apikey 和系统时间。",
                     "13005": "源语言和目标语言相同，请修改语言。",
                     "20002": "请求参数不符合规范，请检查语言和 Flash 应用权限。",
                     "20003": "请求参数校验失败，请检查 Flash 应用配置。"}
            raise TranslationError("小牛 Flash：" + hints.get(code, "调用失败，请检查 Flash 权限、字符额度、余额、长度与频率后主动重试。"))
        return result_text(payload.get("tgtText") if isinstance(payload, dict) else None, "小牛 Flash")


def create_translator(provider_id: str, values: dict[str, str]) -> Translator:
    values = get_provider(provider_id).validate(values)
    factories = {"baidu": BaiduTranslator, "aliyun": AliyunTranslator,
                 "tencent_tokenhub": TokenHubTranslator, "huawei": HuaweiTranslator, "niutrans": NiutransTranslator}
    return factories[provider_id](**values)
