from unittest.mock import MagicMock, patch

import requests

import languagetool
from diff import apply_choices, default_accepted, group_changes


def _match(offset, length, category, *replacements):
    return {"offset": offset, "length": length,
            "rule": {"id": "R", "category": {"id": category}},
            "replacements": [{"value": r} for r in replacements]}


def _server(*matches):
    response = MagicMock()
    response.json.return_value = {"matches": list(matches)}
    return patch("languagetool.requests.post", return_value=response)


class TestImprove:
    def test_safe_single_suggestion_is_applied_with_its_range(self):
        with _server(_match(7, 4, "CAT_HOMONYMES_PARONYMES", "peu")):
            text, ranges = languagetool.improve("Il y a peut de trains", "fr")
        assert text == "Il y a peu de trains"
        assert ranges == [(7, 10)]

    def test_several_suggestions_or_unsafe_category_are_skipped(self):
        with _server(_match(5, 6, "CAT_GRAMMAIRE", "ai", "avais"),
                     _match(0, 3, "TYPOS", "Btw")):
            assert languagetool.improve("Si j'aurais su", "fr") == ("Si j'aurais su", [])

    def test_ranges_follow_earlier_length_changes(self):
        with _server(_match(0, 5, "CAT_HOMONYMES_PARONYMES", "Quant"),
                     _match(20, 4, "CAT_HOMONYMES_PARONYMES", "peu")):
            text, ranges = languagetool.improve("Quand à moi, il y a peut de", "fr")
        assert text == "Quant à moi, il y a peu de"
        assert [text[a:b] for a, b in ranges] == ["Quant", "peu"]

    def test_a_hint_in_parentheses_is_not_a_fix(self):
        with _server(_match(8, 11, "CAT_GRAMMAIRE", "(délicieuses)")):
            assert languagetool.improve("étaient délicieuses", "fr") == ("étaient délicieuses", [])

    def test_server_down_leaves_the_text_alone(self):
        with patch("languagetool.requests.post", side_effect=requests.ConnectionError):
            assert languagetool.improve("I have ate", "en") == ("I have ate", [])


class TestTrustedRanges:
    def test_a_rule_fix_is_applied_by_default_even_if_it_would_be_held(self):
        # "ate" -> "eaten" alone would be a real-word swap; LanguageTool's
        # range marks it as a rule-based fix.
        import diff
        diff.set_word_checker(lambda w: True)
        try:
            parts = group_changes("I have ate already", "I have eaten already", [(7, 12)])
            assert apply_choices(parts, default_accepted(parts)) == "I have eaten already"
        finally:
            diff.set_word_checker(None)
