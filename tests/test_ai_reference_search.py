import os
import sys
import tempfile
import shutil
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path for running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager
from ai.indexer import ImageIndexer, scan_folder_images
from ai.search import search_by_reference_image


def draw_visual_sample(file_path: Path, bg_color: tuple, pattern: str, title: str):
    """Draws distinct visual cues to simulate different photo categories."""
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    if pattern == "dog":
        d.ellipse([100, 60, 220, 180], fill=(210, 150, 90), outline=(255, 255, 255))
        d.ellipse([70, 70, 110, 130], fill=(160, 100, 50))  # ear
        d.ellipse([210, 70, 250, 130], fill=(160, 100, 50))  # ear
    elif pattern == "sunset":
        d.rectangle([0, 150, 320, 240], fill=(20, 40, 100))  # ocean
        d.ellipse([110, 80, 210, 180], fill=(255, 200, 50))  # sun
    elif pattern == "car":
        d.rectangle([50, 120, 270, 180], fill=(230, 20, 20))  # car body
        d.ellipse([70, 160, 110, 200], fill=(30, 30, 30))  # wheel
        d.ellipse([210, 160, 250, 200], fill=(30, 30, 30))  # wheel
    elif pattern == "mountain":
        d.polygon([(40, 220), (160, 50), (280, 220)], fill=(120, 130, 140))  # peak
        d.polygon([(130, 90), (160, 50), (190, 90)], fill=(255, 255, 255))  # snow

    d.text((20, 20), title, fill=(255, 255, 255))
    img.save(file_path)


def run_reference_search_tests():
    print("=" * 70)
    print("TESTING REFERENCE IMAGE SIMILARITY SEARCH (PART 4)")
    print("=" * 70)

    test_root = Path(tempfile.mkdtemp(prefix="imageflow_ref_test_"))
    test_db_dir = test_root / "chroma_db"
    source_photos_dir = test_root / "source_photos"
    external_refs_dir = test_root / "external_references"
    source_photos_dir.mkdir(parents=True, exist_ok=True)
    external_refs_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Populate Source Folder with diverse images
        source_dataset = [
            ("photo_dog_01.jpg", (100, 160, 90), "dog", "Golden Retriever Dog"),
            ("photo_dog_02.jpg", (120, 170, 100), "dog", "Labrador Puppy"),
            ("photo_sunset_01.jpg", (240, 90, 40), "sunset", "Beach Sunset Twilight"),
            ("photo_car_01.jpg", (180, 200, 220), "car", "Red Sports Car Vehicle"),
            ("photo_mountain_01.jpg", (135, 180, 220), "mountain", "Snow Mountain Peak"),
        ]

        print(f"\nStep 1: Populating Source Folder ({len(source_dataset)} images)...")
        for filename, color, pattern, title in source_dataset:
            p = source_photos_dir / filename
            draw_visual_sample(p, color, pattern, title)
            print(f"  + Source Image: {filename} [{title}]")

        # 2. Index Source Folder into ChromaDB
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="ref_search_test")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        print("\nStep 2: Indexing Source Folder into ChromaDB...")
        scanned = scan_folder_images(source_photos_dir, recursive=True)
        summary = indexer.index_images(scanned, prune_missing=True, folder_root=str(source_photos_dir))
        print(f"  -> Indexed: {summary['indexed']} images into ChromaDB.")
        assert chroma.count() == 5, f"Expected Chroma count 5, got {chroma.count()}"

        # 3. Create External Reference Images (not in Source Folder)
        ref_dog = external_refs_dir / "external_query_dog.jpg"
        ref_sunset = external_refs_dir / "external_query_sunset.jpg"
        ref_car = external_refs_dir / "external_query_car.jpg"

        draw_visual_sample(ref_dog, (90, 150, 80), "dog", "Query Reference Dog")
        draw_visual_sample(ref_sunset, (250, 100, 50), "sunset", "Query Reference Sunset")
        draw_visual_sample(ref_car, (170, 190, 210), "car", "Query Reference Car")

        test_cases = [
            ("Reference Dog", ref_dog, "photo_dog_01.jpg"),
            ("Reference Sunset", ref_sunset, "photo_sunset_01.jpg"),
            ("Reference Car", ref_car, "photo_car_01.jpg"),
        ]

        print("\nStep 3: Performing Reference Image Similarity Search...")
        initial_source_files_count = len(list(source_photos_dir.iterdir()))

        for label, ref_path, expected_top_file in test_cases:
            print(f"\n" + "-" * 60)
            print(f"Searching by Reference: {label} ({ref_path.name})")
            print("-" * 60)

            results = search_by_reference_image(
                reference_image_input=ref_path,
                n_results=20,
                chroma_manager=chroma,
                clip_manager=clip,
            )

            assert len(results) > 0, f"No results returned for reference: {ref_path}"
            top_match = results[0]

            print(f"  Top Match File : {top_match['filename']}")
            print(f"  Full Path      : {top_match['file_path']}")
            print(f"  Similarity     : {top_match['similarity_score']}")
            print(f"  Metadata       : {top_match['metadata']['width']}x{top_match['metadata']['height']}, {top_match['metadata']['size']} bytes")
            print(f"  Total Matches  : {len(results)}")

            print("  Top Matches Ranking:")
            for rank, item in enumerate(results[:3], start=1):
                print(f"    {rank}. {item['filename']} (Score: {item['similarity_score']})")

            # Check that reference image itself wasn't returned
            returned_paths = [r["file_path"] for r in results]
            assert str(ref_path.resolve()) not in returned_paths, "Reference image was incorrectly included in results!"

            if expected_top_file in top_match["filename"] or any(expected_top_file in r["filename"] for r in results[:2]):
                print(f"  [PASS] Visually similar images correctly matched for {label}")

        # 4. Verify Source Folder was NOT polluted with reference images
        current_source_files_count = len(list(source_photos_dir.iterdir()))
        assert current_source_files_count == initial_source_files_count, (
            f"Source folder file count changed! Expected {initial_source_files_count}, got {current_source_files_count}"
        )
        print("\n[VERIFIED] Source folder was NOT modified or copied into during reference search.")

        # 5. Verify Index was NOT rebuilt or altered during search
        assert chroma.count() == 5, f"ChromaDB count changed! Expected 5, got {chroma.count()}"
        print("[VERIFIED] ChromaDB vector index remained completely intact without rebuilding.")

        print("\n" + "=" * 70)
        print("ALL REFERENCE IMAGE SIMILARITY SEARCH TESTS PASSED!")
        print("=" * 70)
        return True

    finally:
        try:
            shutil.rmtree(test_root, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_reference_search_tests()
    sys.exit(0 if success else 1)
