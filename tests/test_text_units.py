import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from screen_translator.core.ocr_text import selected_ocr_text
from screen_translator.core.text_blocks import TextBlock, reading_order
from screen_translator.services.argos_tokenizer import SentencePieceTokenizer
from screen_translator.services.ocr import RapidOcrService


def block(identifier, text, x, y, width=100, height=16):
    return TextBlock(identifier, text, ((x, y), (x + width, y),
                                        (x + width, y + height), (x, y + height)))


class TextBlockTests(unittest.TestCase):
    def test_reading_order_sorts_rows_and_columns_and_handles_empty_input(self):
        blocks = [block("right", "second", 160, 12), block("lower", "third", 12, 48),
                  block("left", "first", 12, 10)]
        self.assertEqual([item.id for item in reading_order(blocks)], ["left", "right", "lower"])
        self.assertEqual(reading_order([]), [])

    def test_unknown_ids_and_empty_text_are_ignored(self):
        blocks = [block("a", "  hello\n world  ", 0, 0), block("b", "  ", 0, 30)]
        self.assertEqual(selected_ocr_text(blocks, {"a", "b", "missing"}), "hello world")


class OcrAdapterTests(unittest.TestCase):
    def test_converts_engine_output_and_sorts_blocks(self):
        service = RapidOcrService()
        service._engine = lambda _image: SimpleNamespace(
            boxes=[
                [[80, 0], [130, 0], [130, 20], [80, 20]],
                [[0, 0], [60, 0], [60, 20], [0, 20]],
            ],
            txts=["second", "first"],
        )
        blocks = service.recognize(object())
        self.assertEqual([block.text for block in blocks], ["first", "second"])
        self.assertEqual(blocks[0].bounds, (0.0, 0.0, 60.0, 20.0))

    def test_missing_result_fields_are_an_empty_result(self):
        service = RapidOcrService()
        service._engine = lambda _image: SimpleNamespace(boxes=None, txts=None)
        self.assertEqual(service.recognize(object()), [])


class UnicodeTokenizerTests(unittest.TestCase):
    def test_real_model_encodes_and_decodes_from_chinese_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="分词模型 空格 ") as temporary:
            from sentencepiece import SentencePieceTrainer

            sentences = ["Hello world.", "你好世界。", "不要删除文件。"]
            model = io.BytesIO()
            SentencePieceTrainer.train(sentence_iterator=iter(sentences), model_writer=model,
                                       model_type="char", vocab_size=64, hard_vocab_limit=False,
                                       minloglevel=2)
            path = Path(temporary) / "模型.model"
            path.write_bytes(model.getvalue())
            tokenizer = SentencePieceTokenizer(path)
            for sentence in sentences:
                with self.subTest(sentence=sentence):
                    tokens = tokenizer.encode(sentence)
                    self.assertTrue(tokens)
                    self.assertEqual(tokenizer.decode(tokens), sentence)


if __name__ == "__main__":
    unittest.main()
