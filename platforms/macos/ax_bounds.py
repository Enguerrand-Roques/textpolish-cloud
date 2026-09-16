"""Best-effort retrieval of the on-screen bounds of the current text
selection, via the macOS Accessibility API (AXUIElement).

This is the same TCC permission (Accessibility) that hotkey.py's CGEventTap
already requires and obtains — no extra permission prompt is needed.

Returns None on any failure. Callers MUST have a position fallback: many
apps don't expose AXSelectedTextRange/AXBoundsForRange reliably (a
long-standing macOS limitation, especially for non-native text controls),
and the two AX calls can fail independently of each other.
"""

import ApplicationServices as AS


def get_selection_bounds() -> tuple[float, float, float, float] | None:
    """Return (x, y, width, height) in CG screen coordinates (origin
    top-left, Y increases downward) for the current text selection, or
    None if unavailable.
    """
    try:
        system_wide = AS.AXUIElementCreateSystemWide()

        err, focused = AS.AXUIElementCopyAttributeValue(
            system_wide, AS.kAXFocusedUIElementAttribute, None
        )
        if err != AS.kAXErrorSuccess or focused is None:
            return None

        err, text_range = AS.AXUIElementCopyAttributeValue(
            focused, AS.kAXSelectedTextRangeAttribute, None
        )
        if err != AS.kAXErrorSuccess or text_range is None:
            return None

        err, bounds_value = AS.AXUIElementCopyParameterizedAttributeValue(
            focused, AS.kAXBoundsForRangeParameterizedAttribute, text_range, None
        )
        if err != AS.kAXErrorSuccess or bounds_value is None:
            return None

        ok, rect = AS.AXValueGetValue(bounds_value, AS.kAXValueCGRectType, None)
        if not ok:
            return None

        return (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)
    except Exception:
        return None
