from __future__ import annotations

from itertools import count
from typing import Any

from screen_translator.core.text_blocks import TextBlock, reading_order
from screen_translator.resources import ocr_parameters


class RapidOcrService:
    """Lazily load RapidOCR and convert its result into app-owned text blocks."""

    def __init__(self) -> None:
        self._engine: Any | None = None
        self._ids = count(1)

    def recognize(self, image: Any) -> list[TextBlock]:
        if self._engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as error:
                raise RuntimeError(
                    "OCR 组件尚未安装。请按仓库 README 安装依赖和离线模型。"
                ) from error
            parameters = ocr_parameters()
            self._engine = RapidOCR(params=parameters) if parameters else RapidOCR()

        result = self._engine(image)
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        if boxes is None or texts is None:
            return []
        blocks = []
        for polygon, text in zip(boxes, texts):
            clean_text = str(text).strip()
            if not clean_text:
                continue
            points = tuple((float(point[0]), float(point[1])) for point in polygon)
            blocks.append(TextBlock(f"ocr-{next(self._ids)}", clean_text, points))
        return reading_order(blocks)
