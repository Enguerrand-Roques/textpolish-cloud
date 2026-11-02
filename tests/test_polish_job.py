import threading

from polish_job import PolishJobRunner, _status_message_for_elapsed

_STEPS = [(1.0, "A"), (3.0, "B"), (9999.0, "C")]


class TestStatusMessageForElapsed:
    def test_before_first_threshold(self):
        assert _status_message_for_elapsed(0.5, _STEPS) == "A.."

    def test_between_thresholds(self):
        assert _status_message_for_elapsed(1.5, _STEPS) == "B.."

    def test_after_last_named_threshold_falls_back_to_last_label(self):
        assert _status_message_for_elapsed(5.0, _STEPS) == "C."

    def test_dots_cycle_through_1_2_3(self):
        dots = [_status_message_for_elapsed(t, _STEPS)[-3:].count(".") for t in (0.0, 0.34, 0.67)]
        assert dots == [1, 2, 3]


class TestEmitStatus:
    def test_calls_callback_when_job_is_current(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._status_job = 5
        calls = []
        runner._emit_status(5, "msg", calls.append)
        assert calls == ["msg"]

    def test_ignored_when_job_is_stale(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._status_job = 6
        calls = []
        runner._emit_status(5, "msg", calls.append)
        assert calls == []


class TestEmitToken:
    def test_ignored_when_stream_job_is_stale(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._stream_job = 6
        started = {"v": False}
        stream_start_calls, token_calls = [], []
        runner._emit_token(5, "tok", started, lambda: stream_start_calls.append(1), token_calls.append)
        assert stream_start_calls == []
        assert token_calls == []

    def test_calls_stream_start_once_then_forwards_tokens(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._status_job = 3
        runner._stream_job = 3
        started = {"v": False}
        stream_start_calls, token_calls = [], []
        runner._emit_token(3, "a", started, lambda: stream_start_calls.append(1), token_calls.append)
        runner._emit_token(3, "b", started, lambda: stream_start_calls.append(1), token_calls.append)
        assert stream_start_calls == [1]
        assert token_calls == ["a", "b"]
        assert runner._status_job == 4


class TestFinish:
    def test_increments_status_job_and_calls_callback(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._status_job = 2
        calls = []
        runner._finish(calls.append, "result")
        assert calls == ["result"]
        assert runner._status_job == 3


class TestStartIntegration:
    def test_success_path_calls_on_success_with_result(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        done = threading.Event()
        results = []

        def fake_polish_fn(text, mode, custom_prompt, on_token):
            on_token("chunk1")
            on_token("chunk2")
            return "final result"

        def on_success(result):
            results.append(result)
            done.set()

        runner.start(
            "hello", "casual", None,
            status_steps=[(1.0, "A")],
            polish_fn=fake_polish_fn,
            on_status=lambda m: None,
            on_stream_start=lambda: None,
            on_token=lambda t: None,
            on_success=on_success,
            on_error=lambda e: None,
        )

        assert done.wait(timeout=2)
        assert results == ["final result"]

    def test_error_path_calls_on_error_with_message(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        done = threading.Event()
        errors = []

        def failing_polish_fn(text, mode, custom_prompt, on_token):
            raise RuntimeError("boom")

        def on_error(message):
            errors.append(message)
            done.set()

        runner.start(
            "hello", "casual", None,
            status_steps=[(1.0, "A")],
            polish_fn=failing_polish_fn,
            on_status=lambda m: None,
            on_stream_start=lambda: None,
            on_token=lambda t: None,
            on_success=lambda r: None,
            on_error=on_error,
        )

        assert done.wait(timeout=2)
        assert errors == ["boom"]


class TestStaleJobs:
    def test_finish_ignores_superseded_job(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._stream_job = 2
        calls = []
        runner._finish(calls.append, "old result", job_id=1)
        assert calls == []

    def test_finish_accepts_current_job(self):
        runner = PolishJobRunner(on_main=lambda fn: fn())
        runner._stream_job = 2
        calls = []
        runner._finish(calls.append, "result", job_id=2)
        assert calls == ["result"]
