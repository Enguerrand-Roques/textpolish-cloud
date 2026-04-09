"""
Clipboard and text selection utilities.
Uses pynput (Accessibility) for keystrokes and NSWorkspace for app management.
"""

import sys
import time
import logging
import pyperclip
from pynput.keyboard import Controller, Key

if sys.platform == "darwin":
    from AppKit import NSWorkspace  # type: ignore
elif sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

_kbd = Controller()
_MOD = Key.cmd if sys.platform == "darwin" else Key.ctrl


def get_frontmost_app():
    """
    Return a reference to the currently active app/window.
    - macOS: NSRunningApplication object
    - Windows: HWND (window handle) as an integer
    """
    if sys.platform == "darwin":
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    elif sys.platform == "win32":
        return ctypes.windll.user32.GetForegroundWindow()
    return None


def get_app_and_copy() -> tuple[object, str]:
    """
    Capture the frontmost app, simulate Cmd/Ctrl+C, return (app_ref, selected_text).
    app_ref is saved and passed to paste_text() to restore focus after polishing.
    """
    app_ref = get_frontmost_app()

    if sys.platform == "darwin":
        app_name = app_ref.localizedName() if app_ref else "?"
    else:
        app_name = str(app_ref)
    logging.debug("Source app: %r", app_name)

    try:
        before = pyperclip.paste() or ""
    except Exception:
        before = ""

    with _kbd.pressed(_MOD):
        _kbd.press('c')
        _kbd.release('c')

    time.sleep(0.35)

    try:
        text = pyperclip.paste() or ""
    except Exception as e:
        logging.error("Clipboard read error: %s", e)
        return app_ref, ""

    if text == before:
        logging.warning("Clipboard unchanged after Cmd/Ctrl+C")

    logging.debug("Copied text (%d chars): %r", len(text), text[:60])
    return app_ref, text


def _force_focus_macos(app_ref) -> None:
    """Bring the source app back to front, even if the user switched away."""
    # NSApplicationActivateIgnoringOtherApps = 1
    # Without this flag, activation is ignored when another app is active.
    app_ref.activateWithOptions_(1)
    time.sleep(0.35)


def _force_focus_windows(hwnd: int) -> None:
    """Bring the source window back to front on Windows."""
    user32 = ctypes.windll.user32
    # Restore the window if minimized, then force it to the foreground.
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)


def paste_text(text: str, app_ref=None) -> None:
    """
    Write *text* to the clipboard, restore focus to the source app,
    then simulate Cmd/Ctrl+V.
    """
    logging.debug("Pasting (%d chars)", len(text))
    pyperclip.copy(text)
    time.sleep(0.05)

    if app_ref is not None:
        if sys.platform == "darwin":
            _force_focus_macos(app_ref)
        elif sys.platform == "win32":
            _force_focus_windows(app_ref)

    with _kbd.pressed(_MOD):
        _kbd.press('v')
        _kbd.release('v')

    logging.debug("Cmd/Ctrl+V sent")
