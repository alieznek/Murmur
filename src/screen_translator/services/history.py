"""Local translation conversations. Credentials and full-size captures never enter this file."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class HistoryError(RuntimeError):
    pass


class HistoryStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            raise HistoryError("无法读取本地翻译历史。原文件已保留，暂不覆盖。") from None
        try:
            if data["schema"] != 1 or not isinstance(data["conversations"], list):
                raise ValueError
            for conversation in data["conversations"]:
                if not all(isinstance(conversation[key], str) for key in ("id", "title", "updated")):
                    raise ValueError
                if not isinstance(conversation["messages"], list):
                    raise ValueError
                for message in conversation["messages"]:
                    if not all(isinstance(message[key], str) for key in ("id", "source", "translation", "target", "provider", "status")):
                        raise ValueError
                    if message["status"] not in ("pending", "complete", "failed", "interrupted"):
                        raise ValueError
                    if any(not isinstance(message.get(key, ""), str) for key in ("image", "error")):
                        raise ValueError
                    if message["status"] == "pending":
                        message["status"] = "interrupted"
        except (KeyError, TypeError, ValueError):
            raise HistoryError("本地历史格式不受支持。原文件已保留，暂不覆盖。") from None
        return data["conversations"]

    def save(self, conversations: list[dict]) -> None:
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="history-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({"schema": 1, "conversations": conversations}, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise HistoryError("历史保存失败，当前对话仍保留在窗口中。请检查存储空间或导出记录。") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
