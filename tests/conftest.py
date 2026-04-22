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

sys.modules.setdefault("google", _google_mock)
sys.modules.setdefault("google.genai", _genai_mock)
sys.modules.setdefault("google.genai.types", _types_mock)
