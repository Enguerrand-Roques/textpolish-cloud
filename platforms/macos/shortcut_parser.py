"""Pure parsing of pynput-style shortcuts ("<cmd>+<shift>+p"). No PyObjC
import — importable on any platform (incl. Linux CI). Modifier mask
integers mirror Quartz's public CGEventFlags constants; hotkey.py asserts
this equality at import time so any drift fails loudly on macOS.
"""

# macOS keycodes for a-z
KEY_CODES: dict[str, int] = {
    'a': 0,  's': 1,  'd': 2,  'f': 3,  'h': 4,  'g': 5,  'z': 6,  'x': 7,
    'c': 8,  'v': 9,  'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15, 'y': 16,
    't': 17, 'o': 31, 'u': 32, 'i': 34, 'p': 35, 'l': 37, 'j': 38, 'k': 40,
    'n': 45, 'm': 46,
}

# Values mirror Quartz's CGEventFlags constants (kCGEventFlagMask*).
MODIFIER_MASK_COMMAND   = 0x100000
MODIFIER_MASK_SHIFT     = 0x020000
MODIFIER_MASK_ALTERNATE = 0x080000
MODIFIER_MASK_CONTROL   = 0x040000

MODIFIER_MAP: dict[str, int] = {
    'cmd':    MODIFIER_MASK_COMMAND,
    'shift':  MODIFIER_MASK_SHIFT,
    'alt':    MODIFIER_MASK_ALTERNATE,
    'option': MODIFIER_MASK_ALTERNATE,
    'ctrl':   MODIFIER_MASK_CONTROL,
}


def parse_shortcut(shortcut: str) -> tuple[int, int]:
    """
    Parse a pynput-style shortcut (e.g. "<cmd>+<shift>+p")
    and return (modifier_mask, keycode).
    """
    modifiers = 0
    keycode = None
    for part in shortcut.split('+'):
        part = part.strip().strip('<>').lower()
        if part in MODIFIER_MAP:
            modifiers |= MODIFIER_MAP[part]
        elif part in KEY_CODES:
            keycode = KEY_CODES[part]
        else:
            raise ValueError(f"Unrecognised key: {part!r}")
    if keycode is None:
        raise ValueError(f"No main key found in shortcut: {shortcut!r}")
    return modifiers, keycode
