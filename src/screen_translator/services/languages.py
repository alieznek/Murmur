"""Client language choices and API-specific codes (see docs/providers.md)."""
from dataclasses import dataclass

from screen_translator.services.translator import TranslationError


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    english: str


LANGUAGES = tuple(Language(*row) for row in (
    ("zh", "中文", "Chinese"), ("en", "英语", "English"),
    ("zh-Hant", "繁体中文", "Traditional Chinese"), ("yue", "粤语", "Cantonese"),
    ("ja", "日语", "Japanese"), ("ko", "韩语", "Korean"),
    ("fr", "法语", "French"), ("de", "德语", "German"),
    ("es", "西班牙语", "Spanish"), ("pt", "葡萄牙语", "Portuguese"),
    ("it", "意大利语", "Italian"), ("ru", "俄语", "Russian"),
    ("ar", "阿拉伯语", "Arabic"), ("th", "泰语", "Thai"),
    ("vi", "越南语", "Vietnamese"), ("id", "印尼语", "Indonesian"),
    ("ms", "马来语", "Malay"), ("tr", "土耳其语", "Turkish"),
    ("fil", "菲律宾语", "Filipino"), ("hi", "印地语", "Hindi"),
    ("pl", "波兰语", "Polish"), ("nl", "荷兰语", "Dutch"),
    ("cs", "捷克语", "Czech"), ("uk", "乌克兰语", "Ukrainian"),
    ("he", "希伯来语", "Hebrew"), ("fa", "波斯语", "Persian"),
    ("km", "高棉语", "Khmer"), ("my", "缅甸语", "Burmese"),
    ("gu", "古吉拉特语", "Gujarati"), ("ur", "乌尔都语", "Urdu"),
    ("te", "泰卢固语", "Telugu"), ("mr", "马拉地语", "Marathi"),
    ("bn", "孟加拉语", "Bengali"), ("ta", "泰米尔语", "Tamil"),
    ("bo", "藏语", "Tibetan"), ("kk", "哈萨克语", "Kazakh"),
    ("mn", "蒙古语", "Mongolian"), ("ug", "维吾尔语", "Uyghur"),
))

_ALIASES = {value: language.code for language in LANGUAGES
            for value in (language.code, language.name, language.english)}
_ALIASES.update({"简体中文": "zh", "中文(简体)": "zh", "zh-CN": "zh",
                 "zh-TW": "zh-Hant", "zh-tw": "zh-Hant", "英语": "en",
                 "自动识别": "auto", "auto": "auto"})

# Keep the local API's display aliases compatible with existing callers.
CHOICE_VALUES = {"zh": "中文", "en": "English", "auto": "自动识别"}

_CORE = {code: code for code in ("zh", "en")}
PROVIDER_CODES = {
    "offline": _CORE,
    "huawei": _CORE,  # Other languages and remote auto detection are retiring.
    "tencent_tokenhub": {language.code: language.code for language in LANGUAGES},
    "niutrans": {language.code: language.code for language in LANGUAGES},
    "baidu": {language.code: language.code for language in LANGUAGES
              if language.code not in ("bo", "kk", "mn", "ug")},
    "aliyun": {language.code: language.code for language in LANGUAGES
               if language.code in ("zh", "en", "ja", "ko", "fr", "es", "pt", "it",
                                    "ru", "ar", "tr", "id", "vi", "th", "pl", "de")},
}
PROVIDER_CODES["tencent_tokenhub"].update({"zh-Hant": "zh-TR"})
PROVIDER_CODES["niutrans"].update({"zh-Hant": "cht", "bo": "ti", "kk": "ka", "mn": "mo", "ug": "uy"})
PROVIDER_CODES["baidu"].update({"zh-Hant": "cht", "ja": "jp", "ko": "kor", "fr": "fra",
                              "es": "spa", "ar": "ara", "vi": "vie", "uk": "ukr",
                              "he": "heb", "fa": "per", "km": "hkm", "my": "bur",
                              "gu": "guj", "ur": "urd", "te": "tel", "mr": "mar",
                              "bn": "ben", "ta": "tam", "ms": "may"})


def language_code(value: str) -> str:
    try:
        return _ALIASES[value]
    except KeyError:
        raise TranslationError("不支持所选语种，请从当前平台的语言列表中选择。") from None


def language_choices(provider_id: str, *, source: bool = False) -> tuple[Language, ...]:
    codes = PROVIDER_CODES.get(provider_id, _CORE)
    choices = tuple(language for language in LANGUAGES if language.code in codes)
    return (Language("auto", "自动识别", "Auto detect"), *choices) if source else choices


def provider_language_pair(provider_id: str, target: str, source: str) -> tuple[str, str]:
    target, source = language_code(target), language_code(source)
    codes = PROVIDER_CODES[provider_id]
    if target == "auto":
        raise TranslationError("自动识别只可用于源语言，请选择明确的目标语言。")
    if target not in codes or (source != "auto" and source not in codes):
        raise TranslationError("当前平台不支持所选语种，请切换平台或语言。")
    if source == target:
        raise TranslationError("源语言和目标语言相同，请修改语言。")
    return codes[target], "auto" if source == "auto" else codes[source]
