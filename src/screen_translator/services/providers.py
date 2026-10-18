from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ProviderField:
    key: str
    label: str
    secret: bool = True
    required: bool = True
    default: str = ""
    choices: tuple[str, ...] = ()
    hint: str = ""
    pattern: str = ""


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    fields: tuple[ProviderField, ...]
    guide_url: str
    console_url: str
    quota_note: str
    status: str = "待实测"

    def validate(self, values: dict[str, str]) -> dict[str, str]:
        from screen_translator.services.translator import TranslationError

        cleaned = {}
        for field in self.fields:
            value = values.get(field.key, field.default).strip()
            if field.required and not value:
                raise TranslationError(f"请填写{field.label}，获取方法见官方申请说明。")
            if field.choices and value not in field.choices:
                raise TranslationError(f"请选择有效的{field.label}。")
            if "\n" in value or "\r" in value:
                raise TranslationError(f"{field.label}不能包含换行。")
            if field.pattern and not re.fullmatch(field.pattern, value):
                raise TranslationError(f"{field.label}格式不正确，请按字段说明核对。")
            cleaned[field.key] = value
        return cleaned


PROVIDERS = {
    "baidu": Provider(
        "baidu", "百度翻译", (
            ProviderField("app_id", "APP ID"),
            ProviderField("secret_key", "密钥"),
            ProviderField("edition", "服务版本", False, default="standard",
                          choices=("standard", "advanced"),
                          hint="standard 标准版：1000 字符；advanced 高级/尊享版：6000 UTF-8 字节。"),
        ), "https://fanyi-api.baidu.com/doc/13", "https://fanyi-api.baidu.com/manage/developer",
        "周期性免费：标准版每月 5 万字符；认证高级版额度以账户为准。超额行为请查服务版本与账单。",
    ),
    "aliyun": Provider(
        "aliyun", "阿里云机器翻译", (
            ProviderField("access_key_id", "AccessKey ID"),
            ProviderField("access_key_secret", "AccessKey Secret"),
            ProviderField("region", "地域", False, default="cn-hangzhou",
                          choices=("cn-hangzhou", "cn-shanghai", "ap-southeast-1"),
                          hint="需在对应账户开通机器翻译通用版，并授权 alimt:TranslateGeneral。"),
        ), "https://help.aliyun.com/zh/machine-translation/getting-started/",
        "https://mt.console.aliyun.com/",
        "周期性免费：通用版每月 100 万字符，子账号共享主账号额度。额度用完立即进入后付费。",
    ),
    "tencent_tokenhub": Provider(
        "tencent_tokenhub", "腾讯 TokenHub", (
            ProviderField("api_key", "API Key", hint="在 TokenHub 广州地域创建。", pattern=r"[!-~]+"),
            ProviderField("model", "翻译模型", False, default="hy-mt2-lite",
                          choices=("hy-mt2-lite", "hy-mt2-plus", "hy-mt2-pro"),
                          hint="选择账户已开通的模型。客户端保守限制 3500 UTF-8 字节；服务还按 token 限制。"),
        ), "https://cloud.tencent.com/document/product/1823/132252",
        "https://console.cloud.tencent.com/tokenhub",
        "按模型输入/输出 token 计费；免费权益、到期日与余额以账户为准。当前仅支持广州入口。",
    ),
    "huawei": Provider(
        "huawei", "华为 NLP 文本翻译", (
            ProviderField("access_key_id", "Access Key ID（AK）"),
            ProviderField("secret_access_key", "Secret Access Key（SK）"),
            ProviderField("project_id", "北京四项目 ID", hint="使用 cn-north-4 的 32 位十六进制项目 ID，并在北京四开通 NLP。", pattern=r"[0-9a-fA-F]{32}"),
        ), "https://support.huaweicloud.com/api-nlp/nlp_03_0024.html",
        "https://console.huaweicloud.com/nlp/",
        "文本翻译按字符阶梯计费，不支持套餐包抵扣；权益和账单以账户为准。最多 2000 字符。",
    ),
    "niutrans": Provider(
        "niutrans", "小牛通用文本 Flash", (
            ProviderField("app_id", "API 应用 appId"),
            ProviderField("api_key", "API 应用 apikey", hint="开通通用文本 Flash 权限；Pro 与旧 v1 接口不适用。"),
        ), "https://niutrans.com/documents/contents/transapi_text_v2",
        "https://niutrans.com/cloud/api/list",
        "Flash 的免费字符、有效期与余额以 API 应用为准；客户端最多 5000 字符，不自动拆分或重试。",
    ),
}

def get_provider(provider_id: str) -> Provider:
    from screen_translator.services.translator import TranslationError

    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise TranslationError("当前平台不受支持，请在设置中重新选择平台。") from None
