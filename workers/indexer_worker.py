from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QRunnable
from ai.indexer import ImageIndexer, scan_folder_images


class IndexerSignals(QObject):
    progress = Signal(int, int, str)  # current, total, progress_str (e.g. "245 / 2500 images")
    finished = Signal(dict)          # summary stats dict
    error = Signal(str)


class IndexerWorker(QRunnable):
    """
    Background worker for asynchronous incremental image indexing.
    Runs OpenCLIP embedding extraction and ChromaDB upserts without blocking the UI.
    """
    _active_workers = set()

    def __init__(
        self,
        folder_or_paths: str | Path | list[str],
        recursive: bool = False,
        prune_missing: bool = True,
    ):
        super().__init__()
        self.folder_or_paths = folder_or_paths
        self.recursive = recursive
        self.prune_missing = prune_missing
        self.signals = IndexerSignals()
        self.indexer = ImageIndexer()

        IndexerWorker._active_workers.add(self)
        self.signals.finished.connect(self._cleanup)
        self.signals.error.connect(self._cleanup)

    def _cleanup(self):
        IndexerWorker._active_workers.discard(self)

    def cancel(self):
        self.indexer.request_cancel()

    def run(self):
        try:
            folder_root = None
            if isinstance(self.folder_or_paths, (str, Path)):
                folder_root = str(self.folder_or_paths)
                image_paths = scan_folder_images(folder_root, recursive=self.recursive)
            else:
                image_paths = list(self.folder_or_paths)

            def on_progress(current: int, total: int, msg: str):
                self.signals.progress.emit(current, total, msg)

            summary = self.indexer.index_images(
                image_paths=image_paths,
                progress_callback=on_progress,
                prune_missing=self.prune_missing,
                folder_root=folder_root,
            )
            self.signals.finished.emit(summary)
        except Exception as e:
            self.signals.error.emit(str(e))
