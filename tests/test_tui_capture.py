"""Unit tests for the TUI background capture session.

These exercise `CaptureSession` against the deterministic scaffold
transport backend (which yields exactly two canned frames and then ends)
so the streaming path is testable without a terminal or real hardware.
"""

from __future__ import annotations

import threading
import time

from canarchy.transport import LocalTransport, ScaffoldCanBackend
from canarchy.tui_capture import CaptureError, CaptureSession


def _scaffold_transport() -> LocalTransport:
    """A LocalTransport pinned to the deterministic scaffold backend."""

    return LocalTransport(live_backend=ScaffoldCanBackend())


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_capture_session_streams_scaffold_frames() -> None:
    session = CaptureSession("vcan0", transport=_scaffold_transport())
    session.start()

    # The scaffold backend yields two frames then the generator ends.
    assert _wait_until(lambda: not session.running)

    events: list[dict[str, object]] = []
    events.extend(session.drain())
    assert len(events) == 2
    assert all(event.get("event_type") == "frame" for event in events)
    session.stop()


def test_capture_session_stop_is_safe_before_completion() -> None:
    session = CaptureSession("vcan0", transport=_scaffold_transport())
    session.start()
    session.stop()
    # Draining after stop must not raise and yields at most the buffered frames.
    drained = session.drain()
    assert isinstance(drained, list)


def test_capture_session_reports_transport_errors() -> None:
    class _BoomTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            from canarchy.transport import TransportError

            raise TransportError("CAPTURE_SOURCE_UNAVAILABLE", "boom", "check it")
            yield  # pragma: no cover - marks this a generator

    session = CaptureSession("vcan0", transport=_BoomTransport())  # type: ignore[arg-type]
    session.start()
    assert _wait_until(lambda: not session.running)
    errors = session.errors()
    assert errors == [CaptureError("CAPTURE_SOURCE_UNAVAILABLE", "boom", "check it")]


def test_capture_session_reports_queue_overflow_telemetry() -> None:
    class _BurstTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            for index in range(5):
                yield {"event_type": "frame", "timestamp": float(index), "payload": {}}

    session = CaptureSession("vcan0", transport=_BurstTransport(), maxsize=2)  # type: ignore[arg-type]
    session.start()
    assert _wait_until(lambda: not session.running)

    before = session.stats
    assert before.received == 5
    assert before.drained == 0
    assert before.dropped == 3
    assert before.queue_depth == 2
    assert before.high_water_mark == 2

    assert len(session.drain()) == 2
    after = session.stats
    assert after.drained == 2
    assert after.queue_depth == 0


def test_capture_session_stop_waits_for_worker_exit() -> None:
    class _IdleTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            assert stop_event is not None
            while not stop_event.wait(0.01):
                pass
            return
            yield  # pragma: no cover - marks this a generator

    session = CaptureSession("vcan0", transport=_IdleTransport())  # type: ignore[arg-type]
    session.start()

    assert session.stop(join_timeout=0.25) is True
    assert session.running is False


def test_capture_session_reports_stop_timeout_once() -> None:
    release = threading.Event()

    class _StubbornTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            release.wait(1)
            return
            yield  # pragma: no cover - marks this a generator

    session = CaptureSession("vcan0", transport=_StubbornTransport())  # type: ignore[arg-type]
    session.start()

    assert session.stop(join_timeout=0.01) is False
    errors = session.errors()
    assert len(errors) == 1
    assert errors[0].code == "CAPTURE_STOP_TIMEOUT"
    assert session.stop(join_timeout=0.01) is False
    assert session.errors() == []

    release.set()
    assert _wait_until(lambda: not session.running)
