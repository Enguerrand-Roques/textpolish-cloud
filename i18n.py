"""
User-facing strings on the Python side (menu bar, preferences, history,
fix labels), in English and French. The popup (panel.html) has its own copy
of the same wording; both follow UI_LANGUAGE from config.py ("en" by default).
"""

try:
    from config import UI_LANGUAGE
except ImportError:
    UI_LANGUAGE = "en"

LANGUAGES = {"en": "English", "fr": "Français"}  # each shown in its own language
LANG = UI_LANGUAGE if UI_LANGUAGE in LANGUAGES else "en"

STRINGS = {
    "en": {
        "mode_casual": "Correction",
        "mode_pro": "Pro",
        "mode_custom": "Custom",
        "kind_accent": "Accent",
        "kind_case": "Capitalization",
        "kind_punctuation": "Punctuation",
        "kind_spelling": "Spelling",
        "kind_agreement": "Agreement",
        "kind_conjugation": "Conjugation",
        "kind_grammar": "Grammar",
        "kind_rewrite": "Rewrite",
        "menu_prefs": "Preferences…",
        "menu_history": "History",
        "menu_empty": "No corrections yet",
        "menu_quit": "Quit TextPolish",
        "menu_language": "Language",
        "history_tip": "Click to copy the corrected text",
        "prefs_title": "Preferences",
        "prefs_label": "Keyboard shortcut (pynput format, e.g. <cmd>+<alt>+g):",
        "cancel": "Cancel",
        "save": "Save",
    },
    "fr": {
        "mode_casual": "Correction",
        "mode_pro": "Pro",
        "mode_custom": "Sur mesure",
        "kind_accent": "Accent",
        "kind_case": "Majuscule",
        "kind_punctuation": "Ponctuation",
        "kind_spelling": "Orthographe",
        "kind_agreement": "Accord",
        "kind_conjugation": "Conjugaison",
        "kind_grammar": "Grammaire",
        "kind_rewrite": "Reformulation",
        "menu_prefs": "Préférences…",
        "menu_history": "Historique",
        "menu_empty": "Aucune correction pour l'instant",
        "menu_quit": "Quitter TextPolish",
        "menu_language": "Langue",
        "history_tip": "Cliquer pour copier le texte corrigé",
        "prefs_title": "Préférences",
        "prefs_label": "Raccourci clavier (format pynput, ex. <cmd>+<alt>+g) :",
        "cancel": "Annuler",
        "save": "Enregistrer",
    },
}


def t(key: str, lang: str | None = None) -> str:
    return STRINGS[lang or LANG][key]


def set_language(lang: str) -> None:
    """Switch the interface language for the running app (menu → Language)."""
    global LANG
    if lang in LANGUAGES:
        LANG = lang
