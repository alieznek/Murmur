"""Download official resources into a new directory, without touching app/user data."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import urllib.request
import concurrent.futures
from pathlib import Path

from model_utils import extract_checked, inventory, sha256, verify_resources, write_json

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
REPOSITORY = Path(__file__).resolve().parents[1]


def prepare_ocr(output: Path) -> None:
    """Download only during explicit setup, using the locked engine's model sources."""
    import rapidocr
    from omegaconf import OmegaConf
    from rapidocr.utils.download_models import download_models
    from screen_translator.resources import MODEL_FILES

    if all((output / name).is_file() for name in MODEL_FILES.values()):
        print("Existing OCR models retained", flush=True)
        return
    config = OmegaConf.load(Path(rapidocr.__file__).parent / "config.yaml")
    config.Global.model_root_dir = str(output)
    with tempfile.TemporaryDirectory(prefix="ocr-config-") as temporary:
        path = Path(temporary) / "config.yaml"
        OmegaConf.save(config, path)
        download_models(path)
    if not all((output / name).is_file() for name in MODEL_FILES.values()):
        raise ValueError("The installed OCR engine did not prepare the expected models")


def download(url: str, target: Path) -> None:
    if not url.startswith("https://"):
        raise ValueError("Resource downloads require HTTPS")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            size = int(response.headers.get("Content-Length", "0"))
            ranged = response.headers.get("Accept-Ranges") == "bytes" and size > 0
        if ranged:
            chunk = 1024 * 1024

            def piece(start: int) -> bytes:
                end = min(start + chunk, size) - 1
                request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise ValueError("Invalid range response")
                    data = response.read(chunk + 1)
                    if len(data) != end - start + 1:
                        raise ValueError("Incomplete range response")
                    return data

            # Bounded outstanding requests; keep memory below four chunks.
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool, temporary.open("wb") as output:
                starts = iter(range(0, size, chunk))
                pending = [pool.submit(piece, start) for start in [next(starts, None) for _ in range(4)] if start is not None]
                written = 0
                while pending:
                    data = pending.pop(0).result()
                    output.write(data)
                    written += len(data)
                    print(f"{target.name}: {written}/{size} bytes", flush=True)
                    start = next(starts, None)
                    if start is not None:
                        pending.append(pool.submit(piece, start))
        else:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        if size and temporary.stat().st_size != size:
            raise ValueError("Incomplete resource download")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(output: Path, cache: Path) -> None:
    if output.exists():
        verify_resources(output)
        print("Existing verified resources retained", flush=True)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    index_file = cache / "index.json"
    download(INDEX_URL, index_file)
    index = json.loads(index_file.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="argos-stage-", dir=output.parent) as temporary:
        stage = Path(temporary) / "resources"
        packages = stage / "packages"
        packages.mkdir(parents=True)
        origins = []
        for source, target in (("en", "zh"), ("zh", "en")):
            metadata = next(item for item in index if item["from_code"] == source
                            and item["to_code"] == target and item["package_version"] == "1.9")
            url = next(url for url in metadata["links"] if url.startswith("https://"))
            index_link = url
            archive = cache / url.rsplit("/", 1)[1]
            origin_file = archive.with_suffix(archive.suffix + ".source.json")
            if not archive.is_file():
                print("Downloading " + archive.name, flush=True)
                try:
                    download(url, archive)
                except urllib.error.HTTPError as error:
                    if error.code != 403:
                        raise
                    # Same named/versioned files in Argos's official directory.
                    url = "https://data.argosopentech.com/argospm/v1/" + archive.name
                    print("Using official backup " + url, flush=True)
                    download(url, archive)
                write_json(origin_file, {"url": url, "sha256": sha256(archive)})
            elif origin_file.is_file():
                origin = json.loads(origin_file.read_text(encoding="utf-8"))
                if origin["sha256"] != sha256(archive):
                    raise ValueError("Cached archive provenance checksum mismatch")
                url = origin["url"]
            else:
                # A cached filename alone cannot establish its download origin.
                url = None
            extract_checked(archive, packages)
            origins.append({"kind": "translation", "url": url, "index_link": index_link, "metadata": metadata,
                            "archive_bytes": archive.stat().st_size, "archive_sha256": sha256(archive)})
        # URLs are from MiniSBD v0.9.5's models.py, not a runtime cache lookup.
        minisbd_url = "https://github.com/LibreTranslate/MiniSBD/releases/download/v0.0.1/"
        for package in sorted(packages.iterdir()):
            metadata = json.loads((package / "metadata.json").read_text(encoding="utf-8"))
            language = "en" if metadata["from_code"] == "en" else "zh-hans"
            model = cache / "minisbd" / (language + ".onnx")
            url = minisbd_url + model.name
            if not model.is_file():
                print("Downloading " + model.name, flush=True)
                download(url, model)
            destination = package / "minisbd" / model.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(model, destination)
            origins.append({"kind": "sentence_boundary", "language": language, "url": url,
                            "file": destination.relative_to(stage).as_posix(),
                            "bytes": model.stat().st_size, "sha256": sha256(model)})
        manifest = {"schema": 1, "index_url": INDEX_URL, "index_sha256": sha256(index_file),
                    "model_version": "1.9", "chunk_type": "MINISBD", "sources": origins,
                    "files": inventory(stage)}
        write_json(stage / "resource-manifest.json", manifest)
        verify_resources(stage)
        stage.replace(output)
        print("Prepared " + str(output), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPOSITORY / "models/argos")
    parser.add_argument("--cache", type=Path, default=REPOSITORY / ".cache/models")
    parser.add_argument("--ocr-output", type=Path, default=REPOSITORY / "models/ocr")
    args = parser.parse_args()
    prepare_ocr(args.ocr_output.resolve())
    prepare(args.output.resolve(), args.cache.resolve())
