from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)

from ai.search import search_images


class AISearchWindow(QMainWindow):
    """Separate second screen. It is functional as a local image-search UI."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("ImageFlow AI")
        self.resize(1280, 820)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(36, 28, 36, 28)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("IMAGEFLOW AI ✨")
        title.setStyleSheet("font-size:34px;font-weight:800;color:#243c67;")
        sub = QLabel("Find your photographs using natural language")
        sub.setStyleSheet("font-size:15px;color:#778197;")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        header.addLayout(title_box)
        header.addStretch()

        back = QPushButton("←  Back to ImageFlow")
        back.clicked.connect(self.close)
        header.addWidget(back)
        root.addLayout(header)

        search_card = QFrame()
        search_card.setStyleSheet("QFrame{border:1px solid #dfe4ec;border-radius:14px;background:white;}")
        sl = QVBoxLayout(search_card)
        h = QLabel("AI Image Search")
        h.setStyleSheet("font-size:18px;font-weight:700;color:#3d4560;")
        sl.addWidget(h)

        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Describe the image you want to find…")
        self.send = QPushButton("Send  ➤")
        self.send.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.send)
        sl.addLayout(row)

        chips = QHBoxLayout()
        for text in ["🐕 Dogs", "👨‍👩‍👧 Family", "☀ Sunsets", "△ Mountains", "▣ Photos from 2025"]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked=False, t=text: self.query.setText(t.split(" ", 1)[-1]))
            chips.addWidget(b)
        chips.addStretch()
        sl.addLayout(chips)
        root.addWidget(search_card)

        self.results = QListWidget()
        self.results.setStyleSheet(
            "QListWidget{border:1px solid #dfe4ec;border-radius:14px;background:white;padding:16px;}"
        )
        root.addWidget(self.results, 1)

        self.status = QLabel("Search your images")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("font-size:20px;color:#414b62;")
        root.addWidget(self.status)

        self.apply_theme()

    def apply_theme(self):
        settings = getattr(self.parent_window, "settings", {})
        dark = str(settings.get("theme", "White")).lower() == "dark"
        if dark:
            self.setStyleSheet("""QMainWindow,QWidget{background:#171a21;color:#e7ebf3;font-family:"Segoe UI";} QFrame{background:#20242d;border:1px solid #343b49;border-radius:14px;} QLineEdit{border:1px solid #3d4656;border-radius:8px;padding:11px;background:#20252e;color:#edf1f7;} QPushButton{border:1px solid #3b4352;border-radius:8px;padding:9px 14px;background:#252a34;color:#e8edf5;} QPushButton:hover{background:#2c3441;border-color:#6d91d8;} QListWidget{border:1px solid #343b49;border-radius:14px;background:#20242d;padding:16px;color:#e7ebf3;}""")
        else:
            self.setStyleSheet("""QMainWindow,QWidget{background:#ffffff;color:#29344b;font-family:"Segoe UI";} QFrame{background:white;border:1px solid #dfe4ec;border-radius:14px;} QLineEdit{border:1px solid #d5dce7;border-radius:8px;padding:11px;background:white;} QPushButton{border:1px solid #d5dce7;border-radius:8px;padding:9px 14px;background:white;color:#29344b;} QPushButton:hover{background:#f4f7ff;border-color:#7651c8;} QListWidget{border:1px solid #dfe4ec;border-radius:14px;background:white;padding:16px;color:#29344b;}""")

    def search(self):
        query = self.query.text().strip()
        if not query:
            QMessageBox.information(self, "AI Search", "Enter a description first.")
            return
        paths = getattr(self.parent_window, "paths", [])
        if not paths and hasattr(self.parent_window, "image_manager"):
            paths = self.parent_window.image_manager.paths

        matches = search_images(paths, query)
        self.results.clear()
        for score, p in matches[:100]:
            item = QListWidgetItem(f"{Path(p).name}   —   {p}")
            item.setData(Qt.UserRole, p)
            self.results.addItem(item)
        if matches:
            self.status.setText(f"Found {len(matches)} matching image(s)")
        else:
            self.status.setText(
                "No filename matches. Connect your preferred AI/embedding backend here "
                "for true visual semantic search."
            )
