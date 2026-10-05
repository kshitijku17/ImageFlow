import os
import zipfile
from pathlib import Path

def create_archive():
    base_dir = Path(__file__).resolve().parent
    zip_path = base_dir / "ImageFlow.zip"
    
    include_dirs = ["config", "utils", "workers", "core", "ai", "ui"]
    include_files = ["main.py", "requirements.txt"]
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Add root files
        for fname in include_files:
            fpath = base_dir / fname
            if fpath.exists():
                zipf.write(fpath, arcname=f"ImageFlow/{fname}")
                
        # Add packages
        for dname in include_dirs:
            dpath = base_dir / dname
            for root, dirs, files in os.walk(dpath):
                # Ignore __pycache__
                if "__pycache__" in root:
                    continue
                for file in files:
                    if file.endswith(".pyc"):
                        continue
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(base_dir)
                    zipf.write(full_path, arcname=f"ImageFlow/{rel_path.as_posix()}")

    print(f"Created {zip_path} successfully ({zip_path.stat().st_size} bytes)")

if __name__ == "__main__":
    create_archive()
