"""LanguageTool as a second, rule-based pass after the model (Correction mode).

LanguageTool (open source, LGPL) checks text against thousands of grammar
rules written by linguists ("si" + conditional, "quant à", their/there…). It
runs here as a local server, so nothing leaves the Mac. Its rules never
rewrite a sentence: they replace one span with a suggestion, which makes them
a safe complement to a model that can.

Optional: if LanguageTool or Java is missing (`brew install languagetool`),
every function returns the text unchanged and the app works as before.
"""

from __future__ import annotations

import atexit
import glob
import logging
import os
import subprocess
import threading
import time

import requests

PORT = int(os.environ.get("TEXTPOLISH_LT_PORT", "8081"))
_URL = f"http://localhost:{PORT}/v2"
_TIMEOUT = 2.0  # seconds per check; past that the correction goes on without it

# Rule categories trusted to fix without asking (one suggestion only).
# Left out: spelling (the model handles it, and LanguageTool flags informal
# words), typography (French spaces before "?"), style, casing, punctuation.
SAFE_CATEGORIES = {
    "fr": {"CAT_GRAMMAIRE", "CAT_HOMONYMES_PARONYMES"},
    "en": {"GRAMMAR", "CONFUSED_WORDS"},
}
_LANG_CODES = {"fr": "fr", "en": "en-US"}
# Rules that correct the register, not a mistake: informal French drops the
# "ne" of negation ("j'ai pas") and the "il" of "il faut". TextPolish keeps
# how the user writes, so these never run.
DISABLED_RULES = {"fr": ["P_V_PAS", "IL_FAUT"], "en": []}

# The server rebuilds its French pipeline (dictionary included) on every
# request unless pipelines are cached: ~700 ms instead of ~15 ms per check.
_PROPERTIES = "pipelineCaching=true\nmaxPipelinePoolSize=4\npipelineExpireTimeInSeconds=3600\n"

_server: subprocess.Popen | None = None
_lock = threading.Lock()


def _find(patterns: list[str]) -> str | None:
    for pattern in patterns:
        found = sorted(glob.glob(os.path.expanduser(pattern)))
        if found:
            return found[-1]
    return None


def _java() -> str | None:
    home = os.environ.get("JAVA_HOME")
    return _find(([f"{home}/bin/java"] if home else []) + [
        "/opt/homebrew/opt/openjdk*/libexec/openjdk.jdk/Contents/Home/bin/java",
        "/usr/local/opt/openjdk*/libexec/openjdk.jdk/Contents/Home/bin/java",
    ])


def _jar() -> str | None:
    return _find([
        "/opt/homebrew/Cellar/languagetool/*/libexec/languagetool-server.jar",
        "/usr/local/Cellar/languagetool/*/libexec/languagetool-server.jar",
    ])


def installed() -> bool:
    return _java() is not None and _jar() is not None


def _ready() -> bool:
    try:
        return requests.get(f"{_URL}/languages", timeout=0.5).ok
    except requests.RequestException:
        return False


def start() -> bool:
    """Start the local server if needed (or reuse one already listening).
    Returns True once it answers."""
    global _server
    with _lock:
        if _ready():
            return True
        if not installed():
            return False
        if _server is None or _server.poll() is not None:
            cache = os.path.expanduser("~/Library/Caches/TextPolish")
            os.makedirs(cache, exist_ok=True)
            props = os.path.join(cache, "languagetool.properties")
            with open(props, "w") as f:
                f.write(_PROPERTIES)
            log = open(os.path.join(cache, "languagetool.log"), "w")
            _server = subprocess.Popen(
                [_java(), "-Xmx512m", "-XX:+UseSerialGC", "-cp", _jar(),
                 "org.languagetool.server.HTTPServer", "--port", str(PORT), "--config", props],
                stdout=log, stderr=subprocess.STDOUT)
            atexit.register(stop)
        for _ in range(100):  # up to 10 s
            if _ready():
                return True
            time.sleep(0.1)
        return False


def stop() -> None:
    if _server is not None and _server.poll() is None:
        _server.terminate()


def warm_up() -> None:
    """Start the server and build the French and English pipelines in the
    background: the first check of a language takes 1.5-3 s, later ones ~15 ms."""
    def run():
        if start():
            for lang, text in (("fr", "Bonjour à tous."), ("en", "Hello everyone.")):
                check(text, lang)
    threading.Thread(target=run, daemon=True).start()


def check(text: str, lang: str) -> list[dict]:
    """LanguageTool matches for *text* ("fr" or "en"), or [] if unavailable."""
    try:
        data = {"text": text, "language": _LANG_CODES[lang]}
        if DISABLED_RULES[lang]:
            data["disabledRules"] = ",".join(DISABLED_RULES[lang])
        response = requests.post(f"{_URL}/check", timeout=_TIMEOUT, data=data)
        response.raise_for_status()
        return response.json().get("matches", [])
    except (requests.RequestException, ValueError, KeyError) as e:
        logging.debug("LanguageTool unavailable: %s", e)
        return []


def safe_fixes(text: str, lang: str) -> list[tuple[int, int, str]]:
    """(offset, length, replacement) for the matches trusted to apply: a safe
    category and exactly one suggestion, which is a real replacement (some
    rules return a hint such as "(délicieuses)", meaning "check this")."""
    fixes = []
    for m in check(text, lang):
        replacements = m.get("replacements") or []
        category = m.get("rule", {}).get("category", {}).get("id")
        if category in SAFE_CATEGORIES[lang] and len(replacements) == 1:
            value = replacements[0]["value"]
            if not any(c in value for c in "()[]"):
                fixes.append((m["offset"], m["length"], value))
    return fixes


def improve(text: str, lang: str) -> tuple[str, list[tuple[int, int]]]:
    """Apply the safe fixes to *text* (the model's correction). Returns the new
    text and the character ranges LanguageTool rewrote in it, so that
    diff.group_changes applies those fixes by default instead of holding them."""
    out, ranges, pos, shift = [], [], 0, 0
    for offset, length, value in sorted(safe_fixes(text, lang)):
        if offset < pos or text[offset:offset + length] == value:
            continue  # overlaps the previous fix, or changes nothing
        out.append(text[pos:offset] + value)
        start = offset + shift
        ranges.append((start, start + len(value)))
        shift += len(value) - length
        pos = offset + length
    out.append(text[pos:])
    return "".join(out), ranges
