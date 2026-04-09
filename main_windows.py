"""
TextPolish Cloud — Windows entry point.
"""

import sys
from PyQt6.QtWidgets import QApplication
from config import SHORTCUT
from hotkey_windows import install as install_hotkey
from ui_windows import setup as setup_panel


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep alive when panel is closed

    panel = setup_panel()
    install_hotkey(SHORTCUT, panel.trigger_polish)

    print(f"TextPolish Cloud started — shortcut active: {SHORTCUT.replace('<cmd>', '<ctrl>')}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
