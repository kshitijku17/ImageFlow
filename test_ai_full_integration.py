import os
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager
from ai.indexer import ImageIndexer, scan_folder_images
from ai.search import search_similar_images, search_by_reference_image
from ai.date_parser import parse_date_and_semantic_query


def make_test_photo(file_path: Path, bg_color: tuple, pattern: str, title: str, dt: datetime):
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    if pattern == "dog":
        d.ellipse([90, 60, 230, 180], fill=(210, 150, 90))
        d.ellipse([70, 70, 100, 120], fill=(160, 100, 50))
        d.ellipse([220, 70, 250, 120], fill=(160, 100, 50))
    elif pattern == "sunset":
        d.rectangle([0, 140, 320, 240], fill=(20, 50, 110))
        d.ellipse([110, 70, 210, 170], fill=(255, 190, 40))
    elif pattern == "mountain":
        d.polygon([(30, 220), (160, 40), (290, 220)], fill=(110, 120, 130))
        d.polygon([(130, 80), (160, 40), (190, 80)], fill=(255, 255, 255))
    elif pattern == "car":
        d.rectangle([40, 110, 280, 170], fill=(220, 20, 20))
        d.ellipse([60, 150, 100, 190], fill=(20, 20, 20))
        d.ellipse([220, 150, 260, 190], fill=(20, 20, 20))

    d.text((20, 20), title, fill=(255, 255, 255))
    img.save(file_path)

    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))


def run_full_integration_tests():
    print("=" * 80)
    print("TESTING FULL AI INTEGRATION (PART 6)")
    print("=" * 80)

    test_root = Path(tempfile.mkdtemp(prefix="imageflow_full_test_"))
    test_db_dir = test_root / "chroma_db"
    source_dir = test_root / "source_photos"
    external_dir = test_root / "external_refs"
    source_dir.mkdir(parents=True, exist_ok=True)
    external_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Populate real indexed Source Folder
        photos = [
            ("golden_dog_dec10.jpg", (160, 120, 80), "dog", "Golden Dog Dec 10", datetime(2025, 12, 10, 14, 0)),
            ("puppy_dog_june.jpg", (150, 110, 70), "dog", "Puppy Dog June 2024", datetime(2024, 6, 15, 11, 0)),
            ("beach_sunset_dec10.jpg", (240, 90, 40), "sunset", "Sunset Beach Dec 10", datetime(2025, 12, 10, 18, 30)),
            ("mountain_dec25.jpg", (120, 140, 180), "mountain", "Snow Mountain Dec 25", datetime(2025, 12, 25, 9, 0)),
            ("red_car_jan.jpg", (200, 30, 30), "car", "Red Sports Car Jan 2023", datetime(2023, 1, 1, 12, 0)),
        ]

        print(f"\n[Setup] Creating {len(photos)} real test photos in Source Folder...")
        for fn, col, pat, title, dt in photos:
            p = source_dir / fn
            make_test_photo(p, col, pat, title, dt)
            print(f"  + {fn:24s} | Date: {dt.strftime('%Y-%m-%d')} | Concept: {pat}")

        # 2. Reference Image
        ref_dog_img = external_dir / "reference_golden_dog.jpg"
        make_test_photo(ref_dog_img, (155, 115, 75), "dog", "Ref Dog Query", datetime(2026, 1, 1))

        # 3. Initialize Chroma & OpenCLIP
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="full_test_collection")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        scanned = scan_folder_images(source_dir, recursive=True)
        indexer.index_images(scanned, prune_missing=True, folder_root=str(source_dir))
        assert chroma.count() == 5, f"Chroma count expected 5, got {chroma.count()}"
        print(f"  -> ChromaDB populated with {chroma.count()} indexed image embeddings.")

        # TEST 1: "show me dogs"
        print("\n" + "=" * 60)
        print("TEST 1: User asks \"show me dogs\"")
        print("=" * 60)
        res1 = search_similar_images("show me dogs", chroma_manager=chroma, clip_manager=clip)
        assert len(res1) > 0
        print(f"AI: \"I found {len(res1)} matching images.\"")
        for rank, r in enumerate(res1[:2], 1):
            print(f"  {rank}. {r['filename']} (Score: {r['similarity_score']}) -> {r['file_path']}")
        assert "dog" in res1[0]["filename"]

        # TEST 2: "show me sunset photos"
        print("\n" + "=" * 60)
        print("TEST 2: User asks \"show me sunset photos\"")
        print("=" * 60)
        res2 = search_similar_images("show me sunset photos", chroma_manager=chroma, clip_manager=clip)
        assert len(res2) > 0
        print(f"AI: \"I found {len(res2)} matching images.\"")
        for rank, r in enumerate(res2[:2], 1):
            print(f"  {rank}. {r['filename']} (Score: {r['similarity_score']}) -> {r['file_path']}")
        assert "sunset" in res2[0]["filename"]

        # TEST 3: "show me photos from 10 December 2025"
        print("\n" + "=" * 60)
        print("TEST 3: User asks \"show me photos from 10 December 2025\"")
        print("=" * 60)
        res3 = search_similar_images("show me photos from 10 December 2025", chroma_manager=chroma, clip_manager=clip)
        print(f"AI: \"I found {len(res3)} matching images.\"")
        for rank, r in enumerate(res3, 1):
            print(f"  {rank}. {r['filename']} | Date: {r['metadata'].get('date')} -> {r['file_path']}")
        assert len(res3) == 2
        assert all(r["metadata"].get("date") == "2025-12-10" for r in res3)

        # TEST 4: "show me dog photos from 10 December 2025"
        print("\n" + "=" * 60)
        print("TEST 4: User asks \"show me dog photos from 10 December 2025\"")
        print("=" * 60)
        res4 = search_similar_images("show me dog photos from 10 December 2025", chroma_manager=chroma, clip_manager=clip)
        print(f"AI: \"I found {len(res4)} matching images.\"")
        for rank, r in enumerate(res4, 1):
            print(f"  {rank}. {r['filename']} (Score: {r['similarity_score']}) | Date: {r['metadata'].get('date')}")
        assert len(res4) == 1
        assert res4[0]["filename"] == "golden_dog_dec10.jpg"

        # TEST 5: Upload reference image -> "find similar images"
        print("\n" + "=" * 60)
        print("TEST 5: Upload reference dog image -> \"find similar images\"")
        print("=" * 60)
        res5 = search_by_reference_image(ref_dog_img, chroma_manager=chroma, clip_manager=clip)
        print(f"AI: \"I found {len(res5)} matching images visually similar to '{ref_dog_img.name}'.\"")
        for rank, r in enumerate(res5[:2], 1):
            print(f"  {rank}. {r['filename']} (Score: {r['similarity_score']}) -> {r['file_path']}")
        assert "dog" in res5[0]["filename"]

        # TEST 6: Upload reference image -> "find similar images from December"
        print("\n" + "=" * 60)
        print("TEST 6: Upload reference dog image -> \"find similar images from December\"")
        print("=" * 60)
        parsed6 = parse_date_and_semantic_query("find similar images from December 2025")
        res6_raw = search_by_reference_image(ref_dog_img, chroma_manager=chroma, clip_manager=clip)
        from ai.search import matches_date_filter
        res6 = [r for r in res6_raw if matches_date_filter(r.get("metadata", {}), parsed6)]
        print(f"AI: \"I found {len(res6)} matching images visually similar to '{ref_dog_img.name}' from December 2025.\"")
        for rank, r in enumerate(res6, 1):
            print(f"  {rank}. {r['filename']} (Score: {r['similarity_score']}) | Date: {r['metadata'].get('date')}")
        assert len(res6) > 0
        assert res6[0]["filename"] == "golden_dog_dec10.jpg"

        print("\n" + "=" * 80)
        print("ALL 6 INTEGRATION SCENARIOS TESTED AND PASSED WITH REAL INDEXED IMAGES!")
        print("=" * 80)
        return True

    finally:
        try:
            shutil.rmtree(test_root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_full_integration_tests()
    sys.exit(0 if success else 1)
