"""
TextPolish panel — Windows implementation using PyQt6.
"""

import threading
import time

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
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor

from clipboard import get_app_and_copy, paste_text
from llm import polish_text


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
        self._status_job = 0
        self._create_panel()

    # ----------------------------------------------------------------- setup

    def _create_panel(self):
        self._panel = _Panel()
        self._panel.setWindowTitle("TextPolish")
        self._panel.setFixedSize(440, 330)
        self._panel.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self._panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        title = QLabel("TextPolish")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        # Text preview
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setFont(QFont("Segoe UI", 11))
        layout.addWidget(self._text_view, stretch=1)

        # Status label
        self._status = QLabel("")
        self._status.setFont(QFont("Segoe UI", 9))
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_pro = QPushButton("Professional")
        self._btn_pro.clicked.connect(lambda: self._start_process("pro"))
        self._btn_casual = QPushButton("Casual")
        self._btn_casual.clicked.connect(lambda: self._start_process("casual"))
        self._btn_custom = QPushButton("Custom")
        self._btn_custom.clicked.connect(self._open_custom_dialog)
        for btn in (self._btn_pro, self._btn_casual, self._btn_custom):
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
            self._text_view.setStyleSheet("")
            self._set_enabled(True)
        else:
            self._text_view.setText("No text selected — select text first")
            self._text_view.setStyleSheet("color: gray;")
            self._set_enabled(False)

        self._status.setText("")
        self._status.setStyleSheet("color: gray;")

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
        self._set_enabled(False)
        self._status_job += 1
        job_id = self._status_job
        self._set_status("Preparing correction.")

        def status_worker():
            steps = [
                (1.0,    "Preparing correction"),
                (3.0,    "Calling Gemini"),
                (6.0,    "Rewriting text"),
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

    def _on_success(self, result: str):
        self._status_job += 1
        self._hide()
        paste_text(result, self._app_ref)

    def _on_error(self, message: str):
        self._status_job += 1
        short = message[:60] + ("…" if len(message) > 60 else "")
        self._status.setText(f"Error: {short}")
        self._status.setStyleSheet("color: red;")
        self._set_enabled(True)

    def _set_status(self, message: str):
        self._status.setText(message)
        self._status.setStyleSheet("color: gray;")

    def _update_status_if_current(self, job_id: int, message: str):
        if job_id == self._status_job:
            self._set_status(message)

    def _open_custom_dialog(self):
        dlg = QDialog(self._panel)
        dlg.setWindowTitle("Custom instruction")
        dlg.setFixedSize(400, 200)
        dlg.setWindowFlags(
            dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        lbl = QLabel("Describe how to rewrite the text:")
        lbl.setFont(QFont("Segoe UI", 10))
        layout.addWidget(lbl)

        text_input = QTextEdit()
        text_input.setText("Rewrite this text keeping my style, make it punchier.")
        text_input.setFont(QFont("Segoe UI", 10))
        layout.addWidget(text_input, stretch=1)

        apply_btn = QPushButton("Apply")
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
    tray = QSystemTrayIcon(_make_tray_icon())
    tray.setToolTip("TextPolish Cloud")

    menu = QMenu()
    quit_action = menu.addAction("Quit TextPolish Cloud")
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
