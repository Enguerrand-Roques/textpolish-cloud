"""
Clipboard and text selection utilities.
Uses pynput for keystrokes and NSWorkspace / Quartz for app management.
"""

import sys
import time
import logging
import pyperclip
from pynput.keyboard import Controller, Key

if sys.platform == "darwin":
    from AppKit import NSWorkspace  # type: ignore
    from Quartz import (  # type: ignore
        CGEventCreateKeyboardEvent,
        CGEventSetFlags,
        CGEventPostToPid,
        kCGEventFlagMaskCommand,
    )
elif sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

_kbd = Controller()
_MOD = Key.cmd if sys.platform == "darwin" else Key.ctrl

# macOS keycode for 'v'
_KEYCODE_V = 9


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


def _paste_to_pid(pid: int) -> None:
    """
    Send Cmd+V directly to a process by PID without changing focus.
    The user stays on whatever app they switched to — the paste happens
    silently in the background inside the target app.
    """
    for key_down in (True, False):
        event = CGEventCreateKeyboardEvent(None, _KEYCODE_V, key_down)
        CGEventSetFlags(event, kCGEventFlagMaskCommand)
        CGEventPostToPid(pid, event)
    time.sleep(0.05)


def _paste_windows(hwnd: int) -> None:
    """
    On Windows, bring the source window to the foreground then send Ctrl+V.
    CGEventPostToPid has no equivalent on Windows, so focus must be restored.
    """
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)   # SW_RESTORE — unminimize if needed
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)

    with _kbd.pressed(_MOD):
        _kbd.press('v')
        _kbd.release('v')


def paste_text(text: str, app_ref=None) -> None:
    """
    Write *text* to the clipboard, then paste it into the source app.

    macOS: sends Cmd+V directly to the source process — no focus change,
           the user stays on whatever they switched to.
    Windows: restores focus to the source window, then sends Ctrl+V.
    """
    logging.debug("Pasting (%d chars)", len(text))
    pyperclip.copy(text)
    time.sleep(0.05)

    if app_ref is None:
        # Fallback: paste into whatever is currently focused
        with _kbd.pressed(_MOD):
            _kbd.press('v')
            _kbd.release('v')
        return

    if sys.platform == "darwin":
        pid = app_ref.processIdentifier()
        _paste_to_pid(pid)
    elif sys.platform == "win32":
        _paste_windows(app_ref)

    logging.debug("Paste sent")
