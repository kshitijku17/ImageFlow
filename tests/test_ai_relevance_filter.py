import os
import sys
import tempfile
import shutil
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.constants import MIN_SIMILARITY_THRESHOLD
from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager, get_image_embedding, get_text_embedding
from ai.indexer import ImageIndexer, scan_folder_images
from ai.search import search_similar_images, search_by_reference_image, search_images, format_clip_text_prompt


def draw_test_photo(file_path: Path, bg_color: tuple, title: str, subtitle: str):
    img = Image.new("RGB", (320, 240), color=bg_color)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 310, 230], outline=(255, 255, 255), width=2)
    d.text((20, 70), title, fill=(255, 255, 255))
    d.text((20, 110), subtitle, fill=(240, 240, 200))
    img.save(file_path)


def run_relevance_filter_tests():
    print("=" * 75)
    print("TESTING STRICT SEMANTIC MATCHING & OPENCLIP RETRIEVAL (PART 2/4)")
    print("=" * 75)

    # 1. Verify Normalization
    print("\nStep 1: Verifying OpenCLIP Vector Normalization (L2 Norm = 1.0)...")
    clip = CLIPModelManager.get_instance()
    clip.ensure_loaded()
    
    test_img = Path(tempfile.gettempdir()) / "test_norm_photo.jpg"
    draw_test_photo(test_img, (120, 120, 120), "Sample Test", "Sample Subtitle")
    try:
        img_vec = np.array(get_image_embedding(test_img), dtype=np.float32)
        txt_vec = np.array(get_text_embedding("a photo of a cat"), dtype=np.float32)
        
        img_norm = np.linalg.norm(img_vec)
        txt_norm = np.linalg.norm(txt_vec)
        
        print(f"  - Image vector L2 norm: {img_norm:.6f}")
        print(f"  - Text vector L2 norm : {txt_norm:.6f}")
        assert abs(img_norm - 1.0) < 1e-4, f"Image embedding is not unit normalized: {img_norm}"
        assert abs(txt_norm - 1.0) < 1e-4, f"Text embedding is not unit normalized: {txt_norm}"
        print("  [PASS] Both image and text embeddings are strictly unit-normalized.")
    finally:
        if test_img.exists():
            test_img.unlink()

    # 2. Verify Prompt Formatting
    print("\nStep 2: Verifying OpenCLIP Prompt Formatting for High Precision...")
    prompt_cases = [
        ("cat", "a photo of a cat"),
        ("dog", "a photo of a dog"),
        ("car", "a photo of a car"),
        ("mountain", "a photo of a mountain"),
        ("sunset", "a photo of a sunset"),
        ("airplane", "a photo of an airplane"),
        ("dogs", "a photo of dogs"),
        ("a photo of a red car", "a photo of a red car"),
    ]
    for raw_q, expected_prompt in prompt_cases:
        formatted = format_clip_text_prompt(raw_q)
        print(f"  Query: '{raw_q}' -> Formatted: '{formatted}'")
        assert formatted == expected_prompt, f"Expected '{expected_prompt}', got '{formatted}'"
    print("  [PASS] Prompt template formatting verified.")

    # 3. Setup Test Environment with 10 Real Generated Images
    test_dir = Path(tempfile.mkdtemp(prefix="imageflow_strict_test_"))
    test_db_dir = test_dir / "chroma_db"
    test_images_dir = test_dir / "photos"
    test_images_dir.mkdir(parents=True, exist_ok=True)

    try:
        dataset = [
            ("cat_01_persian.jpg", (200, 180, 140), "Persian Cat Feline", "Fluffy white kitten cat sitting"),
            ("cat_02_tabby.jpg", (170, 150, 120), "Tabby Cat Pet", "Striped domestic cat feline playing"),
            ("cat_03_siamese.jpg", (190, 160, 130), "Siamese Kitten", "Cute Siamese cat pet with blue eyes"),
            ("car_01_red.jpg", (220, 30, 30), "Red Sports Car", "Fast racing vehicle automobile"),
            ("car_02_truck.jpg", (80, 80, 80), "Heavy Duty Truck", "Large transport cargo vehicle"),
            ("mountain_01_alps.jpg", (100, 140, 200), "Snowy Mountain", "Alpine peak nature rock and ice"),
            ("beach_01_ocean.jpg", (40, 160, 220), "Sunny Ocean Beach", "Blue waves tropical sea coast"),
            ("food_01_pizza.jpg", (230, 120, 40), "Hot Delicious Pizza", "Italian cheese and tomato pie"),
            ("airplane_01_jet.jpg", (180, 190, 210), "Commercial Jetliner", "Airplane flying in blue sky"),
            ("building_01_city.jpg", (110, 110, 130), "Modern Skyscraper", "Downtown city architecture"),
        ]

        print(f"\nStep 3: Creating {len(dataset)} labeled images in test source folder...")
        for filename, color, title, subtitle in dataset:
            p = test_images_dir / filename
            draw_test_photo(p, color, title, subtitle)

        # 4. Indexing into ChromaDB
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="strict_search_test")
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        scanned = scan_folder_images(test_images_dir, recursive=True)
        summary = indexer.index_images(scanned, prune_missing=True, folder_root=str(test_images_dir))
        print(f"  Indexed: {summary['indexed']} images into ChromaDB.")
        assert chroma.count() == 10

        # TEST A: Exact Match Count (3 cats should return ONLY the 3 cats, sorted descending)
        print("\n" + "-" * 60)
        print(f"TEST A: Query for 'Show me cat images' (Threshold: {MIN_SIMILARITY_THRESHOLD})")
        print("-" * 60)
        cat_results = search_similar_images(
            query="Show me cat images",
            n_results=20,
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results returned: {len(cat_results)}")
        for r in cat_results:
            print(f"    - {r['filename']} (Score: {r['similarity_score']})")

        # Must return exactly 3 cats without padding remaining slots with cars/buildings
        assert len(cat_results) == 3, f"Expected exactly 3 cat matches, got {len(cat_results)}"
        cat_filenames = [r["filename"] for r in cat_results]
        assert "cat_01_persian.jpg" in cat_filenames
        assert "cat_02_tabby.jpg" in cat_filenames
        assert "cat_03_siamese.jpg" in cat_filenames
        assert not any("car" in fn or "mountain" in fn for fn in cat_filenames)
        
        # Verify scores are sorted descending and all >= MIN_SIMILARITY_THRESHOLD
        scores = [r["similarity_score"] for r in cat_results]
        assert scores == sorted(scores, reverse=True), "Results are not sorted descending by score!"
        assert all(s >= MIN_SIMILARITY_THRESHOLD for s in scores), f"Some scores below threshold: {scores}"
        print("  [PASS] Exact 3 cat images returned, sorted descending by score, all >= threshold.")

        # TEST B: Non-matching Query -> Must return 0 images
        print("\n" + "-" * 60)
        print("TEST B: Query for non-existent concept 'astronaut walking on moon'")
        print("-" * 60)
        zero_results = search_similar_images(
            query="astronaut walking on moon in space",
            n_results=20,
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results returned: {len(zero_results)}")
        assert len(zero_results) == 0, f"Expected 0 results for non-existent concept, got {len(zero_results)}"
        print("  [PASS] Zero valid matches correctly returned ZERO images without padding.")

        # TEST C: TOP-K acts strictly as a ceiling maximum limit
        print("\n" + "-" * 60)
        print("TEST C: Query for 'cat' with n_results=2 maximum limit (when 3 exist)")
        print("-" * 60)
        capped_results = search_similar_images(
            query="cat",
            n_results=2,
            chroma_manager=chroma,
            clip_manager=clip,
        )
        print(f"  Results returned: {len(capped_results)}")
        assert len(capped_results) == 2, f"Expected capped 2 results, got {len(capped_results)}"
        print("  [PASS] Top-k correctly acted as a maximum limit ceiling.")

        print("\n" + "=" * 75)
        print("ALL STRICT SEMANTIC MATCHING TESTS PASSED SUCCESSFULLY!")
        print("=" * 75)
        return True

    finally:
        try:
            shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_relevance_filter_tests()
    sys.exit(0 if success else 1)
