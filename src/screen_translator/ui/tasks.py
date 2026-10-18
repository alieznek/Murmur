from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal
from screen_translator.services.translator import TranslationError


class WorkerSignals(QObject):
    result = Signal(object, object)
    error = Signal(object, str)
    finished = Signal(object)


class FunctionWorker(QRunnable):
    def __init__(self, function, context=None, *, failure_message: str | None = None):
        super().__init__()
        self.function = function
        self.context = context
        self.failure_message = failure_message
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.context, self.function())
        except Exception as error:
            message = str(error) if self.failure_message is None or isinstance(error, TranslationError) else self.failure_message
            self.signals.error.emit(self.context, message)
        finally:
            self.signals.finished.emit(self)
