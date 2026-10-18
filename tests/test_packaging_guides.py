import importlib.util
import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote


class PackagedGuideTests(unittest.TestCase):
    def test_copy_guides_replaces_stale_output_and_resolves_offline(self):
        script = Path(__file__).resolve().parents[1] / "scripts/packaging/build.py"
        spec = importlib.util.spec_from_file_location("current_packaging", script)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            stale = bundle / "guides/old"
            stale.mkdir(parents=True)
            (stale / "old.md").write_text("obsolete")
            builder.copy_guides(bundle)
            guides = bundle / "guides"
            self.assertFalse(stale.exists())
            self.assertTrue((guides / "usage.md").is_file())
            self.assertIn("guides/usage.md", (bundle / "README.txt").read_text(encoding="utf-8"))
            self.assertTrue((bundle / "THIRD_PARTY_NOTICES.md").is_file())
            for document in guides.glob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                    if "://" in target or target.startswith("#"):
                        continue
                    with self.subTest(document=document.name, target=target):
                        self.assertTrue((document.parent / unquote(target.split("#", 1)[0])).is_file())
