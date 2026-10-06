import os
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.constants import MIN_SIMILARITY_THRESHOLD
from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager
from ai.indexer import ImageIndexer, scan_folder_images
from ai.search import search_similar_images, search_by_reference_image
from ai.date_parser import parse_date_and_semantic_query


def make_test_photo_with_date(
    file_path: Path,
    bg_color: tuple,
    title: str,
    subtitle: str,
    dt: datetime,
    exif_original_dt: datetime | None = None,
    exif_modify_dt: datetime | None = None,
):
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 310, 230], outline=(255, 255, 255), width=2)
    d.text((20, 70), title, fill=(255, 255, 255))
    d.text((20, 110), subtitle, fill=(240, 240, 200))

    exif = img.getexif()
    if exif_modify_dt:
        exif[0x0132] = exif_modify_dt.strftime("%Y:%m:%d %H:%M:%S")
    if exif_original_dt:
        exif_ifd = exif.get_ifd(0x8769)
        exif_ifd[0x9003] = exif_original_dt.strftime("%Y:%m:%d %H:%M:%S")

    img.save(file_path, exif=exif)

    # Set filesystem modification time
    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))


def run_advanced_strict_search_tests():
    print("=" * 80)
    print("TESTING ADVANCED SEARCH STRICT RELEVANCE RULES (PART 3/4)")
    print("=" * 80)

    test_root = Path(tempfile.mkdtemp(prefix="imageflow_adv_test_"))
    test_db_dir = test_root / "chroma_db"
    source_photos_dir = test_root / "source_photos"
    external_refs_dir = test_root / "external_refs"
    source_photos_dir.mkdir(parents=True, exist_ok=True)
    external_refs_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Dataset setup:
        # 1. cat_dec10_2025.jpg -> Cat on 2025-12-10 (via mtime)
        # 2. cat_exif_dec10.jpg -> Cat on 2025-12-10 (via EXIF DateTimeOriginal priority)
        # 3. cat_june15_2024.jpg -> Cat on 2024-06-15 (DIFFERENT DATE)
        # 4. sunset_dec10_2025.jpg -> Sunset on 2025-12-10 (SAME DATE, NOT A CAT)
        # 5. car_dec10_2025.jpg -> Car on 2025-12-10 (SAME DATE, NOT A CAT)
        # 6. mountain_jan2026.jpg -> Mountain on 2026-01-01
        dataset = [
            ("cat_dec10_2025.jpg", (200, 180, 140), "Fluffy Persian Cat", "Cute domestic feline pet kitten", datetime(2025, 12, 10, 14, 0), None, None),
            ("cat_exif_dec10.jpg", (190, 170, 130), "Tabby Cat Pet", "Domestic cat feline kitten sleeping", datetime(2026, 5, 20, 12, 0), datetime(2025, 12, 10, 9, 30), datetime(2025, 12, 11, 10, 0)),
            ("cat_june15_2024.jpg", (180, 160, 120), "Siamese Cat Pet", "Blue eyed siamese kitten cat", datetime(2024, 6, 15, 10, 0), None, None),
            ("sunset_dec10_2025.jpg", (240, 90, 40), "Beach Sunset Evening", "Golden sunlight over ocean waves", datetime(2025, 12, 10, 18, 30), None, None),
            ("car_dec10_2025.jpg", (220, 30, 30), "Red Sports Car", "Fast racing vehicle automobile", datetime(2025, 12, 10, 12, 0), None, None),
            ("mountain_jan2026.jpg", (100, 140, 200), "Snowy Mountain Peak", "Rocky mountain summit alps", datetime(2026, 1, 1, 8, 0), None, None),
        ]

        print(f"\nStep 1: Creating {len(dataset)} structured test photos in Source Folder...")
        for fn, col, title, sub, dt, ex_orig, ex_mod in dataset:
            p = source_photos_dir / fn
            make_test_photo_with_date(p, col, title, sub, dt, ex_orig, ex_mod)
            print(f"  + Created: {fn:24s} | EXIF-Orig: {str(ex_orig)[:10]} | MTime: {dt.strftime('%Y-%m-%d')}")

        # Indexing Source Folder into ChromaDB
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="adv_search_collection")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        scanned = scan_folder_images(source_photos_dir, recursive=True)
        indexer.index_images(scanned, prune_missing=True, folder_root=str(source_photos_dir))
        assert chroma.count() == 6
        print(f"  -> ChromaDB populated with {chroma.count()} indexed image records.")

        # =========================================================================
        # 1. DATE + SEMANTIC SEARCH
        # =========================================================================
        print("\n" + "=" * 70)
        print("SCENARIO 1: DATE + SEMANTIC SEARCH ('Show me cat photos from 10 December 2025')")
        print("=" * 70)
        q_date_semantic = "Show me cat photos from 10 December 2025"
        res1 = search_similar_images(
            query=q_date_semantic,
            n_results=20,
            folder_filter=str(source_photos_dir),
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results returned: {len(res1)}")
        for r in res1:
            print(f"    - {r['filename']} | Score: {r['similarity_score']} | Date: {r['metadata'].get('date')}")

        # Strict Assertions:
        # Must return exactly the 2 cats from 2025-12-10 (cat_dec10_2025.jpg and cat_exif_dec10.jpg)
        assert len(res1) == 2, f"Expected exactly 2 results, got {len(res1)}"
        res1_files = [r["filename"] for r in res1]
        assert "cat_dec10_2025.jpg" in res1_files
        assert "cat_exif_dec10.jpg" in res1_files
        
        # NEVER return a cat from another date:
        assert "cat_june15_2024.jpg" not in res1_files, "Cat from June 2024 was incorrectly included!"
        
        # NEVER return a December image that is not a cat:
        assert "sunset_dec10_2025.jpg" not in res1_files, "Sunset was incorrectly included!"
        assert "car_dec10_2025.jpg" not in res1_files, "Car was incorrectly included!"
        
        print("  [PASS] Both DATE MATCH and SEMANTIC MATCH strictly enforced.")

        # =========================================================================
        # 2. REFERENCE IMAGE SEARCH
        # =========================================================================
        print("\n" + "=" * 70)
        print("SCENARIO 2: REFERENCE IMAGE SEARCH")
        print("=" * 70)
        ref_cat_img = external_refs_dir / "external_query_cat.jpg"
        make_test_photo_with_date(
            ref_cat_img,
            (195, 175, 135),
            "Query Ref Cat",
            "Cute domestic cat feline kitten",
            datetime(2026, 1, 1),
        )

        res2 = search_by_reference_image(
            reference_image_input=ref_cat_img,
            n_results=20,
            folder_filter=str(source_photos_dir),
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results returned for Reference Cat: {len(res2)}")
        for r in res2:
            print(f"    - {r['filename']} | Score: {r['similarity_score']}")

        # Should find cats in source folder, excluding cars/mountains
        assert len(res2) > 0, "Expected at least 1 match for reference cat"
        res2_files = [r["filename"] for r in res2]
        assert all("cat" in fn for fn in res2_files), f"Non-cat returned in ref search: {res2_files}"
        
        # Reference image itself must NOT be in results
        assert str(ref_cat_img.resolve()) not in [r["file_path"] for r in res2]

        # Non-matching reference image (e.g. alien spaceship) -> must return 0
        ref_alien_img = external_refs_dir / "external_alien_spaceship.jpg"
        make_test_photo_with_date(
            ref_alien_img,
            (10, 240, 10),
            "Green Alien UFO",
            "Flying saucer extraterrestrial spaceship in galaxy",
            datetime(2026, 1, 1),
        )
        res_alien = search_by_reference_image(
            reference_image_input=ref_alien_img,
            n_results=20,
            min_similarity=0.45,
            folder_filter=str(source_photos_dir),
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results for non-matching reference: {len(res_alien)}")
        assert len(res_alien) == 0, "Non-matching reference image returned unrelated results!"
        print("  [PASS] Reference image search returned only genuine visual matches and excluded ref image.")

        # =========================================================================
        # 3. REFERENCE + DATE SEARCH
        # =========================================================================
        print("\n" + "=" * 70)
        print("SCENARIO 3: REFERENCE + DATE SEARCH ('Find similar images from December 2025')")
        print("=" * 70)
        parsed_dec2025 = parse_date_and_semantic_query("Find similar images from December 2025")
        
        res3 = search_by_reference_image(
            reference_image_input=ref_cat_img,
            n_results=20,
            folder_filter=str(source_photos_dir),
            parsed_date_query=parsed_dec2025,
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results returned for Reference Cat + Dec 2025: {len(res3)}")
        for r in res3:
            print(f"    - {r['filename']} | Score: {r['similarity_score']} | Date: {r['metadata'].get('date')}")

        # Must only return cats from December 2025 (2 cats)
        assert len(res3) == 2, f"Expected 2 matches for cat in Dec 2025, got {len(res3)}"
        res3_files = [r["filename"] for r in res3]
        assert "cat_dec10_2025.jpg" in res3_files
        assert "cat_exif_dec10.jpg" in res3_files
        assert "cat_june15_2024.jpg" not in res3_files, "2024 cat was returned despite Dec 2025 filter!"
        print("  [PASS] Reference + Date search strictly satisfied both filters.")

        print("\n" + "=" * 80)
        print("ALL ADVANCED STRICT RETRIEVAL TESTS COMPLETED AND PASSED!")
        print("=" * 80)
        return True

    finally:
        try:
            shutil.rmtree(test_root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_advanced_strict_search_tests()
    sys.exit(0 if success else 1)
