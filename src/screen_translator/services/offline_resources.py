"""Offline resource policy, independent of Argos and Qt imports."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath

from screen_translator.services.translator import TranslationError

RESOURCE_ERROR = "离线翻译资源缺失或损坏，请从完整试用包重新解压 _internal/resources/argos；开发环境按仓库 README 准备资源。不会自动下载。"


def resource_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources/argos"
    return Path(__file__).resolve().parents[3] / "models/argos"


def verify_resources(root: Path) -> dict:
    try:
        manifest = json.loads((root / "resource-manifest.json").read_text(encoding="utf-8"))
        if manifest["schema"] != 1 or manifest["model_version"] != "1.9" or not manifest["files"]:
            raise ValueError
        paths = set()
        for item in manifest["files"]:
            relative = PurePosixPath(item["path"].replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
                raise ValueError
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()) or str(relative) in paths:
                raise ValueError
            paths.add(str(relative))
            if path.stat().st_size != item["bytes"]:
                raise ValueError
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError
        for direction, language in (("en_zh", "en"), ("zh_en", "zh-hans")):
            prefix = f"packages/translate-{direction}-1_9/"
            if not {prefix + "metadata.json", prefix + "model/model.bin",
                    prefix + f"minisbd/{language}.onnx"}.issubset(paths):
                raise ValueError
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise TranslationError(RESOURCE_ERROR) from None


def configure_offline(root: Path, state: Path) -> None:
    # Ignore inherited Argos options and the user's model/cache directories.
    for key in list(os.environ):
        if key.startswith("ARGOS_"):
            del os.environ[key]
    for directory in ("data", "config", "cache"):
        path = state / directory
        path.mkdir(parents=True, exist_ok=True)
        os.environ["XDG_" + directory.upper() + "_HOME"] = str(path)
    os.environ.update({"ARGOS_PACKAGES_DIR": str(root / "packages"),
                       "ARGOS_DEVICE_TYPE": "cpu", "ARGOS_MODEL_PROVIDER": "OPENNMT",
                       "ARGOS_CHUNK_TYPE": "MINISBD", "ARGOS_COMPUTE_TYPE": "int8",
                       "ARGOS_INTRA_THREADS": "4", "ARGOS_INTER_THREADS": "1",
                       "ARGOS_DEBUG": "0", "HF_HUB_OFFLINE": "1"})


class NetworkGuard:
    def __init__(self):
        self.attempts: list[str] = []
        sys.addaudithook(self._audit)

    def _audit(self, event, _args):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
            self.attempts.append(event)
            raise RuntimeError("Offline translation forbids network access")
