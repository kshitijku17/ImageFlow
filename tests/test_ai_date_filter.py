import os
import sys
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path for running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager
from ai.indexer import ImageIndexer, scan_folder_images, extract_image_metadata
from ai.search import search_similar_images, matches_date_filter
from ai.date_parser import parse_date_and_semantic_query


def create_image_with_timestamp(file_path: Path, bg_color: tuple, title: str, dt: datetime, exif_original_dt: datetime | None = None, exif_modify_dt: datetime | None = None):
    """Creates a test image with optional EXIF timestamps and filesystem mtime."""
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 310, 230], outline=(255, 255, 255), width=2)
    d.text((20, 70), title, fill=(255, 255, 255))
    d.text((20, 110), f"Date: {dt.strftime('%Y-%m-%d')}", fill=(240, 240, 200))

    exif = img.getexif()
    if exif_modify_dt:
        exif[0x0132] = exif_modify_dt.strftime("%Y:%m:%d %H:%M:%S")
    if exif_original_dt:
        exif_ifd = exif.get_ifd(0x8769)
        exif_ifd[0x9003] = exif_original_dt.strftime("%Y:%m:%d %H:%M:%S")

    img.save(file_path, exif=exif)

    # Set file access and modification times to dt
    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))


def run_date_filtering_tests():
    print("=" * 75)
    print("TESTING DATE AND METADATA FILTERING SUITE")
    print("=" * 75)

    test_root = Path(tempfile.mkdtemp(prefix="imageflow_date_test_"))
    test_db_dir = test_root / "chroma_db"
    source_photos_dir = test_root / "source_photos"
    outside_photos_dir = test_root / "outside_photos"
    source_photos_dir.mkdir(parents=True, exist_ok=True)
    outside_photos_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Create dataset with explicit target dates & EXIF tags
        dataset = [
            ("dog_dec10_2025.jpg", (170, 120, 70), "Golden Dog", datetime(2025, 12, 10, 14, 30), None, None),
            ("dog_june15_2024.jpg", (160, 110, 60), "Puppy Dog", datetime(2024, 6, 15, 10, 0), None, None),
            ("sunset_dec10_2025.jpg", (230, 80, 40), "Beach Sunset", datetime(2025, 12, 10, 18, 45), None, None),
            ("mountain_dec25_2025.jpg", (100, 130, 180), "Snow Mountain", datetime(2025, 12, 25, 8, 15), None, None),
            ("car_jan01_2023.jpg", (210, 40, 40), "Red Sports Car", datetime(2023, 1, 1, 12, 0), None, None),
            # EXIF priority test image: DateTimeOriginal takes precedence over DateTime and mtime
            ("exif_priority_photo.jpg", (90, 150, 120), "Exif Photo", datetime(2026, 5, 20, 12, 0), datetime(2025, 12, 10, 9, 0), datetime(2025, 12, 11, 9, 0)),
        ]

        print(f"\nStep 1: Creating test images with specific timestamps and EXIF in {source_photos_dir.name}...")
        for filename, color, title, dt, ex_orig, ex_mod in dataset:
            p = source_photos_dir / filename
            create_image_with_timestamp(p, color, title, dt, exif_original_dt=ex_orig, exif_modify_dt=ex_mod)
            print(f"  + {filename:26s} | MTime: {dt.strftime('%Y-%m-%d')} | ExifOriginal: {ex_orig}")

        # Outside photo (should be excluded from source folder searches)
        p_out = outside_photos_dir / "dog_outside_dec10.jpg"
        create_image_with_timestamp(p_out, (170, 120, 70), "Outside Dog", datetime(2025, 12, 10, 12, 0))

        # 2. Test EXIF Priority directly on metadata extraction
        print("\nStep 2: Testing EXIF Date Priority (1. DateTimeOriginal -> 2. DateTime -> 3. mtime)...")
        meta_exif, _ = extract_image_metadata(source_photos_dir / "exif_priority_photo.jpg")
        print(f"  Exif priority image extracted date: {meta_exif['date']}, source: {meta_exif.get('date_source')}")
        assert meta_exif["date"] == "2025-12-10", f"Expected 2025-12-10 (DateTimeOriginal), got {meta_exif['date']}"
        assert meta_exif["has_exif_date"] is True

        meta_fallback, _ = extract_image_metadata(source_photos_dir / "dog_dec10_2025.jpg")
        print(f"  Fallback mtime image extracted date: {meta_fallback['date']}, source: {meta_fallback.get('date_source')}")
        assert meta_fallback["date"] == "2025-12-10"
        assert meta_fallback["date_source"] == "file_mtime"
        print("  [PASS] EXIF priority logic verified.")

        # 3. Index into ChromaDB
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="date_test_collection")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        print("\nStep 3: Indexing metadata and embeddings into ChromaDB...")
        scanned_source = scan_folder_images(source_photos_dir, recursive=True)
        scanned_out = scan_folder_images(outside_photos_dir, recursive=True)
        indexer.index_images(scanned_source + scanned_out, prune_missing=True)
        print(f"  -> Total images in DB: {chroma.count()}")

        # 4. Test Date Parser across natural language query formats
        print("\nStep 4: Validating Date Parser on natural language formats...")
        format_tests = [
            ("Show me photos from 10 December 2025", 2025, 12, 10, True, ""),
            ("Give me pictures taken on 10 December 2025", 2025, 12, 10, True, ""),
            ("Find photos from December 2025", 2025, 12, None, True, ""),
            ("show me dog photos from 10 December 2025", 2025, 12, 10, False, "dog"),
            ("10 December 2025", 2025, 12, 10, True, ""),
            ("10 Dec 2025", 2025, 12, 10, True, ""),
            ("December 10 2025", 2025, 12, 10, True, ""),
            ("10/12/2025", 2025, 12, 10, True, ""),
            ("12/2025", 2025, 12, None, True, ""),
            ("Dec 2025", 2025, 12, None, True, ""),
        ]
        for query_str, ey, em, ed, e_date_only, e_clean in format_tests:
            parsed = parse_date_and_semantic_query(query_str)
            print(f"  Query: \"{query_str}\" -> Year={parsed.year}, Month={parsed.month}, Day={parsed.day}, DateOnly={parsed.is_date_only}, Clean='{parsed.clean_query}'")
            assert parsed.year == ey, f"Expected year {ey}, got {parsed.year}"
            assert parsed.month == em, f"Expected month {em}, got {parsed.month}"
            assert parsed.day == ed, f"Expected day {ed}, got {parsed.day}"
            assert parsed.is_date_only == e_date_only, f"Expected date_only={e_date_only}, got {parsed.is_date_only}"
            if e_clean:
                assert e_clean in parsed.clean_query.lower()
        print("  [PASS] Date parser accurately handles all natural language formats.")

        # 5. Test 1: Date-Only Searches (Scoped to source_photos_dir)
        print("\nStep 5: Testing Date-Only Searches...")

        # "Show me photos from 10 December 2025"
        q_dec10 = "Show me photos from 10 December 2025"
        res_dec10 = search_similar_images(q_dec10, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        filenames_dec10 = [r["filename"] for r in res_dec10]
        print(f"\nResults for \"{q_dec10}\":")
        for r in res_dec10:
            print(f"  -> {r['filename']} | Date: {r['metadata'].get('date')} | Path: {r['file_path']}")
        # 3 matching photos in source_photos_dir on 2025-12-10 (dog, sunset, and exif_priority_photo)
        assert len(res_dec10) == 3, f"Expected 3 matches, got {len(res_dec10)}"
        assert "dog_dec10_2025.jpg" in filenames_dec10
        assert "sunset_dec10_2025.jpg" in filenames_dec10
        assert "exif_priority_photo.jpg" in filenames_dec10
        assert "dog_outside_dec10.jpg" not in filenames_dec10, "Outside photo was incorrectly included!"
        print("  [PASS] Date-only search returned exact matching images inside Source Folder.")

        # "Give me pictures taken on 10 December 2025"
        q_give = "Give me pictures taken on 10 December 2025"
        res_give = search_similar_images(q_give, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        assert len(res_give) == 3, f"Expected 3 matches for 'Give me...', got {len(res_give)}"
        print("  [PASS] 'Give me pictures taken on 10 December 2025' succeeded.")

        # 6. Test 2: Month/Year Search
        print("\nStep 6: Testing Month/Year Searches...")
        q_month = "Find photos from December 2025"
        res_month = search_similar_images(q_month, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        filenames_month = [r["filename"] for r in res_month]
        print(f"\nResults for \"{q_month}\":")
        for r in res_month:
            print(f"  -> {r['filename']} | Date: {r['metadata'].get('date')}")
        # dog_dec10, sunset_dec10, exif_priority_photo, mountain_dec25 -> 4 matches in source folder
        assert len(res_month) == 4, f"Expected 4 matches for Dec 2025, got {len(res_month)}"
        assert "mountain_dec25_2025.jpg" in filenames_month
        print("  [PASS] Month/Year search returned all 4 December 2025 photos in source folder.")

        # 7. Test 3: Semantic + Date Search
        print("\nStep 7: Testing Semantic + Date Search...")
        q_combo = "Show me dog photos from 10 December 2025"
        res_combo = search_similar_images(q_combo, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        print(f"\nResults for \"{q_combo}\":")
        for r in res_combo:
            print(f"  -> {r['filename']} | Score: {r['similarity_score']} | Date: {r['metadata'].get('date')}")

        assert len(res_combo) > 0, "No results returned for combo query!"
        top_combo = res_combo[0]
        assert top_combo["filename"] == "dog_dec10_2025.jpg", f"Expected top match dog_dec10_2025.jpg, got {top_combo['filename']}"
        assert "dog_june15_2024.jpg" not in [r["filename"] for r in res_combo], "2024 dog was incorrectly included despite 2025 date filter!"
        print("  [PASS] Semantic + Date query ranked the 10 Dec 2025 dog photo at top.")

        # 8. Test 4: No-Result Search
        print("\nStep 8: Testing No-Result Date Search...")
        q_empty = "Show me photos from 15 August 1999"
        res_empty = search_similar_images(q_empty, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        print(f"Results for non-existent date: {res_empty}")
        assert len(res_empty) == 0, f"Expected 0 results, got {len(res_empty)}"
        print("  [PASS] Non-matching date query correctly returned empty list.")

        # 9. Test Incremental Indexing (Skipping unchanged images)
        print("\nStep 9: Testing Incremental Indexing (Skipping unchanged files)...")
        summary_reindex = indexer.index_images(scanned_source, prune_missing=True, folder_root=str(source_photos_dir))
        print(f"  Reindex summary: {summary_reindex}")
        assert summary_reindex["skipped"] == len(scanned_source), f"Expected all {len(scanned_source)} images skipped, got {summary_reindex}"
        assert summary_reindex["indexed"] == 0
        print("  [PASS] Unchanged images were correctly skipped without re-indexing.")

        print("\n" + "=" * 75)
        print("ALL DATE-BASED SEARCH AND METADATA TESTS PASSED SUCCESSFULLY!")
        print("=" * 75)
        return True

    finally:
        try:
            shutil.rmtree(test_root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_date_filtering_tests()
    sys.exit(0 if success else 1)
