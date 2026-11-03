"""Threading pattern for running a text-polish request, shared between the
macOS and Windows UIs. No PyObjC/Qt dependency — the caller supplies a
main-thread dispatcher and the polish function to call.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

StatusStep = tuple[float, str]
MainThreadDispatcher = Callable[[Callable[[], None]], None]

_TICK_SECONDS = 0.35


def _status_message_for_elapsed(elapsed: float, steps: list[StatusStep]) -> str:
    label = steps[-1][1]
    for threshold, lbl in steps:
        if elapsed < threshold:
            label = lbl
            break
    dots = "." * ((int(elapsed * 3) % 3) + 1)
    return label + dots


class PolishJobRunner:
    """One instance per panel. Owns the job-id counters that supersede
    stale status/stream updates when a new correction starts."""

    def __init__(self, on_main: MainThreadDispatcher):
        self._on_main = on_main
        self._status_job = 0
        self._stream_job = 0

    def start(
        self,
        text: str,
        mode: str,
        custom_prompt: str | None,
        *,
        polish_fn: Callable[..., str],
        on_stream_start: Callable[[], None],
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
        status_steps: list[StatusStep] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> None:
        """Run *polish_fn* on a worker thread. Status messages (if
        *status_steps* is given) and tokens are delivered on the main thread,
        and dropped once a newer job has started."""
        self._status_job += 1
        job_id = self._status_job
        self._stream_job = job_id
        streaming_started = {"v": False}

        def status_worker():
            start = time.monotonic()
            last = None
            while job_id == self._status_job:
                msg = _status_message_for_elapsed(time.monotonic() - start, status_steps)
                if msg != last:
                    self._on_main(lambda m=msg, jid=job_id: self._emit_status(jid, m, on_status))
                    last = msg
                time.sleep(_TICK_SECONDS)

        def handle_token(token: str):
            self._on_main(
                lambda t=token, jid=job_id: self._emit_token(
                    jid, t, streaming_started, on_stream_start, on_token
                )
            )

        def worker():
            try:
                result = polish_fn(text, mode, custom_prompt, on_token=handle_token)
                self._on_main(lambda r=result, jid=job_id: self._finish(on_success, r, jid))
            except Exception as exc:
                self._on_main(lambda e=exc, jid=job_id: self._finish(on_error, str(e), jid))

        if status_steps and on_status:
            threading.Thread(target=status_worker, daemon=True).start()
        threading.Thread(target=worker, daemon=True).start()

    def _emit_status(self, job_id, message, on_status):
        if job_id == self._status_job:
            on_status(message)

    def _emit_token(self, job_id, token, streaming_started, on_stream_start, on_token):
        if job_id != self._stream_job:
            return
        if not streaming_started["v"]:
            streaming_started["v"] = True
            self._status_job += 1
            on_stream_start()
        if on_token:
            on_token(token)

    def _finish(self, callback, arg, job_id=None):
        # A newer job superseded this one: drop its result instead of letting
        # it overwrite the current correction.
        if job_id is not None and job_id != self._stream_job:
            return
        self._status_job += 1
        callback(arg)
