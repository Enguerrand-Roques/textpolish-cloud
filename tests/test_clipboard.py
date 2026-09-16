"""
Tests for clipboard.py.

All platform-specific names (NSWorkspace, ctypes, CGEvent*) are patched with
create=True since clipboard.py only binds them under an `if sys.platform ==
...` guard at import time — on CI (Linux) none of them exist as module
attributes, so tests inject them regardless of the host OS running the
suite. `clipboard.sys.platform` is patched to force a specific branch
independently of the real host platform.
"""

from unittest.mock import MagicMock, call, patch

import clipboard


class TestGetFrontmostApp:
    def test_darwin_branch_returns_frontmost_application(self):
        fake_app = object()
        fake_workspace = MagicMock()
        fake_workspace.sharedWorkspace.return_value.frontmostApplication.return_value = fake_app
        with patch.object(clipboard.sys, "platform", "darwin"), \
             patch.object(clipboard, "NSWorkspace", fake_workspace, create=True):
            result = clipboard.get_frontmost_app()
        assert result is fake_app

    def test_win32_branch_returns_foreground_window(self):
        fake_ctypes = MagicMock()
        fake_ctypes.windll.user32.GetForegroundWindow.return_value = 777
        with patch.object(clipboard.sys, "platform", "win32"), \
             patch.object(clipboard, "ctypes", fake_ctypes, create=True):
            result = clipboard.get_frontmost_app()
        assert result == 777

    def test_other_platform_returns_none(self):
        with patch.object(clipboard.sys, "platform", "linux"):
            result = clipboard.get_frontmost_app()
        assert result is None


class TestGetAppAndCopy:
    def test_normal_case_returns_app_and_new_clipboard_text(self):
        app_ref = MagicMock()
        with patch.object(clipboard, "get_frontmost_app", return_value=app_ref), \
             patch.object(clipboard, "pyperclip") as mock_pyperclip, \
             patch.object(clipboard, "_kbd") as mock_kbd, \
             patch.object(clipboard.time, "sleep"):
            mock_pyperclip.paste.side_effect = ["before", "after"]
            result_app, text = clipboard.get_app_and_copy()

        assert result_app is app_ref
        assert text == "after"
        mock_kbd.press.assert_called_once_with("c")
        mock_kbd.release.assert_called_once_with("c")

    def test_clipboard_unchanged_still_returns_the_text(self):
        app_ref = MagicMock()
        with patch.object(clipboard, "get_frontmost_app", return_value=app_ref), \
             patch.object(clipboard, "pyperclip") as mock_pyperclip, \
             patch.object(clipboard, "_kbd"), \
             patch.object(clipboard.time, "sleep"):
            mock_pyperclip.paste.side_effect = ["same", "same"]
            _, text = clipboard.get_app_and_copy()

        assert text == "same"

    def test_clipboard_read_error_returns_empty_string(self):
        app_ref = MagicMock()
        with patch.object(clipboard, "get_frontmost_app", return_value=app_ref), \
             patch.object(clipboard, "pyperclip") as mock_pyperclip, \
             patch.object(clipboard, "_kbd"), \
             patch.object(clipboard.time, "sleep"):
            mock_pyperclip.paste.side_effect = ["before", Exception("boom")]
            result_app, text = clipboard.get_app_and_copy()

        assert result_app is app_ref
        assert text == ""


class TestPasteToPid:
    def test_sends_key_down_then_key_up_with_command_flag(self):
        with patch.object(clipboard, "CGEventCreateKeyboardEvent", create=True) as mock_create, \
             patch.object(clipboard, "CGEventSetFlags", create=True) as mock_set_flags, \
             patch.object(clipboard, "CGEventPostToPid", create=True) as mock_post, \
             patch.object(clipboard, "kCGEventFlagMaskCommand", 0x100000, create=True), \
             patch.object(clipboard.time, "sleep"):
            mock_create.side_effect = ["event_down", "event_up"]
            clipboard._paste_to_pid(1234)

        assert mock_create.call_args_list == [
            call(None, clipboard._KEYCODE_V, True),
            call(None, clipboard._KEYCODE_V, False),
        ]
        assert mock_set_flags.call_args_list == [
            call("event_down", 0x100000),
            call("event_up", 0x100000),
        ]
        assert mock_post.call_args_list == [
            call(1234, "event_down"),
            call(1234, "event_up"),
        ]


class TestPasteWindows:
    def test_restores_focus_before_sending_ctrl_v(self):
        fake_ctypes = MagicMock()
        with patch.object(clipboard, "ctypes", fake_ctypes, create=True), \
             patch.object(clipboard, "_kbd") as mock_kbd, \
             patch.object(clipboard.time, "sleep"):
            clipboard._paste_windows(999)

        user32 = fake_ctypes.windll.user32
        assert user32.method_calls[0] == call.ShowWindow(999, 9)
        assert user32.method_calls[1] == call.SetForegroundWindow(999)
        mock_kbd.press.assert_called_once_with("v")
        mock_kbd.release.assert_called_once_with("v")


class TestPasteText:
    def test_always_copies_to_clipboard_first(self):
        with patch.object(clipboard, "pyperclip") as mock_pyperclip, \
             patch.object(clipboard, "_kbd"), \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hello world")

        mock_pyperclip.copy.assert_called_once_with("hello world")

    def test_no_app_ref_falls_back_to_focused_window(self):
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard, "_kbd") as mock_kbd, \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hello", app_ref=None)

        mock_kbd.press.assert_called_once_with("v")
        mock_kbd.release.assert_called_once_with("v")

    def test_darwin_dispatches_to_paste_to_pid(self):
        app_ref = MagicMock()
        app_ref.processIdentifier.return_value = 42
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard.sys, "platform", "darwin"), \
             patch.object(clipboard, "_paste_to_pid") as mock_paste_pid, \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hi", app_ref)

        mock_paste_pid.assert_called_once_with(42)

    def test_win32_dispatches_to_paste_windows(self):
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard.sys, "platform", "win32"), \
             patch.object(clipboard, "_paste_windows") as mock_paste_windows, \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hi", app_ref=555)

        mock_paste_windows.assert_called_once_with(555)
