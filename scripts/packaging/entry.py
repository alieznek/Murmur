import json
import sys
from pathlib import Path


try:
    if "--self-check" in sys.argv:
        report = Path(sys.argv[sys.argv.index("--self-check") + 1])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"passed": False, "stage": "imports"}), encoding="utf-8")
    from screen_translator.app import main
    result = main()
except Exception as error:
    if "--self-check" not in sys.argv:
        raise
    report = Path(sys.argv[sys.argv.index("--self-check") + 1])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"passed": False, "error_type": type(error).__name__,
                                  "error_module": getattr(error, "name", None)}), encoding="utf-8")
    result = 1
raise SystemExit(result)
