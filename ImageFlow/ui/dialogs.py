from pathlib import Path
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGroupBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QDialogButtonBox,
)


class FilterDialog(QDialog):
    def __init__(self, parent, paths):
        super().__init__(parent)
        self.original = list(paths)
        self.setWindowTitle("ImageFlow Filter")
        self.resize(460, 300)
        l = QVBoxLayout(self)

        g = QGroupBox("Filter")
        gl = QGridLayout(g)
        gl.addWidget(QLabel("File name contains:"), 0, 0)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. vacation")
        gl.addWidget(self.name, 0, 1)

        gl.addWidget(QLabel("Extension:"), 1, 0)
        self.ext = QComboBox()
        self.ext.addItems(["All", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"])
        gl.addWidget(self.ext, 1, 1)
        l.addWidget(g)

        self.count = QLabel(f"{len(paths)} images")
        l.addWidget(self.count)
        self.name.textChanged.connect(self.update_count)
        self.ext.currentTextChanged.connect(self.update_count)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        l.addWidget(buttons)

    def filtered_paths(self):
        term = self.name.text().strip().lower()
        ext = self.ext.currentText().lower()
        result = []
        for p in self.original:
            pp = Path(p)
            if term and term not in pp.name.lower():
                continue
            if ext != "all" and pp.suffix.lower() != ext:
                continue
            result.append(p)
        return result

    def update_count(self):
        self.count.setText(f"{len(self.filtered_paths())} images")


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("ImageFlow Settings")
        self.resize(520, 380)
        self.s = dict(settings)
        l = QVBoxLayout(self)

        g = QGroupBox("Preferences")
        gl = QGridLayout(g)

        gl.addWidget(QLabel("Thumbnail quality:"), 0, 0)
        self.quality = QSpinBox()
        self.quality.setRange(30, 100)
        self.quality.setValue(int(self.s.get("thumb_quality", 80)))
        gl.addWidget(self.quality, 0, 1)

        gl.addWidget(QLabel("Slideshow seconds:"), 1, 0)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 60)
        self.seconds.setValue(int(self.s.get("slideshow_seconds", 3)))
        gl.addWidget(self.seconds, 1, 1)

        gl.addWidget(QLabel("Theme:"), 2, 0)
        self.theme = QComboBox()
        self.theme.addItems(["White", "Dark"])
        current_theme = str(self.s.get("theme", "White"))
        self.theme.setCurrentText("Dark" if current_theme.lower() == "dark" else "White")
        gl.addWidget(self.theme, 2, 1)

        self.recursive = QCheckBox("Scan subfolders recursively")
        self.recursive.setChecked(bool(self.s.get("recursive", False)))
        gl.addWidget(self.recursive, 3, 0, 1, 2)

        self.remember = QCheckBox("Remember selected source/destination folders")
        self.remember.setChecked(bool(self.s.get("remember_paths", True)))
        gl.addWidget(self.remember, 4, 0, 1, 2)

        l.addWidget(g)
        note = QLabel(
            "Performance: ImageFlow keeps file paths in memory and loads only the "
            "current full-resolution image plus a small timeline window."
        )
        note.setWordWrap(True)
        l.addWidget(note)
        l.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        l.addWidget(buttons)

    def values(self):
        return {
            "thumb_quality": self.quality.value(),
            "slideshow_seconds": self.seconds.value(),
            "theme": self.theme.currentText(),
            "recursive": self.recursive.isChecked(),
            "remember_paths": self.remember.isChecked(),
        }
