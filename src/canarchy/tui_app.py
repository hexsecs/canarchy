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
from contextlib import redirect_stdout
from io import StringIO
from collections import deque
from typing import Any, TypeVar

from collections.abc import Callable

from rich.text import Text
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static, TextArea

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
_WORKSPACES = ("traffic", "decoded", "j1939", "uds", "findings")
_WORKSPACE_LABELS = ("Traffic", "Signals", "J1939", "UDS", "Findings")


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
        with redirect_stdout(StringIO()):
            args = build_parser().parse_args(argv)
    except BaseException:
        # argparse errors (CliUsageError) and --help/--version (SystemExit)
        # are handled downstream by the shared command path.
        return False
    return getattr(args, "command", None) in ACTIVE_TRANSMIT_COMMANDS or _is_doip_active_command(
        args
    )


_WidgetT = TypeVar("_WidgetT", bound=Widget)


class WorkspaceBody(Horizontal):
    def on_resize(self) -> None:
        self.app._apply_width()


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
    #workspace-nav {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    #workspace-content {
        width: 1fr;
        height: 1fr;
    }
    #inspector {
        width: 36;
        height: 1fr;
        border: round $accent;
        padding: 0 1;
    }
    #body.narrow #inspector {
        display: none;
    }
    #body.detail #workspace-content {
        display: none;
    }
    #body.detail #inspector {
        display: block;
        width: 1fr;
    }
    #empty-state {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }
    #results {
        display: none;
        height: 1fr;
        border: round $accent;
    }
    .pane {
        border: round $accent;
        height: 1fr;
    }
    #alerts {
        border: none;
        height: 1;
    }
    #alerts.expanded {
        border: round $warning;
        height: 7;
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
        ("f2", "toggle_results", "Results/Panes"),
        ("f3", "toggle_activity", "Activity"),
        ("alt+1", "workspace('traffic')", "Traffic"),
        ("alt+2", "workspace('decoded')", "Signals"),
        ("alt+3", "workspace('j1939')", "J1939"),
        ("alt+4", "workspace('uds')", "UDS"),
        ("alt+5", "workspace('findings')", "Findings"),
        ("enter", "show_detail", "Inspect"),
        ("escape", "show_panes", "Panes"),
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
        self._has_result = False
        self.workspace = "traffic"
        self._detail_open = False
        self._alert_count = 0

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("interface: none  mode: idle", id="bus-status")
        yield Static(id="workspace-nav")
        with WorkspaceBody(id="body"):
            with Vertical(id="workspace-content"):
                yield Static(
                    "Start: /capture <iface> for a live bus, or run "
                    "datasets fetch offline:can-basic and inspect its cache_path. "
                    "Use Alt+1–5 for workspaces, F2 for results, F3 for activity.",
                    id="empty-state",
                )
                yield DataTable(id="traffic", classes="pane")
                yield DataTable(id="decoded", classes="pane")
                yield Static("(no J1939 summary)", id="j1939-ribbon")
                yield DataTable(id="j1939", classes="pane")
                yield DataTable(id="uds", classes="pane")
                yield DataTable(id="findings", classes="pane")
            yield Static("Select a row to inspect its complete fields.", id="inspector")
        yield TextArea(read_only=True, soft_wrap=False, id="results")
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
        findings = self.query_one("#findings", DataTable)
        findings.border_title = "Findings & Activity"
        findings.add_column("event")
        self.query_one("#results", TextArea).border_title = "Command Result — F2 panes, Esc close"
        self._apply_workspace()
        self._apply_width()
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
            self._cmd_capture(rest)
            return
        if name == "stop":
            self._cmd_stop(rest)
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
        elif disposition is _HotkeyResult.CLEARED:
            # /clear reset the fold state; mirror that in the panes. Only
            # this disposition may discard rows — a read-only handler such
            # as /help returns LOCAL and leaves the view alone (issue #517).
            self._reset_panes()
        elif disposition is _HotkeyResult.EXPANDED and expanded is not None:
            self._run_command(expanded)

    def _split_slash_args(self, name: str, rest: str) -> list[str] | None:
        """Tokenise a slash command's arguments, or report why it failed.

        Mirrors the guard `_run_command` already has around `shlex.split`.
        An unmatched quote or a dangling backslash raises `ValueError`;
        that must surface as an Alerts diagnostic, not as a traceback that
        tears down the full-screen app (issue #518). Returns `None` when
        the text could not be parsed, in which case the caller does
        nothing further.
        """

        try:
            return shlex.split(rest)
        except ValueError as exc:
            self._emit_alert(f"error: could not parse /{name} arguments: {exc}")
            return None

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
        output = StringIO()
        try:
            with redirect_stdout(output):
                _exit_code, result = self._execute_command(argv)
        except SystemExit:
            if output.getvalue():
                self._show_result(command, output.getvalue(), status="complete")
            return
        if result is not None:
            self._ingest_result(result)
            from canarchy.cli import emit_result

            output_format = "json" if "--json" in argv else "jsonl" if "--jsonl" in argv else "text"
            with redirect_stdout(output):
                emit_result(result, output_format)
            self._show_result(
                command,
                output.getvalue(),
                status="complete" if result.ok else f"error (exit {_exit_code})",
                reveal=not self._result_has_rows(result) or not result.ok,
            )

    def _result_has_rows(self, result: Any) -> bool:
        return any(
            (
                _traffic_row_tuples(result),
                _decoded_signal_tuples(result),
                _j1939_row_tuples(result),
                _uds_row_tuples(result),
            )
        )

    def _show_result(self, command: str, output: str, *, status: str, reveal: bool = True) -> None:
        result_view = self.query_one("#results", TextArea)
        result_view.border_title = f"{command} — {status} — F2 panes, Esc close"
        result_view.load_text(output.rstrip("\n") or "(no output)")
        self._has_result = True
        if reveal:
            self._set_result_visible(True)

    def _set_result_visible(self, visible: bool) -> None:
        self.query_one("#body", Horizontal).display = not visible
        result_view = self.query_one("#results", TextArea)
        result_view.display = visible
        (result_view if visible else self.query_one("#command", Input)).focus()

    def action_toggle_results(self) -> None:
        if self._has_result:
            self._set_result_visible(not self.query_one("#results", TextArea).display)

    def action_show_panes(self) -> None:
        closing_detail = self._detail_open
        if closing_detail:
            self._detail_open = False
            self.query_one("#body").remove_class("detail")
            self._apply_width()
        self._set_result_visible(False)
        if closing_detail and self.workspace in _PANES:
            self.query_one(_PANES[self.workspace][0], DataTable).focus()

    def action_workspace(self, name: str) -> None:
        if name not in _WORKSPACES:
            return
        self.workspace = name
        self._detail_open = False
        self.query_one("#body").remove_class("detail")
        self._apply_workspace()
        self._apply_width()
        if name in _PANES:
            self.query_one(_PANES[name][0], DataTable).focus()
        else:
            self.query_one("#findings", DataTable).focus()

    def action_toggle_activity(self) -> None:
        drawer = self.query_one("#alerts", RichLog)
        drawer.toggle_class("expanded")
        self._refresh_nav()

    def action_show_detail(self) -> None:
        if self.workspace not in _PANES or not self.query_one("#body").has_class("narrow"):
            return
        self._detail_open = True
        self.query_one("#body").add_class("detail")
        self.query_one("#inspector", Static).focus()

    def _apply_width(self) -> None:
        body = self._find_widget("#body", Horizontal)
        if body is None:
            return
        narrow = self.size.width < 110
        body.set_class(narrow, "narrow")
        if not narrow and self._detail_open:
            self._detail_open = False
            body.remove_class("detail")
            self.query_one(_PANES[self.workspace][0], DataTable).focus()
        traffic = self._find_widget("#traffic", DataTable)
        if traffic is not None and self._col_keys["traffic"]:
            widths = (
                12,
                8,
                7,
                10,
                3,
                max(16, self.size.width - (54 if body.has_class("narrow") else 90)),
            )
            for key, width in zip(self._col_keys["traffic"], widths):
                traffic.columns[key].width = width
            traffic.refresh()
        if self._find_widget("#alerts", RichLog) is not None:
            self._refresh_nav()

    def _apply_workspace(self) -> None:
        for name, (selector, _) in _PANES.items():
            self.query_one(selector).display = name == self.workspace
        self.query_one("#findings", DataTable).display = self.workspace == "findings"
        self.query_one("#j1939-ribbon", Static).display = self.workspace == "j1939"
        self.query_one("#empty-state", Static).display = (
            self.workspace == "traffic" and not self._rows["traffic"]
        )
        self._refresh_nav()
        self._refresh_inspector()

    def _refresh_nav(self) -> None:
        labels = [
            f"[{index} {label}]" if name == self.workspace else f"{index} {label}"
            for index, (name, label) in enumerate(zip(_WORKSPACES, _WORKSPACE_LABELS), 1)
        ]
        drawer = "open" if self.query_one("#alerts", RichLog).has_class("expanded") else "closed"
        prefix = "Alt+ "
        suffix = f"  F2 Results  F3 Activity ({self._alert_count}, {drawer})"
        if self.size.width < 110:
            suffix = "  F2 Result  F3 Log"
        self.query_one("#workspace-nav", Static).update(Text(prefix + "  ".join(labels) + suffix))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == self.workspace:
            self._refresh_inspector()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == self.workspace:
            self.action_show_detail()

    def _refresh_inspector(self) -> None:
        inspector = self._find_widget("#inspector", Static)
        if inspector is None:
            return
        if self.workspace not in _PANES:
            inspector.update(Text("Activity and findings from the current session."))
            return
        table = self.query_one(_PANES[self.workspace][0], DataTable)
        if not table.row_count:
            inspector.update(Text("No rows yet. Run a command or start a capture."))
            return
        row = table.get_row_at(table.cursor_row)
        labels = _PANES[self.workspace][1]
        inspector.update(Text("\n".join(f"{label}: {value}" for label, value in zip(labels, row))))

    # -- live capture -------------------------------------------------------

    def _cmd_stop(self, rest: str) -> None:
        """Validate `/stop` before ending the capture.

        `/stop` takes no arguments. It used to discard `rest` entirely, so
        `/stop "` stopped a running capture instead of reporting the
        unmatched quote — a destructive action taken on input the command
        contract says must be refused (issue #542). Rejection happens
        before `action_stop_capture`, so the capture survives.
        """

        tokens = self._split_slash_args("stop", rest)
        if tokens is None:
            return
        if tokens:
            self._emit_alert(
                f"/stop takes no arguments; got {len(tokens)}. "
                "Use /stop on its own to end the capture."
            )
            return
        self.action_stop_capture()

    def _cmd_capture(self, rest: str) -> None:
        """Validate `/capture <iface>` before touching the capture session.

        Every rejection happens before `_start_capture`, so malformed input
        can never stop or replace a running capture nor erase displayed
        history. `/capture` takes exactly one interface: it is a hotkey for
        the app-native live stream, which has nowhere to put flags. Extra
        tokens are rejected rather than silently dropped so that
        `/capture can0 --dbc truck.dbc` cannot look like it applied a DBC —
        use the full `capture` command for anything with options.
        """

        tokens = self._split_slash_args("capture", rest)
        if tokens is None:
            return
        if not tokens:
            self._emit_alert("/capture requires an interface; e.g. /capture vcan0")
            return
        if len(tokens) > 1:
            self._emit_alert(
                "/capture takes a single interface; "
                f"got {len(tokens)} arguments. Run the full `capture` command for options."
            )
            return
        interface = tokens[0].strip()
        if not interface:
            self._emit_alert("/capture interface must not be empty; e.g. /capture vcan0")
            return
        self._start_capture(interface)

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
        # The interval timer keeps firing while the app tears down, after the
        # widget tree is gone. Nothing is left to draw at that point, so skip
        # the whole drain rather than reaching a query that cannot match.
        if not self.is_running:
            return
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
        if pane == "traffic":
            self.query_one("#empty-state", Static).display = False
        if pane == self.workspace:
            self._refresh_inspector()

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
        if pane == self.workspace:
            self._refresh_inspector()

    def _reset_panes(self) -> None:
        for pane in _PANES:
            self._rows[pane].clear()
            self._row_keys[pane].clear()
            self.query_one(_PANES[pane][0], DataTable).clear()
        self._refresh_status()
        self._refresh_j1939_ribbon()
        self._apply_workspace()
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

    def _find_widget(self, selector: str, kind: type[_WidgetT]) -> _WidgetT | None:
        """Return the widget, or None when it is not mounted.

        Teardown does not stop the capture drain timer synchronously, so a
        refresh can still run after the widget tree is gone. `is_running` is
        cleared first in practice, but the ordering is Textual's to change;
        callers that run off a timer should tolerate a missing node.
        """
        try:
            return self.query_one(selector, kind)
        except NoMatches:
            return None

    def _emit_alert(self, line: str) -> None:
        alerts = self._find_widget("#alerts", RichLog)
        if alerts is not None:
            alerts.write(line)
            findings = self._find_widget("#findings", DataTable)
            if findings is not None:
                findings.add_row(line)
                while findings.row_count > self.backlog_cap:
                    findings.remove_row(next(iter(findings.rows)))
            self._alert_count += 1
            self._refresh_nav()

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
        bus_status = self._find_widget("#bus-status", Static)
        if bus_status is not None:
            bus_status.update(Text("  ".join(lines)))

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
        ribbon = self._find_widget("#j1939-ribbon", Static)
        if ribbon is not None:
            ribbon.update(Text("  ".join(parts) or "(no J1939 summary)"))

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
