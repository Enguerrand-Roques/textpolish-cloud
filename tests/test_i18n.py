import i18n
from diff import group_changes
from history import format_menu_label


def _changes(parts):
    return [p for p in parts if p["op"] == "change"]


class TestI18n:
    def teardown_method(self):
        i18n.set_language("en")

    def test_both_languages_have_the_same_keys(self):
        assert i18n.STRINGS["en"].keys() == i18n.STRINGS["fr"].keys()

    def test_switching_language_relabels_fixes_and_history(self):
        entry = {"original": "hello", "corrected": "x", "mode": "custom", "ts": "10:00"}
        i18n.set_language("fr")
        assert _changes(group_changes("Les enfant", "Les enfants"))[0]["label"] == "Accord"
        assert "Sur mesure" in format_menu_label(entry)
        i18n.set_language("en")
        assert _changes(group_changes("Les enfant", "Les enfants"))[0]["label"] == "Agreement"
        assert "Custom" in format_menu_label(entry)

    def test_unknown_language_is_ignored(self):
        i18n.set_language("de")
        assert i18n.LANG == "en"
