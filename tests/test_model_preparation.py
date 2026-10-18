import json
import sys
import tempfile
import unittest
import zipfile
import io
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from model_utils import extract_checked, inventory, verify_resources, write_json
from prepare_models import download, prepare


class ModelPreparationTests(unittest.TestCase):

    def test_range_download_checks_each_response_and_keeps_output_atomic(self):
        data = b"abcde" * (1024 * 1024)

        class Response(io.BytesIO):
            def __init__(self, body, headers, status=200):
                super().__init__(body)
                self.headers, self.status = headers, status

        def response(request, **_kwargs):
            if request.get_method() == "HEAD":
                return Response(b"", {"Content-Length": str(len(data)), "Accept-Ranges": "bytes"})
            start, end = map(int, request.get_header("Range").removeprefix("bytes=").split("-"))
            return Response(data[start:end + 1], {"Content-Range": f"bytes {start}-{end}/{len(data)}"}, 206)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "model.bin"
            with patch("prepare_models.urllib.request.urlopen", side_effect=response):
                download("https://official.example/model", output)
            self.assertEqual(output.read_bytes(), data)
            def invalid_response(request, **_kwargs):
                if request.get_method() == "HEAD":
                    return Response(b"", {"Content-Length": str(len(data)), "Accept-Ranges": "bytes"})
                return Response(b"bad", {"Content-Range": "invalid"}, 206)

            with patch("prepare_models.urllib.request.urlopen", side_effect=invalid_response):
                with self.assertRaises(ValueError):
                    download("https://official.example/model", output)
            self.assertEqual(output.read_bytes(), data)
            self.assertFalse(output.with_suffix(".bin.part").exists())

    def test_resource_inventory_detects_missing_and_corrupt_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / "model.bin"
            file.write_bytes(b"synthetic model")
            write_json(root / "resource-manifest.json", {"files": inventory(root)})
            self.assertEqual(len(verify_resources(root)["files"]), 1)
            file.write_bytes(b"synthetic other")
            with self.assertRaisesRegex(ValueError, "corrupt"):
                verify_resources(root)
            file.unlink()
            with self.assertRaisesRegex(ValueError, "Missing"):
                verify_resources(root)

    def test_archive_rejects_unsafe_paths_before_writing_any_file(self):
        for name in ("../escaped", "C:/escaped", "nested/../../escaped", "..\\escaped", "/escaped"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, output = root / "bad.zip", root / "output"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr("safe.txt", "first member")
                    bundle.writestr(name, "unsafe member")
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    extract_checked(archive, output)
                self.assertFalse(output.exists())

    def test_existing_resources_are_verified_and_never_redownloaded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "resources"
            root.mkdir()
            (root / "model.bin").write_bytes(b"synthetic model")
            write_json(root / "resource-manifest.json", {"files": inventory(root)})
            with patch("prepare_models.download") as download:
                prepare(root, Path(temporary) / "cache")
                download.assert_not_called()
                (root / "model.bin").write_bytes(b"corrupt")
                with self.assertRaises(ValueError):
                    prepare(root, Path(temporary) / "cache")
                download.assert_not_called()
                self.assertEqual((root / "model.bin").read_bytes(), b"corrupt")

    def test_cached_model_provenance_uses_recorded_origin_and_checks_its_hash(self):
        from model_utils import sha256
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            cache.mkdir()
            metadata = []
            for source, target in (("en", "zh"), ("zh", "en")):
                name = f"translate-{source}_{target}-1_9.argosmodel"
                item = {"from_code": source, "to_code": target, "package_version": "1.9",
                        "links": ["https://argos-net.com/v1/" + name]}
                metadata.append(item)
                archive = cache / name
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(name.removesuffix(".argosmodel") + "/metadata.json", json.dumps(item))
                if source == "en":
                    write_json(archive.with_suffix(".argosmodel.source.json"),
                               {"url": "https://data.argosopentech.com/argospm/v1/" + name, "sha256": sha256(archive)})

            def download_fixture(url, path):
                path.parent.mkdir(parents=True, exist_ok=True)
                if url.endswith("index.json"):
                    write_json(path, metadata)
                else:
                    path.write_bytes(b"synthetic sentence model")

            with patch("prepare_models.download", side_effect=download_fixture):
                prepare(root / "resources", cache)
                manifest = verify_resources(root / "resources")
                origins = [row for row in manifest["sources"] if row["kind"] == "translation"]
                self.assertIn("data.argosopentech.com", origins[0]["url"])
                self.assertIsNone(origins[1]["url"], "A filename cannot establish the cached origin")
                self.assertIn("argos-net.com", origins[1]["index_link"])
                sidecar = cache / "translate-en_zh-1_9.argosmodel.source.json"
                origin = json.loads(sidecar.read_text())
                origin["sha256"] = "0" * 64
                write_json(sidecar, origin)
                with self.assertRaisesRegex(ValueError, "provenance"):
                    prepare(root / "retry", cache)
                self.assertFalse((root / "retry").exists())
