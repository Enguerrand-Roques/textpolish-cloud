from diff import group_changes, apply_choices, classify_change, choose_layout


class TestDiffEdges:
    def test_identical_text_is_one_equal_part(self):
        assert group_changes("hello world", "hello world") == [
            {"op": "equal", "text": "hello world"}]

    def test_empty_strings(self):
        assert group_changes("", "") == []

    def test_pure_insertion_and_deletion_round_trip(self):
        for original, corrected in (("", "new text"), ("old text", ""),
                                    ("hello", "hello world"), ("hello world", "hello")):
            parts = group_changes(original, corrected)
            ids = [p["id"] for p in parts if p["op"] == "change"]
            assert apply_choices(parts, ids) == corrected
            assert apply_choices(parts, []) == original


def _changes(parts):
    return [p for p in parts if p["op"] == "change"]


class TestClassifyChange:
    def test_plural_or_feminine_ending_is_agreement(self):
        assert classify_change("chiffre", "chiffres") == "agreement"
        assert classify_change("bon", "bons") == "agreement"

    def test_swapped_verb_ending_is_conjugation(self):
        assert classify_change("valider", "validés") == "conjugation"
        assert classify_change("finit", "fini") == "conjugation"
        assert classify_change("était", "été") == "conjugation"

    def test_homophone_swap_is_grammar(self):
        assert classify_change("ces", "c'est") == "grammar"
        assert classify_change("sa", "ça") == "grammar"
        assert classify_change("a", "à") == "grammar"

    def test_english_homophones_and_verb_forms(self):
        assert classify_change("Their", "They're") == "grammar"
        assert classify_change("then", "than") == "grammar"
        assert classify_change("finish", "finished") == "conjugation"
        assert classify_change("go", "goes") == "agreement"

    def test_person_ending_is_conjugation(self):
        assert classify_change("peux", "peut") == "conjugation"

    def test_other_one_word_typos_stay_spelling(self):
        assert classify_change("testes", "tests") == "spelling"
        assert classify_change("opérationel", "opérationnel") == "spelling"

    def test_accent(self):
        assert classify_change("ca", "ça") == "accent"

    def test_case(self):
        assert classify_change("yo", "Yo") == "case"

    def test_punctuation(self):
        assert classify_change("", " ?") == "punctuation"
        assert classify_change("va", "va,") == "punctuation"

    def test_spelling(self):
        assert classify_change("opérationel", "opérationnel") == "spelling"
        assert classify_change("coment", "comment") == "spelling"

    def test_grammar_word_swap(self):
        assert classify_change("ce", "se") == "grammar"

    def test_rewrite(self):
        assert classify_change("tu vas", "comment allez-vous") == "rewrite"
        assert classify_change("t'as 5min", "auriez-vous quelques minutes") == "rewrite"


class TestGroupChanges:
    def test_each_fix_is_its_own_numbered_change(self):
        parts = group_changes("yo coment ca va", "yo comment ça va")
        changes = _changes(parts)
        assert [(c["before"], c["after"]) for c in changes] == [("coment", "comment"), ("ca", "ça")]
        assert [c["id"] for c in changes] == [0, 1]
        assert [c["kind"] for c in changes] == ["spelling", "accent"]

    def test_no_changes(self):
        assert _changes(group_changes("ça va", "ça va")) == []

    def test_context_words_around_change(self):
        parts = group_changes("RH et opérationel on veut plus", "RH et opérationnel on veut plus")
        c = _changes(parts)[0]
        assert c["context_before"].strip() == "RH et"
        assert c["context_after"].strip() == "on veut plus"

    def test_long_context_is_ellipsed(self):
        c = _changes(group_changes("one two three four five six bad", "one two three four five six good"))[0]
        assert c["context_before"].startswith("…")

    def test_label_present(self):
        assert _changes(group_changes("ca", "ça"))[0]["label"] == "Accent"


class TestApplyChoices:
    ORIG = "yo coment ca va frerot"
    CORR = "Yo, comment ça va frérot ?"

    def test_accept_all_gives_corrected(self):
        parts = group_changes(self.ORIG, self.CORR)
        ids = [c["id"] for c in _changes(parts)]
        assert apply_choices(parts, ids) == self.CORR

    def test_accept_none_gives_original(self):
        parts = group_changes(self.ORIG, self.CORR)
        assert apply_choices(parts, []) == self.ORIG

    def test_partial_acceptance(self):
        parts = group_changes("coment ca va", "comment ça va")
        assert apply_choices(parts, [0]) == "comment ca va"
        assert apply_choices(parts, [1]) == "coment ça va"


class TestChooseLayout:
    def test_none_when_unchanged(self):
        assert choose_layout(group_changes("ok", "ok"), "ok") == "none"

    def test_cards_for_short_text(self):
        assert choose_layout(group_changes("coment ca va", "comment ça va"), "coment ca va") == "cards"

    def test_document_for_many_changes(self):
        orig = "a b c d e"
        parts = group_changes(orig, "A B C D E")
        assert choose_layout(parts, orig) == "document"

    def test_document_for_long_text(self):
        orig = "word " * 80 + "teh"
        parts = group_changes(orig, "word " * 80 + "the")
        assert choose_layout(parts, orig) == "document"

    def test_rewrite_for_pro_and_custom(self):
        parts = group_changes("coment ca va", "comment ça va")
        assert choose_layout(parts, "coment ca va", mode="pro") == "rewrite"
        assert choose_layout(parts, "coment ca va", mode="custom") == "rewrite"
        assert choose_layout(group_changes("ok", "ok"), "ok", mode="pro") == "none"


class TestCosmeticChanges:
    def test_typographic_apostrophe_is_not_a_change(self):
        parts = group_changes("qu'on parle", "qu\u2019on parle")
        assert _changes(parts) == []
        assert apply_choices(parts, []) == "qu'on parle"

    def test_non_breaking_space_before_question_mark_is_ignored(self):
        assert _changes(group_changes("on parle?", "on parle\u00a0?")) == []

    def test_real_fix_next_to_apostrophe_is_kept(self):
        parts = group_changes("j'ai coment", "j\u2019ai comment")
        assert [(c["before"], c["after"]) for c in _changes(parts)] == [("coment", "comment")]
        assert apply_choices(parts, [0]) == "j'ai comment"


class TestLayoutThresholds:
    """Cards up to 3 fixes on up to 280 characters, the document view beyond."""

    def _parts(self, n_changes):
        return [{"op": "change", "id": i} for i in range(n_changes)]

    def test_three_fixes_are_cards_four_are_a_document(self):
        assert choose_layout(self._parts(3), "x" * 100) == "cards"
        assert choose_layout(self._parts(4), "x" * 100) == "document"

    def test_280_characters_are_cards_281_are_a_document(self):
        assert choose_layout(self._parts(1), "x" * 280) == "cards"
        assert choose_layout(self._parts(1), "x" * 281) == "document"


from diff import keep_sentence_marks


class TestKeepQuestionMarks:
    def test_dropped_question_mark_is_put_back(self):
        # The only miss of Round 6: two questions merged into one sentence.
        assert keep_sentence_marks(
            "slt tu fait quoi ce soir ? on peut se retrouver vers 19h",
            "slt tu fais quoi ce soir on peut se retrouver vers 19h",
        ) == "slt tu fais quoi ce soir ? on peut se retrouver vers 19h"

    def test_other_fixes_are_kept(self):
        assert keep_sentence_marks("tu viens?", "Tu viens ?") == "Tu viens ?"
        assert keep_sentence_marks("Est ce que tu peux ?", "Est-ce que tu peux ?") == "Est-ce que tu peux ?"

    def test_mark_replaced_by_other_punctuation_is_left_alone(self):
        assert keep_sentence_marks("on se voit ? oui", "On se voit. Oui") == "On se voit. Oui"

    def test_moved_mark_is_not_doubled(self):
        assert keep_sentence_marks("tu fais quoi ? ce soir", "Tu fais quoi ce soir ?") == "Tu fais quoi ce soir ?"

    def test_repeated_marks_may_be_reduced(self):
        assert keep_sentence_marks("Vraiment ??", "Vraiment ?") == "Vraiment ?"
        assert keep_sentence_marks("Super !!!", "Super !") == "Super !"
