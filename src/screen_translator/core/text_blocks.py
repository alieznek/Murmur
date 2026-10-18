from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TextBlock:
    id: str
    text: str
    polygon: tuple[tuple[float, float], ...]
    order: int = 0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs = [point[0] for point in self.polygon]
        ys = [point[1] for point in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)


def reading_order(blocks: Iterable[TextBlock]) -> list[TextBlock]:
    """Sort OCR lines into approximate top-to-bottom, left-to-right reading order."""
    items = list(blocks)
    if not items:
        return []
    heights = [max(1.0, block.bounds[3] - block.bounds[1]) for block in items]
    tolerance = max(4.0, sorted(heights)[len(heights) // 2] * 0.55)
    return sorted(items, key=lambda block: (
        round(((block.bounds[1] + block.bounds[3]) / 2) / tolerance),
        block.bounds[0], block.order,
    ))
