from PySide6.QtCore import QObject, Signal, QRunnable


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    _active_workers = set()

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()
        Worker._active_workers.add(self)
        self.signals.finished.connect(self._cleanup)

    def _cleanup(self):
        Worker._active_workers.discard(self)

    def run(self):
        try:
            result = self.fn()
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()