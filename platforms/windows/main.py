"""
TextPolish Cloud — Windows entry point.
"""

import sys
from PyQt6.QtWidgets import QApplication
from config import SHORTCUT
from platforms.windows.hotkey import install as install_hotkey
from platforms.windows.ui import setup as setup_panel

try:
    from config import SHORTCUT_WINDOWS as _WIN_SHORTCUT
except ImportError:
    _WIN_SHORTCUT = None


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    win_shortcut = _WIN_SHORTCUT or SHORTCUT.replace("<cmd>", "<ctrl>")

    panel = setup_panel()
    install_hotkey(win_shortcut, panel.trigger_polish)

    print(f"TextPolish Cloud started — shortcut active: {win_shortcut}")
    sys.exit(app.exec())
