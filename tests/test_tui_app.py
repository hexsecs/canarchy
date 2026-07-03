"""Integration tests for the full-screen Textual TUI.

These drive the app headlessly with Textual's `App.run_test()` / `Pilot`
harness. Async coroutines are run via `asyncio.run` so no async pytest
plugin is required. The scaffold transport backend gives the live-capture
path a deterministic two-frame stream.
"""

from __future__ import annotations

import asyncio

from textual.widgets import DataTable, Input, RichLog

from canarchy.cli import execute_command
from canarchy.transport import LocalTransport, ScaffoldCanBackend
from canarchy.tui_app import CanarchyTuiApp
from canarchy.tui_capture import CaptureSession


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
