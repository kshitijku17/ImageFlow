from pathlib import Path


def generate_unique_target(dst: Path, name: str) -> Path:
    """Generate a unique file path in destination folder to avoid overwriting existing files."""
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
