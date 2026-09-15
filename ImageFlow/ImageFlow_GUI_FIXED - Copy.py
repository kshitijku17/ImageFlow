
import sys
import os
import shutil
import json
import time
from pathlib import Path
from collections import OrderedDict

from PySide6.QtCore import (
    Qt, QObject, Signal, QRunnable, QThreadPool, QTimer, QSize, QUrl
)
from PySide6.QtGui import (
    QAction, QPixmap, QImage, QImageReader, QPainter, QKeySequence, QIcon,
    QDesktopServices, QKeyEvent
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QToolButton,
    QFrame, QFileDialog, QMessageBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QLineEdit, QDialog, QDialogButtonBox, QSlider, QCheckBox,
    QComboBox, QSpinBox, QGroupBox, QListWidget, QListWidgetItem, QProgressBar,
    QSizePolicy, QSplitter
)

APP_NAME = "ImageFlow"
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
THUMB_COUNT = 9
THUMB_SIZE = QSize(118, 82)
MAX_CACHE = 120
CONFIG_PATH = Path.home() / ".imageflow_settings.json"


def load_settings():
    defaults = {
        "thumb_quality": 80,
        "theme": "White",
        "recursive": False,
        "slideshow_seconds": 3,
        "remember_paths": True,
    }
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        defaults.update(data)
    except Exception:
        pass
    return defaults


def save_settings(settings):
    try:
        CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn()
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class ThumbSignals(QObject):
    ready = Signal(int, str, object)


class ThumbnailWorker(QRunnable):
    def __init__(self, index, path, size, quality=80):
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


class ImageLoadSignals(QObject):
    ready = Signal(int, str, object)


class ImageLoadWorker(QRunnable):
    def __init__(self, generation, index, path):
        super().__init__()
        self.generation = generation
        self.index = index
        self.path = str(path)
        self.signals = ImageLoadSignals()

    def run(self):
        try:
            reader = QImageReader(self.path)
            reader.setAutoTransform(True)
            image = reader.read()
            self.signals.ready.emit(self.generation, self.path, image)
        except Exception:
            self.signals.ready.emit(self.generation, self.path, QImage())


class ImageFlowWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1536, 1000)
        self.setMinimumSize(1150, 760)

        self.settings = load_settings()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(8, os.cpu_count() or 4)))

        self.paths = []
        self.index = -1
        self.generation = 0
        self.selected = set()
        self.copied_count = 0
        self.deleted_count = 0
        self.last_deleted = None
        self.thumb_cache = OrderedDict()
        self.thumb_jobs = set()
        self.fullscreen = False
        self.fullscreen_viewer = None
        self.zoom = 1.0
        self.fit_mode = True
        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.timeout.connect(self.next_image)

        self._build_ui()
        self._apply_theme()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(7)

        # Header
        header = QHBoxLayout()
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
        self.theme_toggle.setChecked(str(self.settings.get("theme", "White")).lower() == "dark")
        self.theme_toggle.clicked.connect(self.toggle_theme)
        self.theme_toggle.setText(
            "☀ Light" if self.theme_toggle.isChecked() else "☾ Dark"
        )
        header.addWidget(self.theme_toggle)

        stats = QFrame()
        stats.setObjectName("stats")
        stats_l = QHBoxLayout(stats)
        stats_l.setContentsMargins(20, 10, 20, 10)
        self.total_label = self._stat(stats_l, "▧", "Total Images", "0")
        self.copied_label = self._stat(stats_l, "▣", "Copied", "0")
        self.deleted_label = self._stat(stats_l, "♜", "Deleted", "0")
        header.addWidget(stats)
        root.addLayout(header)

        # Folder row
        folders = QHBoxLayout()
        self.source_card = self._folder_card(
            "SOURCE FOLDER", "", "📁", self.choose_source
        )
        self.dest_card = self._folder_card(
            "DESTINATION FOLDER", "", "📂", self.choose_destination
        )
        folders.addWidget(self.source_card, 1)
        folders.addWidget(self.dest_card, 1)
        root.addLayout(folders)

        # Main splitter: image area + right controls
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)

        image_frame = QFrame()
        image_frame.setObjectName("imageFrame")
        image_l = QGridLayout(image_frame)
        image_l.setContentsMargins(18, 10, 18, 12)

        self.image_number = QLabel("Image 0 / 0")
        self.image_number.setObjectName("imageNumber")
        image_l.addWidget(self.image_number, 0, 1, alignment=Qt.AlignCenter)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.fit_image)
        fs_btn = QPushButton("⛶")
        fs_btn.setToolTip("Full Screen")
        fs_btn.clicked.connect(self.toggle_fullscreen)
        top_tools = QHBoxLayout()
        top_tools.addStretch()
        top_tools.addWidget(fit_btn)
        top_tools.addWidget(fs_btn)
        image_l.addLayout(top_tools, 0, 2)

        self.prev_btn = self._nav_button("←", "Prev\n(←)", self.previous_image)
        self.next_btn = self._nav_button("→", "Next\n(→)", self.next_image)
        image_l.addWidget(self.prev_btn, 1, 0, alignment=Qt.AlignVCenter)
        image_l.addWidget(self.next_btn, 1, 2, alignment=Qt.AlignVCenter)

        self.image_label = QLabel()
        self.image_label.setObjectName("imageLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.mouseDoubleClickEvent = self._image_double_click
        image_l.addWidget(self.image_label, 1, 1)

        left_l.addWidget(image_frame, 1)

        # Timeline
        timeline_frame = QFrame()
        timeline_frame.setObjectName("timeline")
        tl = QVBoxLayout(timeline_frame)
        tl.setContentsMargins(10, 6, 10, 6)
        top = QHBoxLayout()
        tl_title = QLabel("☷  TIMELINE")
        tl_title.setObjectName("sectionTitle")
        top.addWidget(tl_title)
        top.addStretch()
        tl.addLayout(top)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setFrameShape(QFrame.NoFrame)

        thumb_host = QWidget()
        self.thumb_layout = QHBoxLayout(thumb_host)
        self.thumb_layout.setContentsMargins(2, 2, 2, 2)
        self.thumb_layout.setSpacing(8)
        self.thumb_buttons = []
        for slot in range(THUMB_COUNT):
            b = QPushButton()
            b.setObjectName("thumb")
            b.setFixedSize(108, 70)
            b.clicked.connect(lambda checked=False, s=slot: self.thumb_clicked(s))
            self.thumb_buttons.append(b)
            self.thumb_layout.addWidget(b)
        self.thumb_layout.addStretch()
        self.thumb_scroll.setWidget(thumb_host)
        tl.addWidget(self.thumb_scroll)

        timeline_frame.setMinimumHeight(112)
        timeline_frame.setMaximumHeight(128)
        left_l.addWidget(timeline_frame, 0)


        splitter.addWidget(left)

        # Right panel
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_widget = QWidget()
        right_l = QVBoxLayout(right_widget)
        right_l.setContentsMargins(4, 0, 4, 0)
        right_l.setSpacing(12)

        right_l.addWidget(self._action_card(
            "Y", "SELECT / COPY",
            "Copy current image to destination folder",
            "▣", self.copy_current
        ))
        right_l.addWidget(self._action_card(
            "Delete", "DELETE",
            "Move image to the Recycle folder",
            "♜", self.delete_current, danger=True
        ))

        undo_card = self._action_card(
            "Z", "UNDO DELETE",
            "Restore the last deleted image",
            "↶", self.undo_delete
        )
        right_l.addWidget(undo_card)

        other = QFrame()
        other.setObjectName("card")
        ol = QVBoxLayout(other)
        ol.setContentsMargins(16, 14, 16, 14)
        ol.setSpacing(8)
        h = QLabel("OTHER ACTIONS")
        h.setObjectName("purpleTitle")
        ol.addWidget(h)
        ol.addWidget(self._key_action("M", "Move Image", self.move_current))
        ol.addWidget(self._key_action("+", "Zoom In", self.zoom_in))
        ol.addWidget(self._key_action("−", "Zoom Out", self.zoom_out))
        ol.addWidget(self._key_action("🖱", "Double Click — Full Screen", self.toggle_fullscreen))
        ol.addWidget(self._key_action("ESC", "Back to Source Folder", self.back_to_source))
        right_l.addWidget(other)

        ai = QFrame()
        ai.setObjectName("card")
        ail = QVBoxLayout(ai)
        ail.setContentsMargins(18, 16, 18, 16)
        ai_title = QLabel("🤖  AI INTEGRATION")
        ai_title.setObjectName("purpleTitle")
        ai_desc = QLabel("Search and interact with AI")
        ai_desc.setWordWrap(True)
        ai_btn = QPushButton("Open AI Chat")
        ai_btn.clicked.connect(self.open_ai_screen)
        ail.addWidget(ai_title)
        ail.addWidget(ai_desc)
        ail.addWidget(ai_btn, alignment=Qt.AlignCenter)
        right_l.addWidget(ai)

        right_l.addStretch(1)
        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1120, 340])
        root.addWidget(splitter, 1)

        # Keyboard shortcuts
        self._shortcut("Y", self.copy_current)
        self._shortcut("Delete", self.delete_current)
        self._shortcut("M", self.move_current)
        self._shortcut("+", self.zoom_in)
        self._shortcut("=", self.zoom_in)
        self._shortcut("-", self.zoom_out)
        self._shortcut("Escape", self.back_to_source)
        self._shortcut("Left", self.previous_image)
        self._shortcut("Right", self.next_image)
        self._shortcut("Ctrl+A", self.select_all)
        self._shortcut("Ctrl+D", self.deselect_all)
        self._shortcut("Ctrl+I", self.invert_selection)
        self._shortcut("Z", self.undo_delete)
        
    def _shortcut(self, key, fn):
        a = QAction(self)
        a.setShortcut(QKeySequence(key))
        a.triggered.connect(fn)
        self.addAction(a)

    def _stat(self, layout, icon, name, value):
        box = QVBoxLayout()
        l = QLabel(f"{icon}   {name}")
        v = QLabel(value)
        v.setObjectName("statValue")
        box.addWidget(l)
        box.addWidget(v)
        layout.addLayout(box)
        return v

    def _folder_card(self, title, path, icon, fn):
        card = QFrame()
        card.setObjectName("folderCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 12)
        text = QVBoxLayout()
        t = QLabel(title)
        t.setObjectName("cardTitle")
        p = QLabel(path if path else "")
        p.setObjectName("pathLabel")
        p.setWordWrap(False)
        p.setMinimumWidth(0)
        p.setTextInteractionFlags(Qt.TextSelectableByMouse)
        p.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        p.setMinimumHeight(20)
        text.addWidget(t)
        text.addWidget(p)
        lay.addLayout(text, 1)
        b = QPushButton(f"{icon}  Choose")
        b.setObjectName("folderButton")
        b.setFixedSize(120, 42)
        b.clicked.connect(fn)
        lay.addWidget(b)
        card.path_label = p
        return card

    def _nav_button(self, arrow, text, fn):
        b = QPushButton(f"{arrow}\n{text}")
        b.setObjectName("navButton")
        b.setFixedSize(72, 112)
        b.clicked.connect(fn)
        return b

    def _action_card(self, key, title, desc, icon, fn, danger=False):
        card = QFrame()
        card.setObjectName("dangerCard" if danger else "actionCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        keyb = QPushButton(key)
        keyb.setObjectName("dangerKey" if danger else "keyButton")
        keyb.setFixedSize(88 if len(key) > 4 else 52, 42)
        keyb.clicked.connect(fn)
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
        iconb.clicked.connect(fn)
        lay.addWidget(iconb)
        return card

    def _key_action(self, key, text, fn):
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 3, 0, 3)
        l.setSpacing(8)

        # The shortcut itself is a real clickable button.
        k = QPushButton(key)
        k.setObjectName("keySmall")
        k.setFixedWidth(76 if len(key) > 4 else 52)
        k.setFixedHeight(36)
        k.clicked.connect(fn)
        l.addWidget(k)

        label = QLabel(text)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        l.addWidget(label, 1)

        return w

    def _bottom_action(self, layout, icon, title, shortcut, fn):
        b = QPushButton()
        b.setObjectName("bottomAction")
        b.clicked.connect(fn)
        l = QHBoxLayout(b)
        l.setContentsMargins(10, 6, 10, 6)
        il = QLabel(icon)
        il.setObjectName("bottomIcon")
        tx = QVBoxLayout()
        t = QLabel(title)
        s = QLabel(shortcut)
        s.setObjectName("smallText")
        tx.addWidget(t)
        tx.addWidget(s)
        l.addWidget(il)
        l.addLayout(tx)
        layout.addWidget(b, 1)

    def _apply_theme(self):
        dark = str(self.settings.get("theme", "White")).lower() in {"dark", "black"}
        if dark:
            self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; font-size: 13px; color: #e7ebf3; }
            QMainWindow, QWidget { background: #171a21; }
            QLabel#brand { font-size: 39px; font-weight: 800; color: #72a8ff; letter-spacing: 1px; }
            QLabel#subtitle { color: #9aa6ba; font-size: 15px; }
            QFrame#stats, QFrame#folderCard, QFrame#imageFrame, QFrame#timeline,
            QFrame#bottomBar, QFrame#card, QFrame#actionCard, QFrame#dangerCard {
                background: #20242d; border: 1px solid #343b49; border-radius: 14px;
            }
            QFrame#stats { background: #1c2028; }
            QLabel#statValue { font-size: 21px; font-weight: 700; color: #78a9ff; }
            QLabel#cardTitle { font-weight: 700; color: #e4e9f2; }
            QLabel#pathLabel { color: #9da8ba; }
            QLabel#imageNumber { font-size: 17px; font-weight: 700; }
            QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
            QPushButton { background: #252a34; border: 1px solid #3b4352; border-radius: 8px; padding: 7px 12px; color: #e8edf5; }
            QPushButton:hover { background: #2c3441; border-color: #6d91d8; }
            QPushButton:pressed { background: #333c4b; }
            QPushButton#navButton { font-size: 14px; font-weight: 600; }
            QPushButton#thumb { padding: 2px; border-radius: 9px; background: #1b1f27; }
            QPushButton#thumb:checked { border: 2px solid #8a62e6; }
            QPushButton#keyButton, QPushButton#dangerKey { font-size: 16px; font-weight: 700; }
            QPushButton#dangerKey { color: #ff7777; border-color: #744040; }
            QLabel#greenTitle { color: #69c394; font-weight: 700; }
            QLabel#dangerTitle { color: #ff6e6e; font-weight: 700; }
            QLabel#purpleTitle { color: #b08bea; font-weight: 700; }
            QLabel#keySmall { background: #292e39; border: 1px solid #414958; border-radius: 6px; color: #b99ce9; font-weight: 700; padding: 5px; }
            QPushButton#bottomAction { border: none; border-right: 1px solid #343b49; border-radius: 0; }
            QPushButton#bottomAction:hover { background: #252b35; }
            QLabel#bottomIcon { font-size: 20px; }
            QLabel#smallText { color: #929db0; font-size: 11px; }
            QLineEdit, QSpinBox, QComboBox { border: 1px solid #3d4656; border-radius: 7px; padding: 7px; background: #20252e; color: #edf1f7; }
            QScrollBar:vertical { width: 10px; background: #1b1f26; }
            QScrollBar::handle:vertical { background: #4b5567; border-radius: 5px; }
            QDialog, QGroupBox { background: #20242d; color: #e7ebf3; }
            QCheckBox { color: #e7ebf3; }
            """)
        else:
            self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; font-size: 13px; color: #27344d; }
            QMainWindow, QWidget { background: #ffffff; }
            QLabel#brand { font-size: 39px; font-weight: 800; color: #2d72c9; letter-spacing: 1px; }
            QLabel#subtitle { color: #7a8496; font-size: 15px; }
            QFrame#stats, QFrame#folderCard, QFrame#imageFrame, QFrame#timeline,
            QFrame#bottomBar, QFrame#card, QFrame#actionCard, QFrame#dangerCard {
                background: #ffffff; border: 1px solid #e0e5ee; border-radius: 14px;
            }
            QFrame#stats { background: #fbfcfe; }
            QLabel#statValue { font-size: 21px; font-weight: 700; color: #2b66bd; }
            QLabel#cardTitle { font-weight: 700; color: #33415c; }
            QLabel#pathLabel { color: #68758a; }
            QLabel#imageNumber { font-size: 17px; font-weight: 700; }
            QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
            QPushButton { background: #ffffff; border: 1px solid #d8deea; border-radius: 8px; padding: 7px 12px; color: #33415c; }
            QPushButton:hover { background: #f3f7ff; border-color: #83aee8; }
            QPushButton:pressed { background: #e8f0ff; }
            QPushButton#navButton { font-size: 14px; font-weight: 600; }
            QPushButton#thumb { padding: 2px; border-radius: 9px; }
            QPushButton#thumb:checked { border: 2px solid #7546c7; }
            QPushButton#keyButton, QPushButton#dangerKey { font-size: 16px; font-weight: 700; }
            QPushButton#dangerKey { color: #d83c3c; border-color: #efb6b6; }
            QLabel#greenTitle { color: #3a9d70; font-weight: 700; }
            QLabel#dangerTitle { color: #df4343; font-weight: 700; }
            QLabel#purpleTitle { color: #7044b8; font-weight: 700; }
            QLabel#keySmall { background: #f7f8fb; border: 1px solid #dce1eb; border-radius: 6px; color: #5e4a9e; font-weight: 700; padding: 5px; }
            QPushButton#bottomAction { border: none; border-right: 1px solid #e2e6ee; border-radius: 0; }
            QPushButton#bottomAction:hover { background: #f7f9fc; }
            QLabel#bottomIcon { font-size: 20px; }
            QLabel#smallText { color: #8791a1; font-size: 11px; }
            QLineEdit, QSpinBox, QComboBox { border: 1px solid #d6dce7; border-radius: 7px; padding: 7px; background: white; color: #27344d; }
            QScrollBar:vertical { width: 10px; background: #f4f5f7; }
            QScrollBar::handle:vertical { background: #c7cfdd; border-radius: 5px; }
            """)

    # ---------- Folder / indexing ----------
    def _restore_paths(self):
        if not self.settings.get("remember_paths", True):
            return
        src = self.settings.get("source", "")
        dst = self.settings.get("destination", "")
        if src and Path(src).is_dir():
            self._set_source_path(Path(src))
        if dst and Path(dst).is_dir():
            self._set_dest_path(Path(dst))

    def choose_source(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Source Folder", str(Path.home()))
        if path:
            self._set_source_path(Path(path))

    def _set_source_path(self, path):
        self.settings["source"] = str(path)
        save_settings(self.settings)
        self.source_card.path_label.setText(str(path))
        self.source_card.path_label.setToolTip(str(path))
        self._scan_source(path)

    def choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Destination Folder", str(Path.home()))
        if path:
            self._set_dest_path(Path(path))

    def _set_dest_path(self, path):
        self.settings["destination"] = str(path)
        save_settings(self.settings)
        self.dest_card.path_label.setText(str(path))
        self.dest_card.path_label.setToolTip(str(path))

    def _scan_source(self, folder):
        self.paths = []
        self.index = -1
        self.selected.clear()
        self.thumb_cache.clear()
        self._clear_thumbnails()
        self.image_label.clear()
        self.image_label.setText("Scanning folder…")
        self._set_enabled(False)

        recursive = bool(self.settings.get("recursive", False))

        def scan():
            result = []
            iterator = folder.rglob("*") if recursive else folder.iterdir()
            for p in iterator:
                try:
                    if p.is_file() and p.suffix.lower() in SUPPORTED:
                        result.append(str(p))
                except OSError:
                    pass
            result.sort(key=lambda x: x.lower())
            return result

        w = Worker(scan)
        w.signals.result.connect(self._scan_finished)
        w.signals.error.connect(lambda e: self._scan_error(e))
        self.pool.start(w)

    def _scan_finished(self, result):
        self.paths = result
        self._set_enabled(True)
        self.total_label.setText(str(len(self.paths)))
        if self.paths:
            self.show_image(0)
        else:
            self.image_label.setText("No supported images found")
            self.image_number.setText("Image 0 / 0")
        self._update_stats()

    def _scan_error(self, error):
        self._set_enabled(True)
        QMessageBox.critical(self, "Folder Scan Error", error)

    def _set_enabled(self, enabled):
        for b in [self.prev_btn, self.next_btn]:
            b.setEnabled(enabled and bool(self.paths))

    # ---------- Images ----------
    def show_image(self, index):
        if not self.paths:
            return
        index = max(0, min(index, len(self.paths) - 1))
        self.index = index
        self.generation += 1
        generation = self.generation
        path = self.paths[index]
        self.image_number.setText(f"Image {index + 1} / {len(self.paths)}")
        self._update_nav()
        self._update_timeline()

        self.image_label.setText("Loading image…")
        worker = ImageLoadWorker(generation, index, path)
        worker.signals.ready.connect(self._image_loaded)
        worker.signals.ready.connect(
            lambda *_: self._image_worker_finished(worker)
        )
        self._active_image_worker = worker
        self.pool.start(worker)

    def _image_loaded(self, generation, path, image):
        if generation != self.generation or self.index < 0:
            return
        if str(self.paths[self.index]) != str(path):
            return
        if image.isNull():
            self.image_label.setText("Unable to read image")
            return
        self.current_image = image
        self._render_current()

    def _image_worker_finished(self, worker):
        if getattr(self, "_active_image_worker", None) is worker:
            self._active_image_worker = None

    def _image_double_click(self, event):
        self.toggle_fullscreen()
        event.accept()

    def _render_current(self):
        if not hasattr(self, "current_image") or self.current_image.isNull():
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
        if hasattr(self, "current_image"):
            self._render_current()

    def _update_nav(self):
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(0 <= self.index < len(self.paths) - 1)

    def previous_image(self):
        if self.index > 0:
            self.show_image(self.index - 1)

    def next_image(self):
        if self.index < len(self.paths) - 1:
            self.show_image(self.index + 1)
        elif self.slideshow_timer.isActive():
            self.show_image(0)

    def _clear_thumbnails(self):
        for b in self.thumb_buttons:
            b.setText("")
            b.setIcon(QIcon())
            b.setEnabled(False)
            b.setChecked(False)
            b.setProperty("image_index", None)
            b.style().unpolish(b)
            b.style().polish(b)

    def _update_timeline(self):
        if not self.paths:
            self._clear_thumbnails()
            return

        # Keep the current image near the center of the timeline.
        half = THUMB_COUNT // 2
        start = max(0, min(self.index - half, len(self.paths) - THUMB_COUNT))

        for slot, b in enumerate(self.thumb_buttons):
            idx = start + slot
            valid = idx < len(self.paths)
            b.setEnabled(valid)
            b.setProperty("image_index", idx if valid else None)
            b.setChecked(valid and idx == self.index)

            if not valid:
                b.setText("")
                b.setIcon(QIcon())
                continue

            key = str(self.paths[idx])
            cached = self.thumb_cache.get(key)
            if cached is not None:
                self._set_thumb_button(b, cached)
            else:
                b.setIcon(QIcon())
                b.setText("Loading…")
                if key not in self.thumb_jobs:
                    self.thumb_jobs.add(key)
                    w = ThumbnailWorker(
                        idx, key, THUMB_SIZE,
                        self.settings.get("thumb_quality", 80)
                    )
                    w.signals.ready.connect(self._thumb_ready)
                    self.pool.start(w)

        # Keep the selected thumbnail visible when the timeline is resized.
        if 0 <= self.index < len(self.paths):
            QTimer.singleShot(0, lambda: self._scroll_thumb_to_current())

    def _scroll_thumb_to_current(self):
        if not self.thumb_buttons or not self.paths:
            return
        for b in self.thumb_buttons:
            if b.property("image_index") == self.index:
                self.thumb_scroll.ensureWidgetVisible(b, 24, 0)
                break

    def _thumb_ready(self, index, path, image):
        self.thumb_jobs.discard(path)
        if image is not None and not image.isNull():
            self.thumb_cache[path] = image
            self.thumb_cache.move_to_end(path)
            while len(self.thumb_cache) > MAX_CACHE:
                self.thumb_cache.popitem(last=False)
        if not self.paths or not (0 <= index < len(self.paths)):
            return

        half = THUMB_COUNT // 2
        start = max(0, min(self.index - half, len(self.paths) - THUMB_COUNT))
        slot = index - start

        if 0 <= slot < len(self.thumb_buttons) and str(self.paths[index]) == path:
            b = self.thumb_buttons[slot]
            if image is not None and not image.isNull():
                self._set_thumb_button(b, image)
            else:
                b.setIcon(QIcon())
                b.setText(str(index + 1))

    def _set_thumb_button(self, button, image):
        pix = QPixmap.fromImage(image)
        button.setIcon(pix)
        button.setIconSize(QSize(102, 62))
        button.setText("")

    def thumb_clicked(self, slot):
        b = self.thumb_buttons[slot]
        idx = b.property("image_index")
        if idx is not None and 0 <= int(idx) < len(self.paths):
            self.show_image(int(idx))

    # ---------- Selection ----------
    def select_all(self):
        self.selected = set(range(len(self.paths)))
        self._update_stats()

    def deselect_all(self):
        self.selected.clear()
        self._update_stats()

    def invert_selection(self):
        all_indices = set(range(len(self.paths)))
        self.selected = all_indices - self.selected
        self._update_stats()

    def _update_stats(self):
        self.copied_label.setText(str(self.copied_count))
        self.deleted_label.setText(str(self.deleted_count))

    # ---------- File operations ----------
    def _destination(self):
        dst = self.settings.get("destination", "")
        if not dst or not Path(dst).is_dir():
            return None
        return Path(dst)

    def copy_current(self):
        if not self.paths or self.index < 0:
            QMessageBox.information(self, "Copy", "Select a source folder and image first.")
            return
        dst = self._destination()
        if dst is None:
            QMessageBox.warning(self, "Destination Required", "Please select a destination folder first.")
            return
        source = Path(self.paths[self.index])
        self._file_copy(source, dst)

    def _unique_target(self, dst, name):
        target = dst / name
        if not target.exists():
            return target
        stem, suffix = Path(name).stem, Path(name).suffix
        n = 1
        while True:
            candidate = dst / f"{stem} ({n}){suffix}"
            if not candidate.exists():
                return candidate
            n += 1

    def _file_copy(self, source, dst):
        self._set_enabled(False)

        def op():
            # Copy the original image to destination using its original name.
            target = self._unique_target(dst, source.name)
            shutil.copy2(source, target)

            # Then mark the source copy as selected:
            # photo.jpg -> photo-selected.jpg
            selected_source = source.with_name(
                f"{source.stem}-selected{source.suffix}"
            )

            if selected_source.exists():
                selected_source = self._unique_target(
                    source.parent,
                    f"{source.stem}-selected{source.suffix}"
                )

            source.rename(selected_source)
            return target, selected_source

        w = Worker(op)
        w.signals.result.connect(
            lambda result: self._copy_done(result[0], result[1])
        )
        w.signals.error.connect(lambda e: self._file_error("Copy failed", e))
        w.signals.finished.connect(lambda: self._set_enabled(True))
        self.pool.start(w)

    def _copy_done(self, target, selected_source):
        old_index = self.index

        # Update the in-memory source path because the source filename changed.
        if 0 <= old_index < len(self.paths):
            self.paths[old_index] = str(selected_source)

        self.copied_count += 1
        self._update_stats()
        self._update_timeline()
        self.statusBar().showMessage(
            f"Image copied: {target.name}  |  Source marked selected",
            5000
        )
        QMessageBox.information(
            self,
            "ImageFlow",
            f"Image copied to destination\\n{target.name}\\n\\n"
            f"Source renamed to\\n{selected_source.name}"
        )
        self.show_image(old_index)

    def move_current(self):
        if not self.paths or self.index < 0:
            QMessageBox.information(self, "Move", "Select an image first.")
            return
        dst = QFileDialog.getExistingDirectory(self, "Move Image To")
        if not dst:
            return
        source = Path(self.paths[self.index])
        destination = Path(dst)
        self._set_enabled(False)

        def op():
            target = self._unique_target(destination, source.name)
            shutil.move(str(source), str(target))
            return target

        w = Worker(op)
        w.signals.result.connect(lambda target: self._move_done(source, target))
        w.signals.error.connect(lambda e: self._file_error("Move failed", e))
        w.signals.finished.connect(lambda: self._set_enabled(True))
        self.pool.start(w)

    def _move_done(self, source, target):
        self._remove_current_from_index()
        self.statusBar().showMessage(f"Image moved: {source.name}", 4000)
        QMessageBox.information(self, "ImageFlow", f"Image moved\n{source.name}")

    def delete_current(self):
        if not self.paths or self.index < 0:
            QMessageBox.information(self, "Delete", "Select an image first.")
            return

        source = Path(self.paths[self.index])
        recycle = source.parent / "Recycle"
        old_index = self.index

        try:
            recycle.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self, "Delete", f"Could not create Recycle folder.\\n\\n{e}"
            )
            return

        target = self._unique_target(recycle, source.name)
        self._set_enabled(False)

        def op():
            shutil.move(str(source), str(target))
            return target

        w = Worker(op)
        w.signals.result.connect(
            lambda t: self._delete_done(source, t, old_index)
        )
        w.signals.error.connect(lambda e: self._file_error("Delete failed", e))
        w.signals.finished.connect(lambda: self._set_enabled(True))
        self.pool.start(w)

    def _delete_done(self, source, recycle_target, old_index):
        # Keep the exact original index so Z can put the image back in the same place.
        self.last_deleted = (source, recycle_target, old_index)
        self.deleted_count += 1

        if 0 <= old_index < len(self.paths):
            self.paths.pop(old_index)

        self.index = min(old_index, len(self.paths) - 1) if self.paths else -1
        self.selected.clear()
        self.total_label.setText(str(len(self.paths)))
        self._update_stats()
        self._update_timeline()

        # The image is gone from the UI immediately.
        self.current_image = QImage()
        self.image_label.clear()

        if self.paths:
            self.show_image(self.index)
        else:
            self.image_number.setText("Image 0 / 0")
            self.image_label.setText("No images in source folder")

        self.statusBar().showMessage(
            f"Image deleted: {source.name}  |  Z = Undo", 5000
        )
        QMessageBox.information(
            self, "ImageFlow",
            f"Image deleted\\n{source.name}\\n\\nMoved to Recycle."
        )

    def undo_delete(self):
        if not self.last_deleted:
            self.statusBar().showMessage("Nothing to undo.", 2500)
            return

        source, recycle_target, old_index = self.last_deleted

        if not recycle_target.exists():
            self.statusBar().showMessage(
                "The deleted file is no longer available.", 3000
            )
            return

        target = source
        if target.exists():
            target = self._unique_target(source.parent, source.name)

        self._set_enabled(False)

        def op():
            shutil.move(str(recycle_target), str(target))
            return target

        w = Worker(op)
        w.signals.result.connect(
            lambda t: self._undo_done(t, old_index)
        )
        w.signals.error.connect(lambda e: self._file_error("Undo failed", e))
        w.signals.finished.connect(lambda: self._set_enabled(True))
        self.pool.start(w)

    def _undo_done(self, target, old_index):
        # Put it back at the exact position it had before Delete.
        insert_at = max(0, min(old_index, len(self.paths)))
        self.paths.insert(insert_at, str(target))
        self.index = insert_at

        self.total_label.setText(str(len(self.paths)))
        self.deleted_count = max(0, self.deleted_count - 1)
        self.last_deleted = None
        self._update_stats()
        self._update_timeline()
        self.show_image(insert_at)

        self.statusBar().showMessage(
            f"Image restored: {target.name}", 4000
        )
        QMessageBox.information(
            self, "ImageFlow", f"Image restored\\n{target.name}"
        )

    def _file_error(self, title, error):
        QMessageBox.critical(self, title, error)

    # ---------- View ----------
    def zoom_in(self):
        self.fit_mode = False
        self.zoom = min(4.0, self.zoom * 1.15)
        self._render_current()

    def zoom_out(self):
        self.fit_mode = False
        self.zoom = max(0.1, self.zoom / 1.15)
        self._render_current()

    def fit_image(self):
        self.fit_mode = True
        self.zoom = 1.0
        self._render_current()

    def toggle_fullscreen(self):
        """Open only the current image in a dedicated fullscreen viewer."""
        if self.fullscreen_viewer is not None:
            self.fullscreen_viewer.close()
            return
        if not hasattr(self, "current_image") or self.current_image.isNull():
            return
        self.fullscreen_viewer = ImageOnlyFullscreen(self, self.current_image)
        self.fullscreen_viewer.closed.connect(self._fullscreen_closed)
        self.fullscreen = True
        self.fullscreen_viewer.showFullScreen()
        self.fullscreen_viewer.raise_()
        self.fullscreen_viewer.activateWindow()

    def _fullscreen_closed(self):
        self.fullscreen = False
        self.fullscreen_viewer = None
        self.image_label.setFocus()
        self._render_current()

    def back_to_source(self):
        if self.fullscreen_viewer is not None:
            self.fullscreen_viewer.close()
            return
        if self.paths:
            self.fit_image()
            self.show_image(self.index if self.index >= 0 else 0)

    # ---------- Slideshow ----------
    def toggle_slideshow(self):
        if self.slideshow_timer.isActive():
            self.slideshow_timer.stop()
            self.statusBar().showMessage("Slide show stopped.", 2500)
        else:
            if not self.paths:
                QMessageBox.information(self, "Slide Show", "Select a source folder first.")
                return
            self.slideshow_timer.start(int(self.settings.get("slideshow_seconds", 3) * 1000))
            self.statusBar().showMessage("Slide show started. Press F5 to stop.", 3000)

    # ---------- Filter ----------
    def open_filter(self):
        dialog = FilterDialog(self, self.paths)
        if dialog.exec() == QDialog.Accepted:
            filtered = dialog.filtered_paths()
            if filtered is not None:
                self.paths = filtered
                self.index = 0 if self.paths else -1
                self.selected.clear()
                self.thumb_cache.clear()
                self.total_label.setText(str(len(self.paths)))
                if self.paths:
                    self.show_image(0)
                else:
                    self.image_label.clear()
                    self.image_label.setText("No images match the filter")
                    self.image_number.setText("Image 0 / 0")
                self._update_stats()

    def toggle_theme(self):
        self.settings["theme"] = "Dark" if self.theme_toggle.isChecked() else "White"
        save_settings(self.settings)
        self.theme_toggle.setText("☀ Light" if self.theme_toggle.isChecked() else "☾ Dark")
        self._apply_theme()

    # ---------- Settings ----------
    def open_settings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec() == QDialog.Accepted:
            self.settings.update(dialog.values())
            save_settings(self.settings)
            self._apply_theme()
            self.thumb_cache.clear()
            self._update_timeline()

    # ---------- AI screen ----------
    def open_ai_screen(self):
        self.ai_window = AISearchWindow(self)
        self.ai_window.show()
        self.ai_window.raise_()
        self.ai_window.activateWindow()

    # ---------- cleanup ----------
    def closeEvent(self, event):
        self.slideshow_timer.stop()
        if self.fullscreen_viewer is not None:
            self.fullscreen_viewer.close()
            self.fullscreen_viewer = None
        event.accept()


class ImageOnlyFullscreen(QWidget):
    """Dedicated fullscreen viewer; the main ImageFlow window never enters fullscreen."""
    closed = Signal()

    def __init__(self, parent, image):
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
        dark = str(self.parent_window.settings.get("theme", "White")).lower() == "dark"
        if dark:
            self.setStyleSheet("""QMainWindow,QWidget{background:#171a21;color:#e7ebf3;font-family:"Segoe UI";} QFrame{background:#20242d;border:1px solid #343b49;border-radius:14px;} QLineEdit{border:1px solid #3d4656;border-radius:8px;padding:11px;background:#20252e;color:#edf1f7;} QPushButton{border:1px solid #3b4352;border-radius:8px;padding:9px 14px;background:#252a34;color:#e8edf5;} QPushButton:hover{background:#2c3441;border-color:#6d91d8;} QListWidget{border:1px solid #343b49;border-radius:14px;background:#20242d;padding:16px;color:#e7ebf3;}""")
        else:
            self.setStyleSheet("""QMainWindow,QWidget{background:#ffffff;color:#29344b;font-family:"Segoe UI";} QFrame{background:white;border:1px solid #dfe4ec;border-radius:14px;} QLineEdit{border:1px solid #d5dce7;border-radius:8px;padding:11px;background:white;} QPushButton{border:1px solid #d5dce7;border-radius:8px;padding:9px 14px;background:white;color:#29344b;} QPushButton:hover{background:#f4f7ff;border-color:#7651c8;} QListWidget{border:1px solid #dfe4ec;border-radius:14px;background:white;padding:16px;color:#29344b;}""")

    def search(self):
        query = self.query.text().strip()
        if not query:
            QMessageBox.information(self, "AI Search", "Enter a description first.")
            return
        paths = self.parent_window.paths
        q = query.lower()
        # Local semantic-lite search: filename/path token matching.
        matches = []
        tokens = [x for x in q.replace(",", " ").split() if len(x) > 2]
        for p in paths:
            name = Path(p).stem.lower().replace("_", " ").replace("-", " ")
            score = sum(1 for token in tokens if token in name)
            if score:
                matches.append((score, p))
        matches.sort(key=lambda x: (-x[0], x[1].lower()))
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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = ImageFlowWindow()
    win.statusBar().showMessage("Ready")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
