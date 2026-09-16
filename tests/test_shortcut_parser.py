import pytest

from platforms.macos.shortcut_parser import KEY_CODES, MODIFIER_MAP, parse_shortcut


class TestParseShortcut:
    def test_single_modifier_and_key(self):
        mods, keycode = parse_shortcut("<cmd>+g")
        assert mods == MODIFIER_MAP["cmd"]
        assert keycode == KEY_CODES["g"]

    def test_multiple_modifiers_combine_with_bitwise_or(self):
        mods, _ = parse_shortcut("<cmd>+<shift>+p")
        assert mods == MODIFIER_MAP["cmd"] | MODIFIER_MAP["shift"]

    def test_option_is_alias_for_alt(self):
        mods_alt, _ = parse_shortcut("<alt>+g")
        mods_option, _ = parse_shortcut("<option>+g")
        assert mods_alt == mods_option == MODIFIER_MAP["alt"]

    def test_case_insensitive(self):
        mods, keycode = parse_shortcut("<CMD>+<Alt>+G")
        assert mods == MODIFIER_MAP["cmd"] | MODIFIER_MAP["alt"]
        assert keycode == KEY_CODES["g"]

    def test_unrecognised_key_raises_value_error(self):
        with pytest.raises(ValueError, match="Unrecognised key"):
            parse_shortcut("<cmd>+1")

    def test_missing_main_key_raises_value_error(self):
        with pytest.raises(ValueError, match="No main key found"):
            parse_shortcut("<cmd>+<shift>")

    def test_all_26_letters_covered(self):
        import string
        for letter in string.ascii_lowercase:
            mods, keycode = parse_shortcut(f"<cmd>+{letter}")
            assert keycode == KEY_CODES[letter]
