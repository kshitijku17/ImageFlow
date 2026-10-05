from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Callable, Any
from PIL import Image

from utils.constants import SUPPORTED
from ai.clip_manager import get_model_manager
from ai.chroma_manager import get_chroma_manager

logger = logging.getLogger(__name__)


def normalize_doc_id(file_path: str | Path) -> str:
    """Returns normalized absolute path string used as unique ChromaDB document ID."""
    return os.path.abspath(os.path.normpath(str(file_path)))


def scan_folder_images(folder: Path | str, recursive: bool = False) -> list[str]:
    """Scans folder for supported image files."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        return []

    result = []
    iterator = folder_path.rglob("*") if recursive else folder_path.iterdir()
    for p in iterator:
        try:
            if p.is_file() and p.suffix.lower() in SUPPORTED:
                result.append(normalize_doc_id(p))
        except OSError:
            pass
    result.sort(key=lambda x: x.lower())
    return result


from datetime import datetime


def _parse_date_string(raw_val: Any) -> tuple[str, int, int, int] | None:
    """Helper to parse EXIF date strings into (YYYY-MM-DD, year, month, day)."""
    if not raw_val or not isinstance(raw_val, str):
        return None
    try:
        cleaned = raw_val.strip()
        date_part = cleaned.split(" ", 1)[0].replace(":", "-").replace("/", "-").replace(".", "-")
        d_components = [int(x) for x in date_part.split("-") if x.isdigit()]
        if len(d_components) >= 3:
            y, m, d = d_components[:3]
            if y < 100:
                y += 2000 if y < 70 else 1900
            if y <= 31 and d >= 1900:
                y, d = d, y
            if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{m:02d}-{d:02d}", y, m, d
    except Exception:
        pass
    return None


def parse_exif_date(img: Image.Image) -> tuple[str | None, int | None, int | None, int | None, str | None]:
    """
    Extracts (iso_date_str, year, month, day, source_tag) from EXIF metadata.
    Priority:
    1. EXIF DateTimeOriginal (Tag 0x9003 / 36867 in Exif IFD)
    2. EXIF DateTime (Tag 0x0132 / 306 in 0th IFD or 0x9004 / 36868 in Exif IFD)
    """
    try:
        exif = img.getexif()
        raw_original = None
        raw_datetime = None

        if exif:
            exif_ifd = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
            # Priority 1 tag: DateTimeOriginal (0x9003)
            raw_original = exif_ifd.get(0x9003) if exif_ifd else None
            # Priority 2 tags: DateTime (0x0132) or DateTimeDigitized (0x9004)
            raw_datetime = exif.get(0x0132) or (exif_ifd.get(0x9004) if exif_ifd else None)

        # Fallback to legacy _getexif() if available
        if not raw_original and not raw_datetime and hasattr(img, "_getexif"):
            legacy_exif = img._getexif()
            if legacy_exif and isinstance(legacy_exif, dict):
                raw_original = legacy_exif.get(36867)  # DateTimeOriginal
                raw_datetime = legacy_exif.get(306) or legacy_exif.get(36868)  # DateTime / DateTimeDigitized

        # 1. Check DateTimeOriginal
        if raw_original:
            res = _parse_date_string(raw_original)
            if res:
                return res[0], res[1], res[2], res[3], "exif_original"

        # 2. Check DateTime
        if raw_datetime:
            res = _parse_date_string(raw_datetime)
            if res:
                return res[0], res[1], res[2], res[3], "exif_datetime"

    except Exception as e:
        logger.debug(f"Error parsing EXIF date: {e}")

    return None, None, None, None, None


def extract_image_metadata(file_path: str | Path) -> tuple[dict[str, Any], Image.Image | None]:
    """
    Safely opens an image with Pillow to extract EXIF and file metadata.
    Returns (metadata_dict, pil_image).
    Priority:
    1. EXIF DateTimeOriginal
    2. EXIF DateTime
    3. File modification date as fallback
    """
    path_str = normalize_doc_id(file_path)
    p = Path(path_str)
    stat = p.stat()
    mtime = float(stat.st_mtime)
    ctime = float(getattr(stat, "st_birthtime", stat.st_ctime))
    size = int(stat.st_size)

    # Priority 3: Fallback date from file mtime
    fallback_dt = datetime.fromtimestamp(mtime)
    date_str = fallback_dt.strftime("%Y-%m-%d")
    year = fallback_dt.year
    month = fallback_dt.month
    day = fallback_dt.day
    has_exif_date = False
    date_source = "file_mtime"

    pil_rgb = None
    width = 0
    height = 0

    try:
        with Image.open(path_str) as img:
            width, height = img.size
            # Check Priority 1 & 2 EXIF dates
            exif_date, ey, em, ed, src_tag = parse_exif_date(img)
            if exif_date:
                date_str = exif_date
                year = ey
                month = em
                day = ed
                has_exif_date = True
                date_source = src_tag or "exif"
            # Convert to RGB while open
            pil_rgb = img.convert("RGB")
    except Exception as e:
        logger.warning(f"Could not open image for metadata {path_str}: {e}")

    metadata = {
        "file_path": path_str,
        "filename": p.name,
        "mtime": mtime,
        "ctime": ctime,
        "size": size,
        "width": int(width),
        "height": int(height),
        "date": date_str,
        "year": int(year),
        "month": int(month),
        "day": int(day),
        "has_exif_date": bool(has_exif_date),
        "date_source": str(date_source),
    }
    return metadata, pil_rgb



class ImageIndexer:
    """
    Incremental Image Indexing Engine for OpenCLIP + ChromaDB.
    - Compares file path + mtime to skip unchanged images.
    - Upserts new or modified images into ChromaDB.
    - Prunes deleted files from ChromaDB.
    - Emits progress updates without holding full-res images in RAM.
    """

    def __init__(
        self,
        clip_manager=None,
        chroma_manager=None,
        batch_size: int = 16,
    ):
        self.clip = clip_manager or get_model_manager()
        self.chroma = chroma_manager or get_chroma_manager()
        self.batch_size = batch_size
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def index_images(
        self,
        image_paths: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
        prune_missing: bool = True,
        folder_root: str | None = None,
    ) -> dict[str, int]:
        """
        Indexes a list of image paths incrementally.

        Args:
            image_paths: List of absolute image file paths.
            progress_callback: Optional callable(current, total, status_message).
            prune_missing: If True and folder_root is provided, removes records for deleted files under folder_root.
            folder_root: Root directory for scoping pruning.

        Returns:
            Dict summary: {'total': N, 'indexed': N, 'skipped': N, 'deleted': N, 'failed': N}
        """
        self._cancel_requested = False
        summary = {"total": len(image_paths), "indexed": 0, "skipped": 0, "deleted": 0, "failed": 0}

        # Ensure model and DB are initialized
        if not self.chroma.ensure_ready():
            logger.error("ChromaDB initialization failed; aborting index.")
            return summary
        if not self.clip.ensure_loaded():
            logger.error("OpenCLIP model initialization failed; aborting index.")
            return summary

        normalized_paths = [normalize_doc_id(p) for p in image_paths]
        existing_records = self.chroma.get_all_indexed_metadata()

        # Prune deleted files if folder_root specified
        if prune_missing and folder_root:
            norm_root = normalize_doc_id(folder_root)
            current_set = set(normalized_paths)
            ids_to_delete = []
            for doc_id, meta in existing_records.items():
                # Check if record belongs to this folder hierarchy
                if doc_id.startswith(norm_root) and doc_id not in current_set:
                    if not os.path.exists(doc_id):
                        ids_to_delete.append(doc_id)
            if ids_to_delete:
                self.chroma.delete_by_ids(ids_to_delete)
                summary["deleted"] = len(ids_to_delete)
                for doc_id in ids_to_delete:
                    existing_records.pop(doc_id, None)

        total_count = len(normalized_paths)
        pending_ids = []
        pending_embeddings = []
        pending_metadatas = []

        def flush_batch():
            if pending_ids:
                success = self.chroma.upsert_batch(
                    ids=list(pending_ids),
                    embeddings=list(pending_embeddings),
                    metadatas=list(pending_metadatas)
                )
                if success:
                    summary["indexed"] += len(pending_ids)
                else:
                    summary["failed"] += len(pending_ids)
                pending_ids.clear()
                pending_embeddings.clear()
                pending_metadatas.clear()

        for idx, path_str in enumerate(normalized_paths, start=1):
            if self._cancel_requested:
                logger.info("Indexing cancelled by user request.")
                break

            try:
                stat = os.stat(path_str)
                current_mtime = float(stat.st_mtime)
            except OSError:
                summary["failed"] += 1
                continue

            # Check if unchanged
            existing_meta = existing_records.get(path_str)
            if existing_meta:
                record_mtime = float(existing_meta.get("mtime", 0.0))
                # If mtime matches within tolerance, skip recalculation
                if abs(current_mtime - record_mtime) < 0.001:
                    summary["skipped"] += 1
                    if progress_callback:
                        progress_callback(idx, total_count, f"{idx} / {total_count} images (Skipped)")
                    continue

            # Compute embedding for new or modified image
            metadata, pil_img = extract_image_metadata(path_str)
            if pil_img is None:
                summary["failed"] += 1
                continue

            try:
                emb = self.clip.get_image_embedding(pil_img)
            finally:
                # Explicitly close and clean up PIL Image to keep RAM low
                try:
                    pil_img.close()
                except Exception:
                    pass
                del pil_img

            if emb is None:
                summary["failed"] += 1
                continue

            pending_ids.append(path_str)
            pending_embeddings.append(emb)
            pending_metadatas.append(metadata)

            if len(pending_ids) >= self.batch_size:
                flush_batch()

            if progress_callback:
                progress_callback(idx, total_count, f"{idx} / {total_count} images")

        flush_batch()

        if progress_callback:
            progress_callback(total_count, total_count, f"{total_count} / {total_count} images completed")

        logger.info(f"Indexing complete: {summary}")
        return summary
