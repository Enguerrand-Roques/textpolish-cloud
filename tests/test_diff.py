from diff import compute_word_diff


class TestComputeWordDiff:
    def test_identical_text_is_all_equal(self):
        segments = compute_word_diff("hello world", "hello world")
        assert segments == [{"text": "hello world", "op": "equal"}]

    def test_pure_insertion(self):
        segments = compute_word_diff("hello", "hello world")
        assert segments[0] == {"text": "hello", "op": "equal"}
        assert {"text": " world", "op": "insert"} in segments or \
               {"text": "world", "op": "insert"} in segments
        assert all(s["op"] != "delete" for s in segments)

    def test_pure_deletion(self):
        segments = compute_word_diff("hello world", "hello")
        assert any(s["op"] == "delete" for s in segments)
        assert all(s["op"] != "insert" for s in segments)

    def test_replacement_produces_delete_then_insert(self):
        segments = compute_word_diff("salut les gars", "salut les gens")
        ops = [s["op"] for s in segments]
        assert "delete" in ops
        assert "insert" in ops
        delete_idx = ops.index("delete")
        insert_idx = ops.index("insert")
        assert delete_idx < insert_idx

    def test_punctuation_and_spacing_preserved(self):
        segments = compute_word_diff("Bonjour, ca va?", "Bonjour, ça va ?")
        rebuilt_original = "".join(
            s["text"] for s in segments if s["op"] in ("equal", "delete")
        )
        rebuilt_corrected = "".join(
            s["text"] for s in segments if s["op"] in ("equal", "insert")
        )
        assert rebuilt_original == "Bonjour, ca va?"
        assert rebuilt_corrected == "Bonjour, ça va ?"

    def test_empty_strings(self):
        assert compute_word_diff("", "") == []

    def test_empty_original_is_pure_insertion(self):
        segments = compute_word_diff("", "new text")
        assert all(s["op"] == "insert" for s in segments)
        assert "".join(s["text"] for s in segments) == "new text"

    def test_empty_corrected_is_pure_deletion(self):
        segments = compute_word_diff("old text", "")
        assert all(s["op"] == "delete" for s in segments)
        assert "".join(s["text"] for s in segments) == "old text"


from diff import group_changes, apply_choices, classify_change, choose_layout


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
