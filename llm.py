"""
Google Gemini cloud backend — sends text to Gemini and returns the polished version.
"""

import os
import logging
from google import genai
from google.genai import types
from google.genai import errors
from config import GEMINI_API_KEY, GEMINI_MODEL
from diff import keep_sentence_marks

try:
    from config import GEMINI_TIMEOUT
except ImportError:
    GEMINI_TIMEOUT = 30  # seconds

# Long inputs are slow and costly on the free tier; the popup shows this
# error instead of hanging.
MAX_INPUT_CHARS = 4000

# Correction should give the same fix every time; rewrites keep a little variety.
_TEMPERATURE = {"casual": 0.0, "pro": 0.4, "custom": 0.4}

# The SDK logs every request at INFO; keep the app log to our own lines.
for _name in ("httpx", "google_genai"):
    logging.getLogger(_name).setLevel(logging.WARNING)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

_client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(
        api_version="v1",
        timeout=GEMINI_TIMEOUT * 1000,  # HttpOptions.timeout is in milliseconds
    ),
)


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def polish_text(
    text: str,
    mode: str = "pro",
    custom_prompt: str | None = None,
    on_token=None,
) -> str:
    """
    Send *text* to Gemini and return the corrected version.

    Args:
        text:          The raw text to polish.
        mode:          "pro" | "casual" — selects the matching prompt file.
        custom_prompt: If provided, applied through the custom prompt template.
        on_token:      Optional callback(token: str) called for each streamed
                       token. When provided, streaming mode is used. The full
                       result is still returned at the end.

    Returns:
        The polished text string.
    """
    if not text.strip():
        return text

    if len(text) > MAX_INPUT_CHARS:
        raise RuntimeError(
            f"Text too long ({len(text)} characters, max {MAX_INPUT_CHARS}). "
            "Select a shorter passage."
        )

    prompt_name = "custom" if custom_prompt else mode
    system = _load_prompt(prompt_name)

    if custom_prompt:
        user_message = (
            f"{system}\n\n"
            "Custom instruction to apply:\n"
            f"{custom_prompt.strip()}\n\n"
            "Text to rewrite:\n"
            f"{text}"
        )
    else:
        user_message = f"{system}\n\nText to rewrite:\n{text}"

    logging.debug("Calling Gemini | model=%s | mode=%s | %d chars | stream=%s",
                  GEMINI_MODEL, mode, len(text), on_token is not None)

    config = types.GenerateContentConfig(temperature=_TEMPERATURE.get(mode, 0.4))

    try:
        if on_token is not None:
            parts: list[str] = []
            for chunk in _client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=user_message,
                config=config,
            ):
                token = chunk.text or ""
                if token:
                    on_token(token)
                    parts.append(token)
            result = "".join(parts).strip()
        else:
            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_message,
                config=config,
            )
            result = response.text.strip()
    except errors.ClientError as e:
        if e.code == 429 and "PerMinute" in str(e):
            raise RuntimeError(
                "Too many requests in one minute (Gemini free tier allows 10). "
                "Wait a few seconds and try again."
            )
        if e.code == 429:
            raise RuntimeError(
                "Gemini quota exceeded for today. Free tier resets daily — "
                "try again later, or check your usage at https://aistudio.google.com"
            )
        if e.code in (401, 403):
            raise RuntimeError(
                "Gemini rejected the API key. Check GEMINI_API_KEY in config.py — "
                "get a new one at https://aistudio.google.com"
            )
        raise RuntimeError(f"Gemini request failed ({e.code}): {e.message}")
    except errors.ServerError as e:
        raise RuntimeError(
            f"Gemini is having issues on their end ({e.code}). Try again shortly."
        )

    # Models sometimes wrap the words they changed in Markdown bold.
    if "**" not in text:
        result = result.replace("**", "")
    if "__" not in text:
        result = result.replace("__", "")

    # Correction must not remove a question or exclamation (same rule as
    # the local version, where the model kept merging "soir ? on peut").
    if mode == "casual":
        result = keep_sentence_marks(text, result)

    logging.debug("Response received — %d chars", len(result))
    return result
