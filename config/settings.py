import json
from utils.constants import CONFIG_PATH


def load_settings():
    defaults = {
        "thumb_quality": 80,
        "theme": "White",
        "recursive": False,
        "slideshow_seconds": 3,
        "remember_paths": True,
    }
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        defaults.update(data)
    except Exception:
        pass
    return defaults


def save_settings(settings):
    try:
        CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass