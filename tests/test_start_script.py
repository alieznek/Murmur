import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from pathlib import Path


START_SCRIPT = Path(__file__).resolve().parents[1] / "start-translator.bat"


@unittest.skipUnless(os.name == "nt", "The batch launcher is Windows-only")
class StartScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="translator 中文 path ")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project with spaces"
        self.project.mkdir()
        self.script = self.project / START_SCRIPT.name
        shutil.copy2(START_SCRIPT, self.script)
        source = self.project / "src" / "screen_translator"
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("", encoding="utf-8")
        # Exercise the real launch command without opening a GUI in the tests.
        (source / "app.py").write_text(
            'if __name__ == "__main__":\n'
            '    import json, os, sys\n'
            '    from pathlib import Path\n'
            '    Path(os.environ["TRANSLATOR_TEST_MARKER"]).write_text(\n'
            '        json.dumps({"python": sys.executable, "cwd": os.getcwd(),\n'
            '                    "source": __file__}), encoding="utf-8")\n',
            encoding="utf-8",
        )
        self.marker = self.project / "started.json"
        self.environment = os.environ.copy()
        self.environment["TRANSLATOR_TEST_MARKER"] = str(self.marker)
        # Reuse installed dependencies with the temporary virtual environments.
        self.environment["PYTHONPATH"] = os.pathsep.join(sys.path)

    def create_environment(self, relative):
        scripts = self.project / relative / "Scripts"
        venv.EnvBuilder(with_pip=False).create(scripts.parent)
        return scripts

    def run_script(self, *arguments):
        return subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(self.script), *arguments],
            cwd=self.temporary.name,
            env=self.environment,
            input="",
            capture_output=True,
            encoding="utf-8",
            timeout=15,
        )

    def test_root_environment_check_accepts_dependencies_without_argostranslate(self):
        scripts = self.create_environment(".venv")
        # An older developer environment may still have Argos Translate installed.
        # Simulate its absence while retaining the current runtime dependencies.
        (self.project / "src" / "sitecustomize.py").write_text(
            "import importlib.metadata\n"
            "original_distribution = importlib.metadata.distribution\n"
            "def distribution(name):\n"
            "    if name.lower().replace('_', '-') == 'argostranslate':\n"
            "        raise importlib.metadata.PackageNotFoundError(name)\n"
            "    return original_distribution(name)\n"
            "importlib.metadata.distribution = distribution\n",
            encoding="utf-8",
        )
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(scripts / "python.exe"), result.stdout)
        self.assertFalse(self.marker.exists())

    def test_launches_with_root_environment_from_another_directory(self):
        scripts = self.create_environment(".venv")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        deadline = time.monotonic() + 5
        while not self.marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.marker.exists(), "The launcher did not start the app")
        started = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual(Path(started["python"]), scripts / "pythonw.exe")
        self.assertEqual(Path(started["cwd"]), self.project)
        self.assertEqual(Path(started["source"]), self.project / "src/screen_translator/app.py")

    def test_missing_environment_explains_installation_and_exits_with_error(self):
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR]", result.stdout)
        self.assertIn("pip install -r requirements.lock", result.stdout)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
