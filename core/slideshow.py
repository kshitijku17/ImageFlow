from PySide6.QtCore import QObject, QTimer, Signal


class SlideshowController(QObject):
    """Controls automatic slideshow timing and triggers image progression."""
    timeout = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timeout.emit)

    def start(self, seconds: int = 3):
        self.timer.start(max(1, int(seconds)) * 1000)

    def stop(self):
        if self.timer.isActive():
            self.timer.stop()

    def is_active(self) -> bool:
        return self.timer.isActive()
