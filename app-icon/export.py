"""Export the editable SVG to PNG, Windows ICO, and a size review sheet.

Run from the project root with the project's virtual environment:
    .venv/Scripts/python.exe app-icon/export.py

The SVG and outputs are resolved relative to this script, independent of cwd.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


ICONS = Path(__file__).resolve().parent
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_icon(size: int) -> QImage:
    renderer = QSvgRenderer(str(ICONS / "translator.svg"))
    if not renderer.isValid():
        raise ValueError("translator.svg is not a valid SVG")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Prefer the normal Windows UI font; keep export usable on other systems.
    candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if candidate.is_file():
        return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def export_preview(icon: Image.Image, frames: list[Image.Image]) -> None:
    board = Image.new("RGB", (1400, 850), "#faf7f1")
    draw = ImageDraw.Draw(board)
    draw.text((68, 50), "Murmur", fill="#54443c", font=font(48))
    draw.text((70, 117), "SCREEN TEXT TRANSLATION / QUOTATION MARK", fill="#846a58", font=font(16))
    draw.rounded_rectangle((68, 190, 642, 764), radius=28, fill="#FFFFFF")
    large = icon.resize((424, 424), Image.Resampling.LANCZOS)
    board.paste(large, (143, 236), large)
    draw.text((355, 708), "Murmur quotation mark", fill="#846a58", font=font(22), anchor="mm")

    draw.text((708, 192), "ONE MARK. EVERY SIZE.", fill="#54443c", font=font(22))
    sizes = (16, 24, 32, 48, 64, 128)
    by_size = {frame.width: frame for frame in frames}
    x = 724
    for size in sizes:
        small = by_size[size]
        board.paste(small, (x, 338 - size), small)
        draw.text((x + size / 2, 371), str(size), fill="#846a58", font=font(16), anchor="mm")
        x += size + 26

    draw.rounded_rectangle((704, 428, 997, 741), radius=24, fill="#FFFFFF")
    draw.rounded_rectangle((1017, 428, 1310, 741), radius=24, fill="#342b25")
    medium = icon.resize((208, 208), Image.Resampling.LANCZOS)
    for x in (746, 1059):
        board.paste(medium, (x, 464), medium)
    draw.text((850, 706), "LIGHT", fill="#846a58", font=font(14), anchor="mm")
    draw.text((1163, 706), "DARK", fill="#e4d8c9", font=font(14), anchor="mm")
    board.save(ICONS / "preview.png")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    master = render_icon(1024)
    if not master.save(str(ICONS / "translator.png")):
        raise OSError("Failed to export translator.png")
    with Image.open(ICONS / "translator.png") as png:
        icon = png.convert("RGBA")
    # Explicitly render each size from the vector source for crisp small icons.
    frames = []
    for size in ICO_SIZES:
        image = render_icon(size).convertToFormat(QImage.Format.Format_RGBA8888)
        frames.append(Image.frombytes("RGBA", (size, size), bytes(image.bits())))
    frames[-1].save(
        ICONS / "translator.ico",
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=frames[:-1],
    )
    export_preview(icon, frames)
    print(f"Exported PNG, {len(ICO_SIZES)} ICO sizes, and preview to {ICONS}")
    # Keep the Qt application alive until all rendering has finished.
    _ = app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
