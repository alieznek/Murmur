"""Integrity helpers for preparing the product's offline model resources."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_checked(archive: Path, destination: Path) -> None:
    """Reject unsafe names before writing any members of a downloaded archive."""
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            name = PurePosixPath(item.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or ":" in item.filename:
                raise ValueError("Unsafe model archive path")
            if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Model archives cannot contain symbolic links")
        if bundle.testzip() is not None:
            raise ValueError("Model archive CRC mismatch")
        bundle.extractall(destination)


def inventory(root: Path) -> list[dict]:
    return [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
             "sha256": sha256(path)} for path in sorted(root.rglob("*")) if path.is_file()]


def verify_resources(root: Path) -> dict:
    manifest = json.loads((root / "resource-manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or ":" in item["path"]:
            raise ValueError("Unsafe resource manifest path")
        path = root / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError("Missing or corrupt offline resource: " + item["path"])
    return manifest
