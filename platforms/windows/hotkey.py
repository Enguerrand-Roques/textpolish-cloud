"""
Global hotkey listener using pynput GlobalHotKeys (Windows).
Maps <cmd> → <ctrl> so the config shortcut works cross-platform.
"""

from pynput import keyboard as _keyboard


def install(shortcut: str, callback) -> None:
    """
    Install a global keyboard shortcut.

    Args:
        shortcut: pynput format, e.g. "<cmd>+<shift>+p"
        callback: Function called (from a daemon thread) when the shortcut fires.
    """
    win_shortcut = shortcut.replace("<cmd>", "<ctrl>")

    hotkeys = _keyboard.GlobalHotKeys({win_shortcut: callback})
    hotkeys.daemon = True
    hotkeys.start()
