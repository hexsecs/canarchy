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
