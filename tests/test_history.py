import datetime

from history import CorrectionHistory, format_menu_label, format_tooltip


class TestCorrectionHistory:
    def test_add_inserts_most_recent_first(self):
        h = CorrectionHistory()
        h.add("first", "First.", "casual")
        h.add("second", "Second.", "pro")
        assert [e["original"] for e in h.entries] == ["second", "first"]

    def test_truncates_to_max_entries(self):
        h = CorrectionHistory(max_entries=3)
        for i in range(5):
            h.add(f"text {i}", f"Text {i}.", "casual")
        assert len(h.entries) == 3
        assert [e["original"] for e in h.entries] == ["text 4", "text 3", "text 2"]

    def test_entry_has_expected_keys(self):
        h = CorrectionHistory()
        entry = h.add("orig", "corrected", "pro")
        assert set(entry.keys()) == {"original", "corrected", "mode", "ts"}
        assert entry["original"] == "orig"
        assert entry["corrected"] == "corrected"
        assert entry["mode"] == "pro"

    def test_custom_clock_is_used_for_timestamp(self):
        h = CorrectionHistory()
        fixed_time = datetime.datetime(2024, 1, 1, 9, 5)
        entry = h.add("orig", "corrected", "pro", now=lambda: fixed_time)
        assert entry["ts"] == "09:05"


class TestFormatMenuLabel:
    def _entry(self, original="short text", mode="casual", ts="10:00"):
        return {"original": original, "corrected": "irrelevant", "mode": mode, "ts": ts}

    def test_short_text_not_truncated(self):
        entry = self._entry(original="hello")
        label = format_menu_label(entry)
        assert label == "10:00  Correction — hello"

    def test_long_text_truncated_with_ellipsis(self):
        entry = self._entry(original="x" * 50)
        label = format_menu_label(entry)
        assert label == f"10:00  Correction — {'x' * 40}…"

    def test_newlines_replaced_with_spaces(self):
        entry = self._entry(original="line one\nline two")
        label = format_menu_label(entry)
        assert "\n" not in label
        assert "line one line two" in label

    def test_mode_id_shown_with_its_display_name(self):
        assert "Sur mesure" in format_menu_label(self._entry(mode="custom"))
        assert "custom" not in format_menu_label(self._entry(mode="custom"))


class TestFormatTooltip:
    def test_truncates_to_200_chars(self):
        entry = {"original": "x", "corrected": "y" * 250, "mode": "pro", "ts": "10:00"}
        tooltip = format_tooltip(entry)
        assert tooltip == "y" * 200

    def test_short_text_unchanged(self):
        entry = {"original": "x", "corrected": "short", "mode": "pro", "ts": "10:00"}
        assert format_tooltip(entry) == "short"
