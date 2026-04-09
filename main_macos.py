#!/usr/bin/env python3
"""
TextPolish — main entry point.

Starts a global shortcut listener (Cmd+Shift+P) and displays a native NSPanel
that stays visible above all windows, including fullscreen apps.

Required macOS permissions:
  - Accessibility  (for pynput / GlobalHotKeys)
  - Automation     (for osascript / keystroke)
"""

import sys

from AppKit import (
    NSApplication,
    NSApp,
    NSApplicationActivationPolicyAccessory,
    NSDate,
    NSDefaultRunLoopMode,
    NSEventMaskAny,
)

from config import SHORTCUT
from hotkey import install as install_hotkey
from ui import setup as setup_panel


def main() -> None:
    NSApplication.sharedApplication()
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    # Required before manually dispatching events
    NSApp.finishLaunching()

    panel = setup_panel()

    install_hotkey(SHORTCUT, panel.trigger_polish)

    print(f"TextPolish started — shortcut active: {SHORTCUT}")
    print("Press Ctrl+C in this terminal to quit.")

    # Full Cocoa run loop: dispatches NSEvents (clicks, keyboard, etc.)
    # 0.5s timeout so Python can catch KeyboardInterrupt (Ctrl+C).
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


if __name__ == "__main__":
    main()
