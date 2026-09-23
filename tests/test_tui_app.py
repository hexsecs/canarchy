"""Integration tests for the full-screen Textual TUI.

These drive the app headlessly with Textual's `App.run_test()` / `Pilot`
harness. Async coroutines are run via `asyncio.run` so no async pytest
plugin is required. The scaffold transport backend gives the live-capture
path a deterministic two-frame stream.
"""

from __future__ import annotations

import asyncio
import time

from textual.widgets import DataTable, Input, RichLog, Static, TextArea

from canarchy.cli import execute_command
from canarchy.models import CanFrame, FrameEvent
from canarchy.transport import LocalTransport, ScaffoldCanBackend
from canarchy.tui_app import CanarchyTuiApp, _FoldResult
from canarchy.tui_capture import CaptureSession, CaptureStats
from canarchy.tui_explorer import IdentifierKey


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


def _frame_event(
    arbitration_id: int,
    data: bytes,
    *,
    bus: str = "can0",
    extended: bool = False,
    timestamp: float = 1.0,
) -> dict:
    frame = CanFrame(
        arbitration_id,
        data,
        timestamp=timestamp,
        interface=bus,
        is_extended_id=extended,
    )
    return FrameEvent(frame, source="capture").to_event().to_payload()


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


def test_decode_fixture_displays_six_distinct_signal_observations() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            await _submit(
                app,
                pilot,
                "decode --file tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc",
            )
            assert app.query_one("#decoded", DataTable).row_count == 6
            assert len(app.tstate.decoded_signals) == 6

    _run(scenario())


def test_reference_and_diagnostic_results_are_visible_and_switchable() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            rows = app.query_one("#j1939", DataTable).row_count
            await _submit(app, pilot, "/filter traffic 0x")
            filters = dict(app._pane_filters)
            for command, expected in (
                ("stats --file tests/fixtures/sample.candump", "command: stats"),
                ("dbc inspect tests/fixtures/complex.dbc", "dbc"),
                ("/doctor", "checks:"),
                ("/config", "Effective transport configuration:"),
                ("j1939 pgn 65262", "65262"),
                ("j1939 spn 175", "175"),
            ):
                await _submit(app, pilot, command)
                result = app.query_one("#results", TextArea)
                assert result.display
                assert result.size.height >= 3
                assert expected in result.text
                assert app.query_one("#body").display is False
                if command.startswith("stats"):
                    copied: list[str] = []
                    app.copy_to_clipboard = copied.append
                    await pilot.press("f7", "ctrl+c")
                    assert copied == [result.text]
                await pilot.press("f2")
                assert app.query_one("#body").display
                assert app.query_one("#j1939", DataTable).row_count == rows
                assert app._pane_filters == filters

    _run(scenario())


def test_help_version_and_errors_use_results_view(capsys) -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(80, 24)) as pilot:
            for command, expected in (
                ("--help", "usage:"),
                ("--version", "canarchy"),
                ("not-a-command", "INVALID_ARGUMENTS"),
            ):
                await _submit(app, pilot, command)
                result = app.query_one("#results", TextArea)
                assert result.display
                assert expected in result.text
                if command == "not-a-command":
                    assert "error (exit 1)" in str(result.border_title)
                await pilot.press("escape")
                assert not result.display

    _run(scenario())
    assert capsys.readouterr().out == ""


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
            await _submit(app, pilot, "fuzz identify --interface can0 -- --help")
            await _submit(app, pilot, "send can0 0x123 0011 -- --version")
            assert calls == []
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


def test_refresh_helpers_tolerate_a_torn_down_widget_tree() -> None:
    """The capture drain timer can fire after the widget tree is gone.

    Textual does not stop interval timers synchronously on exit, so a drain
    scheduled by `on_mount` can still run once the screen is unmounted. The
    refresh helpers must not raise `NoMatches` in that window; see issue #509.
    """

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command)
        async with app.run_test() as pilot:
            await pilot.pause()
            # The widgets exist while the app is mounted.
            assert app.query_one("#bus-status", Static) is not None

        # Outside the context the app has exited and the tree is gone. These
        # are exactly the calls the drain timer makes.
        app._refresh_status(mode="capturing", interface="can0")
        app._refresh_j1939_ribbon()
        app._emit_alert("late alert after teardown")
        app._drain_capture()

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


def _alert_text(app: CanarchyTuiApp) -> str:
    """Every line written to the Alerts log, joined for substring checks."""

    return "\n".join(strip.text for strip in app.query_one("#alerts", RichLog).lines)


def _holding_factory(interface: str) -> CaptureSession:
    """A capture that yields the two scaffold frames and then stays alive.

    The scaffold stream is finite and releases its session as soon as it
    drains, which would make "does the running capture survive?" vacuous.
    This one parks on the stop event so the session is still live while the
    test submits help and malformed input.
    """

    sample = next(
        LocalTransport(live_backend=ScaffoldCanBackend()).capture_stream_events(interface)
    )

    class _HoldingTransport:
        def capture_stream_events(self, interface: str, *, stop_event=None):
            for _ in range(2):
                yield dict(sample)
            assert stop_event is not None
            stop_event.wait(2)

    return CaptureSession(interface, transport=_HoldingTransport())  # type: ignore[arg-type]


async def _await_rows(app: CanarchyTuiApp, pilot, selector: str, count: int) -> None:
    for _ in range(60):
        await pilot.pause(0.05)
        if app.query_one(selector, DataTable).row_count >= count:
            return


def test_help_does_not_clear_rows_or_stores() -> None:
    """`/help` is read-only: issue #517 had it wiping panes and row stores."""

    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            traffic = app.query_one("#traffic", DataTable)
            rows_before = traffic.row_count
            store_before = len(app._rows["traffic"])
            j1939_before = len(app._rows["j1939"])
            assert rows_before >= 1
            assert store_before == rows_before

            await _submit(app, pilot, "/help")

            # Displayed rows and the underlying stores both survive.
            assert traffic.row_count == rows_before
            assert len(app._rows["traffic"]) == store_before
            assert len(app._rows["j1939"]) == j1939_before
            assert app.query_one("#j1939", DataTable).row_count >= 1
            alerts = _alert_text(app)
            assert "Hotkeys:" in alerts
            assert "/capture <iface>" in alerts
            assert "panes cleared" not in alerts

            # Filter state is untouched, and a filter round-trip still
            # recovers every stored row (the #517 report's check).
            assert app._pane_filters == {}
            await _submit(app, pilot, "/filter traffic zzzznomatch")
            assert traffic.row_count == 0
            await _submit(app, pilot, "/filter traffic")
            assert traffic.row_count == rows_before

            # /clear still clears.
            await _submit(app, pilot, "/clear")
            assert traffic.row_count == 0
            assert app._rows["traffic"] == []
            assert "panes cleared" in _alert_text(app)

    _run(scenario())


def test_help_during_capture_and_while_paused_preserves_state() -> None:
    """Help must not disturb the capture lifecycle or the paused feed."""

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=_holding_factory)
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            await _await_rows(app, pilot, "#traffic", 2)
            capture = app._capture
            assert capture is not None
            assert capture.running is True
            assert app.query_one("#traffic", DataTable).row_count == 2

            await _submit(app, pilot, "/help")
            assert app._capture is capture
            assert app._capture.running is True
            assert app.query_one("#traffic", DataTable).row_count == 2
            assert len(app._rows["traffic"]) == 2

            # ... and again while presentation is paused.
            app.action_toggle_pause()
            await pilot.pause()
            await _submit(app, pilot, "/help")
            assert app.paused is True
            assert app._capture is capture
            assert app.query_one("#traffic", DataTable).row_count == 2
            assert len(app._rows["traffic"]) == 2
            assert "panes cleared" not in _alert_text(app)

            app.action_toggle_pause()
            app.action_stop_capture()
            await pilot.pause()

    _run(scenario())


def test_malformed_slash_quoting_reports_instead_of_crashing() -> None:
    """Issue #518: `/capture "` escaped shlex and tore down the whole app."""

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=_holding_factory)
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            await _await_rows(app, pilot, "#traffic", 2)
            capture = app._capture
            assert capture is not None

            # Submitted through the real Input event, exactly as typed.
            await _submit(app, pilot, '/capture "')
            assert "could not parse /capture arguments" in _alert_text(app)
            assert "No closing quotation" in _alert_text(app)
            # The running capture and the displayed history are untouched.
            assert app._capture is capture
            assert app._capture.running is True
            assert app.query_one("#traffic", DataTable).row_count == 2

            # A dangling backslash escape is reported the same way.
            await _submit(app, pilot, "/capture vcan0\\")
            assert "No escaped character" in _alert_text(app)
            assert app._capture is capture

            # The app is still usable: a valid command still runs.
            await _submit(app, pilot, "j1939 monitor --pgn 65262")
            assert app.query_one("#j1939", DataTable).row_count >= 1

            app.action_stop_capture()
            await pilot.pause()

    _run(scenario())


def test_capture_rejects_empty_and_extra_arguments() -> None:
    """Empty interface tokens and extra `/capture` tokens are refused."""

    started: list[str] = []

    def recording_factory(interface: str) -> CaptureSession:
        started.append(interface)
        return _holding_factory(interface)

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=recording_factory)
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            await _await_rows(app, pilot, "#traffic", 2)
            capture = app._capture
            assert started == ["vcan0"]

            await _submit(app, pilot, '/capture ""')
            assert "interface must not be empty" in _alert_text(app)
            await _submit(app, pilot, "/capture vcan1 --candump")
            assert "takes a single interface" in _alert_text(app)
            await _submit(app, pilot, "/capture")
            assert "/capture requires an interface" in _alert_text(app)

            # No rejected form reached the capture factory, so the running
            # capture was neither stopped nor replaced.
            assert started == ["vcan0"]
            assert app._capture is capture
            assert app._capture is not None
            assert app._capture.interface == "vcan0"
            assert app._capture.running is True
            assert app.query_one("#traffic", DataTable).row_count == 2

            app.action_stop_capture()
            await pilot.pause()

    _run(scenario())


def test_stop_rejects_arguments_instead_of_ending_the_capture() -> None:
    """Issue #542: `/stop "` stopped the capture instead of refusing it.

    `_run_slash` discarded `/stop`'s arguments entirely, so malformed input
    still reached `action_stop_capture`. REQ-TUI-15 requires the opposite:
    report the failure and leave capture state alone.
    """

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=_holding_factory)
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            await _submit(app, pilot, "/capture vcan0")
            await _await_rows(app, pilot, "#traffic", 2)
            capture = app._capture
            assert capture is not None

            # An unmatched quote is reported, not acted on.
            await _submit(app, pilot, '/stop "')
            assert "could not parse /stop arguments" in _alert_text(app)
            assert app._capture is capture
            assert app._capture.running is True

            # A well-formed but unexpected argument is refused too, rather
            # than being silently dropped the way it used to be.
            await _submit(app, pilot, "/stop now")
            assert "/stop takes no arguments" in _alert_text(app)
            assert app._capture is capture
            assert app._capture.running is True

            # The displayed history survived both rejections.
            assert app.query_one("#traffic", DataTable).row_count == 2

            # Bare /stop still works.
            await _submit(app, pilot, "/stop")
            await pilot.pause()
            assert app._capture is None or app._capture.running is False

    _run(scenario())


def test_filter_still_accepts_raw_text_with_a_quote() -> None:
    """`/filter` and `/sort` take raw text, so they must not be tokenised.

    Guards the narrowed REQ-TUI-15 (#542): routing every slash command
    through `shlex.split` would make a filter needle containing a quote
    unusable, which would be a regression rather than a fix.
    """

    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=_holding_factory)
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            await _submit(app, pilot, '/filter traffic "')
            assert app._pane_filters.get("traffic") == '"'
            assert "could not parse" not in _alert_text(app)

            # An unknown pane is still rejected without touching state.
            await _submit(app, pilot, '/sort "')
            assert "/sort <" in _alert_text(app)

    _run(scenario())


def test_responsive_workspace_keeps_traffic_usable_at_small_sizes() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await _submit(app, pilot, "filter all --file tests/fixtures/sample.candump")
            traffic = app.query_one("#identifiers", DataTable)
            assert traffic.display
            assert traffic.size.height >= 10
            assert app.query_one("#body").has_class("narrow")
            assert app.query_one("#empty-state", Static).display is False
            assert traffic.columns[next(iter(traffic.columns))].width >= 6
            assert len(app.query_one("#workspace-nav", Static).render().plain) <= 78
            traffic.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#body").has_class("detail")
            assert "Raw hex:" in str(app.query_one("#inspector", Static).render())
            await pilot.press("escape")
            assert traffic.display
            assert not app.query_one("#body").has_class("detail")
            assert app.focused is traffic
            await pilot.press("down")
            assert traffic.cursor_row == min(1, traffic.row_count - 1)

            await pilot.press("enter")
            assert app.query_one("#body").has_class("detail")

            await pilot.resize_terminal(100, 35)
            await pilot.pause()
            assert app.query_one("#body").has_class("narrow")
            await pilot.resize_terminal(140, 45)
            await pilot.pause()
            assert not app.query_one("#body").has_class("narrow")
            assert not app.query_one("#body").has_class("detail")
            assert not app._detail_open
            assert app.focused is traffic
            assert traffic.size.height >= 30
            assert app.query_one("#inspector", Static).display

    _run(scenario())


def test_workspace_navigation_preserves_rows_capture_and_activity() -> None:
    async def scenario() -> None:
        app = CanarchyTuiApp(execute_command, capture_factory=_holding_factory)
        async with app.run_test(size=(80, 24)) as pilot:
            await _submit(app, pilot, "/capture vcan0")
            await _await_rows(app, pilot, "#traffic", 2)
            capture = app._capture
            traffic = app.query_one("#traffic", DataTable)
            traffic.cursor_coordinate = (1, 0)
            await pilot.press("alt+3")
            assert app.workspace == "j1939"
            await pilot.press("alt+5")
            assert app.workspace == "findings"
            findings = app.query_one("#findings", DataTable)
            assert findings.row_count >= 2
            await pilot.press("f3")
            assert app.query_one("#alerts", RichLog).has_class("expanded")
            await pilot.press("alt+1")
            assert app.workspace == "traffic"
            assert traffic.cursor_row == 1
            assert traffic.row_count == 2
            assert app._capture is capture
            app.action_stop_capture()

    _run(scenario())


def test_identifier_selection_survives_updates_filters_and_eviction() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            events = [
                _frame_event(0x123, b"\x00\x01", timestamp=1.0),
                _frame_event(0x123, b"\x02", extended=True, timestamp=2.0),
                _frame_event(0x123, b"\x03", bus="can1", timestamp=3.0),
            ]
            app._ingest_result(_FoldResult("capture", {"events": events, "interface": "can0"}))
            await pilot.pause()
            table = app.query_one("#identifiers", DataTable)
            assert table.row_count == 3
            assert set(app._summary_keys) == {
                IdentifierKey("can0", 0x123, False),
                IdentifierKey("can0", 0x123, True),
                IdentifierKey("can1", 0x123, False),
            }
            table.focus()
            await pilot.press("down")
            selected = app._selected_identifier
            assert selected is not None
            assert not app.follow_live
            frozen = app._selected_detail

            app._cmd_sort("traffic id")
            app._cmd_filter("traffic id==0x123")
            app.action_workspace("j1939")
            app.action_workspace("traffic")
            assert app._selected_identifier == selected
            assert app._selected_detail == frozen

            app.backlog_cap = 2
            app._trim_all_panes()
            app._ingest_result(
                _FoldResult(
                    "capture",
                    {"events": [_frame_event(0x222, b"\x04", timestamp=4.0)]},
                )
            )
            assert app._selected_identifier == selected
            assert app._selected_detail == frozen
            assert app._incoming_since_inspect == 1
            assert "INSPECTING" in str(app.query_one("#traffic-mode", Static).render())
            app.action_toggle_follow()
            assert app.follow_live
            assert app._selected_identifier == IdentifierKey("can0", 0x222, False)

    _run(scenario())


def test_traffic_filter_sort_and_log_use_shared_frame_values() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(80, 24)) as pilot:
            assert "nocolor" in app.pseudo_classes
            events = [
                _frame_event(0x18FEEE31, b"\x01", extended=True, timestamp=86399.0),
                _frame_event(0x123, b"\x02", timestamp=86401.0),
                _frame_event(0x18F00431, b"\x03", extended=True, timestamp=86402.0),
            ]
            app._ingest_result(_FoldResult("capture", {"events": events}))
            table = app.query_one("#identifiers", DataTable)
            app._cmd_filter("traffic sa==0x31")
            assert table.row_count == 2
            app._cmd_filter("traffic pgn==65262")
            assert table.row_count == 1
            assert app._summary_keys == [IdentifierKey("can0", 0x18FEEE31, True)]
            app._cmd_filter("traffic id==invalid")
            assert table.row_count == 1
            assert "INVALID_FILTER_EXPRESSION" in _alert_text(app)
            app._cmd_filter("traffic")
            before = app._identifier_sort
            app._cmd_sort("traffic nonexistent")
            assert app._identifier_sort == before
            assert "unknown column" in _alert_text(app)
            app._cmd_sort("traffic id")
            assert [key.arbitration_id for key in app._summary_keys] == sorted(
                (0x18FEEE31, 0x123, 0x18F00431), reverse=True
            )

            table.focus()
            await pilot.press("v")
            assert app.traffic_view == "log"
            log = app.query_one("#traffic", DataTable)
            assert log.display
            app._cmd_sort("traffic time")
            assert app._visible_log_ids == [0, 1, 2]
            app._cmd_filter("traffic sa==0x31")
            assert log.row_count == 2
            app.action_toggle_follow()
            log.focus()
            log.cursor_coordinate = (1, 0)
            await pilot.press("up")
            assert not app.follow_live
            assert "INSPECTING" in str(app.query_one("#traffic-mode", Static).render())
            frozen = str(app.query_one("#inspector", Static).render())
            assert "Raw hex: 01" in frozen
            app._ingest_result(
                _FoldResult(
                    "capture",
                    {
                        "events": [
                            _frame_event(0x18FEEE31, b"\xff", extended=True, timestamp=86403.0)
                        ]
                    },
                )
            )
            assert str(app.query_one("#inspector", Static).render()).find("Raw hex: 01") >= 0

    _run(scenario())


def test_identifier_ui_synthetic_batch_stays_responsive() -> None:
    async def scenario() -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            events = [
                _frame_event(0x100 + index % 32, bytes((index % 256,)), timestamp=float(index))
                for index in range(1000)
            ]
            started = time.perf_counter()
            app._ingest_result(_FoldResult("capture", {"events": events}))
            await pilot.pause()
            assert time.perf_counter() - started < 10.0
            assert app.query_one("#identifiers", DataTable).row_count == 32
            assert app.query_one("#traffic", DataTable).row_count == 1000
            assert len(app.explorer.observations) == app.backlog_cap

    _run(scenario())
