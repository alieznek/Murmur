from __future__ import annotations

import sys
from pathlib import Path


MODEL_FILES = {"Det": "PP-OCRv6_det_small.onnx", "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
               "Rec": "PP-OCRv6_rec_small.onnx"}


def app_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources" / "app-icon" / "translator.ico"
    return Path(__file__).resolve().parents[2] / "app-icon" / "translator.ico"


def ocr_parameters() -> dict:
    frozen = getattr(sys, "frozen", False)
    directory = (Path(sys._MEIPASS) / "resources" / "models" if frozen
                 else Path(__file__).resolve().parents[2] / "models" / "ocr")
    paths = {stage: directory / filename for stage, filename in MODEL_FILES.items()}
    if any(not path.is_file() for path in paths.values()):
        recovery = "重新解压完整程序包（包括 _internal 目录）" if frozen else "按仓库 README 准备 models/ocr"
        raise RuntimeError(f"离线 OCR 模型不完整，请{recovery}。不会自动下载。")
    return {**{f"{stage}.model_path": str(path) for stage, path in paths.items()},
            "Global.log_level": "error"}
