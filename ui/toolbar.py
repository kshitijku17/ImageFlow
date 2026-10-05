from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)


class HeaderWidget(QWidget):
    """Header widget containing brand title, subtitle, theme toggle, and statistics cards."""
    theme_toggled = Signal()

    def __init__(self, is_dark: bool = False, parent=None):
        super().__init__(parent)
        header = QHBoxLayout(self)
        header.setContentsMargins(0, 0, 0, 0)

        brand = QVBoxLayout()
        title = QLabel("📷 IMAGEFLOW")
        title.setObjectName("brand")
        subtitle = QLabel("Smart Photo Selection for Photographers")
        subtitle.setObjectName("subtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()

        self.theme_toggle = QPushButton("☾ Dark")
        self.theme_toggle.setObjectName("themeToggle")
        self.theme_toggle.setCheckable(True)
        self.theme_toggle.setChecked(is_dark)
        self.theme_toggle.setText("☀ Light" if is_dark else "☾ Dark")
        self.theme_toggle.clicked.connect(self.theme_toggled.emit)
        header.addWidget(self.theme_toggle)

        stats = QFrame()
        stats.setObjectName("stats")
        stats_l = QHBoxLayout(stats)
        stats_l.setContentsMargins(20, 10, 20, 10)
        self.total_label = self._create_stat(stats_l, "▧", "Total Images", "0")
        self.selected_label = self._create_stat(stats_l, "☑", "Selected", "0")
        self.copied_label = self._create_stat(stats_l, "▣", "Copied", "0")
        self.deleted_label = self._create_stat(stats_l, "♜", "Deleted", "0")
        header.addWidget(stats)

    def _create_stat(self, layout: QHBoxLayout, icon: str, name: str, value: str) -> QLabel:
        box = QVBoxLayout()
        label = QLabel(f"{icon}   {name}")
        val = QLabel(value)
        val.setObjectName("statValue")
        box.addWidget(label)
        box.addWidget(val)
        layout.addLayout(box)
        return val

    def update_stats(self, total: int, selected: int, copied: int, deleted: int):
        self.total_label.setText(str(total))
        self.selected_label.setText(str(selected))
        self.copied_label.setText(str(copied))
        self.deleted_label.setText(str(deleted))

    def update_theme_button(self, is_dark: bool):
        self.theme_toggle.setChecked(is_dark)
        self.theme_toggle.setText("☀ Light" if is_dark else "☾ Dark")


class FolderCard(QFrame):
    """Card displaying a folder title, path, and a 'Choose' button."""
    choose_clicked = Signal()

    def __init__(self, title: str, path: str, icon: str, parent=None):
        super().__init__(parent)
        self.setObjectName("folderCard")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)

        text = QVBoxLayout()
        t = QLabel(title)
        t.setObjectName("cardTitle")
        self.path_label = QLabel(path if path else "")
        self.path_label.setObjectName("pathLabel")
        self.path_label.setWordWrap(False)
        self.path_label.setMinimumWidth(0)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.path_label.setMinimumHeight(20)
        text.addWidget(t)
        text.addWidget(self.path_label)
        lay.addLayout(text, 1)

        b = QPushButton(f"{icon}  Choose")
        b.setObjectName("folderButton")
        b.setFixedSize(120, 42)
        b.clicked.connect(self.choose_clicked.emit)
        lay.addWidget(b)

    def set_path(self, path: str):
        self.path_label.setText(str(path))
        self.path_label.setToolTip(str(path))


class ActionCard(QFrame):
    """Large action card with key trigger button, title, description, and icon."""
    triggered = Signal()

    def __init__(self, key: str, title: str, desc: str, icon: str, danger: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("dangerCard" if danger else "actionCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)

        keyb = QPushButton(key)
        keyb.setObjectName("dangerKey" if danger else "keyButton")
        keyb.setFixedSize(88 if len(key) > 4 else 52, 42)
        keyb.clicked.connect(self.triggered.emit)
        lay.addWidget(keyb)

        text = QVBoxLayout()
        t = QLabel(title)
        t.setObjectName("dangerTitle" if danger else "greenTitle")
        d = QLabel(desc)
        d.setWordWrap(True)
        text.addWidget(t)
        text.addWidget(d)
        lay.addLayout(text, 1)

        iconb = QPushButton(icon)
        iconb.setFlat(True)
        iconb.clicked.connect(self.triggered.emit)
        lay.addWidget(iconb)


class KeyActionWidget(QWidget):
    """Compact shortcut row with a clickable key button and descriptive text."""
    triggered = Signal()

    def __init__(self, key: str, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(8)

        k = QPushButton(key)
        k.setObjectName("keySmall")
        k.setFixedWidth(76 if len(key) > 4 else 52)
        k.setFixedHeight(36)
        k.clicked.connect(self.triggered.emit)
        lay.addWidget(k)

        label = QLabel(text)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(label, 1)


class AICard(QFrame):
    """Side panel card for opening AI image search."""
    open_ai_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        ail = QVBoxLayout(self)
        ail.setContentsMargins(18, 16, 18, 16)

        ai_title = QLabel("🤖  AI INTEGRATION")
        ai_title.setObjectName("purpleTitle")
        ai_desc = QLabel("Search and interact with AI")
        ai_desc.setWordWrap(True)
        ai_btn = QPushButton("Open AI Chat")
        ai_btn.clicked.connect(self.open_ai_clicked.emit)

        ail.addWidget(ai_title)
        ail.addWidget(ai_desc)
        ail.addWidget(ai_btn, alignment=Qt.AlignCenter)
