"""
TextPolish panel — a transparent WKWebView over native macOS vibrancy
(NSVisualEffectView) inside a borderless-looking NSPanel.

panel.html renders the UI; Python talks to it through a
WKScriptMessageHandler bridge (JS→Python) and evaluateJavaScript
(Python→JS). The page reports its natural height and the panel hugs it.
"""

import json
import logging
import os
import re
import threading
import time
import objc
from Foundation import NSObject, NSURL

from AppKit import (
    NSPanel,
    NSButton,
    NSTextField,
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
    NSVisualEffectView,
    NSVisualEffectMaterialPopover,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectStateActive,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowTitleHidden,
    NSWindowCloseButton,
    NSWindowMiniaturizeButton,
    NSWindowZoomButton,
)

from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController

from clipboard import get_app_and_copy, paste_text
from llm import polish_text
from history import CorrectionHistory, format_menu_label, format_tooltip
from polish_job import PolishJobRunner
from diff import group_changes, apply_choices, choose_layout
from platforms.macos.ax_bounds import get_selection_bounds

_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config.py")
)
_HTML_PATH = os.path.join(os.path.dirname(__file__), "panel.html")

# Titled + full-size content + transparent titlebar = rounded corners and a
# system shadow without any visible chrome.
_PANEL_STYLE = (
    NSWindowStyleMaskTitled
    | NSWindowStyleMaskClosable
    | NSWindowStyleMaskFullSizeContentView
    | NSWindowStyleMaskNonactivatingPanel
)
_COLLECTION = (
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorFullScreenAuxiliary
)

_PANEL_WIDTH = 380
_INITIAL_HEIGHT = 230
_MAX_HEIGHT = 560

_MOD_SYMBOLS = [("ctrl", "⌃"), ("alt", "⌥"), ("option", "⌥"), ("shift", "⇧"), ("cmd", "⌘")]


def _shortcut_label(shortcut: str) -> str:
    """'<cmd>+<alt>+g' -> '⌥⌘G' (macOS modifier order)."""
    keys = [k.strip().strip("<>").lower() for k in shortcut.split("+")]
    mods = "".join(sym for name, sym in _MOD_SYMBOLS if name in keys and not (name == "option" and "alt" in keys))
    main = [k for k in keys if k not in dict(_MOD_SYMBOLS)]
    return mods + "".join(k.upper() for k in main)


def _read_shortcut_from_config() -> str:
    try:
        with open(_CONFIG_PATH) as f:
            content = f.read()
        m = re.search(r'SHORTCUT\s*=\s*"([^"]*)"', content)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "<cmd>+<alt>+g"


def _write_shortcut_to_config(shortcut: str) -> None:
    with open(_CONFIG_PATH) as f:
        content = f.read()
    new_content = re.sub(
        r'(SHORTCUT\s*=\s*)"[^"]*"',
        f'\\1"{shortcut}"',
        content,
    )
    with open(_CONFIG_PATH, "w") as f:
        f.write(new_content)


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


# ---------------------------------------------------------------------------
# Preferences dialog
# ---------------------------------------------------------------------------

class _PrefsHandler(NSObject):
    def init(self):
        self = objc.super(_PrefsHandler, self).init()
        if self is None:
            return None
        self._dialog = None
        self._field = None
        self._error_label = None
        return self

    @objc.python_method
    def open(self):
        if self._dialog is not None:
            self._dialog.makeKeyAndOrderFront_(None)
            return
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskUtilityWindow
            | NSWindowStyleMaskNonactivatingPanel
        )
        dlg = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 390, 160), style, NSBackingStoreBuffered, False,
        )
        dlg.setTitle_("Préférences")
        dlg.setLevel_(NSFloatingWindowLevel)
        dlg.setCollectionBehavior_(_COLLECTION)
        cv = dlg.contentView()
        W, H, pad = 390, 160, 16

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, H - 46, W - 2 * pad, 22))
        lbl.setStringValue_("Raccourci clavier (format pynput, ex. <cmd>+<alt>+g) :")
        lbl.setEditable_(False); lbl.setBordered_(False); lbl.setDrawsBackground_(False)
        lbl.setFont_(NSFont.systemFontOfSize_(12)); lbl.setTextColor_(NSColor.secondaryLabelColor())
        cv.addSubview_(lbl)

        field = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, H - 80, W - 2 * pad, 26))
        field.setStringValue_(_read_shortcut_from_config())
        field.setFont_(NSFont.systemFontOfSize_(13))
        cv.addSubview_(field)

        err = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, H - 106, W - 2 * pad, 18))
        err.setStringValue_(""); err.setEditable_(False); err.setBordered_(False)
        err.setDrawsBackground_(False); err.setFont_(NSFont.systemFontOfSize_(11))
        err.setTextColor_(NSColor.systemRedColor())
        cv.addSubview_(err)

        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(W - pad - 196, pad, 88, 34))
        cancel_btn.setTitle_("Annuler"); cancel_btn.setBezelStyle_(1)
        cancel_btn.setTarget_(self); cancel_btn.setAction_("cancelPrefs:")
        cv.addSubview_(cancel_btn)

        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(W - pad - 100, pad, 100, 34))
        save_btn.setTitle_("Enregistrer"); save_btn.setBezelStyle_(1)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self); save_btn.setAction_("saveShortcut:")
        cv.addSubview_(save_btn)

        self._dialog = dlg; self._field = field; self._error_label = err
        dlg.center(); dlg.makeKeyAndOrderFront_(None)

    def saveShortcut_(self, sender):
        shortcut = self._field.stringValue().strip()
        try:
            from platforms.macos import hotkey as _hotkey
            _hotkey.update_shortcut(shortcut)
        except ValueError as e:
            self._error_label.setStringValue_(str(e))
            return
        _write_shortcut_to_config(shortcut)
        self._dialog.orderOut_(None)
        self._dialog = None

    def cancelPrefs_(self, sender):
        self._dialog.orderOut_(None)
        self._dialog = None

    def openPrefs_(self, sender):
        self.open()


_prefs_handler: _PrefsHandler | None = None


def _add_to_history(original: str, corrected: str, mode: str) -> None:
    _history.add(original, corrected, mode)
    _update_history_menu()


def _update_history_menu() -> None:
    if _history_menu is None:
        return
    _history_menu.removeAllItems()
    if not _history.entries:
        empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Aucune correction pour l'instant", None, "")
        empty.setEnabled_(False)
        _history_menu.addItem_(empty)
        return
    for entry in _history.entries:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            format_menu_label(entry), "copyText:", ""
        )
        item.setTarget_(_history_handler)
        item.setRepresentedObject_(entry["corrected"])
        item.setToolTip_(f"Cliquer pour copier le texte corrigé\n\n{format_tooltip(entry)}")
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
            "TextPolish needs Accessibility access to listen for the global "
            "keyboard shortcut. Grant it in System Settings → Privacy & "
            "Security → Accessibility, then restart TextPolish."
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
        self._parts: list[dict] = []
        self._t_job = 0.0
        self._job_runner = PolishJobRunner(on_main=_on_main)
        self._webview_ready = False
        self._pending_js: list[str] = []
        self._create_panel()
        return self

    # ── Setup ────────────────────────────────────────────────────────────────

    @objc.python_method
    def _create_panel(self):
        self._panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _PANEL_WIDTH, _INITIAL_HEIGHT),
            _PANEL_STYLE,
            NSBackingStoreBuffered,
            False,
        )
        self._panel.setTitle_("TextPolish")
        self._panel.setTitleVisibility_(NSWindowTitleHidden)
        self._panel.setTitlebarAppearsTransparent_(True)
        for button in (NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton):
            b = self._panel.standardWindowButton_(button)
            if b is not None:
                b.setHidden_(True)
        self._panel.setMovableByWindowBackground_(True)
        self._panel.setOpaque_(False)
        self._panel.setBackgroundColor_(NSColor.clearColor())
        self._panel.setHasShadow_(True)
        self._panel.setLevel_(NSFloatingWindowLevel)
        self._panel.setHidesOnDeactivate_(False)
        self._panel.setCollectionBehavior_(_COLLECTION)
        self._panel.setDelegate_(self)

        blur = NSVisualEffectView.alloc().initWithFrame_(self._panel.contentView().bounds())
        blur.setMaterial_(NSVisualEffectMaterialPopover)
        blur.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        blur.setState_(NSVisualEffectStateActive)
        blur.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self._panel.setContentView_(blur)
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
        self._webview = WKWebView.alloc().initWithFrame_configuration_(cv.bounds(), config)
        self._webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self._webview.setNavigationDelegate_(self)
        # Let the vibrancy behind the web view show through.
        self._webview.setValue_forKey_(False, "drawsBackground")

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
            self._accept(body.get("accepted") or [])
        elif msg_type == "resize":
            self._resize_to(float(body.get("height") or 0))

    # ── Cocoa delegate ───────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._hide()
        return False

    def windowDidResignKey_(self, notification):
        # Behave like a popover: clicking elsewhere dismisses it.
        self._hide()

    # ── Public API ───────────────────────────────────────────────────────────

    @objc.python_method
    def trigger_polish(self):
        """Called from hotkey background thread on shortcut press."""
        t0 = time.perf_counter()
        self._app_ref, self._selected_text = get_app_and_copy()
        logging.info("Copied %d chars in %.0f ms",
                     len(self._selected_text), (time.perf_counter() - t0) * 1000)
        _on_main(self._show)

    # ── Internal UI ──────────────────────────────────────────────────────────

    @objc.python_method
    def _show(self):
        self._parts = []
        self._resize_to(_INITIAL_HEIGHT, keep_top=False)
        self._js("App.reset()")
        app_name = None
        if self._app_ref is not None:
            try:
                app_name = self._app_ref.localizedName()
            except Exception:
                pass
        self._js(f"App.setSourceApp({json.dumps(app_name)})")
        self._js(f"App.setShortcut({json.dumps(_shortcut_label(_read_shortcut_from_config()))})")
        has_text = bool(self._selected_text.strip())
        self._current_mode = "casual"
        self._js(f"App.setMode({json.dumps(self._current_mode)})")
        if has_text:
            self._js(f"App.setInputText({json.dumps(self._selected_text)})")
        else:
            self._js("App.noSelection()")
        self._position_near_selection()
        self._panel.setAlphaValue_(0.0)
        self._panel.makeKeyAndOrderFront_(None)
        self._panel.animator().setAlphaValue_(1.0)
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
        panel_w, panel_h = _PANEL_WIDTH, self._panel.frame().size.height
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
    def _resize_to(self, height: float, keep_top: bool = True):
        """Resize the panel to the page's natural height, keeping the top edge
        fixed so it grows downward from just below the selection."""
        if height <= 0:
            return
        h = min(max(height, 120), _MAX_HEIGHT)
        frame = self._panel.frame()
        if abs(frame.size.height - h) < 1 and frame.size.width == _PANEL_WIDTH:
            return
        top = frame.origin.y + frame.size.height
        new_y = top - h if keep_top else frame.origin.y
        new_x = frame.origin.x
        screen = NSScreen.mainScreen()
        if screen is not None:
            sf = screen.visibleFrame()
            new_x = max(sf.origin.x, min(new_x, sf.origin.x + sf.size.width - _PANEL_WIDTH))
            new_y = max(sf.origin.y, min(new_y, sf.origin.y + sf.size.height - h))
        animate = keep_top and self._panel.isVisible()
        self._panel.setFrame_display_animate_(NSMakeRect(new_x, new_y, _PANEL_WIDTH, h), True, animate)

    @objc.python_method
    def _hide(self):
        self._panel.orderOut_(None)

    @objc.python_method
    def _start_process(self, mode: str, custom_prompt: str | None = None):
        if not self._selected_text.strip():
            return
        self._js("App.onPolishStart()")
        self._t_job = time.perf_counter()
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
        self._js("App.onDone()")
        self._parts = group_changes(self._selected_text, result)
        layout = choose_layout(self._parts, self._selected_text, self._current_mode)
        logging.info("%s ready in %.0f ms: %s, %d change(s)", self._current_mode,
                     (time.perf_counter() - self._t_job) * 1000, layout,
                     sum(p["op"] == "change" for p in self._parts))
        self._js(f"App.setChanges({json.dumps(self._parts)}, {json.dumps(layout)})")

    @objc.python_method
    def _accept(self, accepted_ids):
        if not self._parts:
            self._hide()
            return
        final = apply_choices(self._parts, accepted_ids)
        self._parts = []
        if final == self._selected_text:
            self._hide()
            return
        self._do_paste(final)

    @objc.python_method
    def _do_paste(self, result: str):
        self._hide()
        paste_text(result, self._app_ref)
        _add_to_history(self._selected_text, result, self._current_mode)

    @objc.python_method
    def _on_error(self, message: str):
        self._js(f"App.onError({json.dumps(message)})")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def setup() -> TextPolishPanel:
    global _bridge, _status_item, _history_handler, _prefs_handler
    _bridge = _MainThreadBridge.alloc().init()
    _history_handler = _HistoryHandler.alloc().init()
    _prefs_handler = _PrefsHandler.alloc().init()
    _status_item = _create_status_item()
    return TextPolishPanel.alloc().init()


def _create_status_item():
    bar  = NSStatusBar.systemStatusBar()
    item = bar.statusItemWithLength_(NSVariableStatusItemLength)

    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_("pencil", "TextPolish")
    if img is not None:
        img.setTemplate_(True)
        item.button().setImage_(img)
    else:
        item.button().setTitle_("✏️")
    item.button().setToolTip_("TextPolish")

    menu = NSMenu.alloc().init()

    prefs_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Préférences…", "openPrefs:", ","
    )
    prefs_item.setTarget_(_prefs_handler)
    menu.addItem_(prefs_item)
    menu.addItem_(NSMenuItem.separatorItem())

    history_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Historique", None, "")
    submenu = NSMenu.alloc().initWithTitle_("Historique")
    empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Aucune correction pour l'instant", None, "")
    empty.setEnabled_(False)
    submenu.addItem_(empty)
    menu.addItem_(history_item)
    menu.setSubmenu_forItem_(submenu, history_item)

    menu.addItem_(NSMenuItem.separatorItem())

    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quitter TextPolish", "terminate:", "q"
    )
    menu.addItem_(quit_item)
    item.setMenu_(menu)

    global _history_menu
    _history_menu = submenu

    return item


_status_item = None
