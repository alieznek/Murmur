"""Run the fixed Argos 1.9 models without importing unused NLP frameworks.

Sentence splitting and decoding options follow Argos Translate 1.11.0's
MiniSBD path. The models, tokenizer and request policies remain unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

from screen_translator.services.argos_tokenizer import SentencePieceTokenizer


class ModelTranslation:
    def __init__(self, package: Path, source: str, target: str):
        metadata = json.loads((package / "metadata.json").read_text(encoding="utf-8"))
        if (metadata["from_code"], metadata["to_code"]) != (source, target):
            raise ValueError("Model direction does not match its resource directory")
        self.package = package
        self.sentence_model = package / "minisbd" / ("en.onnx" if source == "en" else "zh-hans.onnx")
        self.tokenizer = SentencePieceTokenizer(package / "sentencepiece.model")
        self.target_prefix = metadata.get("target_prefix", "")
        self.translator = None
        self.detector = None
        self.cache = {}

    def translate(self, text: str) -> str:
        if self.translator is None:
            from ctranslate2 import Translator
            self.translator = Translator(str(self.package / "model"), device="cpu", compute_type="int8",
                                         inter_threads=1, intra_threads=4)
        if self.detector is None:
            from minisbd import SBDetect
            self.detector = SBDetect(str(self.sentence_model), use_gpu=False)
        current_cache = {}
        for paragraph in text.split("\n"):
            if paragraph in current_cache:
                continue
            if paragraph in self.cache:
                current_cache[paragraph] = self.cache[paragraph]
                continue
            sentences = self.detector.sentences(paragraph) if paragraph else []
            tokens = [self.tokenizer.encode(sentence) for sentence in sentences]
            prefix = [[self.target_prefix]] * len(tokens) if self.target_prefix else None
            batches = self.translator.translate_batch(
                tokens, target_prefix=prefix, replace_unknowns=True, max_batch_size=32, batch_type="tokens",
                beam_size=4, num_hypotheses=1, length_penalty=0.2, return_scores=True)
            translated_tokens = [token for batch in batches for token in batch.hypotheses[0]]
            result = self.tokenizer.decode(translated_tokens)
            if self.target_prefix and result.startswith(self.target_prefix):
                result = result[len(self.target_prefix):]
            if result.startswith(" "):
                result = result[1:]
            current_cache[paragraph] = result
        self.cache = current_cache
        return "\n".join(current_cache[paragraph] for paragraph in text.split("\n")).lstrip("\n")


def create_directions(resources: Path) -> dict:
    return {(source, target): ModelTranslation(
        resources / "packages" / f"translate-{source}_{target}-1_9", source, target)
        for source, target in (("en", "zh"), ("zh", "en"))}
