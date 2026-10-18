"""Rejoin nearby OCR word boxes while retaining rows and column gaps."""
from __future__ import annotations

import re
from collections.abc import Sequence

from screen_translator.core.text_blocks import TextBlock


def selected_ocr_text(blocks: Sequence[TextBlock], selected_ids: set[str]) -> str:
    rows: list[list[TextBlock]] = []
    for block in sorted((b for b in blocks if b.id in selected_ids and b.text.strip()),
                        key=lambda b: (b.bounds[1], b.bounds[0])):
        left, top, right, bottom = block.bounds
        height = max(1, bottom - top)
        for row in rows:
            anchor = row[0].bounds
            overlap = min(bottom, anchor[3]) - max(top, anchor[1])
            if overlap >= 0.55 * max(height, anchor[3] - anchor[1]):
                row.append(block)
                break
        else:
            rows.append([block])
    lines = []
    for row in rows:
        line, previous = "", None
        for block in sorted(row, key=lambda b: b.bounds[0]):
            text = " ".join(block.text.split())
            if previous:
                gap = block.bounds[0] - previous.bounds[2]
                height = max(1, min(block.bounds[3] - block.bounds[1], previous.bounds[3] - previous.bounds[1]))
                if gap > 2 * height:
                    lines.append(line)
                    line = ""
                elif not (re.match(r"[\u3400-\u9fff]$", line[-1:]) and re.match(r"[\u3400-\u9fff]", text)):
                    line += " "
            line += text
            previous = block
        lines.append(line)
    return "\n".join(lines)
