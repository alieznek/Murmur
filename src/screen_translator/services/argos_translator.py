from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

from screen_translator.core.offline_text import validate_request
from screen_translator.services.offline_resources import resource_directory
from screen_translator.services.translator import TranslationError
from screen_translator.services.worker_process import start_process, stop_process


class ArgosTranslator:
    """Lazy, cancellable worker. At most one request, no queued inference."""
    def __init__(self, *, resources: Path | None = None, timeout: float = 60):
        self.resources = resources or resource_directory()
        self.timeout = timeout
        self._serial = threading.Lock()
        self._state = threading.Lock()
        self._process = None
        self._epoch = 0
        self._request_id = 0
        self._responses = None

    @property
    def pid(self):
        with self._state:
            return self._process.pid if self._process and self._process.poll() is None else None

    def close(self):
        with self._state:
            self._epoch += 1
            process, self._process = self._process, None
        if process:
            try:
                stop_process(process)
            except OSError:
                pass
        # The reader owns pipe closure/reaping. No waits on the UI thread.

    @staticmethod
    def _read(process, responses):
        try:
            for line in process.stdout:
                if len(line) > 100_000:
                    break
                responses.put(json.loads(line))
        except (OSError, ValueError):
            pass
        finally:
            responses.put(None)
            stop_process(process)
            process.wait()
            process.stdout.close()
            process.stdin.close()

    def _start(self, epoch):
        with self._state:
            if epoch != self._epoch:
                raise TranslationError("本地翻译已取消。")
            if self._process and self._process.poll() is None:
                return self._process, self._responses, False
            if self._process:
                # A crashed launcher may have left an inherited stdout pipe in
                # its child. Close the old job before replacing the session.
                stop_process(self._process)
            if getattr(sys, "frozen", False):
                command = [str(Path(sys.executable).with_name("ArgosWorker.exe")), str(self.resources)]
            else:
                executable = Path(sys.executable)
                if executable.name.lower() == "pythonw.exe":
                    executable = executable.with_name("python.exe")
                command = [str(executable), "-m", "screen_translator.services.argos_worker", str(self.resources)]
            environment = os.environ.copy()
            if not getattr(sys, "frozen", False):
                environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
            try:
                process = start_process(command, environment)
            except OSError:
                raise TranslationError("无法启动离线工作进程，请重新解压完整试用包后重试。") from None
            responses = queue.Queue(maxsize=4)
            self._process, self._responses = process, responses
            threading.Thread(target=self._read, args=(process, responses), daemon=True).start()
            return process, responses, True

    def _receive(self, responses, epoch, deadline):
        while time.monotonic() < deadline:
            with self._state:
                if self._epoch != epoch:
                    raise TranslationError("本地翻译已取消。")
            try:
                response = responses.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if not isinstance(response, dict):
                raise TranslationError("离线工作进程已退出，请主动重试。")
            if response.get("error"):
                raise TranslationError(response["error"])
            return response
        raise TranslationError("本地翻译超时，模型已释放，请缩短原文后重试。")

    def translate(self, text: str, target: str, source: str = "auto", *, ticket: int | None = None) -> str:
        source, target = validate_request(text, target, source)
        if source == target:
            return text
        if not self._serial.acquire(blocking=False):
            raise TranslationError("上一个本地任务正在收尾，请稍后重试。")
        try:
            with self._state:
                epoch = self._epoch if ticket is None else ticket
            process, responses, started = self._start(epoch)
            deadline = time.monotonic() + self.timeout
            if started and not self._receive(responses, epoch, deadline).get("ready"):
                raise TranslationError("离线工作进程未能就绪，请检查资源后重试。")
            self._request_id += 1
            process.stdin.write(json.dumps({"id": self._request_id, "text": text,
                                           "source": source, "target": target}, ensure_ascii=False) + "\n")
            process.stdin.flush()
            response = self._receive(responses, epoch, deadline)
            if response.get("id") != self._request_id or not isinstance(response.get("result"), str) or not response["result"].strip():
                raise TranslationError("离线组件响应无效，请主动重试。")
            return response["result"]
        except (OSError, ValueError, TranslationError) as error:
            self.close()
            if isinstance(error, TranslationError):
                raise
            raise TranslationError("离线工作进程已退出，请主动重试。") from None
        finally:
            self._serial.release()

    def ticket(self) -> int:
        with self._state:
            return self._epoch
