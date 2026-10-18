from __future__ import annotations

import hashlib
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from packaging.version import Version


PACKAGING = Path(__file__).resolve().parent
REPOSITORY = PACKAGING.parents[1]
GUIDE_FILES = ("usage.md", "providers.md", "architecture.md", "privacy.md", "licensing.md")
sys.path.insert(0, str(REPOSITORY / "src"))

from screen_translator import __version__


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def copy_guides(bundle: Path) -> None:
    documentation = bundle / "guides"
    if documentation.resolve().parent != bundle.resolve():
        raise ValueError("Guide output must stay inside the bundle")
    if documentation.exists():
        shutil.rmtree(documentation)
    documentation.mkdir()
    for name in GUIDE_FILES:
        shutil.copy2(REPOSITORY / "docs" / name, documentation / name)
    shutil.copytree(REPOSITORY / "docs/images", documentation / "images")
    for name in ("LICENSE", "COPYRIGHT", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(REPOSITORY / name, bundle / name)
    (documentation / "README.md").write_text(
        "# 屏幕翻译器使用资料\n\n"
        "- [使用指南](usage.md)\n"
        "- [平台配置](providers.md)\n"
        "- [架构说明](architecture.md)\n", encoding="utf-8")
    (bundle / "README.txt").write_text(
        f"Murmur（译语） {__version__}\n"
        "Start Murmur.exe. Keep ArgosWorker.exe and _internal alongside it.\n"
        "Current guide: guides/usage.md\n"
        "Ctrl+Alt+S: capture the monitor under the pointer. Double-click the floating icon to restore.\n"
        "Use tray Exit to quit. Online providers require your own credentials.\n",
        encoding="utf-8")
    (bundle / "运行自检.bat").write_bytes(
        (PACKAGING / "self-check.bat").read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))


def build_manifest(bundle: Path) -> dict:
    notices = bundle / "third-party-licenses"
    notices.mkdir(exist_ok=True)
    shutil.copy2(PACKAGING / "languages/INNO-LICENSE.txt", notices / "INNO-LICENSE.txt")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, notices / "PYTHON-LICENSE.txt")
    # Include the application source so users can review and rebuild it.
    with zipfile.ZipFile(bundle / "source-materials.zip", "w", zipfile.ZIP_DEFLATED) as source_archive:
        for directory in (REPOSITORY / "src/screen_translator", REPOSITORY / "tests",
                          REPOSITORY / "scripts", REPOSITORY / "app-icon", REPOSITORY / "docs", REPOSITORY / "LICENSES", REPOSITORY / ".github"):
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix in (".py", ".json", ".md", ".spec", ".lock", ".svg", ".png", ".ico", ".iss", ".isl", ".bat", ".txt", ".yml", ".yaml"):
                    source_archive.write(path, "project/" + path.relative_to(REPOSITORY).as_posix())
        for name in ("pyproject.toml", "requirements.lock", "requirements-build.lock", "README.md",
                     ".gitignore", ".gitattributes", "start-translator.bat",
                     "LICENSE", "COPYRIGHT", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "SECURITY.md"):
            source_archive.write(REPOSITORY / name, "project/" + name)
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip()
    models = bundle / "_internal/resources/models"
    from screen_translator.services.offline_resources import verify_resources
    offline = verify_resources(bundle / "_internal/resources/argos")
    return {"version": __version__, "created_utc": datetime.now(timezone.utc).isoformat(),
            "git_head": git_head,
            "git_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=REPOSITORY, text=True).strip()),
            "python": sys.version,
            "executables_sha256": {path.name: sha256(path) for path in bundle.glob("*.exe")},
            "source_sha256": {str(path.relative_to(REPOSITORY)): sha256(path)
                              for path in sorted((REPOSITORY / "src").rglob("*.py"))},
            "models_sha256": {path.name: sha256(path) for path in sorted(models.glob("*.onnx"))},
            "offline_resources": offline,
            "packaging_sha256": {path.relative_to(PACKAGING).as_posix(): sha256(path)
                                 for path in sorted(PACKAGING.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}}


def find_iscc(explicit: Path | None) -> Path:
    if explicit is not None:
        compiler = explicit.resolve()
        if not compiler.is_file():
            raise SystemExit(f"Inno Setup compiler not found: {compiler}")
        return compiler
    candidates = [REPOSITORY / ".cache/tools/inno-setup/ISCC.exe"]
    if command := shutil.which("ISCC.exe"):
        candidates.insert(0, Path(command))
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        if base := os.environ.get(variable):
            candidates.extend((Path(base) / "Inno Setup 6/ISCC.exe",
                               Path(base) / "Programs/Inno Setup 6/ISCC.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise SystemExit("Install Inno Setup 6.5+ or pass --iscc PATH_TO_ISCC_EXE. See README.md.")


def write_checksum(path: Path) -> str:
    digest = sha256(path)
    Path(str(path) + ".sha256").write_text(digest + "  " + path.name + "\n", encoding="utf-8")
    return digest


def build_installer(bundle: Path, compiler: Path, environment: dict) -> Path:
    version = Version(__version__)
    numeric = ".".join(map(str, (*version.release[:3], (version.pre or (None, 0))[1])))
    output = bundle.parent
    name = f"Murmur-{__version__}-windows-x64-setup"
    subprocess.run([str(compiler), "/Qp", f"/DAppVersion={__version__}", f"/DNumericVersion={numeric}",
                    f"/DBundleDir={bundle}", f"/DOutputDir={output}", f"/DOutputName={name}",
                    str(PACKAGING / "installer.iss")], cwd=REPOSITORY, env=environment, check=True)
    installer = output / (name + ".exe")
    if not installer.is_file():
        raise SystemExit("Inno Setup did not produce the expected installer.")
    write_checksum(installer)
    print(f"Built installer {installer}")
    return installer


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the complete Windows desktop application")
    parser.add_argument("--clean", action="store_true", help="discard PyInstaller analysis cache")
    parser.add_argument("--installer", action="store_true", help="also build a per-user Windows setup EXE")
    parser.add_argument("--iscc", type=Path, help="path to Inno Setup 6.5+ ISCC.exe")
    parser.add_argument("--bundle-only", action="store_true", help="prepare a bundle for desktop testing before archiving")
    parser.add_argument("--package-only", action="store_true", help="self-check and archive an existing bundle with matching source hashes")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Build this Windows package on Windows x64.")
    compiler = find_iscc(args.iscc) if args.installer else None
    dist = (REPOSITORY / "dist").resolve()
    work = (REPOSITORY / "build").resolve()
    if dist.parent != REPOSITORY.resolve() or work.parent != REPOSITORY.resolve():
        raise SystemExit("Build paths must stay inside the repository.")
    environment = os.environ.copy()
    windows = Path(environment.get("WINDIR", "C:/Windows"))
    # Avoid picking DLLs from unrelated tools (for example an incompatible ICU build).
    environment["PATH"] = os.pathsep.join(map(str, (Path(sys.executable).parent, Path(sys.base_prefix),
                                                    windows / "System32", windows)))
    environment["PYINSTALLER_CONFIG_DIR"] = str(work / "pyinstaller-cache")
    bundle = dist / f"Murmur-{__version__}"
    if args.bundle_only and args.package_only:
        parser.error("--bundle-only and --package-only cannot be combined")
    if args.package_only:
        previous = json.loads((bundle / "build-manifest.json").read_text(encoding="utf-8"))
        current = {str(path.relative_to(REPOSITORY)): sha256(path) for path in sorted((REPOSITORY / "src").rglob("*.py"))}
        if previous.get("version") != __version__ or previous.get("source_sha256") != current:
            raise SystemExit("Existing bundle source changed; rebuild before archiving.")
        for name in ("entry.py", "worker_entry.py", "screen-translator.spec"):
            if previous.get("packaging_sha256", {}).get(name) != sha256(PACKAGING / name):
                raise SystemExit("Existing bundle packaging changed; rebuild before archiving.")
        for name, digest in previous.get("executables_sha256", {}).items():
            if sha256(bundle / name) != digest:
                raise SystemExit("Existing bundle executable changed; rebuild before archiving.")
    else:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", *(["--clean"] if args.clean else []),
                        "--distpath", str(dist), "--workpath", str(work),
                        str(PACKAGING / "screen-translator.spec")], cwd=REPOSITORY, env=environment, check=True)
    copy_guides(bundle)
    manifest = build_manifest(bundle)
    (bundle / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.bundle_only:
        print(f"Prepared {bundle}; run desktop acceptance before --package-only.")
        return 0
    report = work / "package-self-check.json"
    subprocess.run([str(bundle / "Murmur.exe"), "--self-check", str(report)], check=True, timeout=300, env=environment)
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("passed") or not result.get("frozen"):
        raise SystemExit("Bundled offline self-check failed; see build/package-self-check.json.")
    shutil.copy2(report, bundle / "offline-self-check.json")
    archive = shutil.make_archive(str(dist / f"Murmur-{__version__}-windows-x64"), "zip", dist, bundle.name)
    digest = write_checksum(Path(archive))
    print(f"Built {archive}\nSHA256 {digest}")
    if compiler:
        build_installer(bundle, compiler, environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
