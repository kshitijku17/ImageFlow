from PySide6.QtCore import QObject, Signal, QRunnable, QSize
from PySide6.QtGui import QImageReader


class ThumbSignals(QObject):
    ready = Signal(int, str, object)


class ThumbnailWorker(QRunnable):
    def __init__(self, index, path, size: QSize, quality: int = 80):
        super().__init__()
        self.index = index
        self.path = str(path)
        self.size = size
        self.quality = quality
        self.signals = ThumbSignals()

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            reader.setQuality(self.quality)
            # Decode only a small thumbnail, not the full image.
            reader.setScaledSize(self.size)
            image = reader.read()
            if image.isNull():
                self.signals.ready.emit(self.index, self.path, None)
                return
            self.signals.ready.emit(self.index, self.path, image)
        except Exception:
            self.signals.ready.emit(self.index, self.path, None)