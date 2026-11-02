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
    from AppKit import NSWorkspace, NSPasteboard, NSPasteboardItem  # type: ignore
    from Quartz import (  # type: ignore
        CGEventCreateKeyboardEvent,
        CGEventSetFlags,
        CGEventPostToPid,
        CGEventSourceFlagsState,
        kCGEventSourceStateHIDSystemState,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskAlternate,
        kCGEventFlagMaskShift,
        kCGEventFlagMaskControl,
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


_COPY_TIMEOUT = 1.0
_COPY_POLL = 0.02
_RELEASE_TIMEOUT = 1.0


def _wait_for_modifiers_released() -> None:
    """The shortcut fires while the user still holds its modifiers. Copying
    right away would send e.g. ⌥⌘C ("copy style") instead of ⌘C and copy
    nothing, so wait (briefly) until the physical modifiers are up."""
    if sys.platform != "darwin":
        return
    mask = (kCGEventFlagMaskCommand | kCGEventFlagMaskAlternate
            | kCGEventFlagMaskShift | kCGEventFlagMaskControl)
    waited = 0.0
    while waited < _RELEASE_TIMEOUT:
        if not CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState) & mask:
            return
        time.sleep(_COPY_POLL)
        waited += _COPY_POLL


def _snapshot_clipboard():
    """Capture the current clipboard so it can be restored later.
    macOS: every item and type (images, files, rich text). Elsewhere: plain text."""
    if sys.platform == "darwin":
        pb = NSPasteboard.generalPasteboard()
        items = []
        for item in pb.pasteboardItems() or []:
            data = {t: item.dataForType_(t) for t in item.types()}
            items.append({t: d for t, d in data.items() if d is not None})
        return ("mac", items)
    try:
        return ("text", pyperclip.paste() or "")
    except Exception:
        return ("text", "")


def _restore_clipboard(snapshot) -> None:
    kind, content = snapshot
    if kind == "mac":
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        restored = []
        for data in content:
            item = NSPasteboardItem.alloc().init()
            for t, d in data.items():
                item.setData_forType_(d, t)
            restored.append(item)
        if restored:
            pb.writeObjects_(restored)
    else:
        pyperclip.copy(content)


def get_app_and_copy() -> tuple[object, str]:
    """
    Capture the frontmost app, simulate Cmd/Ctrl+C, return (app_ref, selected_text).
    app_ref is saved and passed to paste_text() to restore focus after polishing.

    The clipboard is emptied before copying so that "nothing selected" is
    detectable (empty result) instead of returning stale clipboard content,
    and the user's original clipboard is restored right after.
    """
    app_ref = get_frontmost_app()

    if sys.platform == "darwin":
        app_name = app_ref.localizedName() if app_ref else "?"
    else:
        app_name = str(app_ref)
    logging.debug("Source app: %r", app_name)

    _wait_for_modifiers_released()
    snapshot = _snapshot_clipboard()
    try:
        pyperclip.copy("")
        with _kbd.pressed(_MOD):
            _kbd.press('c')
            _kbd.release('c')

        text = ""
        waited = 0.0
        while waited < _COPY_TIMEOUT:
            time.sleep(_COPY_POLL)
            waited += _COPY_POLL
            text = pyperclip.paste() or ""
            if text:
                break
    except Exception as e:
        logging.error("Clipboard error: %s", e)
        text = ""
    finally:
        try:
            _restore_clipboard(snapshot)
        except Exception as e:
            logging.error("Could not restore clipboard: %s", e)

    if not text:
        logging.warning("Nothing copied after Cmd/Ctrl+C (no selection?)")
    logging.debug("Copied %d chars", len(text))
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
    snapshot = _snapshot_clipboard()
    pyperclip.copy(text)
    time.sleep(0.05)

    try:
        if app_ref is None:
            # Fallback: paste into whatever is currently focused
            with _kbd.pressed(_MOD):
                _kbd.press('v')
                _kbd.release('v')
        elif sys.platform == "darwin":
            _paste_to_pid(app_ref.processIdentifier())
        elif sys.platform == "win32":
            _paste_windows(app_ref)
        time.sleep(0.15)  # let the target app read the clipboard before restoring
    finally:
        try:
            _restore_clipboard(snapshot)
        except Exception as e:
            logging.error("Could not restore clipboard: %s", e)

    logging.debug("Paste sent")
