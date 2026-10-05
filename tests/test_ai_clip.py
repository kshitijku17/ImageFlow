import sys
from pathlib import Path
from PIL import Image, ImageDraw

# Add project root to sys.path for running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.clip_manager import get_model_manager, get_image_embedding, get_text_embedding


def create_test_image(path: Path) -> Path:
    """Generates a small test image if no local image exists."""
    img = Image.new("RGB", (224, 224), color=(73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((30, 90), "ImageFlow Test", fill=(255, 255, 0))
    img.save(path)
    return path


def run_test():
    print("=" * 60)
    print("TESTING OPENCLIP MODEL SETUP (PART 1)")
    print("=" * 60)

    # 1. Model Loading
    manager = get_model_manager()
    print("Attempting to load OpenCLIP model...")
    loaded = manager.load_model()
    print(f"- Model Loaded Successfully: {loaded}")
    print(f"- Target Device Used: {manager.device}")

    if not loaded:
        print(f"- Error: {manager.load_error}")
        print("\nNote: Please ensure dependencies are installed via:")
        print("  pip install torch open_clip_torch Pillow")
        return False

    dim = manager.get_embedding_dimension()
    print(f"- Embedding Dimensions: {dim}")

    # 2. Test Image Embedding
    test_img_path = Path(__file__).parent / "test_sample.png"
    if not test_img_path.exists():
        create_test_image(test_img_path)
        created_temp = True
    else:
        created_temp = False

    print(f"\nTesting image embedding on: {test_img_path.name}")
    img_emb = get_image_embedding(test_img_path)
    img_ok = img_emb is not None and len(img_emb) == dim
    print(f"- Image Embedding Working: {img_ok} (Length: {len(img_emb) if img_emb else 0})")
    if img_emb:
        print(f"  First 5 vector values: {[round(v, 4) for v in img_emb[:5]]}")

    # 3. Test Text Embedding
    test_query = "A photo of nature with sunlight"
    print(f"\nTesting text embedding for query: '{test_query}'")
    txt_emb = get_text_embedding(test_query)
    txt_ok = txt_emb is not None and len(txt_emb) == dim
    print(f"- Text Embedding Working: {txt_ok} (Length: {len(txt_emb) if txt_emb else 0})")
    if txt_emb:
        print(f"  First 5 vector values: {[round(v, 4) for v in txt_emb[:5]]}")

    # Cleanup temp test image
    if created_temp and test_img_path.exists():
        try:
            test_img_path.unlink()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print(f"OVERALL STATUS: {'SUCCESS' if (loaded and img_ok and txt_ok) else 'FAILED'}")
    print("=" * 60)
    return loaded and img_ok and txt_ok


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
