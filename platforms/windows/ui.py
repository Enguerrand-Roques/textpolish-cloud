"""
TextPolish panel — Windows implementation using PyQt6.
"""

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QDialog,
    QSystemTrayIcon,
    QMenu,
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QClipboard

from clipboard import get_app_and_copy, paste_text
from llm import polish_text
from history import CorrectionHistory, format_menu_label, format_tooltip
from polish_job import PolishJobRunner
from i18n import t


# ---------------------------------------------------------------------------
# Thread bridge — routes Python callables to the Qt main thread via signals
# ---------------------------------------------------------------------------

class _Bridge(QObject):
    _call: pyqtSignal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._call.connect(lambda fn: fn(), Qt.ConnectionType.QueuedConnection)

    def schedule(self, fn):
        self._call.emit(fn)


_bridge: _Bridge | None = None


def _on_main(fn):
    assert _bridge is not None, "call ui.setup() first"
    _bridge.schedule(fn)


# ---------------------------------------------------------------------------
# History — last 10 corrections (in-memory)
# ---------------------------------------------------------------------------

_history = CorrectionHistory()
_history_menu: QMenu | None = None

def _status_steps() -> list[tuple[float, str]]:
    return [
        (1.0,    t("status_prepare")),
        (3.0,    "Gemini"),
        (6.0,    t("status_rewrite")),
        (9999.0, t("status_finish")),
    ]


def _add_to_history(original: str, corrected: str, mode: str) -> None:
    _history.add(original, corrected, mode)
    _update_history_menu()


def _update_history_menu() -> None:
    if _history_menu is None:
        return
    _history_menu.clear()
    if not _history.entries:
        act = _history_menu.addAction(t("menu_empty"))
        act.setEnabled(False)
        return
    for entry in _history.entries:
        act = _history_menu.addAction(format_menu_label(entry))
        act.setToolTip(format_tooltip(entry))
        corrected = entry["corrected"]
        act.triggered.connect(
            lambda checked=False, c=corrected: QApplication.clipboard().setText(c)
        )


# Light refresh aligned with the macOS popup: same palette (system blue /
# indigo accents), rounded surfaces, Segoe UI Variable. Not tested on Windows
# from the macOS dev machine.
_STYLE = """
QWidget#panel { background: #f3f3f6; }
QLabel#title { font: 600 11pt "Segoe UI Variable", "Segoe UI"; color: #1c1c1e; }
QLabel#status { font: 9pt "Segoe UI Variable", "Segoe UI"; color: #8a8a8e; }
QLabel#status[error="true"] { color: #d70015; }
QTextEdit#text {
    background: #ffffff; border: 1px solid #e3e3e8; border-radius: 10px;
    padding: 8px; font: 10.5pt "Segoe UI Variable", "Segoe UI"; color: #1c1c1e;
    selection-background-color: #cfe3ff;
}
QPushButton {
    background: #e8e8ed; border: none; border-radius: 7px; padding: 7px 12px;
    font: 600 9.5pt "Segoe UI Variable", "Segoe UI"; color: #1c1c1e;
}
QPushButton:hover { background: #dedee4; }
QPushButton:disabled { color: #a1a1a6; }
QPushButton#primary { background: #007aff; color: white; }
QPushButton#primary:hover { background: #0a6fe8; }
QPushButton#primary:disabled { background: #9cc7ff; color: white; }
"""


# ---------------------------------------------------------------------------
# Panel widget (hides instead of closing)
# ---------------------------------------------------------------------------

class _Panel(QWidget):
    def closeEvent(self, event):
        event.ignore()
        self.hide()


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class TextPolishPanel(QObject):

    def __init__(self):
        super().__init__()
        self._selected_text = ""
        self._app_ref = None
        self._current_mode = "pro"
        self._job_runner = PolishJobRunner(on_main=_on_main)
        self._create_panel()

    # ----------------------------------------------------------------- setup

    def _create_panel(self):
        self._panel = _Panel()
        self._panel.setObjectName("panel")
        self._panel.setStyleSheet(_STYLE)
        self._panel.setWindowTitle("TextPolish")
        self._panel.setFixedSize(420, 300)
        self._panel.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Title
        title = QLabel("TextPolish")
        title.setObjectName("title")
        layout.addWidget(title)

        # Text preview
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setObjectName("text")
        layout.addWidget(self._text_view, stretch=1)

        # Status label
        self._status = QLabel("")
        self._status.setObjectName("status")
        layout.addWidget(self._status)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_pro = QPushButton(t("mode_pro"))
        self._btn_pro.clicked.connect(lambda: self._start_process("pro"))
        self._btn_casual = QPushButton(t("mode_casual"))
        self._btn_casual.setObjectName("primary")
        self._btn_casual.clicked.connect(lambda: self._start_process("casual"))
        self._btn_custom = QPushButton(t("mode_custom"))
        self._btn_custom.clicked.connect(self._open_custom_dialog)
        for btn in (self._btn_casual, self._btn_pro, self._btn_custom):
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

    # ---------------------------------------------------------------- public API

    def trigger_polish(self):
        """Called from hotkey background thread on shortcut."""
        self._app_ref, self._selected_text = get_app_and_copy()
        _on_main(self._show)

    # ---------------------------------------------------------------- internal UI

    def _show(self):
        if self._selected_text.strip():
            self._text_view.setText(self._selected_text)
            self._set_enabled(True)
        else:
            self._text_view.setText(t("no_selection"))
            self._set_enabled(False)

        self._set_status("")

        # Center on primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self._panel.move(
            screen.center().x() - self._panel.width() // 2,
            screen.center().y() - self._panel.height() // 2,
        )
        self._panel.show()
        self._panel.raise_()
        self._panel.activateWindow()

    def _hide(self):
        self._panel.hide()

    def _set_enabled(self, enabled: bool):
        for btn in (self._btn_pro, self._btn_casual, self._btn_custom):
            btn.setEnabled(enabled)

    def _start_process(self, mode: str, custom_prompt: str | None = None):
        if not self._selected_text.strip():
            return
        self._current_mode = mode
        self._set_enabled(False)
        self._set_status(t("status_prepare") + ".")
        self._job_runner.start(
            self._selected_text, mode, custom_prompt,
            status_steps=_status_steps(),
            polish_fn=polish_text,
            on_status=self._set_status,
            on_stream_start=self._on_stream_start,
            on_token=self._text_view.insertPlainText,
            on_success=self._on_success,
            on_error=self._on_error,
        )

    def _on_stream_start(self):
        self._status.setText("")
        self._text_view.setText("")

    def _on_success(self, result: str):
        self._hide()
        paste_text(result, self._app_ref)
        _add_to_history(self._selected_text, result, self._current_mode)

    def _on_error(self, message: str):
        self._status.setText(message)
        self._status.setWordWrap(True)
        self._status.setProperty("error", True)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._set_enabled(True)

    def _set_status(self, message: str):
        self._status.setText(message)
        self._status.setProperty("error", False)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _open_custom_dialog(self):
        dlg = QDialog(self._panel)
        dlg.setWindowTitle(t("custom_title"))
        dlg.setFixedSize(400, 200)
        dlg.setWindowFlags(
            dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        lbl = QLabel(t("custom_label"))
        lbl.setFont(QFont("Segoe UI", 10))
        layout.addWidget(lbl)

        text_input = QTextEdit()
        text_input.setText(t("custom_default"))
        text_input.setFont(QFont("Segoe UI", 10))
        layout.addWidget(text_input, stretch=1)

        apply_btn = QPushButton(t("apply"))
        apply_btn.setFixedWidth(110)
        layout.addWidget(apply_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        def apply():
            prompt = text_input.toPlainText().strip()
            dlg.accept()
            if prompt:
                self._start_process("custom", custom_prompt=prompt)

        apply_btn.clicked.connect(apply)
        dlg.exec()


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------

def _make_tray_icon() -> QIcon:
    """Render a small pencil glyph as the tray icon."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setFont(QFont("Segoe UI Emoji", 11))
    painter.drawText(0, 14, "✏")
    painter.end()
    return QIcon(pixmap)


def _create_tray(panel: TextPolishPanel) -> QSystemTrayIcon:
    global _history_menu

    tray = QSystemTrayIcon(_make_tray_icon())
    tray.setToolTip("TextPolish Cloud")

    menu = QMenu()

    # History submenu
    history_menu = QMenu(t("menu_history"))
    no_history = history_menu.addAction(t("menu_empty"))
    no_history.setEnabled(False)
    menu.addMenu(history_menu)
    _history_menu = history_menu

    menu.addSeparator()

    quit_action = menu.addAction(t("menu_quit") + " Cloud")
    quit_action.triggered.connect(QApplication.instance().quit)
    tray.setContextMenu(menu)
    tray.show()
    return tray


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_tray: QSystemTrayIcon | None = None


def setup() -> TextPolishPanel:
    """Initialize bridge, panel and tray. QApplication must already exist."""
    global _bridge, _tray
    _bridge = _Bridge()
    panel = TextPolishPanel()
    _tray = _create_tray(panel)
    return panel
