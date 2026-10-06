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


def make_test_photo(file_path: Path, bg_color: tuple, title: str, subtitle: str, dt: datetime):
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 310, 230], outline=(255, 255, 255), width=2)
    d.text((20, 70), title, fill=(255, 255, 255))
    d.text((20, 110), subtitle, fill=(240, 240, 200))
    img.save(file_path)

    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))


def run_final_zero_false_positive_tests():
    print("=" * 80)
    print("FINAL STRICT / ZERO-FALSE-POSITIVE VERIFICATION (PART 4/4)")
    print("=" * 80)

    test_root = Path(tempfile.mkdtemp(prefix="imageflow_final_test_"))
    test_db_dir = test_root / "chroma_db"
    source_photos_dir = test_root / "source_photos"
    external_refs_dir = test_root / "external_refs"
    source_photos_dir.mkdir(parents=True, exist_ok=True)
    external_refs_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Realistic Dataset in Source Folder:
        # 3 Cats (2 on 2025-12-10, 1 on 2024-06-15)
        # 1 Sunset on 2025-12-10
        # 1 Red Car on 2023-01-01
        # 1 Snow Mountain on 2025-12-25
        # 1 Commercial Airplane on 2025-05-10
        dataset = [
            ("cat_01_persian_dec10.jpg", (200, 180, 140), "Persian Cat Feline", "Fluffy white kitten cat sitting", datetime(2025, 12, 10, 14, 0)),
            ("cat_02_tabby_dec10.jpg", (170, 150, 120), "Tabby Cat Pet", "Domestic cat feline kitten sleeping", datetime(2025, 12, 10, 9, 30)),
            ("cat_03_siamese_june.jpg", (190, 160, 130), "Siamese Kitten", "Cute Siamese cat pet with blue eyes", datetime(2024, 6, 15, 11, 0)),
            ("sunset_dec10.jpg", (240, 90, 40), "Vibrant Sunset Beach", "Golden sunset over ocean waves", datetime(2025, 12, 10, 18, 30)),
            ("car_red_jan.jpg", (220, 30, 30), "Fast Red Sports Car", "Bright red automobile coupe vehicle", datetime(2023, 1, 1, 12, 0)),
            ("mountain_dec25.jpg", (100, 140, 200), "Rocky Snow Mountain", "Tall mountain peak alpine nature", datetime(2025, 12, 25, 8, 15)),
            ("airplane_may.jpg", (180, 190, 210), "Commercial Jetliner", "Passenger airplane flying in blue sky", datetime(2025, 5, 10, 16, 0)),
        ]

        print(f"\n[Setup] Indexing {len(dataset)} real test photos into ChromaDB...")
        for fn, col, title, sub, dt in dataset:
            p = source_photos_dir / fn
            make_test_photo(p, col, title, sub, dt)
            print(f"  + {fn:28s} | Date: {dt.strftime('%Y-%m-%d')} | {title}")

        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="final_test_collection")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        scanned = scan_folder_images(source_photos_dir, recursive=True)
        indexer.index_images(scanned, prune_missing=True, folder_root=str(source_photos_dir))
        assert chroma.count() == 7

        # ---------------------------------------------------------------------
        # TEST 1: "Show me cat images" -> ONLY actual cat images
        # ---------------------------------------------------------------------
        print("\n" + "-" * 70)
        print("TEST 1: 'Show me cat images' (Precision Test)")
        print("-" * 70)
        res1 = search_similar_images("Show me cat images", folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        print(f"Results returned: {len(res1)}")
        for r in res1:
            print(f"  - {r['filename']} (Score: {r['similarity_score']})")
        assert len(res1) == 3, f"Expected 3 cat images, got {len(res1)}"
        assert all("cat" in r["filename"] for r in res1), "Non-cat image returned in cat search!"
        print("  [PASS] Only actual cat images were retrieved.")

        # ---------------------------------------------------------------------
        # TEST 2: Exactly 3 results, NOT 20 (No top-k padding)
        # ---------------------------------------------------------------------
        print("\n" + "-" * 70)
        print("TEST 2: Strict Result Count (Max limit top_k=20, exactly 3 matching)")
        print("-" * 70)
        res2 = search_similar_images("cat", n_results=20, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        print(f"Results returned with n_results=20: {len(res2)}")
        assert len(res2) == 3, f"Expected exactly 3 results, got {len(res2)}"
        print("  [PASS] Returned exactly 3 results, did NOT pad to 20.")

        # ---------------------------------------------------------------------
        # TEST 3: Search for an object that does not exist -> 0 results
        # ---------------------------------------------------------------------
        print("\n" + "-" * 70)
        print("TEST 3: Non-existent object search ('astronaut on the moon')")
        print("-" * 70)
        res3 = search_similar_images("astronaut on the moon", n_results=20, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        print(f"Results returned for non-existent object: {len(res3)}")
        assert len(res3) == 0, f"Expected 0 results, got {len(res3)}"
        print("  [PASS] Returned exactly 0 results for non-existent concept.")

        # ---------------------------------------------------------------------
        # TEST 4: "Show me cat photos from 10 December 2025" -> Both Date & Cat
        # ---------------------------------------------------------------------
        print("\n" + "-" * 70)
        print("TEST 4: Date + Semantic Search ('Show me cat photos from 10 December 2025')")
        print("-" * 70)
        res4 = search_similar_images("Show me cat photos from 10 December 2025", n_results=20, folder_filter=str(source_photos_dir), chroma_manager=chroma, clip_manager=clip)
        print(f"Results returned: {len(res4)}")
        for r in res4:
            print(f"  - {r['filename']} (Score: {r['similarity_score']}) | Date: {r['metadata'].get('date')}")
        assert len(res4) == 2, f"Expected 2 cats on Dec 10 2025, got {len(res4)}"
        res4_files = [r["filename"] for r in res4]
        assert "cat_01_persian_dec10.jpg" in res4_files
        assert "cat_02_tabby_dec10.jpg" in res4_files
        assert "cat_03_siamese_june.jpg" not in res4_files, "June cat was returned despite Dec 10 date filter!"
        assert "sunset_dec10.jpg" not in res4_files, "Dec 10 sunset was returned despite cat query!"
        print("  [PASS] Returned ONLY images satisfying BOTH 10 Dec 2025 date and cat concept.")

        # ---------------------------------------------------------------------
        # TEST 5: Reference Image Similarity -> ONLY sufficiently similar images
        # ---------------------------------------------------------------------
        print("\n" + "-" * 70)
        print("TEST 5: Reference Image Search (Visual similarity)")
        print("-" * 70)
        ref_cat = external_refs_dir / "ref_query_cat.jpg"
        make_test_photo(ref_cat, (195, 175, 135), "Reference Cat", "Cute domestic kitten cat pet", datetime(2026, 1, 1))

        res5 = search_by_reference_image(
            reference_image_input=ref_cat,
            n_results=20,
            folder_filter=str(source_photos_dir),
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"Results returned for reference cat: {len(res5)}")
        for r in res5:
            print(f"  - {r['filename']} (Score: {r['similarity_score']})")
        assert len(res5) > 0
        assert all("cat" in r["filename"] for r in res5), "Unrelated visual match returned!"
        assert str(ref_cat.resolve()) not in [r["file_path"] for r in res5], "Reference image included in results!"
        print("  [PASS] Reference image search returned ONLY sufficiently similar images.")

        print("\n" + "=" * 80)
        print("ALL 5 ZERO-FALSE-POSITIVE FINAL TESTS COMPLETED AND PASSED!")
        print("=" * 80)
        return True

    finally:
        try:
            shutil.rmtree(test_root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_final_zero_false_positive_tests()
    sys.exit(0 if success else 1)
