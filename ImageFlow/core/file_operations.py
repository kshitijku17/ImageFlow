import shutil
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThreadPool

from utils.helpers import generate_unique_target
from workers.worker import Worker


class FileOperationsManager(QObject):
    """Handles asynchronous file system operations: Copy, Batch Copy, Move, Delete to Recycle, and Undo."""
    started = Signal()
    finished = Signal()
    copy_completed = Signal(object, object, int)          # target: Path, selected_source: Path, old_index: int
    batch_copy_completed = Signal(list, int)              # results: list[tuple[int, Path, Path]], current_index: int
    move_completed = Signal(object, object)                # source: Path, target: Path
    delete_completed = Signal(object, object, int)         # source: Path, recycle_target: Path, old_index: int
    undo_completed = Signal(object, int)                  # target: Path, old_index: int
    error_occurred = Signal(str, str)                     # title: str, error_msg: str

    def __init__(self, pool: QThreadPool | None = None):
        super().__init__()
        self.pool = pool or QThreadPool.globalInstance()

    def copy_image(self, source: Path, dst: Path, old_index: int):
        self.started.emit()

        def op():
            # Copy the original image to destination using its original name.
            target = generate_unique_target(dst, source.name)
            shutil.copy2(source, target)

            # Then mark the source copy as selected:
            # photo.jpg -> photo-selected.jpg
            selected_source = source.with_name(
                f"{source.stem}-selected{source.suffix}"
            )

            if selected_source.exists():
                selected_source = generate_unique_target(
                    source.parent,
                    f"{source.stem}-selected{source.suffix}"
                )

            source.rename(selected_source)
            return target, selected_source

        w = Worker(op)
        w.signals.result.connect(
            lambda res: self.copy_completed.emit(res[0], res[1], old_index)
        )
        w.signals.error.connect(lambda e: self.error_occurred.emit("Copy failed", str(e)))
        w.signals.finished.connect(self.finished.emit)
        self.pool.start(w)

    def copy_selected(self, items: list[tuple[int, str]], dst: Path, current_index: int):
        """Batch-copy selected images in one background operation."""
        self.started.emit()

        def op():
            results = []
            for idx, path_string in items:
                source = Path(path_string)
                if not source.exists():
                    continue

                target = generate_unique_target(dst, source.name)
                shutil.copy2(source, target)

                selected_source = source.with_name(
                    f"{source.stem}-selected{source.suffix}"
                )
                if selected_source.exists():
                    selected_source = generate_unique_target(
                        source.parent, f"{source.stem}-selected{source.suffix}"
                    )
                source.rename(selected_source)
                results.append((idx, target, selected_source))
            return results

        w = Worker(op)
        w.signals.result.connect(
            lambda res: self.batch_copy_completed.emit(res, current_index)
        )
        w.signals.error.connect(lambda e: self.error_occurred.emit("Copy failed", str(e)))
        w.signals.finished.connect(self.finished.emit)
        self.pool.start(w)

    def move_image(self, source: Path, destination: Path):
        self.started.emit()

        def op():
            target = generate_unique_target(destination, source.name)
            shutil.move(str(source), str(target))
            return target

        w = Worker(op)
        w.signals.result.connect(lambda target: self.move_completed.emit(source, target))
        w.signals.error.connect(lambda e: self.error_occurred.emit("Move failed", str(e)))
        w.signals.finished.connect(self.finished.emit)
        self.pool.start(w)

    def delete_image(self, source: Path, old_index: int):
        recycle = source.parent / "Recycle"
        try:
            recycle.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.error_occurred.emit("Delete", f"Could not create Recycle folder.\n\n{e}")
            return

        target = generate_unique_target(recycle, source.name)
        self.started.emit()

        def op():
            shutil.move(str(source), str(target))
            return target

        w = Worker(op)
        w.signals.result.connect(
            lambda t: self.delete_completed.emit(source, t, old_index)
        )
        w.signals.error.connect(lambda e: self.error_occurred.emit("Delete failed", str(e)))
        w.signals.finished.connect(self.finished.emit)
        self.pool.start(w)

    def undo_delete(self, source: Path, recycle_target: Path, old_index: int):
        if not recycle_target.exists():
            self.error_occurred.emit(
                "Undo Delete", "The deleted file is no longer available."
            )
            return

        target = source
        if target.exists():
            target = generate_unique_target(source.parent, source.name)

        self.started.emit()

        def op():
            shutil.move(str(recycle_target), str(target))
            return target

        w = Worker(op)
        w.signals.result.connect(lambda t: self.undo_completed.emit(t, old_index))
        w.signals.error.connect(lambda e: self.error_occurred.emit("Undo failed", str(e)))
        w.signals.finished.connect(self.finished.emit)
        self.pool.start(w)
