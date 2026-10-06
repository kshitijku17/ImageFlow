from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QThreadPool, QSize
from PySide6.QtGui import QPixmap, QIcon, QImage
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
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
)

from ai.search import search_similar_images, search_by_reference_image
from ai.date_parser import parse_date_and_semantic_query
from ai.indexer import ImageIndexer, scan_folder_images
from ai.chroma_manager import get_chroma_manager

logger = logging.getLogger(__name__)


class SearchSignals(QObject):
    finished = Signal(str, str, list)  # query_text, assistant_message, results_list
    error = Signal(str)


class BackgroundSearchWorker(QRunnable):
    """Executes OpenCLIP embedding generation and ChromaDB search in the background."""
    _active_workers = set()

    def __init__(
        self,
        query: str,
        source_folder: str | None,
        reference_image_path: str | None = None,
        paths_filter: list[str] | None = None,
        n_results: int = 20,
    ):
        super().__init__()
        self.query = query
        self.source_folder = source_folder
        self.reference_image_path = reference_image_path
        self.paths_filter = paths_filter
        self.n_results = n_results
        self.signals = SearchSignals()

        BackgroundSearchWorker._active_workers.add(self)
        self.signals.finished.connect(self._cleanup)
        self.signals.error.connect(self._cleanup)

    def _cleanup(self):
        BackgroundSearchWorker._active_workers.discard(self)

    def run(self):
        try:
            # Ensure source folder is indexed
            if self.source_folder and os.path.isdir(self.source_folder):
                chroma = get_chroma_manager()
                if chroma.ensure_ready() and chroma.count() == 0:
                    indexer = ImageIndexer()
                    scanned = scan_folder_images(self.source_folder, recursive=True)
                    if scanned:
                        indexer.index_images(scanned, prune_missing=True, folder_root=self.source_folder)

            results = []
            parsed = parse_date_and_semantic_query(self.query) if self.query else None

            if self.reference_image_path:
                # Reference image search (with optional date filtering from text query)
                results = search_by_reference_image(
                    reference_image_input=self.reference_image_path,
                    n_results=self.n_results,
                    folder_filter=self.source_folder,
                    paths_filter=self.paths_filter,
                    parsed_date_query=parsed,
                )
                count = len(results)
                ref_name = Path(self.reference_image_path).name
                if count == 0:
                    ai_msg = "No matching images found in the selected Source Folder."
                elif parsed and (parsed.year or parsed.start_date):
                    ai_msg = f"I found {count} matching image(s) visually similar to '{ref_name}' with date filter."
                else:
                    ai_msg = f"I found {count} matching image(s) visually similar to '{ref_name}'."
            else:
                # Text / Date / Combined search
                results = search_similar_images(
                    query=self.query,
                    n_results=self.n_results,
                    folder_filter=self.source_folder,
                    paths_filter=self.paths_filter,
                )
                count = len(results)
                if count == 0:
                    ai_msg = "No matching images found in the selected Source Folder."
                elif parsed and parsed.clean_query:
                    concept = parsed.clean_query
                    if parsed.year or parsed.start_date:
                        ai_msg = f"I found {count} matching {concept} image(s) with date filter."
                    else:
                        ai_msg = f"I found {count} matching {concept} image(s)."
                else:
                    ai_msg = f"I found {count} matching image(s) for '{self.query}'."

            self.signals.finished.emit(self.query, ai_msg, results)
        except Exception as e:
            logger.error(f"Search worker error: {e}", exc_info=True)
            self.signals.error.emit(str(e))


class ResultCard(QFrame):
    """Displays a matching image result with thumbnail, metadata, and score."""
    clicked = Signal(str)

    def __init__(self, record: dict[str, Any], is_dark: bool = False, parent=None):
        super().__init__(parent)
        self.record = record
        self.file_path = record.get("file_path", "")
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("resultCard")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 12, 8)
        lay.setSpacing(14)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(72, 54)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet(
            "background:#1f242d;border-radius:6px;" if is_dark else "background:#eef2f8;border-radius:6px;"
        )

        pix = QPixmap(self.file_path)
        if not pix.isNull():
            self.thumb_label.setPixmap(
                pix.scaled(QSize(72, 54), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.thumb_label.setText("📷")
        lay.addWidget(self.thumb_label)

        # Info
        info_lay = QVBoxLayout()
        info_lay.setSpacing(2)

        meta = record.get("metadata", {})
        filename = record.get("filename") or Path(self.file_path).name
        score = record.get("similarity_score")
        date_str = meta.get("date") or ""
        dim_str = f"{meta.get('width', '')}x{meta.get('height', '')}" if meta.get("width") else ""

        title_lbl = QLabel(filename)
        title_lbl.setStyleSheet("font-size:14px;font-weight:700;" + ("color:#f0f3fa;" if is_dark else "color:#1a2233;"))
        info_lay.addWidget(title_lbl)

        details = []
        if score is not None:
            details.append(f"Score: {int(score * 100)}%")
        if date_str:
            details.append(f"Date: {date_str}")
        if dim_str and dim_str != "0x0":
            details.append(dim_str)

        sub_lbl = QLabel(" • ".join(details) if details else self.file_path)
        sub_lbl.setStyleSheet("font-size:12px;" + ("color:#94a3b8;" if is_dark else "color:#64748b;"))
        info_lay.addWidget(sub_lbl)

        path_lbl = QLabel(self.file_path)
        path_lbl.setStyleSheet("font-size:11px;" + ("color:#64748b;" if is_dark else "color:#94a3b8;"))
        info_lay.addWidget(path_lbl)

        lay.addLayout(info_lay, 1)

        # Action view button
        view_btn = QPushButton("View →")
        view_btn.setFixedWidth(75)
        view_btn.clicked.connect(lambda: self.clicked.emit(self.file_path))
        lay.addWidget(view_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.file_path)
        super().mousePressEvent(event)


class AISearchWindow(QMainWindow):
    """
    ChatGPT-style Photo Assistant connected to the OpenCLIP + ChromaDB backend.
    Supports:
        1. Text Query ("Show me photos of dogs")
        2. Date Query ("Show me photos from 10 December 2025")
        3. Combined Query ("Show me dog photos from 10 December 2025")
        4. Reference Image Search ("Find similar images")
        5. Reference Image + Text/Date Search ("Find similar images from December 2025")
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("ImageFlow AI Assistant")
        self.resize(1280, 850)
        self.pool = QThreadPool.globalInstance()
        self.reference_image_path: str | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("IMAGEFLOW AI ✨")
        title.setStyleSheet("font-size:30px;font-weight:800;color:#243c67;")
        self.sub = QLabel("Smart Semantic & Visual Assistant")
        self.sub.setStyleSheet("font-size:14px;color:#778197;")
        title_box.addWidget(title)
        title_box.addWidget(self.sub)
        header.addLayout(title_box)
        header.addStretch()

        self.folder_info = QLabel("📁 Source: Active Workspace")
        self.folder_info.setStyleSheet("font-size:13px;color:#5c6b84;padding:6px 12px;background:#f0f4fa;border-radius:8px;")
        header.addWidget(self.folder_info)

        back = QPushButton("←  Back to ImageFlow")
        back.clicked.connect(self.close)
        header.addWidget(back)
        root.addLayout(header)

        # Chat / Results Scroll Area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(12, 12, 12, 12)
        self.chat_layout.setSpacing(14)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_widget)
        root.addWidget(self.chat_scroll, 1)

        # Reference preview chip bar
        self.ref_bar = QFrame()
        self.ref_bar.setVisible(False)
        self.ref_bar_layout = QHBoxLayout(self.ref_bar)
        self.ref_bar_layout.setContentsMargins(12, 6, 12, 6)
        self.ref_icon_label = QLabel("🖼")
        self.ref_name_label = QLabel("")
        self.ref_name_label.setStyleSheet("font-weight:600;color:#2563eb;")
        self.ref_clear_btn = QPushButton("✕")
        self.ref_clear_btn.setFixedSize(24, 24)
        self.ref_clear_btn.clicked.connect(self.clear_reference_image)
        self.ref_bar_layout.addWidget(self.ref_icon_label)
        self.ref_bar_layout.addWidget(self.ref_name_label)
        self.ref_bar_layout.addStretch()
        self.ref_bar_layout.addWidget(self.ref_clear_btn)
        root.addWidget(self.ref_bar)

        # Search Card with Reference Upload & Chips
        search_card = QFrame()
        search_card.setObjectName("searchCard")
        sl = QVBoxLayout(search_card)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)

        # Upload Reference Image Button
        self.upload_btn = QPushButton("🖼 Attach Ref")
        self.upload_btn.setToolTip("Select a reference photo to find similar images")
        self.upload_btn.clicked.connect(self.select_reference_image)
        row.addWidget(self.upload_btn)

        self.query = QLineEdit()
        self.query.setPlaceholderText("Ask anything (e.g. 'show me dogs', 'photos from 10 Dec 2025', 'find sunsets')…")
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)

        self.send = QPushButton("Send  ➤")
        self.send.clicked.connect(self.search)
        row.addWidget(self.send)
        sl.addLayout(row)

        # Suggestion Chips
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text in [
            "🐕 Dogs",
            "☀ Sunsets",
            "△ Mountains",
            "🚗 Red Cars",
            "📅 Dec 2025",
            "🐕 Dogs from 10 Dec 2025",
        ]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked=False, t=text: self._apply_chip(t))
            chips.addWidget(b)
        chips.addStretch()
        sl.addLayout(chips)
        root.addWidget(search_card)

        self.status = QLabel("Ready to search your photos with local OpenCLIP + ChromaDB")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("font-size:13px;color:#718096;")
        root.addWidget(self.status)

        self.apply_theme()
        self._sync_folders()
        self._add_welcome_message()

    def _sync_folders(self):
        """Syncs source folder from main window."""
        src_path = None
        if hasattr(self.parent_window, "folder_manager") and self.parent_window.folder_manager.source_path:
            src_path = str(self.parent_window.folder_manager.source_path)
        elif hasattr(self.parent_window, "settings"):
            src_path = self.parent_window.settings.get("source", "")

        if src_path and os.path.isdir(src_path):
            self.folder_info.setText(f"📁 Source: {Path(src_path).name}")
            self.folder_info.setToolTip(src_path)
        else:
            self.folder_info.setText("📁 Source: No folder selected")

    def _add_welcome_message(self):
        msg = (
            "👋 Hi! I am your local AI photo assistant.\n\n"
            "You can ask me to find photos by description ('dogs', 'beach sunset'), "
            "by date ('10 December 2025'), combined ('dog photos from Dec 2025'), "
            "or attach a reference photo to find visually similar images."
        )
        self._add_ai_bubble(msg)

    def apply_theme(self):
        settings = getattr(self.parent_window, "settings", {})
        is_dark = str(settings.get("theme", "White")).lower() == "dark"
        self.is_dark = is_dark
        if is_dark:
            self.setStyleSheet("""
                QMainWindow, QWidget { background: #15181e; color: #e2e8f0; font-family: "Segoe UI", sans-serif; }
                QFrame#searchCard { background: #1e232d; border: 1px solid #2d3544; border-radius: 14px; }
                QFrame#resultCard { background: #1a1e27; border: 1px solid #2a3242; border-radius: 10px; }
                QFrame#resultCard:hover { background: #222936; border-color: #3b82f6; }
                QLineEdit { border: 1px solid #334155; border-radius: 8px; padding: 10px 14px; background: #11141a; color: #f8fafc; font-size: 14px; }
                QLineEdit:focus { border-color: #3b82f6; }
                QPushButton { border: 1px solid #334155; border-radius: 8px; padding: 8px 14px; background: #1e2430; color: #e2e8f0; font-size: 13px; font-weight: 500; }
                QPushButton:hover { background: #283142; border-color: #60a5fa; }
                QScrollArea { border: 1px solid #242b38; border-radius: 14px; background: #11141a; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget { background: #f8fafc; color: #1e293b; font-family: "Segoe UI", sans-serif; }
                QFrame#searchCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px; }
                QFrame#resultCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }
                QFrame#resultCard:hover { background: #f1f5f9; border-color: #2563eb; }
                QLineEdit { border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 14px; background: #ffffff; color: #0f172a; font-size: 14px; }
                QLineEdit:focus { border-color: #2563eb; }
                QPushButton { border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 14px; background: #ffffff; color: #334155; font-size: 13px; font-weight: 500; }
                QPushButton:hover { background: #f8fafc; border-color: #2563eb; color: #1e40af; }
                QScrollArea { border: 1px solid #e2e8f0; border-radius: 14px; background: #ffffff; }
            """)

    def _apply_chip(self, text: str):
        # Extract plain clean chip text
        clean = text.split(" ", 1)[-1] if " " in text else text
        self.query.setText(clean)
        self.search()

    def select_reference_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Image",
            str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff)"
        )
        if path:
            self.reference_image_path = path
            self.ref_name_label.setText(f"Reference Image: {Path(path).name}")
            self.ref_bar.setVisible(True)
            if not self.query.text().strip():
                self.query.setText("Find similar images")

    def clear_reference_image(self):
        self.reference_image_path = None
        self.ref_bar.setVisible(False)
        self.ref_name_label.setText("")

    def _add_user_bubble(self, text: str, ref_image: str | None = None):
        bubble = QFrame()
        bubble.setStyleSheet(
            "background:#2563eb;color:white;border-radius:12px;padding:12px;"
            if not self.is_dark else
            "background:#1d4ed8;color:white;border-radius:12px;padding:12px;"
        )
        l = QVBoxLayout(bubble)
        l.setContentsMargins(14, 10, 14, 10)
        l.setSpacing(4)

        if ref_image:
            ref_lbl = QLabel(f"🖼 Reference: {Path(ref_image).name}")
            ref_lbl.setStyleSheet("color:#bfdbfe;font-weight:600;font-size:12px;")
            l.addWidget(ref_lbl)

        txt_lbl = QLabel(text if text else "Find similar images")
        txt_lbl.setStyleSheet("color:white;font-size:14px;font-weight:600;")
        txt_lbl.setWordWrap(True)
        l.addWidget(txt_lbl)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(bubble, 0)

        # Insert before stretch
        idx = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertLayout(idx, row)
        self._scroll_to_bottom()

    def _add_ai_bubble(self, message: str, results: list[dict[str, Any]] | None = None):
        container = QWidget()
        l = QVBoxLayout(container)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(8)

        ai_bubble = QFrame()
        ai_bubble.setStyleSheet(
            "background:#f1f5f9;color:#0f172a;border-radius:12px;padding:12px;"
            if not self.is_dark else
            "background:#1e293b;color:#f8fafc;border-radius:12px;padding:12px;"
        )
        bl = QVBoxLayout(ai_bubble)
        bl.setContentsMargins(14, 10, 14, 10)

        msg_lbl = QLabel(message)
        msg_lbl.setStyleSheet("font-size:14px;" + ("color:#f8fafc;" if self.is_dark else "color:#0f172a;"))
        msg_lbl.setWordWrap(True)
        bl.addWidget(msg_lbl)

        row = QHBoxLayout()
        row.addWidget(ai_bubble, 0)
        row.addStretch()
        l.addLayout(row)

        if results:
            for r in results:
                card = ResultCard(r, is_dark=self.is_dark)
                card.clicked.connect(self._open_image_in_main_window)
                l.addWidget(card)

        idx = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(idx, container)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def _open_image_in_main_window(self, path: str):
        """Highlights and opens the clicked image in the main ImageFlow window."""
        norm_target = os.path.abspath(os.path.normpath(str(path)))
        paths = getattr(self.parent_window, "paths", [])
        if not paths and hasattr(self.parent_window, "image_manager"):
            paths = self.parent_window.image_manager.paths

        # Find index in main window paths
        target_idx = None
        for idx, p in enumerate(paths):
            if os.path.abspath(os.path.normpath(str(p))) == norm_target:
                target_idx = idx
                break

        if target_idx is not None and hasattr(self.parent_window, "show_image"):
            self.parent_window.show_image(target_idx)
            self.parent_window.raise_()
            self.parent_window.activateWindow()
            self.status.setText(f"Opened image: {Path(path).name} in main viewer")
        else:
            self.status.setText(f"Selected: {Path(path).name}")

    def search(self):
        query_text = self.query.text().strip()
        ref_path = self.reference_image_path

        if not query_text and not ref_path:
            QMessageBox.information(self, "AI Assistant", "Please enter a search query or attach a reference image.")
            return

        display_query = query_text if query_text else "Find similar images"
        self._add_user_bubble(display_query, ref_image=ref_path)
        self.query.clear()

        # Get source folder and current paths
        source_folder = None
        if hasattr(self.parent_window, "folder_manager") and self.parent_window.folder_manager.source_path:
            source_folder = str(self.parent_window.folder_manager.source_path)
        elif hasattr(self.parent_window, "settings"):
            src_val = self.parent_window.settings.get("source", "")
            if src_val and os.path.isdir(str(src_val)):
                source_folder = str(src_val)

        paths = getattr(self.parent_window, "paths", [])
        if not paths and hasattr(self.parent_window, "image_manager"):
            paths = self.parent_window.image_manager.paths

        self.send.setEnabled(False)
        self.status.setText("Searching with OpenCLIP + ChromaDB…")

        worker = BackgroundSearchWorker(
            query=query_text,
            source_folder=source_folder,
            reference_image_path=ref_path,
            paths_filter=paths if paths else None,
            n_results=20,
        )
        worker.signals.finished.connect(self._on_search_finished)
        worker.signals.error.connect(self._on_search_error)
        self.pool.start(worker)

    def _on_search_finished(self, query: str, ai_msg: str, results: list):
        self.send.setEnabled(True)
        self.status.setText(f"Search complete: {len(results)} matches found")
        self._add_ai_bubble(ai_msg, results)
        # Clear reference image after search
        if self.reference_image_path:
            self.clear_reference_image()

    def _on_search_error(self, err: str):
        self.send.setEnabled(True)
        self.status.setText(f"Search error: {err}")
        self._add_ai_bubble(f"Sorry, an error occurred during search: {err}")
