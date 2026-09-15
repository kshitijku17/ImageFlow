from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)


class ImageViewer(QFrame):
    """Central image display widget with zoom, fit mode, navigation triggers, and double-click fullscreen."""
    prev_clicked = Signal()
    next_clicked = Signal()
    fit_clicked = Signal()
    fullscreen_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imageFrame")
        self.current_image: QImage = QImage()
        self.zoom: float = 1.0
        self.fit_mode: bool = True

        image_l = QGridLayout(self)
        image_l.setContentsMargins(18, 10, 18, 12)

        self.image_number = QLabel("Image 0 / 0")
        self.image_number.setObjectName("imageNumber")
        image_l.addWidget(self.image_number, 0, 1, alignment=Qt.AlignCenter)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.fit_image)
        fit_btn.clicked.connect(self.fit_clicked.emit)

        fs_btn = QPushButton("⛶")
        fs_btn.setToolTip("Full Screen")
        fs_btn.clicked.connect(self.fullscreen_requested.emit)

        top_tools = QHBoxLayout()
        top_tools.addStretch()
        top_tools.addWidget(fit_btn)
        top_tools.addWidget(fs_btn)
        image_l.addLayout(top_tools, 0, 2)

        self.prev_btn = self._nav_button("←", "Prev\n(←)", self.prev_clicked.emit)
        self.next_btn = self._nav_button("→", "Next\n(→)", self.next_clicked.emit)
        image_l.addWidget(self.prev_btn, 1, 0, alignment=Qt.AlignVCenter)
        image_l.addWidget(self.next_btn, 1, 2, alignment=Qt.AlignVCenter)

        self.image_label = QLabel()
        self.image_label.setObjectName("imageLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.mouseDoubleClickEvent = self._image_double_click
        image_l.addWidget(self.image_label, 1, 1)

    def _nav_button(self, arrow, text, fn):
        b = QPushButton(f"{arrow}\n{text}")
        b.setObjectName("navButton")
        b.setFixedSize(72, 112)
        b.clicked.connect(fn)
        return b

    def _image_double_click(self, event):
        self.fullscreen_requested.emit()
        event.accept()

    def set_image(self, image: QImage, index: int, total: int):
        self.current_image = image
        self.image_number.setText(f"Image {index + 1} / {total}")
        self.render_current()

    def set_loading(self, index: int, total: int):
        self.image_number.setText(f"Image {index + 1} / {total}")
        self.image_label.setText("Loading image…")

    def set_scanning(self):
        self.image_label.clear()
        self.image_label.setText("Scanning folder…")
        self.image_number.setText("Image 0 / 0")

    def set_message(self, text: str):
        self.current_image = QImage()
        self.image_label.clear()
        self.image_label.setText(text)

    def set_counter(self, text: str):
        self.image_number.setText(text)

    def clear(self):
        self.current_image = QImage()
        self.image_label.clear()
        self.image_number.setText("Image 0 / 0")

    def render_current(self):
        if self.current_image.isNull():
            return
        available = self.image_label.size()
        if self.fit_mode:
            pix = QPixmap.fromImage(self.current_image)
            pix = pix.scaled(available, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            size = self.current_image.size() * self.zoom
            pix = QPixmap.fromImage(self.current_image).scaled(
                size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        self.image_label.setPixmap(pix)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_current()

    def zoom_in(self):
        self.fit_mode = False
        self.zoom = min(4.0, self.zoom * 1.15)
        self.render_current()

    def zoom_out(self):
        self.fit_mode = False
        self.zoom = max(0.1, self.zoom / 1.15)
        self.render_current()

    def fit_image(self):
        self.fit_mode = True
        self.zoom = 1.0
        self.render_current()

    def update_nav(self, can_prev: bool, can_next: bool):
        self.prev_btn.setEnabled(can_prev)
        self.next_btn.setEnabled(can_next)
