"""In-memory correction history, shared between the macOS and Windows UIs."""

import datetime

from i18n import t

DEFAULT_MAX_ENTRIES = 10
LABEL_TRUNCATE_CHARS = 40
TOOLTIP_TRUNCATE_CHARS = 200


class CorrectionHistory:
    """Last N corrections, most recent first."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._max_entries = max_entries
        self.entries: list[dict] = []

    def add(self, original: str, corrected: str, mode: str, now=datetime.datetime.now) -> dict:
        entry = {
            "original": original,
            "corrected": corrected,
            "mode": mode,
            "ts": now().strftime("%H:%M"),
        }
        self.entries.insert(0, entry)
        self.entries = self.entries[: self._max_entries]
        return entry




def format_menu_label(entry: dict, truncate: int = LABEL_TRUNCATE_CHARS) -> str:
    orig_short = entry["original"][:truncate].replace("\n", " ")
    if len(entry["original"]) > truncate:
        orig_short += "…"
    mode = t("mode_" + entry["mode"]) if entry["mode"] in ("casual", "pro", "custom") else entry["mode"]
    return f"{entry['ts']}  {mode} — {orig_short}"


def format_tooltip(entry: dict, truncate: int = TOOLTIP_TRUNCATE_CHARS) -> str:
    return entry["corrected"][:truncate]
