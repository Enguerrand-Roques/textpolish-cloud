"""
Shared test fixtures and setup.

Injects synthetic modules so llm.py can be imported in CI without:
- a real config.py (no GEMINI_API_KEY needed)
- the google-genai SDK installed
"""

import os
import sys
import types as _types

# Add project root to sys.path so `import llm` works in CI
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock

# --- Synthetic config module ---
_config = _types.ModuleType("config")
_config.GEMINI_API_KEY = "test-key"
_config.GEMINI_MODEL = "gemini-2.5-flash-lite"
_config.GEMINI_TIMEOUT = 30
_config.SHORTCUT = "<cmd>+<shift>+p"
sys.modules.setdefault("config", _config)

# --- Synthetic google.genai SDK ---
# llm.py creates `_client = genai.Client(...)` at module level.
# We mock the entire SDK so genai.Client() returns a MagicMock,
# making _client a controllable fake in tests.
_genai_mock = MagicMock()
_types_mock = MagicMock()
_google_mock = MagicMock()
_google_mock.genai = _genai_mock

# google.genai.errors is used in `except errors.ClientError`/`ServerError`
# clauses in llm.py — those need real Exception subclasses, not MagicMocks
# (Python raises TypeError if an except clause target isn't a real
# exception class), so this submodule is stubbed for real rather than
# mocked like the rest of the SDK.
_errors_mock = _types.ModuleType("google.genai.errors")


class _MockAPIError(Exception):
    def __init__(self, code: int = 0, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(f"{code} {message}")


class _MockClientError(_MockAPIError):
    pass


class _MockServerError(_MockAPIError):
    pass


_errors_mock.APIError = _MockAPIError
_errors_mock.ClientError = _MockClientError
_errors_mock.ServerError = _MockServerError
_genai_mock.errors = _errors_mock

sys.modules.setdefault("google", _google_mock)
sys.modules.setdefault("google.genai", _genai_mock)
sys.modules.setdefault("google.genai.types", _types_mock)

# --- Synthetic pynput module ---
# Injects a synthetic `pynput` module so clipboard.py (and anything that
# imports it) can be imported in CI without a real X11/pynput backend —
# clipboard.py instantiates pynput.keyboard.Controller() at import time,
# which would otherwise try to connect to a display on Linux runners.
_pynput_keyboard = _types.ModuleType("pynput.keyboard")


class _FakeKey:
    cmd = "cmd"
    ctrl = "ctrl"


class _FakeController:
    def press(self, key):
        pass

    def release(self, key):
        pass

    def pressed(self, *keys):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield

        return _cm()


_pynput_keyboard.Controller = _FakeController
_pynput_keyboard.Key = _FakeKey

_pynput = _types.ModuleType("pynput")
_pynput.keyboard = _pynput_keyboard

sys.modules.setdefault("pynput", _pynput)
sys.modules.setdefault("pynput.keyboard", _pynput_keyboard)
sys.modules.setdefault("google.genai.errors", _errors_mock)
