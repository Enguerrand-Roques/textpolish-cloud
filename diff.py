"""Word-level diff between the original and corrected text, used to render
the strikethrough/highlight suggestion popup.
"""

import difflib
import re
import unicodedata

_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def compute_word_diff(original: str, corrected: str) -> list[dict]:
    """Returns segments: [{"text": str, "op": "equal"|"delete"|"insert"}, ...]"""
    a, b = _tokenize(original), _tokenize(corrected)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    segments: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            segments.append({"text": "".join(a[i1:i2]), "op": "equal"})
        elif tag == "delete":
            segments.append({"text": "".join(a[i1:i2]), "op": "delete"})
        elif tag == "insert":
            segments.append({"text": "".join(b[j1:j2]), "op": "insert"})
        elif tag == "replace":
            segments.append({"text": "".join(a[i1:i2]), "op": "delete"})
            segments.append({"text": "".join(b[j1:j2]), "op": "insert"})
    return segments


# ---------------------------------------------------------------------------
# Corrections: the unit the popup shows and lets the user accept or ignore
# ---------------------------------------------------------------------------

KIND_LABELS = {
    "accent": "Accent",
    "case": "Majuscule",
    "punctuation": "Ponctuation",
    "spelling": "Orthographe",
    "grammar": "Grammaire",
    "rewrite": "Reformulation",
}

_CARDS_MAX_CHANGES = 3
_CARDS_MAX_CHARS = 280
_CONTEXT_WORDS = 4


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


_TYPO_EQUIV = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
                              "\u00a0": " ", "\u202f": " ", "\u2009": " "})


def _is_cosmetic(before: str, after: str) -> bool:
    """True when two strings only differ by typographic quotes or spacing
    (e.g. ' vs ’, a non-breaking space before '?'). Not worth a suggestion."""
    norm = lambda t: " ".join(t.translate(_TYPO_EQUIV).split())
    return norm(before) == norm(after)


def _letters_only(s: str) -> str:
    return "".join(c for c in s if c.isalnum())


def classify_change(before: str, after: str) -> str:
    """Rough type of a correction, for the label shown on its card."""
    b, a = before.strip(), after.strip()
    if b == a:
        return "punctuation"
    if b.lower() == a.lower():
        return "case"
    if _strip_accents(b).lower() == _strip_accents(a).lower():
        return "accent"
    if _letters_only(b).lower() == _letters_only(a).lower():
        return "punctuation"
    if b and a and len(b.split()) <= 2 and len(a.split()) <= 2:
        ratio = difflib.SequenceMatcher(
            a=_strip_accents(b).lower(), b=_strip_accents(a).lower()
        ).ratio()
        if ratio >= 0.6:
            return "spelling"
        if len(b.split()) == 1 and len(a.split()) == 1:
            return "grammar"   # word-for-word swap: ce/se, a/à, et/est…
    return "rewrite"


def _tail_words(text: str, n: int) -> str:
    words = text.split()
    tail = " ".join(words[-n:])
    return ("…" + tail) if len(words) > n else tail


def _head_words(text: str, n: int) -> str:
    words = text.split()
    head = " ".join(words[:n])
    return (head + "…") if len(words) > n else head


def group_changes(original: str, corrected: str) -> list[dict]:
    """Split the diff into parts: unchanged text and numbered corrections.

    Returns [{"op": "equal", "text"} | {"op": "change", "id", "before",
    "after", "kind", "label", "context_before", "context_after"}, ...].
    Concatenating "before" (or "text") gives back *original*; concatenating
    "after" (or "text") gives back *corrected*.
    """
    a, b = _tokenize(original), _tokenize(corrected)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    parts: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        before, after = "".join(a[i1:i2]), "".join(b[j1:j2])
        if tag == "equal" or _is_cosmetic(before, after):
            # Cosmetic-only differences keep the user's original characters.
            if parts and parts[-1]["op"] == "equal":
                parts[-1]["text"] += before
            else:
                parts.append({"op": "equal", "text": before})
        else:
            kind = classify_change(before, after)
            parts.append({"op": "change", "id": 0, "before": before,
                          "after": after, "kind": kind, "label": KIND_LABELS[kind]})

    change_no = 0
    for i, p in enumerate(parts):
        if p["op"] != "change":
            continue
        p["id"] = change_no
        change_no += 1
        prev = parts[i - 1]["text"] if i > 0 and parts[i - 1]["op"] == "equal" else ""
        nxt = parts[i + 1]["text"] if i + 1 < len(parts) and parts[i + 1]["op"] == "equal" else ""
        p["context_before"] = _tail_words(prev, _CONTEXT_WORDS)
        p["context_after"] = _head_words(nxt, _CONTEXT_WORDS)
    return parts


def apply_choices(parts: list[dict], accepted_ids) -> str:
    """Rebuild the text, keeping the correction for accepted ids and the
    original wording for the others."""
    accepted = set(accepted_ids)
    out = []
    for p in parts:
        if p["op"] == "equal":
            out.append(p["text"])
        else:
            out.append(p["after"] if p["id"] in accepted else p["before"])
    return "".join(out)


def choose_layout(parts: list[dict], original: str, mode: str = "casual") -> str:
    """'none' when nothing changed; 'rewrite' for Pro/Perso, where the model
    rewrites the whole text and per-word cards would be noise; 'cards' for a
    few corrections on a short text (one card per fix, Grammarly-style);
    'document' otherwise."""
    changes = [p for p in parts if p["op"] == "change"]
    if not changes:
        return "none"
    if mode in ("pro", "custom"):
        return "rewrite"
    if len(changes) <= _CARDS_MAX_CHANGES and len(original) <= _CARDS_MAX_CHARS:
        return "cards"
    return "document"
