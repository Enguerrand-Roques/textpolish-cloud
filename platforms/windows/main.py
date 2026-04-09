"""
TextPolish Cloud — Windows entry point.
"""

import sys
from PyQt6.QtWidgets import QApplication
from config import SHORTCUT
from platforms.windows.hotkey import install as install_hotkey
from platforms.windows.ui import setup as setup_panel


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    panel = setup_panel()
    install_hotkey(SHORTCUT, panel.trigger_polish)

    print(f"TextPolish Cloud started — shortcut active: {SHORTCUT.replace('<cmd>', '<ctrl>')}")
    sys.exit(app.exec())
