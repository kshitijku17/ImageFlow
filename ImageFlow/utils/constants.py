# pyrefly: ignore [missing-import]
from pathlib import Path
from PySide6.QtCore import QSize
APP_NAME = "ImageFlow"
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
THUMB_COUNT = 9
THUMB_SIZE = QSize(118, 82)
MAX_CACHE = 120
CONFIG_PATH = Path.home() / ".imageflow_settings.json"