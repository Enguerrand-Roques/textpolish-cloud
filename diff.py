"""Word-level diff between the original and corrected text, split into
numbered corrections that the popup shows and the user accepts or ignores,
each labelled with its kind (spelling, agreement, punctuation…).
"""

import difflib
import os
import re
import unicodedata
from collections.abc import Callable, Iterable

from i18n import t

_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")
_WORD_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


# ---------------------------------------------------------------------------
# Corrections: the unit the popup shows and lets the user accept or ignore
# ---------------------------------------------------------------------------

_CARDS_MAX_CHANGES = 3
_CARDS_MAX_CHARS = 280
_CONTEXT_WORDS = 4


_KEPT_MARKS = set("?!")


def keep_sentence_marks(original: str, corrected: str) -> str:
    """Put back a "?" or "!" the model dropped without replacing it.

    Small models sometimes merge "tu fais quoi ce soir ? on se voit" into one
    sentence. A correction should never remove the user's question or
    exclamation. Only deletions made of these marks (and spaces) are undone,
    and only while the answer has fewer of that mark than the input, so a
    "?" the model moved, turned into ".", or a "??" it reduced to "?" stays
    as the model wrote it.
    """
    a, b = _tokenize(original), _tokenize(corrected)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    missing = {m: original.count(m) - corrected.count(m) for m in _KEPT_MARKS}
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        before, after = "".join(a[i1:i2]), "".join(b[j1:j2])
        marks = before.replace(" ", "")
        repeated = (i1 > 0 and a[i1 - 1] in _KEPT_MARKS) or (i2 < len(a) and a[i2] in _KEPT_MARKS)
        dropped = (tag in ("delete", "replace") and marks and set(marks) <= _KEPT_MARKS
                   and not after.strip() and not repeated
                   and all(missing[m] >= marks.count(m) for m in set(marks)))
        if dropped:
            for m in marks:
                missing[m] -= 1
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

# Known confusions: words people really swap for one another. A fix inside a
# group is a recognised mistake and is applied; a swap between two real words
# outside every group is held for review (needs_review).
_CONFUSIONS = [
    # French homophones
    {"a", "à", "as"}, {"ces", "ses", "c'est", "s'est", "sait", "sais"}, {"sa", "ça"},
    {"ce", "se"}, {"et", "est"}, {"ou", "où"}, {"on", "ont", "on n'"}, {"son", "sont"},
    {"la", "là", "l'a", "l'as"}, {"leur", "leurs"}, {"quel", "quelle", "quels", "quelles", "qu'elle", "qu'elles"},
    {"peu", "peut", "peux"}, {"mes", "mais", "m'est", "met", "mets"}, {"ma", "m'a", "m'as"},
    {"près", "prêt", "prête", "prêts", "prêtes"}, {"court", "cours", "cour", "courent"},
    {"croix", "crois", "croit"}, {"quand", "quant", "qu'en"}, {"sans", "s'en", "sent", "cent"},
    {"tout", "tous", "toute", "toutes"}, {"foi", "fois", "foie"}, {"vers", "vert", "verre"},
    {"si", "s'y", "ci"}, {"c", "s"},  # c'est / s'est, split by the tokenizer
    {"dans", "d'en"}, {"plutôt", "plus tôt"}, {"quelque", "quelques", "quel que", "quelle que"},
    # French auxiliaries and common irregular verbs (forms swapped by conjugation)
    {"ai", "est", "es", "a", "as", "ont", "sont", "suis", "sommes", "êtes", "avons", "avez", "sois", "soit", "soient", "aie", "ait"},
    {"fait", "fais", "fasse", "fasses", "font", "faites"}, {"prend", "prends", "prennent", "prenne", "prennes", "pris", "prit"},
    {"vien", "viens", "vient", "viennent", "vienne", "viennes", "venez", "veniez"},
    {"peux", "peut", "peuvent", "puisse", "puisses", "pu", "pourra", "pourras", "pourrai", "pourrais", "pourrait"},
    {"va", "vas", "vont", "aille", "ailles", "allez", "alliez"}, {"veux", "veut", "veulent", "veuille", "voulu"},
    {"dis", "dit", "dise", "dises", "disent"}, {"voie", "voies", "vois", "voit", "voient", "vu"},
    {"part", "pars", "parte", "partes", "parti", "partit", "partie"},
    # English homophones and confusables
    {"their", "there", "they're"}, {"your", "you're", "you"}, {"its", "it's"}, {"to", "too", "two"},
    {"then", "than"}, {"whose", "who's"}, {"were", "where", "we're"}, {"lose", "loose"},
    {"affect", "effect"}, {"accept", "except"}, {"advice", "advise"}, {"weather", "whether"},
    {"principle", "principal"}, {"of", "have", "'ve"}, {"a", "an"}, {"less", "fewer"},
    {"quite", "quiet"}, {"past", "passed"}, {"brake", "break"}, {"lead", "led"},
    # English be / have / do forms (agreement) and contraction pieces
    {"am", "is", "are", "was", "were", "be", "been", "being"}, {"has", "have", "had", "having"},
    {"do", "does", "did", "done", "doing", "don", "doesn", "didn", "dont", "doesnt", "didnt"},
    # English irregular verbs
    *({*forms.split()} for forms in (
        "go goes went gone", "see sees saw seen", "write writes wrote written", "know knows knew known",
        "give gives gave given", "take takes took taken", "eat eats ate eaten", "come comes came",
        "run runs ran", "buy buys bought buyed", "catch catches caught catched", "drive drives drove driven drived",
        "think thinks thought", "bring brings brought", "teach teaches taught", "break breaks broke broken",
        "choose chooses chose chosen", "speak speaks spoke spoken", "begin begins began begun",
        "drink drinks drank drunk", "forget forgets forgot forgotten", "get gets got gotten",
        "find finds found", "leave leaves left", "make makes made", "meet meets met", "pay pays paid",
        "say says said", "sell sells sold", "send sends sent", "sit sits sat", "sleep sleeps slept",
        "stand stands stood", "tell tells told", "win wins won", "wear wears wore worn", "fly flies flew flown",
        "grow grows grew grown", "hear hears heard", "hold holds held", "keep keeps kept", "lose loses lost",
        "mean means meant", "feel feels felt", "fall falls fell fallen", "lend lends lent", "borrow borrows borrowed",
        "rise rises rose risen", "ride rides rode ridden", "steal steals stole stolen", "throw throws threw thrown",
        "want wants wanted", "use used", "suppose supposed")),
]
# Words that sound alike, for the "grammar" label of classify_change.
_HOMOPHONES = {
    "a", "à", "ces", "ses", "c'est", "s'est", "sait", "sa", "ça", "ce", "se", "et", "est",
    "ou", "où", "on", "ont", "son", "sont", "la", "là", "l'a", "leur", "leurs",
    "quel", "quelle", "qu'elle", "peu", "peut", "mes", "mais", "m'est",
    "their", "there", "they're", "your", "you're", "its", "it's", "to", "too", "two",
    "then", "than", "whose", "who's", "were", "where", "we're", "lose", "loose",
    "affect", "effect", "accept", "except",
}
_EN_VERB_SUFFIXES = {"ed", "d", "ing"}


def _is_agreement(b: str, a: str) -> bool:
    """Same word, only a plural/feminine ending added or removed (bon/bons)."""
    short, long_ = sorted((b, a), key=len)
    return long_[:len(short)] == short and long_[len(short):] in {"s", "x", "e", "es", "ue", "ues"}


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


# Informal words and abbreviations the user chose: a fix that touches one is
# never applied by default ("aprem" is not a typo for "après").
INFORMAL_WORDS = {
    # French
    "slt", "cc", "bjr", "jsuis", "chuis", "jsp", "jpp", "jvais", "jte", "jcrois",
    "aprem", "dispo", "dispos", "tkt", "mdr", "ptdr", "rdv", "bcp", "stp", "svp",
    "pk", "pcq", "dsl", "mtn", "tjrs", "qqn", "qqch", "resto", "frero", "wsh",
    # English
    "lol", "btw", "idk", "imo", "imho", "tbh", "brb", "np", "thx", "ty", "pls",
    "plz", "u", "ur", "omg", "gonna", "wanna", "gotta", "kinda", "lmk", "fyi",
}


# Optional dictionary lookup (word -> is it a real word?), set by the platform
# layer: macOS uses its own spell checker (platforms/macos/spelling.py).
_is_word: Callable[[str], bool] | None = None


def set_word_checker(fn: Callable[[str], bool] | None) -> None:
    global _is_word
    _is_word = fn


def _confusion_key(word: str) -> str:
    return _letters_only(word.translate(_TYPO_EQUIV)).lower()


_CONFUSION_KEYS = [{_confusion_key(w) for w in group} for group in _CONFUSIONS]


def _is_known_confusion(before: str, after: str) -> bool:
    b, a = _confusion_key(before), _confusion_key(after)
    if any(b in group and a in group for group in _CONFUSION_KEYS):
        return True
    # French verb vs adjective: intéressent / intéressant, différent / différant
    return len(b) > 4 and b[:-3] == a[:-3] and {b[-3:], a[-3:]} == {"ent", "ant"}


_PLURAL_APOSTROPHE = re.compile(r"^(\w+)'s$")


def _punctuation_count(s: str) -> int:
    return sum(1 for c in s if not c.isalnum() and not c.isspace())


def needs_review(before: str, after: str, kind: str) -> bool:
    """True for a fix that should not be applied by default: the user sees it
    and accepts it with one click. A wrong fix changes what the user meant,
    so anything that is not a recognised kind of mistake waits:
    - a rewording that matches no kind of mistake;
    - punctuation removed (a comma, the apostrophe of "I'm");
    - an informal word "fixed" ("aprem" is not a typo for "après");
    - one real word swapped for another that is not a known confusion
      ("lui" -> "fout", "there" -> "the"); a typo is not a real word.
    """
    if kind == "rewrite":
        return True
    if kind == "punctuation" and _punctuation_count(after) < _punctuation_count(before):
        # "apple's" -> "apples" drops a wrong plural apostrophe; "I'm" -> "Im"
        # drops a needed one.
        m = _PLURAL_APOSTROPHE.match(before.strip().translate(_TYPO_EQUIV))
        return not (m and after.strip().lower() == m.group(1).lower() + "s")
    words = _WORD_RE.findall(before)
    if any(w.lower() in INFORMAL_WORDS for w in words):
        return True
    if kind in ("grammar", "spelling") and _is_known_confusion(before, after):
        return False
    if kind == "grammar":
        # a misspelt word ("runned") is fixed; a real word only for a known confusion
        return _is_word is None or all(_is_word(w) for w in words)
    if kind == "spelling" and _is_word is not None and words and all(_is_word(w) for w in words):
        return True
    return False


def _is_repeated_word(change: dict, prev: str, nxt: str) -> bool:
    """A deletion of a word that is repeated next to it ("the the")."""
    removed = change["before"].split()
    if change["after"].strip() or len(removed) != 1:
        return False
    word = removed[0].lower()
    near = (prev.split()[-1:] or [""])[0].lower(), (nxt.split()[:1] or [""])[0].lower()
    return word in near


def default_accepted(parts: list[dict]) -> list[int]:
    """Ids of the fixes applied unless the user ignores them."""
    return [p["id"] for p in parts if p["op"] == "change" and not p["review"]]


def _tail_words(text: str, n: int) -> str:
    words = text.split()
    tail = " ".join(words[-n:])
    return ("…" + tail) if len(words) > n else tail


def _head_words(text: str, n: int) -> str:
    words = text.split()
    head = " ".join(words[:n])
    return (head + "…") if len(words) > n else head


def group_changes(original: str, corrected: str,
                  trusted: Iterable[tuple[int, int]] = ()) -> list[dict]:
    """Split the diff into parts: unchanged text and numbered corrections.

    Returns [{"op": "equal", "text"} | {"op": "change", "id", "before",
    "after", "kind", "label", "review", "context_before", "context_after"}, ...].
    "review" marks a fix that is shown but not applied by default (needs_review),
    except inside *trusted* ranges of *corrected* (fixes made by LanguageTool).
    Concatenating "before" (or "text") gives back *original*; concatenating
    "after" (or "text") gives back *corrected*.
    """
    a, b = _tokenize(original), _tokenize(corrected)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    trusted = list(trusted)
    offsets = [0]  # offsets[j] = position of token j in *corrected*
    for token in b:
        offsets.append(offsets[-1] + len(token))
    parts: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        before, after = "".join(a[i1:i2]), "".join(b[j1:j2])
        start, end = offsets[j1], offsets[j2]
        by_rule = any(lo <= end and start <= hi for lo, hi in trusted)
        if tag == "equal" or _is_cosmetic(before, after):
            # Cosmetic-only differences keep the user's original characters.
            if parts and parts[-1]["op"] == "equal":
                parts[-1]["text"] += before
            else:
                parts.append({"op": "equal", "text": before})
        else:
            kind = classify_change(before, after)
            parts.append({"op": "change", "id": 0, "before": before, "after": after,
                          "kind": kind, "label": t("kind_" + kind),
                          "review": not by_rule and needs_review(before, after, kind)})

    change_no = 0
    for i, p in enumerate(parts):
        if p["op"] != "change":
            continue
        p["id"] = change_no
        change_no += 1
        prev = parts[i - 1]["text"] if i > 0 and parts[i - 1]["op"] == "equal" else ""
        nxt = parts[i + 1]["text"] if i + 1 < len(parts) and parts[i + 1]["op"] == "equal" else ""
        if p["review"] and _is_repeated_word(p, prev, nxt):
            p["review"] = False
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
