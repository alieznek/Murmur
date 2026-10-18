from pathlib import Path
import os
from fnmatch import fnmatch
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

packaging = Path(SPECPATH)
repository = packaging.parents[1]
from screen_translator import __version__
model_names = ("PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx")
model_directory = repository / "models/ocr"
for name in model_names:
    if not (model_directory / name).is_file():
        raise RuntimeError(f"Missing offline model: {name}. Run scripts/prepare_models.py before building.")

datas = collect_data_files("rapidocr", excludes=["models/*"])
datas += [(str(model_directory / name), "resources/models") for name in model_names]
datas += [(str(repository / "app-icon/translator.ico"), "resources/app-icon")]
datas += copy_metadata("rapidocr") + copy_metadata("keyring", recursive=True)
resources = Path(os.environ.get("MURMUR_ARGOS_RESOURCES", repository / "models/argos"))
from screen_translator.services.offline_resources import verify_resources
verify_resources(resources)
datas += [(str(resources), "resources/argos")]
datas += copy_metadata("ctranslate2") + copy_metadata("sentencepiece") + copy_metadata("minisbd")
datas += [(str(repository / "src/screen_translator/diagnostics/offline-cases.json"), "screen_translator/diagnostics")]
excludes = ["tkinter", "matplotlib", "tensorflow", "paddle", "openvino", "pytest",
            "PyQt5", "PyQt6", "PySide2", "keyring.backends.macOS", "keyring.backends.SecretService"]

a = Analysis([str(packaging / "entry.py")], pathex=[str(repository / "src")],
             datas=datas, binaries=[], hiddenimports=collect_submodules("rapidocr") + ["keyring.backends.Windows"],
             excludes=excludes + ["torch", "spacy", "stanza", "argostranslate", "ctranslate2", "sentencepiece", "minisbd"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Murmur", console=False,
          debug=False, strip=False, upx=False, icon=str(repository / "app-icon/translator.ico"))
worker = Analysis([str(packaging / "worker_entry.py")], pathex=[str(repository / "src")],
                  datas=[], binaries=[], hiddenimports=["minisbd", "ctranslate2", "sentencepiece"],
                  excludes=excludes + ["argostranslate", "torch", "spacy", "stanza", "thinc", "blis",
                                       "ctranslate2.converters", "ctranslate2.specs", "PySide6", "shiboken6"],
                  noarchive=False)
worker_pyz = PYZ(worker.pure)
worker_exe = EXE(worker_pyz, worker.scripts, [], exclude_binaries=True, name="ArgosWorker",
                 console=True, debug=False, strip=False, upx=False,
                 icon=str(repository / "app-icon/translator.ico"))
# Static screenshots and Qt Widgets do not use video, PDF rendering or Qt's
# virtual keyboard. Keep qwindows, system IME, image codecs and software OpenGL.
trimmed_patterns = (
    "cv2/opencv_videoio_ffmpeg*_64.dll",
    "PySide6/plugins/imageformats/qpdf.dll",
    "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "PySide6/Qt6VirtualKeyboard.dll", "PySide6/Qt6Quick.dll",
    "PySide6/Qt6Qml*.dll", "PySide6/Qt6Pdf.dll",
)

def retained(entries):
    return [entry for entry in entries if not any(
        fnmatch(entry[0].replace("\\", "/").casefold(), pattern.casefold()) for pattern in trimmed_patterns)]

coll = COLLECT(exe, worker_exe, retained(a.binaries), retained(a.datas),
               retained(worker.binaries), retained(worker.datas),
               strip=False, upx=False, name=f"Murmur-{__version__}")
