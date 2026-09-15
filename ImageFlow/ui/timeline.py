from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
)

from ui.thumbnail_bar import ThumbnailBar, ThumbnailButton


class TimelineWidget(QFrame):
    """Timeline container frame housing the horizontal thumbnail scroll area."""
    thumbnail_clicked = Signal(int)  # slot index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline")
        self.setMinimumHeight(112)
        self.setMaximumHeight(128)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        top = QHBoxLayout()
        tl_title = QLabel("☷  TIMELINE")
        tl_title.setObjectName("sectionTitle")
        top.addWidget(tl_title)
        top.addStretch()
        layout.addLayout(top)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setFrameShape(QFrame.NoFrame)

        self.bar = ThumbnailBar()
        self.bar.slot_clicked.connect(self.thumbnail_clicked.emit)
        self.thumb_scroll.setWidget(self.bar)
        layout.addWidget(self.thumb_scroll)

    @property
    def thumb_buttons(self) -> list[ThumbnailButton]:
        return self.bar.thumb_buttons

    def scroll_to_current(self, current_index: int):
        for b in self.bar.thumb_buttons:
            if b.property("image_index") == current_index:
                self.thumb_scroll.ensureWidgetVisible(b, 24, 0)
                break

    def clear(self):
        self.bar.clear_thumbnails()
