"""
TextPolish Cloud — macOS entry point.

Starts a global shortcut listener (Cmd+Option+G by default) and displays a native NSPanel
that stays visible above all windows, including fullscreen apps.

Required macOS permissions:
  - Accessibility  (for CGEventTap and reading the selection position)
"""

import fcntl
import logging
import os
import sys

from AppKit import (
    NSApplication,
    NSApp,
    NSApplicationActivationPolicyAccessory,
    NSDate,
    NSDefaultRunLoopMode,
    NSEventMaskAny,
)

import languagetool
from config import SHORTCUT
from platforms.macos.hotkey import install as install_hotkey
from platforms.macos.ui import setup as setup_panel, show_accessibility_denied_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


_LOCK_PATH = os.path.expanduser("~/Library/Caches/TextPolishCloud/instance.lock")


def _acquire_single_instance_lock():
    """Two running copies would both answer the shortcut and fight over the
    clipboard. Hold an exclusive lock for the process lifetime."""
    os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
    lock = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("TextPolish Cloud is already running — look for the pencil icon in the menu bar.")
        sys.exit(0)
    return lock


def main() -> None:
    _lock = _acquire_single_instance_lock()  # noqa: F841 — kept open on purpose
    NSApplication.sharedApplication()
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    NSApp.finishLaunching()

    panel = setup_panel()
    languagetool.warm_up()  # optional second pass; no-op if not installed
    install_hotkey(
        SHORTCUT, panel.trigger_polish,
        on_permission_denied=show_accessibility_denied_alert,
    )

    print(f"TextPolish Cloud started — shortcut active: {SHORTCUT}")
    print("Press Ctrl+C in this terminal to quit.")

    try:
        while True:
            event = NSApp.nextEventMatchingMask_untilDate_inMode_dequeue_(
                NSEventMaskAny,
                NSDate.dateWithTimeIntervalSinceNow_(0.5),
                NSDefaultRunLoopMode,
                True,
            )
            if event is not None:
                NSApp.sendEvent_(event)
                NSApp.updateWindows()
    except KeyboardInterrupt:
        pass
    sys.exit(0)
