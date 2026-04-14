"""
Unit tests for llm.py — no Gemini API key required (SDK is mocked).
"""

import pytest
from unittest.mock import patch, MagicMock

import llm
from llm import _load_prompt, polish_text


# ---------------------------------------------------------------------------
# _load_prompt
# ---------------------------------------------------------------------------

class TestLoadPrompt:
    def test_load_pro_contains_professional(self):
        prompt = _load_prompt("pro")
        assert "professional" in prompt.lower()

    def test_load_casual_is_non_empty(self):
        prompt = _load_prompt("casual")
        assert len(prompt) > 20

    def test_load_custom_is_non_empty(self):
        prompt = _load_prompt("custom")
        assert len(prompt) > 20

    def test_missing_prompt_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            _load_prompt("nonexistent_prompt_xyz")


# ---------------------------------------------------------------------------
# polish_text
# ---------------------------------------------------------------------------

class TestPolishText:
    def test_empty_text_skips_gemini(self):
        with patch.object(llm._client.models, "generate_content") as mock_gen:
            result = polish_text("   ")
            mock_gen.assert_not_called()
            assert result == "   "

    def test_successful_response_returns_text(self):
        mock_response = MagicMock()
        mock_response.text = "  Hello, world!  "
        with patch.object(llm._client.models, "generate_content", return_value=mock_response):
            assert polish_text("Hello world", mode="casual") == "Hello, world!"

    def test_pro_mode_uses_pro_prompt(self):
        mock_response = MagicMock()
        mock_response.text = "Polished."
        with patch.object(llm._client.models, "generate_content", return_value=mock_response) as mock_gen:
            polish_text("hello", mode="pro")
            call_args = mock_gen.call_args
            contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
            pro_prompt = _load_prompt("pro")
            assert pro_prompt[:30] in contents

    def test_custom_prompt_included_in_request(self):
        mock_response = MagicMock()
        mock_response.text = "Result."
        with patch.object(llm._client.models, "generate_content", return_value=mock_response) as mock_gen:
            polish_text("some text", mode="custom", custom_prompt="Make it shorter")
            call_args = mock_gen.call_args
            contents = call_args.kwargs.get("contents") or call_args[1].get("contents")
            assert "Make it shorter" in contents

    def test_gemini_exception_propagates(self):
        with patch.object(llm._client.models, "generate_content", side_effect=Exception("API error")):
            with pytest.raises(Exception, match="API error"):
                polish_text("Hello", mode="pro")

    def test_whitespace_only_text_returned_as_is(self):
        result = polish_text("\n\t  ")
        assert result == "\n\t  "
