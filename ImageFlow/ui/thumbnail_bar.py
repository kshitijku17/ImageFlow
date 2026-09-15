from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton

from utils.constants import THUMB_COUNT


class ThumbnailButton(QPushButton):
    """Timeline thumbnail with a small selection checkbox overlay."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)

    def paintEvent(self, event):
        super().paintEvent(event)
        if bool(self.property("selected")):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            # Checkbox background in the top-right corner.
            box = 20
            x = self.width() - box - 5
            y = 5
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.white)
            painter.drawRoundedRect(x, y, box, box, 5, 5)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.black)
            painter.drawRoundedRect(x + 2, y + 2, box - 4, box - 4, 4, 4)
            painter.setPen(Qt.white)
            painter.drawText(x, y, box, box, Qt.AlignCenter, "✓")
            painter.end()


class ThumbnailBar(QWidget):
    """Row of thumbnail preview buttons with selection and loading states."""
    slot_clicked = Signal(int)  # slot index

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(8)
        self.thumb_buttons: list[ThumbnailButton] = []

        for slot in range(THUMB_COUNT):
            b = ThumbnailButton()
            b.setObjectName("thumb")
            b.setFixedSize(108, 70)
            b.clicked.connect(lambda checked=False, s=slot: self.slot_clicked.emit(s))
            self.thumb_buttons.append(b)
            self.layout.addWidget(b)

        self.layout.addStretch()

    def clear_thumbnails(self):
        for b in self.thumb_buttons:
            b.setText("")
            b.setIcon(QIcon())
            b.setEnabled(False)
            b.setChecked(False)
            b.setProperty("selected", False)
            b.setProperty("image_index", None)
            b.style().unpolish(b)
            b.style().polish(b)
            b.update()

    def set_button_image(self, slot: int, image: QImage):
        if 0 <= slot < len(self.thumb_buttons):
            b = self.thumb_buttons[slot]
            pix = QPixmap.fromImage(image)
            b.setIcon(pix)
            b.setIconSize(QSize(102, 62))
            b.setText("")

    def set_button_text(self, slot: int, text: str):
        if 0 <= slot < len(self.thumb_buttons):
            b = self.thumb_buttons[slot]
            b.setIcon(QIcon())
            b.setText(text)

    def configure_button(
        self,
        slot: int,
        valid: bool,
        image_index: int | None,
        is_current: bool,
        is_selected: bool = False
    ):
        if 0 <= slot < len(self.thumb_buttons):
            b = self.thumb_buttons[slot]
            b.setEnabled(valid)
            b.setProperty("image_index", image_index if valid else None)
            b.setChecked(valid and is_current)
            b.setProperty("selected", valid and is_selected)
            b.style().unpolish(b)
            b.style().polish(b)
            b.update()
            if not valid:
                b.setText("")
                b.setIcon(QIcon())

    def get_button_image_index(self, slot: int) -> int | None:
        if 0 <= slot < len(self.thumb_buttons):
            return self.thumb_buttons[slot].property("image_index")
        return None

    def get_button_at(self, slot: int) -> ThumbnailButton | None:
        if 0 <= slot < len(self.thumb_buttons):
            return self.thumb_buttons[slot]
        return None
