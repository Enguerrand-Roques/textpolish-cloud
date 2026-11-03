"""Word-level diff between the original and corrected text, split into
numbered corrections that the popup shows and the user accepts or ignores,
each labelled with its kind (spelling, agreement, punctuation…).
"""

import difflib
import os
import re
import unicodedata
from collections.abc import Iterable

from i18n import t

_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


# ---------------------------------------------------------------------------
# Corrections: the unit the popup shows and lets the user accept or ignore
# ---------------------------------------------------------------------------

_CARDS_MAX_CHANGES = 3
_CARDS_MAX_CHARS = 280
_CONTEXT_WORDS = 4


_KEPT_MARKS = set("?!")


def keep_question_marks(original: str, corrected: str) -> str:
    """Put back any "?" or "!" the model dropped without replacing it.

    Small models sometimes merge "tu fais quoi ce soir ? on se voit" into one
    sentence. A correction should never remove the user's question or
    exclamation: only deletions made of these marks (and spaces) are undone,
    so a model that rewrites "?" into "." or moves it is left alone.
    """
    a, b = _tokenize(original), _tokenize(corrected)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        before, after = "".join(a[i1:i2]), "".join(b[j1:j2])
        marks = before.strip()
        dropped = (tag in ("delete", "replace") and marks and set(marks) <= _KEPT_MARKS | {" "}
                   and not after.strip())
        out.append(before if dropped else after)
    return "".join(out)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


_TYPO_EQUIV = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
                              "\u00a0": " ", "\u202f": " ", "\u2009": " "})


def _normalize_typography(s: str) -> str:
    return " ".join(s.translate(_TYPO_EQUIV).split())


def _is_cosmetic(before: str, after: str) -> bool:
    """True when two strings only differ by typographic quotes or spacing
    (e.g. ' vs ’, a non-breaking space before '?'). Not worth a suggestion."""
    return _normalize_typography(before) == _normalize_typography(after)


def _letters_only(s: str) -> str:
    return "".join(c for c in s if c.isalnum())


# Verb endings that small typos swap: valider/validé, finit/fini, était/été…
_VERB_ENDINGS = {
    "er", "é", "ée", "és", "ées", "ez", "ai", "ais", "ait", "aient", "as", "a",
    "ons", "ont", "i", "is", "it", "ir", "u", "us", "ue", "ues", "ra", "ras",
    "rai", "rait", "ront", "ent", "x", "t",
}

# French words that sound alike and get swapped: a/à, ces/c'est, sa/ça…
_HOMOPHONES = {
    "a", "à", "ces", "ses", "c'est", "s'est", "sait", "sa", "ça", "ce", "se", "et", "est",
    "ou", "où", "on", "ont", "son", "sont", "la", "là", "l'a", "leur", "leurs",
    "quel", "quelle", "qu'elle", "peu", "peut", "mes", "mais", "m'est",
    # English
    "their", "there", "they're", "your", "you're", "its", "it's", "to", "too", "two",
    "then", "than", "whose", "who's", "were", "where", "we're", "lose", "loose",
    "affect", "effect", "accept", "except",
}
_EN_VERB_SUFFIXES = {"ed", "d", "ing"}


def _is_agreement(b: str, a: str) -> bool:
    """Same word, only a plural/feminine ending added or removed (bon/bons)."""
    short, long_ = sorted((b, a), key=len)
    return long_[:len(short)] == short and long_[len(short):] in {"s", "x", "e", "es"}


def _is_conjugation(b: str, a: str) -> bool:
    """Same stem, two different verb endings (valider → validés, finish → finished)."""
    short, long_ = sorted((b, a), key=len)
    if long_.startswith(short) and long_[len(short):] in _EN_VERB_SUFFIXES and len(short) >= 3:
        return True
    prefix = len(os.path.commonprefix([b, a]))
    for k in range(prefix, max(1, prefix - 3), -1):
        eb, ea = b[k:], a[k:]
        if eb != ea and eb in _VERB_ENDINGS and ea in _VERB_ENDINGS:
            return True
    return False


def classify_change(before: str, after: str) -> str:
    """Rough type of a correction, for the label shown on its card."""
    b, a = before.strip(), after.strip()
    if b == a:
        return "punctuation"
    if b.lower() == a.lower():
        return "case"
    if b.lower().translate(_TYPO_EQUIV) in _HOMOPHONES and a.lower().translate(_TYPO_EQUIV) in _HOMOPHONES:
        return "grammar"
    if _strip_accents(b).lower() == _strip_accents(a).lower():
        return "accent"
    if _letters_only(b).lower() == _letters_only(a).lower():
        return "punctuation"
    one_word = len(b.split()) == 1 and len(a.split()) == 1
    if one_word and _is_agreement(b.lower(), a.lower()):
        return "agreement"
    if one_word and _is_conjugation(b.lower(), a.lower()):
        return "conjugation"
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
                          "after": after, "kind": kind, "label": t("kind_" + kind)})

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


def apply_choices(parts: list[dict], accepted_ids: Iterable[int]) -> str:
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
    """'none' when nothing changed; 'rewrite' for Pro and Custom, where the model
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
