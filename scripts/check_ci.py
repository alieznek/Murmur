"""Run the small, model-free Windows CI suite from any working directory."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "test_text_units", "test_provider_translators", "test_provider_protocols",
    "test_settings_store.SettingsStoreTests", "test_app_assets",
    "test_packaging_guides",
)


def check_documents() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    if project["project"]["license"] != "MIT":
        raise ValueError("Project license metadata needs review")
    for name in project["project"]["license-files"]:
        if not (ROOT / name).is_file():
            raise ValueError(f"Missing project notice: {name}")
    documents = [ROOT / name for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md")]
    documents.extend((ROOT / "docs").glob("*.md"))
    for document in documents:
        text = document.read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)]+)\)", text) + re.findall("src=\"([^\"]+)\"", text)
        for target in links:
            if "://" in target or target.startswith("#"):
                continue
            path = document.parent / unquote(target.split("#", 1)[0])
            if not path.exists():
                raise ValueError(f"Broken local link in {document.name}: {target}")
    import yaml
    for path in (ROOT / ".github").rglob("*.yml"):
        yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    print("Project license, document links and YAML checked", flush=True)


def main() -> int:
    sources = [p for directory in ("src", "scripts", "tests", "app-icon")
               for p in (ROOT / directory).rglob("*.py") if "__pycache__" not in p.parts]
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    print(f"Syntax checked: {len(sources)} Python files", flush=True)
    check_documents()
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests")))
    environment["PYTHONUTF8"] = "1"
    temporary = ROOT / "build/ci-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment["TEMP"] = environment["TMP"] = str(temporary)
    return subprocess.run([sys.executable, "-m", "unittest", *TESTS, "-v"],
                          cwd=ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
