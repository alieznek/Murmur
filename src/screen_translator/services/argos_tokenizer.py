"""Keep Argos model loading compatible with Unicode Windows install paths."""
from __future__ import annotations


class SentencePieceTokenizer:
    def __init__(self, model_file):
        self.model_file = model_file
        self.processor = None

    def lazy_processor(self):
        if self.processor is None:
            from sentencepiece import SentencePieceProcessor
            # The native file loader cannot open Chinese paths on Windows.
            self.processor = SentencePieceProcessor(model_proto=self.model_file.read_bytes())
        return self.processor

    def encode(self, text):
        return self.lazy_processor().encode(text, out_type=str)

    def decode(self, tokens):
        return self.lazy_processor().decode_pieces(tokens).replace("▁", " ").replace("_", " ")
