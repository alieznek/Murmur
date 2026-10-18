"""One serial stdin/stdout worker; imports the model only in this process."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from screen_translator.core.offline_text import translate_preserving_literals, validate_request
from screen_translator.services.offline_resources import NetworkGuard, configure_offline, verify_resources
from screen_translator.services.translator import TranslationError


def run_worker(resources: Path) -> int:
    guard = NetworkGuard()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    protocol = sys.stdout
    # Dependencies sometimes print diagnostics; they must not corrupt the protocol.
    sys.stdout = sys.stderr

    def emit(value):
        protocol.write(json.dumps(value, ensure_ascii=False) + "\n")
        protocol.flush()

    with tempfile.TemporaryDirectory(prefix="screen-translator-argos-") as temporary:
        try:
            verify_resources(resources)
            configure_offline(resources, Path(temporary))
            from screen_translator.services.argos_engine import create_directions
            directions = create_directions(resources)
            if any(value is None for value in directions.values()) or guard.attempts:
                raise TranslationError("离线组件初始化失败，请重新解压完整试用包。")
            emit({"ready": True, "pid": os.getpid(), "network_attempts": guard.attempts})
        except Exception as error:
            emit({"ready": False, "error": str(error) if isinstance(error, TranslationError)
                  else "离线组件无法启动，请检查完整包和依赖后重试。"})
            return 1
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                if request.get("action") == "exit":
                    return 0
                source, target = validate_request(request["text"], request["target"], request["source"])
                result = request["text"] if source == target else translate_preserving_literals(
                    request["text"], directions[source, target].translate)
                if guard.attempts:
                    raise TranslationError("离线组件尝试联网，已阻止并停止回填，请检查资源。")
                emit({"id": request["id"], "result": result, "network_attempts": guard.attempts})
            except Exception as error:
                emit({"id": request.get("id"), "error": str(error) if isinstance(error, TranslationError)
                      else "离线翻译未完成，请编辑原文后重试。"})
    return 0


def main() -> int:
    return run_worker(Path(sys.argv[1]).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
