from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class ImageOnlyFullscreen(QWidget):
    """Dedicated fullscreen viewer; the main ImageFlow window never enters fullscreen."""
    closed = Signal()

    def __init__(self, parent, image: QImage):
        super().__init__(None)
        self.parent_window = parent
        self.image = image
        self.setWindowTitle("ImageFlow — Image Viewer")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background:#000000; color:white;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.setStyleSheet("background:#000000;")
        self._render()

    def _render(self):
        if self.image.isNull():
            return
        pix = QPixmap.fromImage(self.image)
        target = self.size()
        if target.width() > 0 and target.height() > 0:
            pix = pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
