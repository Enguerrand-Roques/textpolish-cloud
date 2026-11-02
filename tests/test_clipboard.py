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
    def _run(self, paste_values):
        app_ref = MagicMock()
        with patch.object(clipboard, "get_frontmost_app", return_value=app_ref), \
             patch.object(clipboard, "pyperclip") as mock_pyperclip, \
             patch.object(clipboard, "_kbd") as mock_kbd, \
             patch.object(clipboard, "_snapshot_clipboard", return_value=("text", "orig")) as snap, \
             patch.object(clipboard, "_restore_clipboard") as restore, \
             patch.object(clipboard, "_wait_for_modifiers_released"), \
             patch.object(clipboard.time, "sleep"):
            mock_pyperclip.paste.side_effect = paste_values
            result = clipboard.get_app_and_copy()
        return app_ref, result, mock_pyperclip, mock_kbd, restore

    def test_normal_case_returns_app_and_copied_text(self):
        app_ref, (result_app, text), pyper, kbd, _ = self._run(["selected"])
        assert result_app is app_ref
        assert text == "selected"
        kbd.press.assert_called_once_with("c")
        kbd.release.assert_called_once_with("c")

    def test_clipboard_is_emptied_before_copy(self):
        _, _, pyper, _, _ = self._run(["selected"])
        pyper.copy.assert_called_once_with("")

    def test_waits_until_clipboard_is_filled(self):
        _, (_, text), _, _, _ = self._run(["", "", "slow app text"])
        assert text == "slow app text"

    def test_nothing_selected_returns_empty_string_not_stale_clipboard(self):
        _, (_, text), _, _, _ = self._run([""] * 100)
        assert text == ""

    def test_original_clipboard_is_restored(self):
        _, _, _, _, restore = self._run(["selected"])
        restore.assert_called_once_with(("text", "orig"))

    def test_clipboard_read_error_returns_empty_string_and_restores(self):
        app_ref, (result_app, text), _, _, restore = self._run([Exception("boom")])
        assert result_app is app_ref
        assert text == ""
        restore.assert_called_once()


class TestClipboardSnapshot:
    def test_text_snapshot_round_trip_on_non_mac(self):
        with patch.object(clipboard.sys, "platform", "linux"), \
             patch.object(clipboard, "pyperclip") as pyper:
            pyper.paste.return_value = "hello"
            snap = clipboard._snapshot_clipboard()
            clipboard._restore_clipboard(snap)
        assert snap == ("text", "hello")
        pyper.copy.assert_called_once_with("hello")

    def test_text_snapshot_survives_read_error(self):
        with patch.object(clipboard.sys, "platform", "linux"), \
             patch.object(clipboard, "pyperclip") as pyper:
            pyper.paste.side_effect = Exception("no clipboard")
            assert clipboard._snapshot_clipboard() == ("text", "")


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
             patch.object(clipboard, "_snapshot_clipboard", return_value=("text", "")), \
             patch.object(clipboard, "_restore_clipboard"), \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hello world")

        mock_pyperclip.copy.assert_called_once_with("hello world")

    def test_no_app_ref_falls_back_to_focused_window(self):
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard, "_kbd") as mock_kbd, \
             patch.object(clipboard, "_snapshot_clipboard", return_value=("text", "")), \
             patch.object(clipboard, "_restore_clipboard"), \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hello", app_ref=None)

        mock_kbd.press.assert_called_once_with("v")
        mock_kbd.release.assert_called_once_with("v")

    def test_darwin_dispatches_to_paste_to_pid(self):
        app_ref = MagicMock()
        app_ref.processIdentifier.return_value = 42
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard, "_snapshot_clipboard", return_value=("text", "")), \
             patch.object(clipboard, "_restore_clipboard"), \
             patch.object(clipboard.sys, "platform", "darwin"), \
             patch.object(clipboard, "_paste_to_pid") as mock_paste_pid, \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hi", app_ref)

        mock_paste_pid.assert_called_once_with(42)

    def test_win32_dispatches_to_paste_windows(self):
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard, "_snapshot_clipboard", return_value=("text", "")), \
             patch.object(clipboard, "_restore_clipboard"), \
             patch.object(clipboard.sys, "platform", "win32"), \
             patch.object(clipboard, "_paste_windows") as mock_paste_windows, \
             patch.object(clipboard.time, "sleep"):
            clipboard.paste_text("hi", app_ref=555)

        mock_paste_windows.assert_called_once_with(555)

    def test_clipboard_restored_after_paste_even_if_paste_fails(self):
        with patch.object(clipboard, "pyperclip"), \
             patch.object(clipboard, "_snapshot_clipboard", return_value=("text", "orig")), \
             patch.object(clipboard, "_restore_clipboard") as restore, \
             patch.object(clipboard, "_kbd") as kbd, \
             patch.object(clipboard.time, "sleep"):
            kbd.pressed.side_effect = RuntimeError("keystroke failed")
            try:
                clipboard.paste_text("x", app_ref=None)
            except RuntimeError:
                pass
        restore.assert_called_once_with(("text", "orig"))


class TestWaitForModifiers:
    def test_returns_immediately_off_macos(self):
        with patch.object(clipboard.sys, "platform", "linux"), \
             patch.object(clipboard.time, "sleep") as sleep:
            clipboard._wait_for_modifiers_released()
        sleep.assert_not_called()

    def test_waits_until_modifiers_are_up(self):
        states = iter([0x80000, 0x80000, 0])
        with patch.object(clipboard.sys, "platform", "darwin"), \
             patch.object(clipboard, "CGEventSourceFlagsState", side_effect=lambda _: next(states), create=True), \
             patch.object(clipboard, "kCGEventSourceStateHIDSystemState", 1, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskCommand", 0x100000, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskAlternate", 0x80000, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskShift", 0x20000, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskControl", 0x40000, create=True), \
             patch.object(clipboard.time, "sleep") as sleep:
            clipboard._wait_for_modifiers_released()
        assert sleep.call_count == 2

    def test_gives_up_after_timeout(self):
        with patch.object(clipboard.sys, "platform", "darwin"), \
             patch.object(clipboard, "CGEventSourceFlagsState", return_value=0x80000, create=True), \
             patch.object(clipboard, "kCGEventSourceStateHIDSystemState", 1, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskCommand", 0x100000, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskAlternate", 0x80000, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskShift", 0x20000, create=True), \
             patch.object(clipboard, "kCGEventFlagMaskControl", 0x40000, create=True), \
             patch.object(clipboard.time, "sleep") as sleep:
            clipboard._wait_for_modifiers_released()
        assert sleep.call_count == int(clipboard._RELEASE_TIMEOUT / clipboard._COPY_POLL)
