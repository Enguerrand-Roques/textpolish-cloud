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
