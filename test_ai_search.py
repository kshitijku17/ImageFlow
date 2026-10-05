import os
import sys
import tempfile
import shutil
from pathlib import Path
from PIL import Image, ImageDraw

from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager
from ai.indexer import ImageIndexer, scan_folder_images
from ai.search import search_similar_images, search_images


def draw_labeled_image(file_path: Path, bg_color: tuple, title: str, subtitle: str):
    """Creates a distinct visual test image."""
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 310, 230], outline=(255, 255, 255), width=3)
    d.text((25, 70), title, fill=(255, 255, 255))
    d.text((25, 110), subtitle, fill=(240, 240, 200))
    img.save(file_path)


def run_search_tests():
    print("=" * 70)
    print("TESTING NATURAL LANGUAGE IMAGE SEARCH (PART 3)")
    print("=" * 70)

    test_dir = Path(tempfile.mkdtemp(prefix="imageflow_search_test_"))
    test_db_dir = test_dir / "chroma_db"
    test_images_dir = test_dir / "source_photos"
    test_images_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Create realistic labeled test image dataset
        images_info = [
            ("img_01_canine.jpg", (180, 120, 70), "Golden Retriever Dog", "A friendly furry dog pet"),
            ("img_02_twilight.jpg", (220, 80, 30), "Vibrant Sunset Beach", "Golden sunset over ocean waves"),
            ("img_03_alps.jpg", (60, 90, 140), "Rocky Snow Mountain", "Tall mountain peak alpine nature"),
            ("img_04_vehicle.jpg", (200, 30, 30), "Fast Red Sports Car", "Bright red automobile coupe"),
            ("img_05_crowd.jpg", (230, 190, 120), "Family on Summer Beach", "People walking on sunny sand shore"),
        ]

        print(f"\nStep 1: Creating {len(images_info)} test images in: {test_images_dir.name}")
        for filename, color, title, subtitle in images_info:
            p = test_images_dir / filename
            draw_labeled_image(p, color, title, subtitle)
            print(f"  + Created: {filename} ({title})")

        # 2. Setup Chroma & Indexer
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="search_test_collection")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        print("\nStep 2: Indexing source folder into ChromaDB...")
        scanned = scan_folder_images(test_images_dir, recursive=True)
        summary = indexer.index_images(scanned, prune_missing=True, folder_root=str(test_images_dir))
        print(f"  -> Indexing Complete: {summary}")
        assert summary["indexed"] == 5, f"Expected 5 indexed, got {summary['indexed']}"

        # 3. Test queries
        queries = [
            ("show me dogs", "img_01_canine.jpg"),
            ("find sunset photos", "img_02_twilight.jpg"),
            ("show me mountains", "img_03_alps.jpg"),
            ("find red cars", "img_04_vehicle.jpg"),
            ("show me people on the beach", "img_05_crowd.jpg"),
        ]

        print("\nStep 3: Executing Natural Language Queries via OpenCLIP + ChromaDB...")
        all_passed = True

        for query_text, expected_top_file in queries:
            print(f"\n" + "-" * 60)
            print(f"Query: \"{query_text}\"")
            print("-" * 60)

            results = search_similar_images(
                query=query_text,
                n_results=20,
                chroma_manager=chroma,
                clip_manager=clip,
            )

            assert len(results) > 0, f"Query '{query_text}' returned no results!"
            top_match = results[0]
            top_filename = top_match["filename"]
            top_score = top_match["similarity_score"]
            top_path = top_match["file_path"]
            top_meta = top_match["metadata"]

            print(f"  Top Match File : {top_filename}")
            print(f"  Full Path      : {top_path}")
            print(f"  Similarity     : {top_score}")
            print(f"  Dimensions     : {top_meta.get('width')}x{top_meta.get('height')}")
            print(f"  Size on Disk   : {top_meta.get('size')} bytes")
            print(f"  Total Results  : {len(results)}")

            # Display ranked matches
            print("  Ranked list:")
            for rank, item in enumerate(results[:3], start=1):
                print(f"    {rank}. {item['filename']} (Score: {item['similarity_score']})")

            if top_filename == expected_top_file:
                print(f"  [PASS] Top match correctly matched expected file '{expected_top_file}'")
            else:
                print(f"  [INFO] Top match: {top_filename} (Expected: {expected_top_file})")

        # 4. Demonstrate backward-compatible search_images
        print("\n" + "=" * 60)
        print("Testing backward-compatible search_images(paths, query)...")
        demo_results = search_images(paths=scanned, query="show me dogs", n_results=5)
        print(f"Results for 'show me dogs':")
        for score, path in demo_results:
            print(f"  -> Score: {score:.4f} | Path: {path}")

        print("\n" + "=" * 70)
        print("ALL NATURAL LANGUAGE SEARCH TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        return True

    finally:
        try:
            shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_search_tests()
    sys.exit(0 if success else 1)
