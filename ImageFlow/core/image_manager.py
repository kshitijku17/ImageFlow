from collections import OrderedDict
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from utils.constants import MAX_CACHE


class ImageManager(QObject):
    """Manages the in-memory image list, current index, multi-selection, thumbnail cache, and statistics."""
    stats_changed = Signal(int, int, int, int)  # total, selected, copied, deleted

    def __init__(self):
        super().__init__()
        self.paths: list[str] = []
        self.index: int = -1
        self.generation: int = 0
        self.selected: set[int] = set()
        self.copied_count: int = 0
        self.deleted_count: int = 0
        self.last_deleted: tuple[Path, Path, int] | None = None
        self.thumb_cache: OrderedDict[str, QImage] = OrderedDict()
        self.thumb_jobs: set[str] = set()
        self.current_image: QImage = QImage()

    def set_paths(self, paths: list[str]):
        self.paths = list(paths)
        self.index = 0 if self.paths else -1
        self.selected.clear()
        self.thumb_cache.clear()
        self.thumb_jobs.clear()
        self.current_image = QImage()
        self.emit_stats()

    def set_current_index(self, index: int) -> int:
        if not self.paths:
            self.index = -1
            return -1
        self.index = max(0, min(index, len(self.paths) - 1))
        self.generation += 1
        return self.index

    def clear(self):
        self.paths.clear()
        self.index = -1
        self.generation += 1
        self.selected.clear()
        self.thumb_cache.clear()
        self.thumb_jobs.clear()
        self.current_image = QImage()
        self.emit_stats()

    def toggle_selection(self, index: int | None = None) -> tuple[bool, str]:
        if index is None:
            index = self.index
        if not self.paths or not (0 <= index < len(self.paths)):
            return False, ""
        if index in self.selected:
            self.selected.remove(index)
            is_selected = False
            msg = f"Deselected image {index + 1}"
        else:
            self.selected.add(index)
            is_selected = True
            msg = f"Selected image {index + 1}"
        self.emit_stats()
        return is_selected, msg

    def select_all(self):
        self.selected = set(range(len(self.paths)))
        self.emit_stats()

    def deselect_all(self):
        self.selected.clear()
        self.emit_stats()

    def invert_selection(self):
        all_indices = set(range(len(self.paths)))
        self.selected = all_indices - self.selected
        self.emit_stats()

    def get_selected_items(self) -> list[tuple[int, str]]:
        return [
            (idx, self.paths[idx])
            for idx in sorted(self.selected)
            if 0 <= idx < len(self.paths)
        ]

    def cache_thumbnail(self, path: str, image: QImage):
        self.thumb_cache[path] = image
        self.thumb_cache.move_to_end(path)
        while len(self.thumb_cache) > MAX_CACHE:
            self.thumb_cache.popitem(last=False)

    def get_cached_thumbnail(self, path: str) -> QImage | None:
        return self.thumb_cache.get(path)

    def clear_thumbnail_cache(self):
        self.thumb_cache.clear()
        self.thumb_jobs.clear()

    def update_path_at(self, index: int, new_path: str):
        if 0 <= index < len(self.paths):
            self.paths[index] = new_path

    def record_copy(self, count: int = 1):
        self.copied_count += count
        self.emit_stats()

    def record_delete(self, source: Path, recycle_target: Path, old_index: int):
        self.last_deleted = (source, recycle_target, old_index)
        self.deleted_count += 1
        self.emit_stats()

    def remove_at(self, old_index: int):
        if 0 <= old_index < len(self.paths):
            self.paths.pop(old_index)

        # Remove the deleted image from the multi-selection and shift indexes after it
        old_selected = set(self.selected)
        self.selected.clear()
        for idx in old_selected:
            if idx == old_index:
                continue
            self.selected.add(idx - 1 if idx > old_index else idx)

        self.index = min(old_index, len(self.paths) - 1) if self.paths else -1
        self.current_image = QImage()
        self.emit_stats()

    def record_undo_delete(self):
        self.deleted_count = max(0, self.deleted_count - 1)
        self.last_deleted = None
        self.emit_stats()

    def insert_at(self, old_index: int, path_str: str):
        insert_at = max(0, min(old_index, len(self.paths)))
        self.paths.insert(insert_at, path_str)

        old_selected = set(self.selected)
        self.selected = {idx + 1 if idx >= insert_at else idx for idx in old_selected}
        self.index = insert_at
        self.emit_stats()

    def emit_stats(self):
        self.stats_changed.emit(
            len(self.paths),
            len(self.selected),
            self.copied_count,
            self.deleted_count
        )
