from PySide6.QtCore import QObject, Signal, QRunnable
from PySide6.QtGui import QImageReader, QImage


class ImageLoadSignals(QObject):
    ready = Signal(int, str, object)
    finished = Signal()


class ImageLoadWorker(QRunnable):
    _active_workers = set()

    def __init__(self, generation: int, index: int, path: str):
        super().__init__()
        self.generation = generation
        self.index = index
        self.path = str(path)
        self.signals = ImageLoadSignals()
        ImageLoadWorker._active_workers.add(self)
        self.signals.finished.connect(self._cleanup)

    def _cleanup(self):
        ImageLoadWorker._active_workers.discard(self)

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            image = reader.read()
            self.signals.ready.emit(self.generation, self.path, image)
        except Exception:
            self.signals.ready.emit(self.generation, self.path, QImage())
        finally:
            self.signals.finished.emit()

