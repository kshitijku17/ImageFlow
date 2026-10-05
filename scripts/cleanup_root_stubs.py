"""Helper script to delete moved/empty leftover files from the project root."""
import os
from pathlib import Path

def cleanup():
    base_dir = Path(__file__).resolve().parent.parent
    stubs = [
        "test_ai_clip.py",
        "test_ai_date_filter.py",
        "test_ai_full_integration.py",
        "test_ai_indexing.py",
        "test_ai_reference_search.py",
        "test_ai_search.py",
        "create_zip.py",
    ]
    
    deleted_count = 0
    for filename in stubs:
        target = base_dir / filename
        if target.exists():
            try:
                target.unlink()
                print(f"Deleted root stub: {filename}")
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {filename}: {e}")
                
    discussion_dir = base_dir / "Discussion"
    if discussion_dir.exists():
        import shutil
        try:
            shutil.rmtree(discussion_dir)
            print("Deleted old Discussion directory.")
        except Exception as e:
            print(f"Error deleting Discussion directory: {e}")

    print(f"\nCleanup complete. Removed {deleted_count} root stub files.")

if __name__ == "__main__":
    cleanup()
