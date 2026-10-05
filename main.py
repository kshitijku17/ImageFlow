import sys
from PySide6.QtWidgets import QApplication
from utils.constants import APP_NAME
from ui.main_window import ImageFlowWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = ImageFlowWindow()
    win.statusBar().showMessage("Ready")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
