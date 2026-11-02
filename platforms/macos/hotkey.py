"""
Global hotkey listener using CGEventTap (Quartz).
Workaround for the pynput/Python 3.13 bug where Thread._handle is
overwritten by a ThreadHandle.

Supports pynput format: "<cmd>+<shift>+p"
"""

import threading
from CoreFoundation import CFRunLoopRun, kCFRunLoopDefaultMode
from Quartz import (
    CGEventTapCreate,
    CGEventMaskBit,
    CFMachPortCreateRunLoopSource,
    CFRunLoopGetCurrent,
    CFRunLoopAddSource,
    CGEventTapEnable,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionListenOnly,
    kCGEventKeyDown,
    kCGKeyboardEventKeycode,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskControl,
)

from platforms.macos.shortcut_parser import (
    KEY_CODES as _KEY_CODES,
    MODIFIER_MAP as _MODIFIER_MAP,
    parse_shortcut as _parse_shortcut,
)

assert _MODIFIER_MAP == {
    'cmd':    kCGEventFlagMaskCommand,
    'shift':  kCGEventFlagMaskShift,
    'alt':    kCGEventFlagMaskAlternate,
    'option': kCGEventFlagMaskAlternate,
    'ctrl':   kCGEventFlagMaskControl,
}, "shortcut_parser.MODIFIER_MAP is out of sync with Quartz's CGEventFlags"

# Relevant modifier mask (ignores CapsLock, NumLock, etc.)
_MOD_MASK = (
    kCGEventFlagMaskCommand
    | kCGEventFlagMaskShift
    | kCGEventFlagMaskAlternate
    | kCGEventFlagMaskControl
)


# Mutable dict holding the active shortcut target — updated live by update_shortcut().
# The event handler reads from this dict on every keypress so changes take effect
# immediately without restarting the CGEventTap thread.
_current_target: dict = {"mods": 0, "keycode": None}


def update_shortcut(shortcut: str) -> None:
    """Update the active shortcut without restarting the listener.

    Args:
        shortcut: pynput format, e.g. "<cmd>+<alt>+g"

    Raises:
        ValueError: if the shortcut string cannot be parsed.
    """
    mods, keycode = _parse_shortcut(shortcut)
    _current_target["mods"] = mods
    _current_target["keycode"] = keycode
    print(f"[hotkey] Shortcut updated to: {shortcut}")


def install(shortcut: str, callback, *, on_permission_denied=None) -> None:
    """
    Install a global keyboard shortcut.

    Args:
        shortcut: pynput format, e.g. "<cmd>+<alt>+g"
        callback: Function called (from a daemon thread) when the shortcut fires.
        on_permission_denied: Called (from a daemon thread) if the Accessibility
            permission is missing and the event tap could not be created.
    """
    mods, keycode = _parse_shortcut(shortcut)
    _current_target["mods"] = mods
    _current_target["keycode"] = keycode

    def _event_handler(proxy, event_type, event, refcon):
        if event_type == kCGEventKeyDown:
            flags = CGEventGetFlags(event) & _MOD_MASK
            keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
            if flags == _current_target["mods"] and keycode == _current_target["keycode"]:
                try:
                    callback()
                except Exception as e:
                    print(f"[hotkey] Error in callback: {e}")
        return event

    def _run():
        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            CGEventMaskBit(kCGEventKeyDown),
            _event_handler,
            None,
        )
        if tap is None:
            print(
                "[hotkey] Could not create event tap.\n"
                "→ Check Accessibility permissions in System Settings."
            )
            if on_permission_denied is not None:
                try:
                    on_permission_denied()
                except Exception as e:
                    print(f"[hotkey] on_permission_denied callback failed: {e}")
            return

        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(loop, source, kCFRunLoopDefaultMode)
        CGEventTapEnable(tap, True)
        CFRunLoopRun()

    t = threading.Thread(target=_run, daemon=True, name="hotkey-listener")
    t.start()
