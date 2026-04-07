"""
TextPolish panel — native NSPanel via PyObjC.
Replaces CustomTkinter to appear correctly above fullscreen apps.
"""

import threading
import time
import objc
from Foundation import NSObject
from AppKit import (
    NSApp,
    NSPanel,
    NSButton,
    NSTextField,
    NSScrollView,
    NSTextView,
    NSColor,
    NSFont,
    NSMakeRect,
    NSBackingStoreBuffered,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskUtilityWindow,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSFloatingWindowLevel,
)

from clipboard import get_app_and_copy, paste_text
from llm import polish_text

_PANEL_STYLE = (
    NSWindowStyleMaskTitled
    | NSWindowStyleMaskClosable
    | NSWindowStyleMaskResizable
    | NSWindowStyleMaskUtilityWindow
    | NSWindowStyleMaskNonactivatingPanel
)
_COLLECTION = (
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorFullScreenAuxiliary
)

# ---------------------------------------------------------------------------
# Thread bridge — schedules Python callables on the AppKit main thread
# ---------------------------------------------------------------------------

class _MainThreadBridge(NSObject):
    """Routes Python callables to the AppKit main run loop."""

    def init(self):
        self = objc.super(_MainThreadBridge, self).init()
        if self is None:
            return None
        self._queue = []
        self._lock = threading.Lock()
        return self

    @objc.python_method
    def schedule(self, fn):
        with self._lock:
            self._queue.append(fn)
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "drain:", None, False
        )

    def drain_(self, _):
        with self._lock:
            fns, self._queue = self._queue, []
        for fn in fns:
            fn()


_bridge: _MainThreadBridge | None = None


def _on_main(fn):
    assert _bridge is not None, "call ui.setup() first"
    _bridge.schedule(fn)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class TextPolishPanel(NSObject):

    def init(self):
        self = objc.super(TextPolishPanel, self).init()
        if self is None:
            return None
        self._selected_text = ""
        self._app_ref = None
        self._custom_dialog = None
        self._custom_input = None
        self._status_job = 0
        self._create_panel()
        return self

    # ----------------------------------------------------------------- setup

    @objc.python_method
    def _create_panel(self):
        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 440, 330),
            _PANEL_STYLE,
            NSBackingStoreBuffered,
            False,
        )
        self._panel.setTitle_("TextPolish")
        self._panel.setLevel_(NSFloatingWindowLevel)
        self._panel.setHidesOnDeactivate_(False)
        self._panel.setCollectionBehavior_(_COLLECTION)
        self._panel.setDelegate_(self)   # for windowShouldClose_
        self._build_views()

    @objc.python_method
    def _build_views(self):
        cv = self._panel.contentView()
        W, H, pad = 440, 330, 16

        # Title
        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, H - 44, W - 2 * pad, 28))
        lbl.setStringValue_("TextPolish")
        lbl.setEditable_(False)
        lbl.setBordered_(False)
        lbl.setDrawsBackground_(False)
        lbl.setFont_(NSFont.boldSystemFontOfSize_(17))
        lbl.setTextColor_(NSColor.labelColor())
        cv.addSubview_(lbl)

        # Buttons row (bottom)
        btn_h, gap = 34, 8
        btn_w = (W - 2 * pad - 2 * gap) / 3
        btn_y = pad

        self._btn_pro = self._make_btn_("Professional", NSMakeRect(pad, btn_y, btn_w, btn_h))
        self._btn_pro.setTarget_(self)
        self._btn_pro.setAction_("onPro:")
        cv.addSubview_(self._btn_pro)

        self._btn_casual = self._make_btn_("Casual", NSMakeRect(pad + btn_w + gap, btn_y, btn_w, btn_h))
        self._btn_casual.setTarget_(self)
        self._btn_casual.setAction_("onCasual:")
        cv.addSubview_(self._btn_casual)

        self._btn_custom = self._make_btn_("Custom", NSMakeRect(pad + 2 * (btn_w + gap), btn_y, btn_w, btn_h))
        self._btn_custom.setTarget_(self)
        self._btn_custom.setAction_("onCustom:")
        cv.addSubview_(self._btn_custom)

        # Status label (just above buttons)
        status_y = btn_y + btn_h + 4
        self._status = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, status_y, W - 2 * pad, 18))
        self._status.setStringValue_("")
        self._status.setEditable_(False)
        self._status.setBordered_(False)
        self._status.setDrawsBackground_(False)
        self._status.setFont_(NSFont.systemFontOfSize_(11))
        self._status.setTextColor_(NSColor.secondaryLabelColor())
        cv.addSubview_(self._status)

        # Preview text (scrollable, between title and status)
        preview_y = status_y + 18 + 6
        preview_h = H - 44 - pad - preview_y - 6

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(pad, preview_y, W - 2 * pad, preview_h)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(2)  # NSBezelBorder

        self._text_view = NSTextView.alloc().initWithFrame_(
            NSMakeRect(0, 0, W - 2 * pad, preview_h)
        )
        self._text_view.setEditable_(False)
        self._text_view.setRichText_(False)
        self._text_view.setFont_(NSFont.systemFontOfSize_(12))
        self._text_view.setTextColor_(NSColor.secondaryLabelColor())
        scroll.setDocumentView_(self._text_view)
        cv.addSubview_(scroll)

        # Hidden button — catches Escape to close the panel
        esc_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
        esc_btn.setKeyEquivalent_("\x1b")
        esc_btn.setTarget_(self)
        esc_btn.setAction_("onClose:")
        cv.addSubview_(esc_btn)

    @objc.python_method
    def _make_btn_(self, title, frame):
        btn = NSButton.alloc().initWithFrame_(frame)
        btn.setTitle_(title)
        btn.setBezelStyle_(1)  # NSBezelStyleRounded
        return btn

    # ---------------------------------------------------------------- ObjC actions (called by Cocoa)

    def onPro_(self, sender):
        self._start_process("pro")

    def onCasual_(self, sender):
        self._start_process("casual")

    def onCustom_(self, sender):
        self._open_custom_dialog()

    def onClose_(self, sender):
        self._hide()

    def windowShouldClose_(self, sender):
        """Called by the red close button — hides the panel without destroying it."""
        self._hide()
        return False

    def applyCustom_(self, sender):
        prompt = self._custom_input.string().strip()
        self._custom_dialog.orderOut_(None)
        self._custom_dialog = None
        self._custom_input = None
        if prompt:
            self._start_process("custom", custom_prompt=prompt)

    # ---------------------------------------------------------------- public API

    @objc.python_method
    def trigger_polish(self):
        """Called from pynput background thread on shortcut."""
        self._app_ref, self._selected_text = get_app_and_copy()
        _on_main(self._show)

    # ---------------------------------------------------------------- internal UI

    @objc.python_method
    def _show(self):
        if self._selected_text.strip():
            self._text_view.setString_(self._selected_text)
            self._text_view.setTextColor_(NSColor.secondaryLabelColor())
            self._set_enabled(True)
        else:
            self._text_view.setString_("No text selected — select text first")
            self._text_view.setTextColor_(NSColor.tertiaryLabelColor())
            self._set_enabled(False)

        self._status.setStringValue_("")
        self._status.setTextColor_(NSColor.secondaryLabelColor())

        self._panel.center()
        self._panel.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _hide(self):
        self._panel.orderOut_(None)

    @objc.python_method
    def _set_enabled(self, enabled: bool):
        self._btn_pro.setEnabled_(enabled)
        self._btn_casual.setEnabled_(enabled)
        self._btn_custom.setEnabled_(enabled)

    @objc.python_method
    def _start_process(self, mode: str, custom_prompt: str | None = None):
        if not self._selected_text.strip():
            return
        self._set_enabled(False)
        self._status_job += 1
        job_id = self._status_job
        self._set_status("Preparing correction.")

        def status_worker():
            steps = [
                (1.0,   "Preparing correction"),
                (3.0,   "Loading local model"),
                (6.0,   "Rewriting text"),
                (9999.0, "Finalising response"),
            ]
            start = time.monotonic()
            last_message = None

            while job_id == self._status_job:
                elapsed = time.monotonic() - start
                for threshold, label in steps:
                    if elapsed < threshold:
                        break

                dots = "." * ((int(elapsed * 3) % 3) + 1)
                message = f"{label}{dots}"
                if message != last_message:
                    _on_main(lambda msg=message, jid=job_id: self._update_status_if_current(jid, msg))
                    last_message = message
                time.sleep(0.35)

        def worker():
            try:
                result = polish_text(self._selected_text, mode, custom_prompt)
                _on_main(lambda: self._on_success(result))
            except Exception as exc:
                _on_main(lambda e=exc: self._on_error(str(e)))

        threading.Thread(target=status_worker, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

    @objc.python_method
    def _on_success(self, result: str):
        self._status_job += 1
        self._hide()
        paste_text(result, self._app_ref)

    @objc.python_method
    def _on_error(self, message: str):
        self._status_job += 1
        short = message[:60] + ("…" if len(message) > 60 else "")
        self._status.setStringValue_(f"Error: {short}")
        self._status.setTextColor_(NSColor.systemRedColor())
        self._set_enabled(True)

    @objc.python_method
    def _set_status(self, message: str):
        self._status.setStringValue_(message)
        self._status.setTextColor_(NSColor.secondaryLabelColor())

    @objc.python_method
    def _update_status_if_current(self, job_id: int, message: str):
        if job_id == self._status_job:
            self._set_status(message)

    @objc.python_method
    def _open_custom_dialog(self):
        if self._custom_dialog is not None:
            self._custom_dialog.makeKeyAndOrderFront_(None)
            return

        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskUtilityWindow
            | NSWindowStyleMaskNonactivatingPanel
        )
        dlg = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 400, 200),
            style,
            NSBackingStoreBuffered,
            False,
        )
        dlg.setTitle_("Custom instruction")
        dlg.setLevel_(NSFloatingWindowLevel)
        dlg.setCollectionBehavior_(_COLLECTION)

        cv = dlg.contentView()
        W, H, pad = 400, 200, 16

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, H - 38, W - 2 * pad, 22))
        lbl.setStringValue_("Describe how to rewrite the text:")
        lbl.setEditable_(False)
        lbl.setBordered_(False)
        lbl.setDrawsBackground_(False)
        lbl.setFont_(NSFont.systemFontOfSize_(12))
        lbl.setTextColor_(NSColor.secondaryLabelColor())
        cv.addSubview_(lbl)

        apply_btn = NSButton.alloc().initWithFrame_(NSMakeRect((W - 110) / 2, pad, 110, 34))
        apply_btn.setTitle_("Apply")
        apply_btn.setBezelStyle_(1)
        apply_btn.setTarget_(self)
        apply_btn.setAction_("applyCustom:")
        cv.addSubview_(apply_btn)

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(pad, pad + 34 + 8, W - 2 * pad, H - 38 - pad - 34 - 8 - 8)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(2)

        text_input = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, W - 2 * pad, 80))
        text_input.setString_("Rewrite this text keeping my style, make it punchier.")
        text_input.setFont_(NSFont.systemFontOfSize_(12))
        scroll.setDocumentView_(text_input)
        cv.addSubview_(scroll)

        self._custom_dialog = dlg
        self._custom_input = text_input

        dlg.center()
        dlg.makeKeyAndOrderFront_(None)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def setup() -> TextPolishPanel:
    """Initialize bridge and panel. Must be called from the main thread."""
    global _bridge
    _bridge = _MainThreadBridge.alloc().init()
    return TextPolishPanel.alloc().init()
