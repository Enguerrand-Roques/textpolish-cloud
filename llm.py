"""
Google Gemini cloud backend — sends text to Gemini and returns the polished version.
"""

import os
import logging
from google import genai
from google.genai import types
from google.genai import errors
from config import GEMINI_API_KEY, GEMINI_MODEL

try:
    from config import GEMINI_TIMEOUT
except ImportError:
    GEMINI_TIMEOUT = 30  # seconds

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

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

    try:
        if on_token is not None:
            parts: list[str] = []
            for chunk in _client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=user_message,
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
            )
            result = response.text.strip()
    except errors.ClientError as e:
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

    logging.debug("Response received — %d chars", len(result))
    return result
