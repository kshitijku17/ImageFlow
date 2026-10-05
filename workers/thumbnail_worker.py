from PySide6.QtCore import QObject, Signal, QRunnable, QSize
from PySide6.QtGui import QImageReader


class ThumbSignals(QObject):
    ready = Signal(int, str, object)
    finished = Signal()


class ThumbnailWorker(QRunnable):
    _active_workers = set()

    def __init__(self, index, path, size: QSize, quality: int = 80):
        super().__init__()
        self.index = index
        self.path = str(path)
        self.size = size
        self.quality = quality
        self.signals = ThumbSignals()
        ThumbnailWorker._active_workers.add(self)
        self.signals.finished.connect(self._cleanup)

    def _cleanup(self):
        ThumbnailWorker._active_workers.discard(self)

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            reader.setQuality(self.quality)
            reader.setScaledSize(self.size)
            image = reader.read()
            if image.isNull():
                reader2 = QImageReader(self.path)
                reader2.setAutoTransform(True)
                image = reader2.read()
                if not image.isNull():
                    image = image.scaled(self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if image.isNull():
                self.signals.ready.emit(self.index, self.path, None)
            else:
                self.signals.ready.emit(self.index, self.path, image)
        except Exception:
            self.signals.ready.emit(self.index, self.path, None)
        finally:
            self.signals.finished.emit()