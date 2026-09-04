"""Full-screen Textual front end for CANarchy.

This is the interactive view layer. It owns no protocol or transport
logic: live frames arrive through `CaptureSession` (a consumer of the
shared `capture_stream_events` generator) and one-off commands run through
the same `execute_command` the CLI uses. Everything the panes display is
derived from the canonical event envelope via the fold-layer helpers in
`canarchy.tui`, so the TUI stays a view over the engine.

Panes: Bus Status, Live Traffic, Decoded Signals, J1939 (summary ribbon +
recent table), UDS Transactions, and an append-only Alerts log, plus a
command entry that accepts real CANarchy commands and slash hotkeys.
"""

from __future__ import annotations

import shlex
from collections import deque
from typing import Any

from collections.abc import Callable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from canarchy.tui import (
    DECODED_SIGNAL_COLUMNS,
    J1939_COLUMNS,
    TRAFFIC_COLUMNS,
    UDS_COLUMNS,
    BacklogCaps,
    TuiState,
    _HotkeyResult,
    _clear_panes,
    _decoded_signal_tuples,
    _handle_hotkey,
    _j1939_row_tuples,
    _traffic_row_tuples,
    _uds_row_tuples,
    _update_state,
)
from canarchy.tui_capture import CaptureSession, CaptureStats

# Pane id → (DataTable selector, column headers).
_PANES: dict[str, tuple[str, tuple[str, ...]]] = {
    "traffic": ("#traffic", TRAFFIC_COLUMNS),
    "decoded": ("#decoded", DECODED_SIGNAL_COLUMNS),
    "j1939": ("#j1939", J1939_COLUMNS),
    "uds": ("#uds", UDS_COLUMNS),
}

_MIN_BACKLOG = 50
_MAX_BACKLOG = 100000
_DEFAULT_BACKLOG = 1000


def _row_matches(row: tuple[Any, ...], needle: str) -> bool:
    needle = needle.lower()
    return any(needle in str(cell).lower() for cell in row)


def _is_active_transmit_command(argv: list[str]) -> bool:
    """True if *argv* resolves to an active-transmit command.

    Reuses the CLI's own definition (`ACTIVE_TRANSMIT_COMMANDS` +
    `_is_doip_active_command`) by parsing the argv the same way
    `execute_command` will. Any parse failure returns False so the shared
    command path still produces the normal structured parse error.
    """

    from canarchy.cli import (
        ACTIVE_TRANSMIT_COMMANDS,
        _is_doip_active_command,
        build_parser,
    )

    try:
        args = build_parser().parse_args(argv)
    except BaseException:
        # argparse errors (CliUsageError) and --help/--version (SystemExit)
        # are handled downstream by the shared command path.
        return False
    return getattr(args, "command", None) in ACTIVE_TRANSMIT_COMMANDS or _is_doip_active_command(
        args
    )


class CanarchyTuiApp(App[int]):
    """The CANarchy full-screen TUI application."""

    TITLE = "CANarchy TUI"

    CSS = """
    #bus-status {
        height: auto;
        padding: 0 1;
        background: $panel;
        color: $text;
    }
    #j1939-ribbon {
        height: auto;
        padding: 0 1;
        color: $warning;
    }
    #body {
        height: 1fr;
    }
    .column {
        width: 1fr;
    }
    .pane {
        border: round $accent;
        height: 1fr;
    }
    #alerts {
        border: round $warning;
        height: 8;
    }
    #command {
        dock: bottom;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("q", "quit", "Quit"),
        ("c", "clear_panes", "Clear"),
        ("x", "stop_capture", "Stop capture"),
        ("space", "toggle_pause", "Pause/Resume"),
        ("ctrl+f", "maximize_pane", "Maximize pane"),
        ("left_square_bracket", "shrink_backlog", "Backlog -"),
        ("right_square_bracket", "grow_backlog", "Backlog +"),
    ]

    def __init__(
        self,
        execute_command: Any,
        *,
        capture_factory: Callable[[str], CaptureSession] | None = None,
    ) -> None:
        super().__init__()
        self._execute_command = execute_command
        self._capture_factory = capture_factory or (lambda interface: CaptureSession(interface))
        self.tstate = TuiState()
        self.backlog_cap = _DEFAULT_BACKLOG
        self.paused = False
        self._capture: CaptureSession | None = None
        self._last_capture_stats = CaptureStats()
        self._reported_dropped = 0
        self._capture_end_announced = False
        # Per-pane retained backlog + bookkeeping for filter/sort/trim.
        self._rows: dict[str, list[tuple[Any, ...]]] = {name: [] for name in _PANES}
        self._row_keys: dict[str, deque] = {name: deque() for name in _PANES}
        self._col_keys: dict[str, list] = {name: [] for name in _PANES}
        self._pane_filters: dict[str, str] = {}
        self._sort_reverse: dict[str, bool] = {}

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("interface: none  mode: idle", id="bus-status")
        with Horizontal(id="body"):
            with Vertical(classes="column"):
                yield DataTable(id="traffic", classes="pane")
                yield DataTable(id="decoded", classes="pane")
            with Vertical(classes="column"):
                yield Static("(no J1939 summary)", id="j1939-ribbon")
                yield DataTable(id="j1939", classes="pane")
                yield DataTable(id="uds", classes="pane")
        yield RichLog(id="alerts", classes="pane", highlight=False, markup=False, wrap=True)
        yield Input(id="command", placeholder="CANarchy command or /help")
        yield Footer()

    def on_mount(self) -> None:
        titles = {
            "traffic": "Live Traffic",
            "decoded": "Decoded Signals",
            "j1939": "J1939",
            "uds": "UDS Transactions",
        }
        for name, (selector, columns) in _PANES.items():
            table = self.query_one(selector, DataTable)
            table.cursor_type = "row"
            table.zebra_stripes = True
            table.border_title = titles[name]
            self._col_keys[name] = list(table.add_columns(*columns))
        self.query_one("#alerts", RichLog).border_title = "Alerts & Replay"
        self._emit_alert("CANarchy TUI ready — /capture <iface> to watch the bus live.")
        self.query_one("#command", Input).focus()
        # Poll the capture queue on the UI thread; the CaptureSession's own
        # daemon thread is the producer, so this drain is thread-safe.
        self.set_interval(0.1, self._drain_capture)

    # -- command entry ------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if text:
            self._run_command_line(text)

    def _run_command_line(self, text: str) -> None:
        if text in {"exit", "quit"}:
            self.action_quit()
            return
        if text.startswith("/"):
            self._run_slash(text)
            return
        self._run_command(text)

    def _run_slash(self, text: str) -> None:
        name, _, rest = text[1:].partition(" ")
        name = name.lower()
        rest = rest.strip()
        # App-native slash commands (live capture, view controls) take
        # precedence over the shared hotkey table.
        if name == "capture":
            if not rest:
                self._emit_alert("/capture requires an interface; e.g. /capture vcan0")
                return
            self._start_capture(shlex.split(rest)[0])
            return
        if name == "stop":
            self.action_stop_capture()
            return
        if name == "filter":
            self._cmd_filter(rest)
            return
        if name == "sort":
            self._cmd_sort(rest)
            return
        # Fall back to the shared hotkeys (/help, /clear, /save, /load,
        # /dbc, /doctor, /config, /quit) with diagnostics routed to Alerts.
        disposition, expanded = _handle_hotkey(text, self.tstate, self._emit_alert)
        if disposition is _HotkeyResult.QUIT:
            self.action_quit()
        elif disposition is _HotkeyResult.LOCAL:
            # /clear resets fold state; mirror that in the panes.
            self._reset_panes()
        elif disposition is _HotkeyResult.EXPANDED and expanded is not None:
            self._run_command(expanded)

    def _run_command(self, command: str) -> None:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            self._emit_alert(f"error: could not parse command: {exc}")
            return
        if _is_active_transmit_command(argv):
            # Active-transmit commands print a preflight to stderr and block
            # on `sys.stdin.readline()` for a `YES` confirmation. In a
            # full-screen app stdin is owned by Textual and stderr is the
            # alt-screen, so that would freeze the UI with an invisible
            # prompt. Refuse them here and point the operator at the CLI,
            # where the confirmation workflow works.
            self._emit_alert(
                "refusing active-transmit command in the TUI — run it from the "
                "CLI (its confirmation prompt cannot be answered here)."
            )
            return
        try:
            _exit_code, result = self._execute_command(argv)
        except SystemExit:
            # --help / --version call sys.exit(); stay in the TUI.
            return
        if result is not None:
            self._ingest_result(result)

    # -- live capture -------------------------------------------------------

    def _start_capture(self, interface: str) -> None:
        if not self._stop_capture(release=False):
            self._emit_alert("capture replacement cancelled until the previous worker exits")
            return
        if self.paused and self._capture is not None and self._capture.stats.queue_depth:
            self._emit_alert("capture replacement cancelled; resume to drain buffered events first")
            return
        self._drain_stopped_capture()
        self._capture = self._capture_factory(interface)
        self._last_capture_stats = CaptureStats()
        self._reported_dropped = 0
        self._capture_end_announced = False
        self._capture.start()
        self._emit_alert(f"capture started on {interface}")
        self._refresh_status(mode="capturing", interface=interface)

    def _stop_capture(self, *, release: bool = True) -> bool:
        if self._capture is not None:
            capture = self._capture
            stopped = capture.stop()
            self._last_capture_stats = capture.stats
            if stopped and release:
                self._capture = None
            else:
                for error in capture.errors():
                    self._emit_alert(f"error: {error.code}: {error.message} Hint: {error.hint}")
            return stopped
        return True

    def action_stop_capture(self) -> None:
        if self._capture is None:
            return
        interface = self._capture.interface
        if self._stop_capture(release=False):
            self._emit_alert(f"capture stopped on {interface}")
            self._capture_end_announced = True
            self._drain_capture()
        else:
            self._refresh_status(mode="stopping")

    def _drain_stopped_capture(self) -> None:
        capture = self._capture
        if capture is None:
            return
        for error in capture.errors():
            self._emit_alert(f"error: {error.code}: {error.message} Hint: {error.hint}")
        self._report_capture_drops(capture)
        events = capture.drain(max_items=max(capture.stats.queue_depth, 1))
        self._last_capture_stats = capture.stats
        if events:
            self._ingest_result(
                _FoldResult(
                    command="capture",
                    data={"events": events, "mode": "stopped", "interface": capture.interface},
                )
            )
        self._capture = None

    def _drain_capture(self) -> None:
        capture = self._capture
        if capture is None:
            return
        for error in capture.errors():
            self._emit_alert(f"error: {error.code}: {error.message} Hint: {error.hint}")
        self._report_capture_drops(capture)
        if self.paused:
            if not capture.running and not self._capture_end_announced:
                self._capture_end_announced = True
                self._emit_alert(
                    f"capture ended on {capture.interface}; buffered events will drain on resume"
                )
                self._refresh_status(mode="ended")
            return
        events = capture.drain()
        self._last_capture_stats = capture.stats
        if events:
            result = _FoldResult(
                command="capture",
                data={"events": events, "mode": "capturing", "interface": capture.interface},
            )
            self._ingest_result(result)
        # A finite backend or an immediate transport error ends the stream
        # without a stop request; return to idle so status stops showing
        # `capturing` and the operator does not have to `/stop` a dead session.
        if not capture.running and capture.stats.queue_depth == 0:
            self._capture = None
            if not self._capture_end_announced:
                self._emit_alert(f"capture ended on {capture.interface}")
            self._refresh_status(mode="idle")
        else:
            self._refresh_status()

    def _report_capture_drops(self, capture: CaptureSession) -> None:
        stats = capture.stats
        self._last_capture_stats = stats
        if stats.dropped <= self._reported_dropped:
            return
        delta = stats.dropped - self._reported_dropped
        self._reported_dropped = stats.dropped
        self._emit_alert(f"warning: capture queue dropped {delta} events ({stats.dropped} total)")

    # -- folding results into panes ----------------------------------------

    def _ingest_result(self, result: Any) -> None:
        _update_state(self.tstate, result, self._caps())
        self._add_pane_rows("traffic", _traffic_row_tuples(result))
        self._add_pane_rows("decoded", _decoded_signal_tuples(result))
        self._add_pane_rows("j1939", _j1939_row_tuples(result))
        self._add_pane_rows("uds", _uds_row_tuples(result))
        self._refresh_status()
        self._refresh_j1939_ribbon()
        for line in self.tstate.alerts:
            self._emit_alert(line)

    def _add_pane_rows(self, pane: str, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        store = self._rows[pane]
        store.extend(rows)
        overflow = len(store) - self.backlog_cap
        if overflow > 0:
            del store[:overflow]
        table = self.query_one(_PANES[pane][0], DataTable)
        keys = self._row_keys[pane]
        needle = self._pane_filters.get(pane, "")
        for row in rows:
            if needle and not _row_matches(row, needle):
                continue
            keys.append(table.add_row(*(str(cell) for cell in row)))
        while len(keys) > self.backlog_cap:
            old = keys.popleft()
            try:
                table.remove_row(old)
            except Exception:
                pass
        table.scroll_end(animate=False)

    def _rebuild_pane(self, pane: str) -> None:
        table = self.query_one(_PANES[pane][0], DataTable)
        table.clear()
        keys = self._row_keys[pane]
        keys.clear()
        needle = self._pane_filters.get(pane, "")
        for row in self._rows[pane]:
            if needle and not _row_matches(row, needle):
                continue
            keys.append(table.add_row(*(str(cell) for cell in row)))
        table.scroll_end(animate=False)

    def _reset_panes(self) -> None:
        for pane in _PANES:
            self._rows[pane].clear()
            self._row_keys[pane].clear()
            self.query_one(_PANES[pane][0], DataTable).clear()
        self._refresh_status()
        self._refresh_j1939_ribbon()
        self._emit_alert("panes cleared")

    # -- filter / sort ------------------------------------------------------

    def _cmd_filter(self, rest: str) -> None:
        parts = rest.split(None, 1)
        if not parts or parts[0] not in _PANES:
            self._emit_alert(f"/filter <{'|'.join(_PANES)}> [text]")
            return
        pane = parts[0]
        needle = parts[1].strip() if len(parts) > 1 else ""
        if needle:
            self._pane_filters[pane] = needle
            self._emit_alert(f"filter {pane}: {needle}")
        else:
            self._pane_filters.pop(pane, None)
            self._emit_alert(f"filter {pane}: cleared")
        self._rebuild_pane(pane)

    def _cmd_sort(self, rest: str) -> None:
        parts = rest.split()
        if not parts or parts[0] not in _PANES:
            self._emit_alert(f"/sort <{'|'.join(_PANES)}> [column]")
            return
        pane = parts[0]
        columns = _PANES[pane][1]
        index = 0
        if len(parts) > 1:
            try:
                index = int(parts[1])
            except ValueError:
                # Allow sorting by column name too.
                lowered = [c.lower() for c in columns]
                if parts[1].lower() in lowered:
                    index = lowered.index(parts[1].lower())
        if not 0 <= index < len(columns):
            self._emit_alert(f"/sort {pane}: column {index} out of range")
            return
        reverse = not self._sort_reverse.get(pane, False)
        self._sort_reverse[pane] = reverse
        table = self.query_one(_PANES[pane][0], DataTable)
        table.sort(self._col_keys[pane][index], reverse=reverse)
        arrow = "desc" if reverse else "asc"
        self._emit_alert(f"sort {pane} by {columns[index]} ({arrow})")

    # -- view helpers -------------------------------------------------------

    def _caps(self) -> BacklogCaps:
        cap = self.backlog_cap
        return BacklogCaps(
            decoded_signals=cap,
            j1939_recent=cap,
            j1939_dm1_alerts=cap,
            uds_recent=cap,
            traffic=cap,
        )

    def _emit_alert(self, line: str) -> None:
        self.query_one("#alerts", RichLog).write(line)

    def _refresh_status(self, *, mode: str | None = None, interface: str | None = None) -> None:
        lines = [line for line in self.tstate.bus_status if not line.startswith("capture:")]
        capturing = self._capture is not None
        status = mode or (
            ("capturing" if self._capture.running else "draining") if capturing else None
        )
        if interface is not None:
            lines = [f"interface: {interface}"] + [
                line for line in lines if not line.startswith("interface:")
            ]
        if status is not None:
            lines = [line for line in lines if not line.startswith("mode:")]
            lines.append(f"mode: {status}")
        if self.paused:
            lines.append("[paused]")
        stats = self._capture.stats if self._capture is not None else self._last_capture_stats
        if stats.received or stats.drained or stats.dropped:
            lines.append(
                "capture: "
                f"received={stats.received} drained={stats.drained} "
                f"queued={stats.queue_depth} dropped={stats.dropped} "
                f"high-water={stats.high_water_mark}"
            )
        lines.append(f"backlog: {self.backlog_cap}")
        # Render as literal Text: status/fault strings contain brackets
        # (e.g. "[paused]", DM1 "[spn=175/fmi=5]") that Static would
        # otherwise try to parse as console markup and raise on.
        self.query_one("#bus-status", Static).update(Text("  ".join(lines)))

    def _refresh_j1939_ribbon(self) -> None:
        state = self.tstate
        parts: list[str] = []
        if state.j1939_pgn_counts:
            top = state.j1939_pgn_counts.most_common(3)
            parts.append("top PGNs: " + ", ".join(f"{pgn}({n})" for pgn, n in top))
        if state.j1939_source_addresses:
            top_sa = state.j1939_source_addresses.most_common(4)
            parts.append("SA: " + ", ".join(f"0x{sa:02X}({n})" for sa, n in top_sa))
        if state.j1939_dm1_alerts:
            parts.append("!! DM1 active faults: " + " | ".join(state.j1939_dm1_alerts))
        # Literal Text — DM1 fault summaries contain "[spn=.../fmi=...]"
        # which Static would otherwise treat as console markup.
        self.query_one("#j1939-ribbon", Static).update(
            Text("  ".join(parts) or "(no J1939 summary)")
        )

    # -- actions ------------------------------------------------------------

    def action_clear_panes(self) -> None:
        _clear_panes(self.tstate)
        self._reset_panes()

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        self._emit_alert("live feed paused" if self.paused else "live feed resumed")
        self._refresh_status()

    def action_maximize_pane(self) -> None:
        focused = self.focused
        if isinstance(focused, DataTable):
            self.screen.maximize(focused)

    def action_shrink_backlog(self) -> None:
        self.backlog_cap = max(_MIN_BACKLOG, self.backlog_cap // 2)
        self._trim_all_panes()

    def action_grow_backlog(self) -> None:
        self.backlog_cap = min(_MAX_BACKLOG, self.backlog_cap * 2)
        self._refresh_status()

    def _trim_all_panes(self) -> None:
        for pane in _PANES:
            store = self._rows[pane]
            overflow = len(store) - self.backlog_cap
            if overflow > 0:
                del store[:overflow]
            self._rebuild_pane(pane)
        self._refresh_status()

    def action_quit(self) -> None:  # type: ignore[override]
        self._stop_capture()
        self.exit(0)

    def on_unmount(self) -> None:
        self._stop_capture()


class _FoldResult:
    """A minimal CommandResult look-alike for streamed capture events.

    The fold-layer helpers read `command`, `data`, `warnings`, `errors`,
    and `to_payload()`. Streamed frames carry no warnings/errors, so a
    tiny stand-in avoids importing the heavy CLI module at UI runtime.
    """

    __slots__ = ("command", "data", "warnings", "errors", "ok")

    def __init__(self, command: str, data: dict[str, Any]) -> None:
        self.command = command
        self.data = data
        self.warnings: list[str] = []
        self.errors: list[dict[str, Any]] = []
        self.ok = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "data": self.data,
            "warnings": self.warnings,
            "errors": self.errors,
            "ok": self.ok,
        }


def run_canarchy_tui(execute_command: Any) -> int:
    """Launch the full-screen TUI and return its exit code."""

    app = CanarchyTuiApp(execute_command)
    result = app.run()
    return result if isinstance(result, int) else 0
