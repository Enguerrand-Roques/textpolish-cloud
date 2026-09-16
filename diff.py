"""Word-level diff between the original and corrected text, used to render
the strikethrough/highlight suggestion popup.
"""

import difflib
import re

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
