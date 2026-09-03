"""Integration tests for the full-screen Textual TUI.

These drive the app headlessly with Textual's `App.run_test()` / `Pilot`
harness. Async coroutines are run via `asyncio.run` so no async pytest
plugin is required. The scaffold transport backend gives the live-capture
path a deterministic two-frame stream.
"""

from __future__ import annotations

import asyncio

from textual.widgets import DataTable, Input, RichLog, Static

from canarchy.cli import execute_command
from canarchy.transport import LocalTransport, ScaffoldCanBackend
from canarchy.tui_app import CanarchyTuiApp
from canarchy.tui_capture import CaptureSession, CaptureStats


def _scaffold_factory(interface: str) -> CaptureSession:
    return CaptureSession(interface, transport=LocalTransport(live_backend=ScaffoldCanBackend()))


def _make_app() -> CanarchyTuiApp:
    return CanarchyTuiApp(execute_command, capture_factory=_scaffold_factory)


def _run(coro) -> None:
    asyncio.run(coro)


async def _submit(app: CanarchyTuiApp, pilot, command: str) -> None:
    app.query_one("#command", Input).value = command
    await pilot.press("enter")
    await pilot.pause()


def test_app_mounts_with_empty_panes() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            for selector in ("#traffic", "#decoded", "#j1939", "#uds"):
                assert app.query_one(selector, DataTable).row_count == 0
            assert app.query_one("#alerts", RichLog) is not None

    _run(scenario())


def test_command_populates_panes() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            assert app.query_one("#j1939", DataTable).row_count >= 1
            assert app.query_one("#traffic", DataTable).row_count >= 1

    _run(scenario())


def test_live_capture_streams_scaffold_frames() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            for _ in range(60):
                await pilot.pause(0.05)
                if app.query_one("#traffic", DataTable).row_count >= 2:
                    break
            assert app.query_one("#traffic", DataTable).row_count == 2
            # Stopping capture tears down the session.
            await _submit(app, pilot, "/stop")
            assert app._capture is None

    _run(scenario())


def test_filter_and_clear_filter() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            baseline = app.query_one("#traffic", DataTable).row_count
            assert baseline >= 1
            await _submit(app, pilot, "/filter traffic zzzznomatch")
            assert app.query_one("#traffic", DataTable).row_count == 0
            await _submit(app, pilot, "/filter traffic")
            assert app.query_one("#traffic", DataTable).row_count == baseline

    _run(scenario())


def test_sort_does_not_lose_rows() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            before = app.query_one("#j1939", DataTable).row_count
            await _submit(app, pilot, "/sort j1939 0")
            assert app.query_one("#j1939", DataTable).row_count == before

    _run(scenario())


def test_clear_resets_panes() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            assert app.query_one("#j1939", DataTable).row_count >= 1
            app.action_clear_panes()
            await pilot.pause()
            assert app.query_one("#j1939", DataTable).row_count == 0
            assert app.query_one("#traffic", DataTable).row_count == 0

    _run(scenario())


def test_backlog_controls_adjust_cap() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            start = app.backlog_cap
            app.action_shrink_backlog()
            assert app.backlog_cap == max(50, start // 2)
            app.action_grow_backlog()
            assert app.backlog_cap == start

    _run(scenario())


def test_pause_toggles_live_feed() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.paused is False
            app.action_toggle_pause()
            assert app.paused is True

    _run(scenario())


def test_active_transmit_command_is_rejected_without_executing() -> None:
    # An active command must never reach execute_command from the TUI: it
    # would block the UI thread on the stdin confirmation prompt.
    calls: list[list[str]] = []

    def spy_execute(argv):
        calls.append(argv)
        return execute_command(argv)

    async def scenario() -> None:
        app = CanarchyTuiApp(spy_execute, capture_factory=_scaffold_factory)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "send can0 0x123 0011 --ack-active")
            assert calls == []  # never dispatched
            assert app.query_one("#traffic", DataTable).row_count == 0
            # A passive command still runs.
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            assert calls  # dispatched

    _run(scenario())


def test_dm1_faults_do_not_crash_ribbon() -> None:
    # DM1 fault summaries contain "[spn=.../fmi=...]"; the J1939 ribbon and
    # bus-status Statics must render that literally, not as console markup.
    import pathlib

    fixture = pathlib.Path("tests/fixtures/j1939_dm1_spn175.candump")

    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, f"j1939 dm1 --file {fixture}")
            # Toggling pause exercises the bracketed "[paused]" status too.
            app.action_toggle_pause()
            await pilot.pause()
            ribbon = app.query_one("#j1939-ribbon", Static).render()
            assert "DM1 active faults" in str(ribbon)

    _run(scenario())


def test_capture_returns_to_idle_when_stream_ends() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            # The scaffold stream is finite (2 frames) — the session should
            # clear itself without an explicit /stop.
            for _ in range(60):
                await pilot.pause(0.05)
                if app._capture is None:
                    break
            assert app._capture is None
            assert app.query_one("#traffic", DataTable).row_count == 2

    _run(scenario())


def test_finished_capture_drains_every_buffered_event() -> None:
    sample = next(LocalTransport(live_backend=ScaffoldCanBackend()).capture_stream_events("vcan0"))

    class _BurstTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            for index in range(1000):
                event = dict(sample)
                event["timestamp"] = float(index)
                yield event

    def burst_factory(interface: str) -> CaptureSession:
        return CaptureSession(interface, transport=_BurstTransport(), maxsize=2000)  # type: ignore[arg-type]

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=burst_factory)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            for _ in range(100):
                await pilot.pause(0.05)
                if app._capture is None:
                    break
            assert app._capture is None
            assert app.query_one("#traffic", DataTable).row_count == 1000

    _run(scenario())


def test_finished_capture_waits_for_resume_before_draining() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_toggle_pause()
            await _submit(app, pilot, "/capture vcan0")
            for _ in range(60):
                await pilot.pause(0.05)
                if app._capture is not None and not app._capture.running:
                    break
            assert app._capture is not None
            assert app._capture.running is False
            assert app.query_one("#traffic", DataTable).row_count == 0

            app.action_toggle_pause()
            for _ in range(60):
                await pilot.pause(0.05)
                if app._capture is None:
                    break
            assert app._capture is None
            assert app.query_one("#traffic", DataTable).row_count == 2

    _run(scenario())


def test_stop_capture_drains_buffered_events_before_release() -> None:
    sample = next(LocalTransport(live_backend=ScaffoldCanBackend()).capture_stream_events("vcan0"))

    class _BufferedTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            for _ in range(600):
                yield dict(sample)
            assert stop_event is not None
            stop_event.wait(1)

    def buffered_factory(interface: str) -> CaptureSession:
        return CaptureSession(
            interface,
            transport=_BufferedTransport(),
            maxsize=1000,  # type: ignore[arg-type]
        )

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=buffered_factory)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            for _ in range(60):
                await pilot.pause(0.01)
                if app._capture is not None and app._capture.stats.received == 600:
                    break
            app.action_stop_capture()
            for _ in range(60):
                await pilot.pause(0.05)
                if app._capture is None:
                    break
            assert app._capture is None
            assert app.query_one("#traffic", DataTable).row_count == 600

    _run(scenario())


def test_capture_queue_loss_is_visible_in_status() -> None:
    sample = next(LocalTransport(live_backend=ScaffoldCanBackend()).capture_stream_events("vcan0"))

    class _OverflowTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            for _ in range(10):
                yield dict(sample)

    def overflow_factory(interface: str) -> CaptureSession:
        return CaptureSession(interface, transport=_OverflowTransport(), maxsize=2)  # type: ignore[arg-type]

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=overflow_factory)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            for _ in range(60):
                await pilot.pause(0.05)
                if app._capture is None:
                    break
            status = str(app.query_one("#bus-status", Static).render())
            assert "received=10" in status
            assert "drained=2" in status
            assert "dropped=8" in status
            assert "high-water=2" in status

    _run(scenario())


def test_capture_replacement_waits_for_previous_worker() -> None:
    class _StubbornCapture:
        def __init__(self, interface: str) -> None:
            self.interface = interface
            self.stats = CaptureStats()
            self.running = True

        def start(self) -> None:
            pass

        def stop(self) -> bool:
            return False

        def errors(self):
            return []

        def drain(self, max_items: int = 256):
            return []

    created: list[_StubbornCapture] = []

    def stubborn_factory(interface: str) -> CaptureSession:
        capture = _StubbornCapture(interface)
        created.append(capture)
        return capture  # type: ignore[return-value]

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=stubborn_factory)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture can0")
            first = app._capture
            await _submit(app, pilot, "/capture can1")
            assert len(created) == 1
            assert app._capture is first
            assert app._capture is not None
            assert app._capture.interface == "can0"

    _run(scenario())
