"""Guess whether a text is French or English, without a model. Used to tell
the model which language to answer in, and to check words in the right
dictionary (diff.needs_review)."""

import re

_FRENCH_CHARS = set("éèêëàâùûüîïôœæç")
_FRENCH_STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "au", "aux",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "que", "qui", "ne", "pas", "sur", "par", "pour", "avec", "dans", "chez",
    "ce", "ça", "ca", "est", "ai", "as", "suis", "es", "sont", "mais", "ou", "donc",
    "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses", "moi", "toi",
    "très", "tres", "bien", "plus", "tout", "rien", "hier", "demain", "soir",
    "merci", "bonjour", "salut", "slt", "oui", "non", "quoi", "peux", "veux",
}
# Common English words. Some French stop words ("on", "as", "son"…) are also
# English, so French must outnumber English instead of just being present.
_ENGLISH_STOP_WORDS = {
    # not "a": in French it is a verb ("on a fini")
    "the", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "from", "by", "as", "is", "are", "was", "were", "be", "been",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your", "our",
    "this", "that", "there", "here", "will", "would", "can", "could", "have",
    "has", "had", "do", "does", "did", "not", "no", "yes", "if", "so", "what",
    "when", "time", "today", "tomorrow", "thanks", "hello", "hi", "please",
}
# Split on apostrophes too, so "j'ai" counts as "j" + "ai".
_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def _detect_language(text: str) -> str:
    """Return 'fr' if the text is likely French, 'en' otherwise.

    Uses two signals in order of priority:
    1. French-specific accented characters (é, è, ç, œ…) — very reliable.
    2. French stop words, when at least two appear and they outnumber English
       ones — catches unaccented French without flagging "on time as usual".
    """
    if any(c in _FRENCH_CHARS for c in text.lower()):
        return "fr"
    words = set(_WORD_RE.findall(text.lower()))
    french = len(words & _FRENCH_STOP_WORDS)
    if french >= 2 and french > len(words & _ENGLISH_STOP_WORDS):
        return "fr"
    return "en"


detect_language = _detect_language
