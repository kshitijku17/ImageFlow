import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path for running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.chroma_manager import ChromaManager
from ai.clip_manager import CLIPModelManager
from ai.indexer import ImageIndexer, scan_folder_images


def create_colored_image(file_path: Path, color: tuple, label: str):
    img = Image.new("RGB", (300, 200), color=color)
    d = ImageDraw.Draw(img)
    d.text((20, 80), label, fill=(255, 255, 255))
    img.save(file_path)


def run_indexing_test():
    print("=" * 65)
    print("TESTING IMAGE INDEXING + CHROMADB (PART 2)")
    print("=" * 65)

    test_dir = Path(tempfile.mkdtemp(prefix="imageflow_test_"))
    test_db_dir = test_dir / "chroma_db"
    test_images_dir = test_dir / "images"
    test_images_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Create sample images
        img1 = test_images_dir / "sunset.jpg"
        img2 = test_images_dir / "forest.png"
        img3 = test_images_dir / "ocean.webp"

        create_colored_image(img1, (200, 70, 30), "Sunset Beach")
        create_colored_image(img2, (30, 150, 40), "Deep Forest")
        create_colored_image(img3, (20, 80, 200), "Blue Ocean")

        print(f"Created 3 test images in: {test_images_dir}")

        # 2. Setup isolated ChromaManager & ImageIndexer for testing
        chroma = ChromaManager(persist_dir=test_db_dir, collection_name="test_collection")
        clip = CLIPModelManager.get_instance()
        indexer = ImageIndexer(clip_manager=clip, chroma_manager=chroma)

        # Progress tracking verification
        progress_reports = []

        def on_progress(current, total, msg):
            progress_reports.append((current, total, msg))
            print(f"  [Progress] {msg}")

        # 3. Initial Indexing
        print("\nStep 1: Running Initial Indexing...")
        image_paths = scan_folder_images(test_images_dir, recursive=True)
        summary1 = indexer.index_images(
            image_paths=image_paths,
            progress_callback=on_progress,
            prune_missing=True,
            folder_root=str(test_images_dir)
        )
        print(f"Initial Index Summary: {summary1}")
        assert summary1["total"] == 3, f"Expected 3 total, got {summary1['total']}"
        assert summary1["indexed"] == 3, f"Expected 3 indexed, got {summary1['indexed']}"
        assert summary1["skipped"] == 0, f"Expected 0 skipped, got {summary1['skipped']}"
        assert chroma.count() == 3, f"Expected ChromaDB count 3, got {chroma.count()}"

        # 4. Verify stored metadata
        print("\nStep 2: Verifying stored metadata in ChromaDB...")
        records = chroma.get_all_indexed_metadata()
        for doc_id, meta in records.items():
            print(f"  Record: {meta.get('filename')} | Dimensions: {meta.get('width')}x{meta.get('height')} | Size: {meta.get('size')} bytes | MTime: {meta.get('mtime')}")
            assert meta.get("file_path"), "Missing file_path in metadata"
            assert meta.get("filename"), "Missing filename in metadata"
            assert meta.get("width") == 300, f"Expected width 300, got {meta.get('width')}"
            assert meta.get("height") == 200, f"Expected height 200, got {meta.get('height')}"

        # 5. Incremental Indexing (Unchanged files should be skipped)
        print("\nStep 3: Testing Incremental Indexing (Unchanged files)...")
        summary2 = indexer.index_images(
            image_paths=image_paths,
            progress_callback=on_progress,
            prune_missing=True,
            folder_root=str(test_images_dir)
        )
        print(f"Second Run Summary: {summary2}")
        assert summary2["indexed"] == 0, f"Expected 0 re-indexed, got {summary2['indexed']}"
        assert summary2["skipped"] == 3, f"Expected 3 skipped, got {summary2['skipped']}"
        print("  -> Unchanged images were successfully detected and skipped without re-calculating embeddings.")

        # 6. Add New Image
        print("\nStep 4: Testing addition of a new image...")
        img4 = test_images_dir / "mountain.jpg"
        create_colored_image(img4, (120, 120, 120), "Snow Mountain")
        image_paths_updated = scan_folder_images(test_images_dir, recursive=True)
        summary3 = indexer.index_images(
            image_paths=image_paths_updated,
            progress_callback=on_progress,
            prune_missing=True,
            folder_root=str(test_images_dir)
        )
        print(f"Addition Summary: {summary3}")
        assert summary3["indexed"] == 1, f"Expected 1 newly indexed, got {summary3['indexed']}"
        assert summary3["skipped"] == 3, f"Expected 3 skipped, got {summary3['skipped']}"
        assert chroma.count() == 4, f"Expected Chroma count 4, got {chroma.count()}"

        # 7. Modify an existing image
        print("\nStep 5: Testing modification of an existing image...")
        time.sleep(0.05)  # Ensure distinct mtime
        create_colored_image(img1, (255, 100, 0), "Sunset Beach Modified")
        summary4 = indexer.index_images(
            image_paths=image_paths_updated,
            progress_callback=on_progress,
            prune_missing=True,
            folder_root=str(test_images_dir)
        )
        print(f"Modification Summary: {summary4}")
        assert summary4["indexed"] == 1, f"Expected 1 modified re-indexed, got {summary4['indexed']}"
        assert summary4["skipped"] == 3, f"Expected 3 skipped, got {summary4['skipped']}"

        # 8. Delete an image and verify pruning
        print("\nStep 6: Testing deletion of an image...")
        img4.unlink()
        image_paths_after_del = scan_folder_images(test_images_dir, recursive=True)
        summary5 = indexer.index_images(
            image_paths=image_paths_after_del,
            progress_callback=on_progress,
            prune_missing=True,
            folder_root=str(test_images_dir)
        )
        print(f"Deletion Summary: {summary5}")
        assert summary5["deleted"] == 1, f"Expected 1 deleted, got {summary5['deleted']}"
        assert chroma.count() == 3, f"Expected Chroma count 3 after delete, got {chroma.count()}"

        print("\n" + "=" * 65)
        print("ALL PART 2 REQUIREMENTS VERIFIED SUCCESSFULLY!")
        print("=" * 65)
        return True

    finally:
        # Clean up temp test directory
        try:
            shutil.rmtree(test_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_indexing_test()
    sys.exit(0 if success else 1)
