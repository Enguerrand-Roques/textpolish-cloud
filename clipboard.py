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

_kbd = Controller()
_MOD = Key.cmd if sys.platform == "darwin" else Key.ctrl


def get_frontmost_app():
    """Return the running NSRunningApplication object for the active app (macOS only)."""
    if sys.platform == "darwin":
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    return None


def get_app_and_copy() -> tuple[object, str]:
    """
    Capture the frontmost app, simulate Cmd+C, return (app_ref, selected_text).
    app_ref is an NSRunningApplication — used later to reactivate.
    """
    app_ref = get_frontmost_app()
    app_name = app_ref.localizedName() if app_ref else "?"
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
        logging.warning("Clipboard unchanged after Cmd+C")

    logging.debug("Copied text (%d chars): %r", len(text), text[:60])
    return app_ref, text


def paste_text(text: str, app_ref=None) -> None:
    """
    Write *text* to the clipboard, reactivate the source app via NSWorkspace,
    then simulate Cmd+V.
    """
    logging.debug("Pasting (%d chars)", len(text))
    pyperclip.copy(text)
    time.sleep(0.05)

    if app_ref is not None:
        app_ref.activateWithOptions_(0)
        time.sleep(0.25)

    with _kbd.pressed(_MOD):
        _kbd.press('v')
        _kbd.release('v')

    logging.debug("Cmd+V sent")
