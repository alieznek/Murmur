"""Conservative language detection and literal protection for basic translation."""
from __future__ import annotations

import re
from collections import Counter

from screen_translator.services.translator import TranslationError

MAX_TEXT_LENGTH = 2000
LITERALS = re.compile(r"(`[^`\n]+`|https?://[^\s]+|[A-Za-z]:[\\/][^\s]+|(?<![A-Za-z0-9_])v?\d+(?:\.\d+){2,}(?![A-Za-z0-9_]))")
NUMBERS = re.compile(r"\d+(?:[.,]\d+)*")
EN_NUMERALS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
ZH_NUMERALS = "零 一 二 三 四 五 六 七 八 九 十 十一 十二 十三 十四 十五 十六 十七 十八 十九 二十".split()
WORD_VALUES = {word: str(value) for words in (EN_NUMERALS, ZH_NUMERALS)
               for value, word in enumerate(words)}
WORD_VALUES.update({"两": "2", "〇": "0"})
EN_NUMBER_PHRASE = re.compile(r"\b(?:" + "|".join(EN_NUMERALS) + r")(?:[ -]+(?:" +
                              "|".join(EN_NUMERALS + ["hundred", "thousand", "million", "billion"]) + r"))*\b", re.I)
ZH_NUMBER_WORD = re.compile(r"(?<![零〇一二两三四五六七八九十百千万亿])[零〇一二两三四五六七八九十]+(?=[个条秒分天小时岁次字符。，,.!?！？\s]|$)")


def numeric_values_agree(source: str, result: str) -> bool:
    original, translated = Counter(NUMBERS.findall(source)), Counter(NUMBERS.findall(result))
    if original == translated:
        return True
    def words(text):
        values = [m.group().lower() for m in EN_NUMBER_PHRASE.finditer(text)]
        values += [m.group() for m in ZH_NUMBER_WORD.finditer(text)]
        return Counter(WORD_VALUES[word] for word in values if word in WORD_VALUES)
    source_words, result_words = words(source), words(result)
    # Only compare quantities represented by digits on at least one side.
    # Extra lexical words such as "try once again" do not invent a digit token.
    return all(original[value] + source_words[value] == translated[value] + result_words[value]
               for value in original.keys() | translated.keys())


def language_code(value: str) -> str:
    return {"中文": "zh", "English": "en", "自动识别": "auto"}.get(value, value)


def validate_request(text: str, target: str, source: str = "auto") -> tuple[str, str]:
    if not isinstance(text, str) or not text.strip():
        raise TranslationError("待翻译文本不能为空。")
    if len(text) > MAX_TEXT_LENGTH:
        raise TranslationError("本地基础翻译单次最多 2000 个字符，请缩短原文；不会截断。")
    source, target = language_code(source), language_code(target)
    if target not in ("en", "zh") or source not in ("auto", "en", "zh"):
        raise TranslationError("本地基础翻译仅支持中文与英文，请手动选择语言。")
    if source == "auto":
        prose = LITERALS.sub("", text)
        han = len(re.findall(r"[\u3400-\u9fff]", prose))
        latin = len(re.findall(r"[A-Za-z]", prose))
        ratio = han / max(1, han + latin)
        if (not han and latin < 2) or (han and latin and 0.2 <= ratio <= 0.8):
            raise TranslationError("原文过短、混合语言或方向不确定，请手动选择源语言。")
        source = "zh" if ratio >= 0.8 else "en"
    return source, target


def translate_preserving_literals(text: str, translate) -> str:
    # Pass only prose to the model. Never guess a replacement for altered digits.
    if len(LITERALS.findall(text)) > 64:
        raise TranslationError("原文包含过多代码或路径，请缩短后再进行基础翻译。")
    output = []
    for line in text.split("\n"):
        parts = LITERALS.split(line)
        pieces = []
        for index, part in enumerate(parts):
            if index % 2 or not re.search(r"[A-Za-z\u3400-\u9fff]", part):
                pieces.append(part)
            else:
                leading = part[:len(part) - len(part.lstrip())]
                trailing = part[len(part.rstrip()):]
                translated = translate(part.strip())
                if not isinstance(translated, str) or not translated.strip():
                    raise TranslationError("本地模型返回空结果，请编辑原文后重试。")
                pieces.append(leading + translated.strip() + trailing)
        output.append("".join(pieces))
    result = "\n".join(output)
    if not numeric_values_agree(text, result):
        raise TranslationError("本地译文中的数字未通过核查，已停止回填；请编辑原文或主动选择在线服务。")
    return result
