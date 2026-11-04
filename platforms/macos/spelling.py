"""macOS spell checker as a word list, for diff.needs_review: a fix that
replaces one real word with another is held for review, a typo is not."""

from functools import lru_cache

from AppKit import NSSpellChecker

_LANGUAGES = ("fr", "en")


@lru_cache(maxsize=4096)
def is_word(word: str, lang: str | None = None) -> bool:
    """True if *word* is spelled correctly in *lang* ("fr" or "en"), or in
    either language when *lang* is None. "connection" is English, not French."""
    checker = NSSpellChecker.sharedSpellChecker()
    for lang in ((lang,) if lang else _LANGUAGES):
        result = checker.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            word, 0, lang, False, 0, None)
        misspelled = result[0] if isinstance(result, tuple) else result
        if misspelled.length == 0:
            return True
    return False
