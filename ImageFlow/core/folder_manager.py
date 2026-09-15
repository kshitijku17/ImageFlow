from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThreadPool

from utils.constants import SUPPORTED
from config.settings import save_settings
from workers.worker import Worker


class FolderManager(QObject):
    """Manages source and destination folder paths and asynchronous directory scanning."""
    source_changed = Signal(Path)
    dest_changed = Signal(Path)
    scan_started = Signal()
    scan_finished = Signal(list)
    scan_error = Signal(str)

    def __init__(self, settings: dict, pool: QThreadPool | None = None):
        super().__init__()
        self.settings = settings
        self.pool = pool or QThreadPool.globalInstance()
        self.source_path: Path | None = None
        self.dest_path: Path | None = None

    def restore_paths(self):
        """Restore remembered source and destination paths from settings."""
        if not self.settings.get("remember_paths", True):
            return
        src = self.settings.get("source", "")
        dst = self.settings.get("destination", "")
        if src and Path(src).is_dir():
            self.set_source_path(Path(src), auto_scan=True)
        if dst and Path(dst).is_dir():
            self.set_dest_path(Path(dst))

    def set_source_path(self, path: Path, auto_scan: bool = True):
        self.source_path = Path(path)
        self.settings["source"] = str(path)
        save_settings(self.settings)
        self.source_changed.emit(self.source_path)
        if auto_scan:
            self.scan_source(self.source_path)

    def set_dest_path(self, path: Path):
        self.dest_path = Path(path)
        self.settings["destination"] = str(path)
        save_settings(self.settings)
        self.dest_changed.emit(self.dest_path)

    def get_destination(self) -> Path | None:
        dst = self.settings.get("destination", "")
        if not dst or not Path(dst).is_dir():
            return None
        return Path(dst)

    def scan_source(self, folder: Path | None = None):
        if folder is None:
            folder = self.source_path
        if folder is None or not folder.is_dir():
            return

        self.scan_started.emit()
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
        w.signals.result.connect(self.scan_finished.emit)
        w.signals.error.connect(self.scan_error.emit)
        self.pool.start(w)
