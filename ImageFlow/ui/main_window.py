import os
from pathlib import Path
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence, QImage
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QDialog,
)

from utils.constants import APP_NAME, THUMB_COUNT, THUMB_SIZE
from utils.helpers import generate_unique_target
from config.settings import load_settings, save_settings
from workers.worker import Worker
from workers.thumbnail_worker import ThumbnailWorker
from workers.image_loader import ImageLoadWorker
from core.folder_manager import FolderManager
from core.image_manager import ImageManager
from core.navigation import NavigationManager
from core.file_operations import FileOperationsManager
from core.slideshow import SlideshowController

from ui.theme import get_theme_stylesheet, is_dark_theme
from ui.toolbar import HeaderWidget, FolderCard, ActionCard, KeyActionWidget, AICard
from ui.image_viewer import ImageViewer
from ui.timeline import TimelineWidget
from ui.dialogs import FilterDialog, SettingsDialog
from ui.fullscreen_viewer import ImageOnlyFullscreen
from ui.ai_window import AISearchWindow


class ImageFlowWindow(QMainWindow):
    """Main application window coordinating ImageFlow's modular components."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1536, 1000)
        self.setMinimumSize(1150, 760)

        self.settings = load_settings()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(8, os.cpu_count() or 4)))

        # Core managers
        self.image_manager = ImageManager()
        self.folder_manager = FolderManager(self.settings, self.pool)
        self.file_ops = FileOperationsManager(self.pool)
        self.slideshow = SlideshowController(self)

        self.fullscreen = False
        self.fullscreen_viewer: ImageOnlyFullscreen | None = None
        self.ai_window: AISearchWindow | None = None
        self._active_image_worker: ImageLoadWorker | None = None

        self._build_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self._apply_theme()
        self._restore_paths()

    # ---------- Properties for compatibility ----------
    @property
    def paths(self) -> list[str]:
        return self.image_manager.paths

    @paths.setter
    def paths(self, value: list[str]):
        self.image_manager.paths = list(value)

    @property
    def index(self) -> int:
        return self.image_manager.index

    @index.setter
    def index(self, value: int):
        self.image_manager.index = value

    @property
    def selected(self) -> set[int]:
        return self.image_manager.selected

    @property
    def generation(self) -> int:
        return self.image_manager.generation

    @generation.setter
    def generation(self, value: int):
        self.image_manager.generation = value

    @property
    def copied_count(self) -> int:
        return self.image_manager.copied_count

    @copied_count.setter
    def copied_count(self, value: int):
        self.image_manager.copied_count = value

    @property
    def deleted_count(self) -> int:
        return self.image_manager.deleted_count

    @deleted_count.setter
    def deleted_count(self, value: int):
        self.image_manager.deleted_count = value

    @property
    def last_deleted(self):
        return self.image_manager.last_deleted

    @last_deleted.setter
    def last_deleted(self, value):
        self.image_manager.last_deleted = value

    @property
    def thumb_cache(self):
        return self.image_manager.thumb_cache

    @property
    def thumb_jobs(self):
        return self.image_manager.thumb_jobs

    @property
    def current_image(self) -> QImage:
        return self.image_manager.current_image

    @current_image.setter
    def current_image(self, value: QImage):
        self.image_manager.current_image = value

    @property
    def image_label(self):
        return self.viewer.image_label

    @property
    def image_number(self):
        return self.viewer.image_number

    @property
    def prev_btn(self):
        return self.viewer.prev_btn

    @property
    def next_btn(self):
        return self.viewer.next_btn

    @property
    def thumb_buttons(self):
        return self.timeline.thumb_buttons

    @property
    def thumb_scroll(self):
        return self.timeline.thumb_scroll

    @property
    def total_label(self):
        return self.header.total_label

    @property
    def selected_label(self):
        return self.header.selected_label

    @property
    def copied_label(self):
        return self.header.copied_label

    @property
    def deleted_label(self):
        return self.header.deleted_label

    @property
    def theme_toggle(self):
        return self.header.theme_toggle

    @property
    def slideshow_timer(self):
        return self.slideshow.timer

    @property
    def zoom(self) -> float:
        return self.viewer.zoom

    @zoom.setter
    def zoom(self, value: float):
        self.viewer.zoom = value

    @property
    def fit_mode(self) -> bool:
        return self.viewer.fit_mode

    @fit_mode.setter
    def fit_mode(self, value: bool):
        self.viewer.fit_mode = value

    # ---------- UI Setup ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(7)

        # Header
        is_dark = is_dark_theme(self.settings.get("theme", "White"))
        self.header = HeaderWidget(is_dark=is_dark)
        root.addWidget(self.header)

        # Folder selection row
        folders = QHBoxLayout()
        self.source_card = FolderCard("SOURCE FOLDER", "", "📁")
        self.dest_card = FolderCard("DESTINATION FOLDER", "", "📂")
        folders.addWidget(self.source_card, 1)
        folders.addWidget(self.dest_card, 1)
        root.addLayout(folders)

        # Main horizontal splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left area: Image Viewer + Timeline
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)

        self.viewer = ImageViewer()
        left_l.addWidget(self.viewer, 1)

        self.timeline = TimelineWidget()
        left_l.addWidget(self.timeline, 0)

        splitter.addWidget(left)

        # Right area: Action cards & controls
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_widget = QWidget()
        right_l = QVBoxLayout(right_widget)
        right_l.setContentsMargins(4, 0, 4, 0)
        right_l.setSpacing(12)

        self.copy_card = ActionCard(
            "Y", "COPY SELECTED",
            "Copy all selected images to destination folder",
            "▣", danger=False
        )
        right_l.addWidget(self.copy_card)

        self.delete_card = ActionCard(
            "Delete", "DELETE",
            "Move image to the Recycle folder",
            "♜", danger=True
        )
        right_l.addWidget(self.delete_card)

        self.undo_card = ActionCard(
            "Z", "UNDO DELETE",
            "Restore the last deleted image",
            "↶", danger=False
        )
        right_l.addWidget(self.undo_card)

        # Other actions
        other = QFrame()
        other.setObjectName("card")
        ol = QVBoxLayout(other)
        ol.setContentsMargins(16, 14, 16, 14)
        ol.setSpacing(8)
        h = QLabel("OTHER ACTIONS")
        h.setObjectName("purpleTitle")
        ol.addWidget(h)

        self.move_action = KeyActionWidget("M", "Move Image")
        self.zoom_in_action = KeyActionWidget("+", "Zoom In")
        self.zoom_out_action = KeyActionWidget("−", "Zoom Out")
        self.fullscreen_action = KeyActionWidget("🖱", "Double Click — Full Screen")
        self.back_action = KeyActionWidget("ESC", "Back to Source Folder")

        ol.addWidget(self.move_action)
        ol.addWidget(self.zoom_in_action)
        ol.addWidget(self.zoom_out_action)
        ol.addWidget(self.fullscreen_action)
        ol.addWidget(self.back_action)
        right_l.addWidget(other)

        # AI card
        self.ai_card = AICard()
        right_l.addWidget(self.ai_card)

        right_l.addStretch(1)
        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1120, 340])
        root.addWidget(splitter, 1)

    def _connect_signals(self):
        # Header & Theme
        self.header.theme_toggled.connect(self.toggle_theme)
        self.image_manager.stats_changed.connect(self.header.update_stats)

        # Folder management
        self.source_card.choose_clicked.connect(self.choose_source)
        self.dest_card.choose_clicked.connect(self.choose_destination)
        self.folder_manager.source_changed.connect(lambda p: self.source_card.set_path(str(p)))
        self.folder_manager.dest_changed.connect(lambda p: self.dest_card.set_path(str(p)))
        self.folder_manager.scan_started.connect(self._on_scan_started)
        self.folder_manager.scan_finished.connect(self._on_scan_finished)
        self.folder_manager.scan_error.connect(self._on_scan_error)

        # Viewer navigation & fullscreen
        self.viewer.prev_clicked.connect(self.previous_image)
        self.viewer.next_clicked.connect(self.next_image)
        self.viewer.fullscreen_requested.connect(self.toggle_fullscreen)

        # Timeline thumbnail clicked
        self.timeline.thumbnail_clicked.connect(self.thumb_clicked)

        # Actions
        self.copy_card.triggered.connect(self.copy_current)
        self.delete_card.triggered.connect(self.delete_current)
        self.undo_card.triggered.connect(self.undo_delete)

        self.move_action.triggered.connect(self.move_current)
        self.zoom_in_action.triggered.connect(self.zoom_in)
        self.zoom_out_action.triggered.connect(self.zoom_out)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.back_action.triggered.connect(self.back_to_source)

        self.ai_card.open_ai_clicked.connect(self.open_ai_screen)

        # Slideshow
        self.slideshow.timeout.connect(self.next_image)

        # File operations
        self.file_ops.started.connect(lambda: self._set_enabled(False))
        self.file_ops.finished.connect(lambda: self._set_enabled(True))
        self.file_ops.copy_completed.connect(self._on_copy_done)
        self.file_ops.batch_copy_completed.connect(self._batch_copy_done)
        self.file_ops.move_completed.connect(self._on_move_done)
        self.file_ops.delete_completed.connect(self._on_delete_done)
        self.file_ops.undo_completed.connect(self._on_undo_done)
        self.file_ops.error_occurred.connect(self._file_error)

    def _setup_shortcuts(self):
        self._shortcut("I", self.toggle_current_selection)
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
        self._shortcut("F5", self.toggle_slideshow)

    def _shortcut(self, key: str, fn):
        a = QAction(self)
        a.setShortcut(QKeySequence(key))
        a.triggered.connect(fn)
        self.addAction(a)

    def _apply_theme(self):
        theme_name = self.settings.get("theme", "White")
        self.setStyleSheet(get_theme_stylesheet(theme_name))
        self.header.update_theme_button(is_dark_theme(theme_name))

    def _restore_paths(self):
        self.folder_manager.restore_paths()

    # ---------- Folder / Indexing ----------
    def choose_source(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Source Folder", str(Path.home()))
        if path:
            self._set_source_path(Path(path))

    def _set_source_path(self, path: Path):
        self.folder_manager.set_source_path(Path(path), auto_scan=True)

    def choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Destination Folder", str(Path.home()))
        if path:
            self._set_dest_path(Path(path))

    def _set_dest_path(self, path: Path):
        self.folder_manager.set_dest_path(Path(path))

    def _scan_source(self, folder: Path):
        self.folder_manager.scan_source(folder)

    def _on_scan_started(self):
        self.image_manager.clear()
        self.timeline.clear()
        self.viewer.set_scanning()
        self._set_enabled(False)

    def _on_scan_finished(self, result: list[str]):
        self.image_manager.set_paths(result)
        self._set_enabled(True)
        if self.image_manager.paths:
            self.show_image(0)
        else:
            self.viewer.set_message("No supported images found")
            self.viewer.set_counter("Image 0 / 0")
        self._update_stats()

    def _on_scan_error(self, error: str):
        self._set_enabled(True)
        QMessageBox.critical(self, "Folder Scan Error", error)

    def _set_enabled(self, enabled: bool):
        has_paths = bool(self.image_manager.paths)
        can_prev = enabled and has_paths and NavigationManager.can_navigate_previous(self.image_manager.index)
        can_next = enabled and has_paths and NavigationManager.can_navigate_next(self.image_manager.index, len(self.image_manager.paths))
        self.viewer.update_nav(can_prev, can_next)

    # ---------- Images ----------
    def show_image(self, index: int):
        if not self.image_manager.paths:
            return
        index = self.image_manager.set_current_index(index)
        generation = self.image_manager.generation
        path = self.image_manager.paths[index]

        self.viewer.set_loading(index, len(self.image_manager.paths))
        self._update_nav()
        self._update_timeline()

        worker = ImageLoadWorker(generation, index, path)
        worker.signals.ready.connect(self._image_loaded)
        worker.signals.ready.connect(lambda *_: self._image_worker_finished(worker))
        self._active_image_worker = worker
        self.pool.start(worker)

    def _image_loaded(self, generation: int, path: str, image: QImage):
        if generation != self.image_manager.generation or self.image_manager.index < 0:
            return
        if str(self.image_manager.paths[self.image_manager.index]) != str(path):
            return
        if image.isNull():
            self.viewer.set_message("Unable to read image")
            return
        self.image_manager.current_image = image
        self.viewer.set_image(image, self.image_manager.index, len(self.image_manager.paths))

    def _image_worker_finished(self, worker):
        if self._active_image_worker is worker:
            self._active_image_worker = None

    def _render_current(self):
        self.viewer.render_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewer.render_current()

    def _update_nav(self):
        can_prev = NavigationManager.can_navigate_previous(self.image_manager.index)
        can_next = NavigationManager.can_navigate_next(self.image_manager.index, len(self.image_manager.paths))
        self.viewer.update_nav(can_prev, can_next)

    def previous_image(self):
        prev_idx = NavigationManager.get_previous_index(self.image_manager.index)
        if prev_idx is not None:
            self.show_image(prev_idx)

    def next_image(self):
        wrap = self.slideshow.is_active()
        next_idx = NavigationManager.get_next_index(
            self.image_manager.index, len(self.image_manager.paths), wrap=wrap
        )
        if next_idx is not None:
            self.show_image(next_idx)

    # ---------- Timeline ----------
    def _clear_thumbnails(self):
        self.timeline.clear()

    def _update_timeline(self):
        paths = self.image_manager.paths
        if not paths:
            self.timeline.clear()
            return

        half = THUMB_COUNT // 2
        start = max(0, min(self.image_manager.index - half, len(paths) - THUMB_COUNT))

        for slot in range(THUMB_COUNT):
            idx = start + slot
            valid = idx < len(paths)
            is_current = valid and (idx == self.image_manager.index)
            is_selected = valid and (idx in self.image_manager.selected)
            self.timeline.bar.configure_button(slot, valid, idx if valid else None, is_current, is_selected)

            if not valid:
                continue

            key = str(paths[idx])
            cached = self.image_manager.get_cached_thumbnail(key)
            if cached is not None:
                self.timeline.bar.set_button_image(slot, cached)
            else:
                self.timeline.bar.set_button_text(slot, "Loading…")
                if key not in self.image_manager.thumb_jobs:
                    self.image_manager.thumb_jobs.add(key)
                    w = ThumbnailWorker(
                        idx, key, THUMB_SIZE,
                        self.settings.get("thumb_quality", 80)
                    )
                    w.signals.ready.connect(self._thumb_ready)
                    self.pool.start(w)

        if 0 <= self.image_manager.index < len(paths):
            QTimer.singleShot(0, self._scroll_thumb_to_current)

    def _scroll_thumb_to_current(self):
        self.timeline.scroll_to_current(self.image_manager.index)

    def _thumb_ready(self, index: int, path: str, image: QImage):
        self.image_manager.thumb_jobs.discard(path)
        if image is not None and not image.isNull():
            self.image_manager.cache_thumbnail(path, image)

        paths = self.image_manager.paths
        if not paths or not (0 <= index < len(paths)):
            return

        half = THUMB_COUNT // 2
        start = max(0, min(self.image_manager.index - half, len(paths) - THUMB_COUNT))
        slot = index - start

        if 0 <= slot < THUMB_COUNT and str(paths[index]) == path:
            if image is not None and not image.isNull():
                self.timeline.bar.set_button_image(slot, image)
            else:
                self.timeline.bar.set_button_text(slot, str(index + 1))

    def _set_thumb_button(self, button, image):
        if image is not None and not image.isNull():
            button.setIcon(image)
            button.setText("")

    def thumb_clicked(self, slot: int):
        idx = self.timeline.bar.get_button_image_index(slot)
        if idx is not None and 0 <= int(idx) < len(self.image_manager.paths):
            self.show_image(int(idx))

    # ---------- Selection ----------
    def toggle_current_selection(self):
        """Press I to select/deselect the currently displayed image."""
        if not self.image_manager.paths or self.image_manager.index < 0:
            return
        _, message = self.image_manager.toggle_selection(self.image_manager.index)
        self._update_timeline()
        self.statusBar().showMessage(
            f"{message}  |  Selected: {len(self.image_manager.selected)}", 1800
        )

    def select_all(self):
        self.image_manager.select_all()
        self._update_timeline()

    def deselect_all(self):
        self.image_manager.deselect_all()
        self._update_timeline()

    def invert_selection(self):
        self.image_manager.invert_selection()
        self._update_timeline()

    def _update_stats(self):
        self.image_manager.emit_stats()

    # ---------- File operations ----------
    def _destination(self) -> Path | None:
        return self.folder_manager.get_destination()

    def copy_current(self):
        """Copy all selected images; if none are selected, copy the current image."""
        if not self.image_manager.paths or self.image_manager.index < 0:
            QMessageBox.information(self, "Copy", "Select a source folder and image first.")
            return
        dst = self._destination()
        if dst is None:
            QMessageBox.warning(self, "Destination Required", "Please select a destination folder first.")
            return

        selected_items = self.image_manager.get_selected_items()
        if selected_items:
            self._copy_selected(selected_items, dst)
            return

        source = Path(self.image_manager.paths[self.image_manager.index])
        self._file_copy(source, dst)

    def _copy_selected(self, items: list[tuple[int, str]], dst: Path):
        """Batch-copy selected images in one background operation."""
        current_index = self.image_manager.index
        self.file_ops.copy_selected(items, dst, current_index)

    def _batch_copy_done(self, results: list, current_index: int):
        if not results:
            self._update_stats()
            self.statusBar().showMessage("No selected images could be copied.", 3000)
            return

        # Update in-memory paths for renamed source files.
        for idx, target, selected_source in results:
            self.image_manager.update_path_at(idx, str(selected_source))

        self.image_manager.record_copy(len(results))
        self.image_manager.selected.clear()
        self._update_stats()
        self._update_timeline()

        names = ", ".join(target.name for _, target, _ in results[:3])
        if len(results) > 3:
            names += f" and {len(results) - 3} more"
        self.statusBar().showMessage(
            f"Copied {len(results)} image(s) to destination: {names}", 5000
        )
        QMessageBox.information(
            self,
            "ImageFlow",
            f"{len(results)} selected image(s) copied to destination successfully.\n\n"
            f"Source files were marked with '-selected'."
        )
        if 0 <= current_index < len(self.image_manager.paths):
            self.show_image(current_index)

    def _unique_target(self, dst: Path, name: str) -> Path:
        return generate_unique_target(dst, name)

    def _file_copy(self, source: Path, dst: Path):
        self.file_ops.copy_image(source, dst, self.image_manager.index)

    def _on_copy_done(self, target: Path, selected_source: Path, old_index: int):
        self.image_manager.update_path_at(old_index, str(selected_source))
        self.image_manager.record_copy(1)
        self._update_timeline()
        self.statusBar().showMessage(
            f"Image copied: {target.name}  |  Source marked selected",
            5000
        )
        QMessageBox.information(
            self,
            "ImageFlow",
            f"Image copied to destination\n{target.name}\n\n"
            f"Source renamed to\n{selected_source.name}"
        )
        self.show_image(old_index)

    def move_current(self):
        if not self.image_manager.paths or self.image_manager.index < 0:
            QMessageBox.information(self, "Move", "Select an image first.")
            return
        dst = QFileDialog.getExistingDirectory(self, "Move Image To")
        if not dst:
            return
        source = Path(self.image_manager.paths[self.image_manager.index])
        self.file_ops.move_image(source, Path(dst))

    def _on_move_done(self, source: Path, target: Path):
        self.image_manager.remove_at(self.image_manager.index)
        self.statusBar().showMessage(f"Image moved: {source.name}", 4000)
        QMessageBox.information(self, "ImageFlow", f"Image moved\n{source.name}")
        if self.image_manager.paths:
            self.show_image(self.image_manager.index)
        else:
            self.viewer.clear()

    def delete_current(self):
        if not self.image_manager.paths or self.image_manager.index < 0:
            QMessageBox.information(self, "Delete", "Select an image first.")
            return
        source = Path(self.image_manager.paths[self.image_manager.index])
        self.file_ops.delete_image(source, self.image_manager.index)

    def _on_delete_done(self, source: Path, recycle_target: Path, old_index: int):
        self.image_manager.record_delete(source, recycle_target, old_index)
        self.image_manager.remove_at(old_index)
        self._update_timeline()

        self.viewer.clear()
        if self.image_manager.paths:
            self.show_image(self.image_manager.index)
        else:
            self.viewer.set_message("No images in source folder")

        self.statusBar().showMessage(
            f"Image deleted: {source.name}  |  Z = Undo", 5000
        )
        QMessageBox.information(
            self, "ImageFlow",
            f"Image deleted\n{source.name}\n\nMoved to Recycle."
        )

    def undo_delete(self):
        if not self.image_manager.last_deleted:
            self.statusBar().showMessage("Nothing to undo.", 2500)
            return
        source, recycle_target, old_index = self.image_manager.last_deleted
        self.file_ops.undo_delete(source, recycle_target, old_index)

    def _on_undo_done(self, target: Path, old_index: int):
        self.image_manager.record_undo_delete()
        self.image_manager.insert_at(old_index, str(target))
        self._update_timeline()
        self.show_image(old_index)

        self.statusBar().showMessage(
            f"Image restored: {target.name}", 4000
        )
        QMessageBox.information(
            self, "ImageFlow", f"Image restored\n{target.name}"
        )

    def _file_error(self, title: str, error: str):
        QMessageBox.critical(self, title, error)

    # ---------- View ----------
    def zoom_in(self):
        self.viewer.zoom_in()

    def zoom_out(self):
        self.viewer.zoom_out()

    def fit_image(self):
        self.viewer.fit_image()

    def toggle_fullscreen(self):
        """Open only the current image in a dedicated fullscreen viewer."""
        if self.fullscreen_viewer is not None:
            self.fullscreen_viewer.close()
            return
        if self.image_manager.current_image.isNull():
            return
        self.fullscreen_viewer = ImageOnlyFullscreen(self, self.image_manager.current_image)
        self.fullscreen_viewer.closed.connect(self._fullscreen_closed)
        self.fullscreen = True
        self.fullscreen_viewer.showFullScreen()
        self.fullscreen_viewer.raise_()
        self.fullscreen_viewer.activateWindow()

    def _fullscreen_closed(self):
        self.fullscreen = False
        self.fullscreen_viewer = None
        self.viewer.image_label.setFocus()
        self.viewer.render_current()

    def back_to_source(self):
        if self.fullscreen_viewer is not None:
            self.fullscreen_viewer.close()
            return
        if self.image_manager.paths:
            self.fit_image()
            self.show_image(self.image_manager.index if self.image_manager.index >= 0 else 0)

    # ---------- Slideshow ----------
    def toggle_slideshow(self):
        if self.slideshow.is_active():
            self.slideshow.stop()
            self.statusBar().showMessage("Slide show stopped.", 2500)
        else:
            if not self.image_manager.paths:
                QMessageBox.information(self, "Slide Show", "Select a source folder first.")
                return
            seconds = int(self.settings.get("slideshow_seconds", 3))
            self.slideshow.start(seconds)
            self.statusBar().showMessage("Slide show started. Press F5 to stop.", 3000)

    # ---------- Filter ----------
    def open_filter(self):
        dialog = FilterDialog(self, self.image_manager.paths)
        if dialog.exec() == QDialog.Accepted:
            filtered = dialog.filtered_paths()
            if filtered is not None:
                self.image_manager.set_paths(filtered)
                if self.image_manager.paths:
                    self.show_image(0)
                else:
                    self.viewer.clear()
                    self.viewer.set_message("No images match the filter")
                self._update_stats()

    def toggle_theme(self):
        self.settings["theme"] = "Dark" if self.header.theme_toggle.isChecked() else "White"
        save_settings(self.settings)
        self._apply_theme()

    # ---------- Settings ----------
    def open_settings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec() == QDialog.Accepted:
            self.settings.update(dialog.values())
            save_settings(self.settings)
            self._apply_theme()
            self.image_manager.clear_thumbnail_cache()
            self._update_timeline()

    # ---------- AI screen ----------
    def open_ai_screen(self):
        self.ai_window = AISearchWindow(self)
        self.ai_window.show()
        self.ai_window.raise_()
        self.ai_window.activateWindow()

    # ---------- Cleanup ----------
    def closeEvent(self, event):
        self.slideshow.stop()
        if self.fullscreen_viewer is not None:
            self.fullscreen_viewer.close()
            self.fullscreen_viewer = None
        event.accept()
