"""
TextPolish panel — WKWebView inside NSPanel.
The panel.html file provides the full Pip-design UI; Python communicates
with it via a WKScriptMessageHandler bridge (JS→Python) and
evaluateJavaScript (Python→JS).
"""

import json
import os
import threading
import objc
from Foundation import NSObject, NSURL

from AppKit import (
    NSPanel,
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
    NSStatusBar,
    NSVariableStatusItemLength,
    NSMenu,
    NSMenuItem,
    NSImage,
    NSPasteboard,
    NSViewWidthSizable,
    NSViewHeightSizable,
    NSAlert,
    NSAlertFirstButtonReturn,
    NSWorkspace,
    NSScreen,
    NSMakePoint,
)

from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController

from clipboard import get_app_and_copy, paste_text
from llm import polish_text
from history import CorrectionHistory, format_menu_label, format_tooltip
from polish_job import PolishJobRunner
from diff import compute_word_diff
from platforms.macos.ax_bounds import get_selection_bounds

_HTML_PATH = os.path.join(os.path.dirname(__file__), "panel.html")

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

_COMPACT_SIZE = (380, 258)
_EXPANDED_SIZE = (420, 520)


# ---------------------------------------------------------------------------
# Thread bridge — routes Python callables to the AppKit main thread
# ---------------------------------------------------------------------------

class _MainThreadBridge(NSObject):
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


# ---------------------------------------------------------------------------
# JS → Python message handler
# ---------------------------------------------------------------------------

class _BridgeHandler(NSObject):
    """Receives postMessage calls from the WKWebView JS."""

    def init(self):
        self = objc.super(_BridgeHandler, self).init()
        if self is None:
            return None
        self._panel_ref = None
        return self

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        body = message.body()
        panel = self._panel_ref
        if panel is None:
            return
        _on_main(lambda b=body: panel._handle_js_message(b))


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

_history = CorrectionHistory()
_history_menu: NSMenu | None = None

_STATUS_STEPS = [
    (1.0,    "Préparation"),
    (3.0,    "Appel à Gemini"),
    (6.0,    "Réécriture en cours"),
    (9999.0, "Finalisation"),
]


class _HistoryHandler(NSObject):
    def copyText_(self, sender):
        corrected = sender.representedObject()
        if corrected:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(str(corrected), "public.utf8-plain-text")


_history_handler: _HistoryHandler | None = None


def _add_to_history(original: str, corrected: str, mode: str) -> None:
    _history.add(original, corrected, mode)
    _update_history_menu()


def _update_history_menu() -> None:
    if _history_menu is None:
        return
    _history_menu.removeAllItems()
    if not _history.entries:
        empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("No corrections yet", None, "")
        empty.setEnabled_(False)
        _history_menu.addItem_(empty)
        return
    for entry in _history.entries:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            format_menu_label(entry), "copyText:", ""
        )
        item.setTarget_(_history_handler)
        item.setRepresentedObject_(entry["corrected"])
        item.setToolTip_(f"Click to copy corrected text\n\n{format_tooltip(entry)}")
        _history_menu.addItem_(item)


def _on_main(fn):
    assert _bridge is not None, "call ui.setup() first"
    _bridge.schedule(fn)


def show_accessibility_denied_alert() -> None:
    """Show a native alert when the Accessibility permission is missing,
    with a button that deep-links into System Settings. Safe to call from
    any thread — dispatches to the main thread internally."""
    def _show():
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Accessibility permission required")
        alert.setInformativeText_(
            "TextPolish Cloud needs Accessibility access to listen for the "
            "global keyboard shortcut. Grant it in System Settings → Privacy "
            "& Security → Accessibility, then restart TextPolish Cloud."
        )
        alert.addButtonWithTitle_("Open System Settings")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() == NSAlertFirstButtonReturn:
            url = NSURL.URLWithString_(
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
            )
            NSWorkspace.sharedWorkspace().openURL_(url)
    _on_main(_show)


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
        self._current_mode = "pro"
        self._pending_result = None
        self._job_runner = PolishJobRunner(on_main=_on_main)
        self._webview_ready = False
        self._pending_js: list[str] = []
        self._create_panel()
        return self

    # ── Setup ────────────────────────────────────────────────────────────────

    @objc.python_method
    def _create_panel(self):
        w, h = _COMPACT_SIZE
        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, w, h),
            _PANEL_STYLE,
            NSBackingStoreBuffered,
            False,
        )
        self._panel.setTitle_("TextPolish")
        self._panel.setLevel_(NSFloatingWindowLevel)
        self._panel.setHidesOnDeactivate_(False)
        self._panel.setCollectionBehavior_(_COLLECTION)
        self._panel.setDelegate_(self)
        self._build_webview()

    @objc.python_method
    def _build_webview(self):
        config = WKWebViewConfiguration.alloc().init()
        controller = WKUserContentController.alloc().init()

        self._bridge_handler = _BridgeHandler.alloc().init()
        self._bridge_handler._panel_ref = self
        controller.addScriptMessageHandler_name_(self._bridge_handler, "bridge")
        config.setUserContentController_(controller)

        cv = self._panel.contentView()
        frame = cv.bounds()
        self._webview = WKWebView.alloc().initWithFrame_configuration_(frame, config)
        self._webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self._webview.setNavigationDelegate_(self)

        html_url  = NSURL.fileURLWithPath_(_HTML_PATH)
        base_url  = NSURL.fileURLWithPath_(os.path.dirname(_HTML_PATH))
        self._webview.loadFileURL_allowingReadAccessToURL_(html_url, base_url)

        cv.addSubview_(self._webview)

    # ── WKNavigationDelegate ─────────────────────────────────────────────────

    def webView_didFinishNavigation_(self, webview, navigation):
        self._webview_ready = True
        for code in self._pending_js:
            self._webview.evaluateJavaScript_completionHandler_(code, None)
        self._pending_js = []

    # ── JS helper ────────────────────────────────────────────────────────────

    @objc.python_method
    def _js(self, code: str):
        if self._webview_ready:
            self._webview.evaluateJavaScript_completionHandler_(code, None)
        else:
            self._pending_js.append(code)

    # ── JS → Python message handler ──────────────────────────────────────────

    @objc.python_method
    def _handle_js_message(self, body: dict):
        msg_type = body.get("type")
        if msg_type == "polish":
            mode = body.get("mode", "pro")
            instruction = body.get("instruction") or None
            self._current_mode = mode
            self._start_process(mode, custom_prompt=instruction)
        elif msg_type == "close":
            self._hide()
        elif msg_type == "accept":
            if self._pending_result is not None:
                self._do_paste(self._pending_result)
        elif msg_type == "expand":
            self._set_expanded(bool(body.get("value")))

    # ── Cocoa delegate ───────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._hide()
        return False

    # ── Public API ───────────────────────────────────────────────────────────

    @objc.python_method
    def trigger_polish(self):
        """Called from hotkey background thread on shortcut press."""
        self._app_ref, self._selected_text = get_app_and_copy()
        _on_main(self._show)

    # ── Internal UI ──────────────────────────────────────────────────────────

    @objc.python_method
    def _show(self):
        self._set_expanded(False, animate=False)
        self._js("App.reset()")
        app_name = None
        if self._app_ref is not None:
            try:
                app_name = self._app_ref.localizedName()
            except Exception:
                pass
        self._js(f"App.setSourceApp({json.dumps(app_name)})")
        has_text = bool(self._selected_text.strip())
        if has_text:
            self._current_mode = "casual"
            self._js(f"App.setInputText({json.dumps(self._selected_text)})")
            self._js(f"App.setMode({json.dumps(self._current_mode)})")
        else:
            self._js("App.setInputText('Aucun texte sélectionné — sélectionnez du texte d\\'abord')")
        self._position_near_selection()
        self._panel.makeKeyAndOrderFront_(None)
        if has_text:
            self._start_process(self._current_mode)

    @objc.python_method
    def _position_near_selection(self):
        """Anchor the panel just below the current text selection using the
        Accessibility API. Falls back to centering the panel on screen if
        the selection bounds are unavailable (no selection, app doesn't
        expose it, or the AX call fails) — see platforms/macos/ax_bounds.py.
        """
        bounds = get_selection_bounds()
        screen = NSScreen.mainScreen()
        if bounds is None or screen is None:
            self._panel.center()
            return

        x, y, w, h = bounds
        screen_frame = screen.frame()
        panel_w, panel_h = _COMPACT_SIZE
        gap = 8

        # AX bounds use a top-left, Y-down origin; Cocoa screen coordinates
        # use a bottom-left, Y-up origin.
        origin_x = x
        origin_y = screen_frame.size.height - (y + h) - panel_h - gap
        if origin_y < 0:
            # Not enough room below the selection — place it above instead.
            origin_y = screen_frame.size.height - y + gap

        origin_x = max(0, min(origin_x, screen_frame.size.width - panel_w))
        origin_y = max(0, min(origin_y, screen_frame.size.height - panel_h))
        self._panel.setFrameOrigin_(NSMakePoint(origin_x, origin_y))

    @objc.python_method
    def _set_expanded(self, expand: bool, animate: bool = True):
        """Resize the native panel between the compact and expanded sizes,
        keeping the top edge fixed (the panel grows/shrinks downward, which
        matches it being anchored below the text selection)."""
        w, h = _EXPANDED_SIZE if expand else _COMPACT_SIZE
        frame = self._panel.frame()
        screen = NSScreen.mainScreen()
        top = frame.origin.y + frame.size.height
        new_origin_y = top - h
        new_origin_x = frame.origin.x
        if screen is not None:
            screen_frame = screen.frame()
            new_origin_x = max(0, min(new_origin_x, screen_frame.size.width - w))
            new_origin_y = max(0, min(new_origin_y, screen_frame.size.height - h))
        new_frame = NSMakeRect(new_origin_x, new_origin_y, w, h)
        self._panel.setFrame_display_animate_(new_frame, True, animate)

    @objc.python_method
    def _hide(self):
        self._panel.orderOut_(None)

    @objc.python_method
    def _start_process(self, mode: str, custom_prompt: str | None = None):
        if not self._selected_text.strip():
            return
        self._js("App.onPolishStart()")
        self._job_runner.start(
            self._selected_text, mode, custom_prompt,
            status_steps=_STATUS_STEPS,
            polish_fn=polish_text,
            on_status=lambda m: self._js(f"App.setStatus({json.dumps(m)})"),
            on_stream_start=lambda: self._js("App.startStream()"),
            on_token=lambda t: self._js(f"App.appendToken({json.dumps(t)})"),
            on_success=self._on_success,
            on_error=self._on_error,
        )

    @objc.python_method
    def _on_success(self, result: str):
        self._pending_result = result
        self._js("App.onDone()")
        segments = compute_word_diff(self._selected_text, result)
        self._js(f"App.setDiff({json.dumps(segments)})")

    @objc.python_method
    def _do_paste(self, result: str):
        self._pending_result = None
        self._hide()
        paste_text(result, self._app_ref)
        _add_to_history(self._selected_text, result, self._current_mode)
        self._update_history_webview()

    @objc.python_method
    def _update_history_webview(self):
        items = [
            {
                "mode":      e["mode"],
                "ts":        e["ts"],
                "preview":   e["original"][:60] + ("…" if len(e["original"]) > 60 else ""),
                "corrected": e["corrected"],
            }
            for e in _history.entries
        ]
        self._js(f"App.updateHistory({json.dumps(items)})")

    @objc.python_method
    def _on_error(self, message: str):
        short = message[:80] + ("…" if len(message) > 80 else "")
        self._js(f"App.onError({json.dumps(short)})")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def setup() -> TextPolishPanel:
    global _bridge, _status_item, _history_handler
    _bridge = _MainThreadBridge.alloc().init()
    _history_handler = _HistoryHandler.alloc().init()
    _status_item = _create_status_item()
    return TextPolishPanel.alloc().init()


def _create_status_item():
    bar  = NSStatusBar.systemStatusBar()
    item = bar.statusItemWithLength_(NSVariableStatusItemLength)

    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_("pencil", "TextPolish Cloud")
    if img is not None:
        img.setTemplate_(True)
        item.button().setImage_(img)
    else:
        item.button().setTitle_("✏️")
    item.button().setToolTip_("TextPolish Cloud")

    menu = NSMenu.alloc().init()

    history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("History", None, "")
    submenu = NSMenu.alloc().initWithTitle_("History")
    empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("No corrections yet", None, "")
    empty.setEnabled_(False)
    submenu.addItem_(empty)
    menu.addItem_(history_item)
    menu.setSubmenu_forItem_(submenu, history_item)

    menu.addItem_(NSMenuItem.separatorItem())

    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit TextPolish Cloud", "terminate:", "q"
    )
    menu.addItem_(quit_item)
    item.setMenu_(menu)

    global _history_menu
    _history_menu = submenu

    return item


_status_item = None
