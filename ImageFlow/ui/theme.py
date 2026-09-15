DARK_THEME = """
QWidget { font-family: "Segoe UI"; font-size: 13px; color: #e7ebf3; }
QMainWindow, QWidget { background: #171a21; }
QLabel#brand { font-size: 39px; font-weight: 800; color: #72a8ff; letter-spacing: 1px; }
QLabel#subtitle { color: #9aa6ba; font-size: 15px; }
QFrame#stats, QFrame#folderCard, QFrame#imageFrame, QFrame#timeline,
QFrame#bottomBar, QFrame#card, QFrame#actionCard, QFrame#dangerCard {
    background: #20242d; border: 1px solid #343b49; border-radius: 14px;
}
QFrame#stats { background: #1c2028; }
QLabel#statValue { font-size: 21px; font-weight: 700; color: #78a9ff; }
QLabel#cardTitle { font-weight: 700; color: #e4e9f2; }
QLabel#pathLabel { color: #9da8ba; }
QLabel#imageNumber { font-size: 17px; font-weight: 700; }
QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
QPushButton { background: #252a34; border: 1px solid #3b4352; border-radius: 8px; padding: 7px 12px; color: #e8edf5; }
QPushButton:hover { background: #2c3441; border-color: #6d91d8; }
QPushButton:pressed { background: #333c4b; }
QPushButton#navButton { font-size: 14px; font-weight: 600; }
QPushButton#thumb { padding: 2px; border-radius: 9px; background: #1b1f27; }
QPushButton#thumb:checked { border: 2px solid #8a62e6; }
QPushButton#thumb[selected="true"] { border: 2px solid #43a047; }
QPushButton#thumb[selected="true"]:checked { border: 3px solid #8a62e6; }
QPushButton#keyButton, QPushButton#dangerKey { font-size: 16px; font-weight: 700; }
QPushButton#dangerKey { color: #ff7777; border-color: #744040; }
QLabel#greenTitle { color: #69c394; font-weight: 700; }
QLabel#dangerTitle { color: #ff6e6e; font-weight: 700; }
QLabel#purpleTitle { color: #b08bea; font-weight: 700; }
QLabel#keySmall { background: #292e39; border: 1px solid #414958; border-radius: 6px; color: #b99ce9; font-weight: 700; padding: 5px; }
QPushButton#bottomAction { border: none; border-right: 1px solid #343b49; border-radius: 0; }
QPushButton#bottomAction:hover { background: #252b35; }
QLabel#bottomIcon { font-size: 20px; }
QLabel#smallText { color: #929db0; font-size: 11px; }
QLineEdit, QSpinBox, QComboBox { border: 1px solid #3d4656; border-radius: 7px; padding: 7px; background: #20252e; color: #edf1f7; }
QScrollBar:vertical { width: 10px; background: #1b1f26; }
QScrollBar::handle:vertical { background: #4b5567; border-radius: 5px; }
QDialog, QGroupBox { background: #20242d; color: #e7ebf3; }
QCheckBox { color: #e7ebf3; }
"""

LIGHT_THEME = """
QWidget { font-family: "Segoe UI"; font-size: 13px; color: #27344d; }
QMainWindow, QWidget { background: #ffffff; }
QLabel#brand { font-size: 39px; font-weight: 800; color: #2d72c9; letter-spacing: 1px; }
QLabel#subtitle { color: #7a8496; font-size: 15px; }
QFrame#stats, QFrame#folderCard, QFrame#imageFrame, QFrame#timeline,
QFrame#bottomBar, QFrame#card, QFrame#actionCard, QFrame#dangerCard {
    background: #ffffff; border: 1px solid #e0e5ee; border-radius: 14px;
}
QFrame#stats { background: #fbfcfe; }
QLabel#statValue { font-size: 21px; font-weight: 700; color: #2b66bd; }
QLabel#cardTitle { font-weight: 700; color: #33415c; }
QLabel#pathLabel { color: #68758a; }
QLabel#imageNumber { font-size: 17px; font-weight: 700; }
QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
QPushButton { background: #ffffff; border: 1px solid #d8deea; border-radius: 8px; padding: 7px 12px; color: #33415c; }
QPushButton:hover { background: #f3f7ff; border-color: #83aee8; }
QPushButton:pressed { background: #e8f0ff; }
QPushButton#navButton { font-size: 14px; font-weight: 600; }
QPushButton#thumb { padding: 2px; border-radius: 9px; }
QPushButton#thumb:checked { border: 2px solid #7546c7; }
QPushButton#thumb[selected="true"] { border: 2px solid #43a047; }
QPushButton#thumb[selected="true"]:checked { border: 3px solid #7546c7; }
QPushButton#keyButton, QPushButton#dangerKey { font-size: 16px; font-weight: 700; }
QPushButton#dangerKey { color: #d83c3c; border-color: #efb6b6; }
QLabel#greenTitle { color: #3a9d70; font-weight: 700; }
QLabel#dangerTitle { color: #df4343; font-weight: 700; }
QLabel#purpleTitle { color: #7044b8; font-weight: 700; }
QLabel#keySmall { background: #f7f8fb; border: 1px solid #dce1eb; border-radius: 6px; color: #5e4a9e; font-weight: 700; padding: 5px; }
QPushButton#bottomAction { border: none; border-right: 1px solid #e2e6ee; border-radius: 0; }
QPushButton#bottomAction:hover { background: #f7f9fc; }
QLabel#bottomIcon { font-size: 20px; }
QLabel#smallText { color: #8791a1; font-size: 11px; }
QLineEdit, QSpinBox, QComboBox { border: 1px solid #d6dce7; border-radius: 7px; padding: 7px; background: white; color: #27344d; }
QScrollBar:vertical { width: 10px; background: #f4f5f7; }
QScrollBar::handle:vertical { background: #c7cfdd; border-radius: 5px; }
"""


def is_dark_theme(theme_name: str) -> bool:
    return str(theme_name).lower() in {"dark", "black"}


def get_theme_stylesheet(theme_name: str) -> str:
    return DARK_THEME if is_dark_theme(theme_name) else LIGHT_THEME
