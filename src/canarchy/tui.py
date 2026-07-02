"""Minimal text-mode TUI shell for CANarchy."""

from __future__ import annotations

import enum
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from canarchy.cli import CommandResult


class _HotkeyResult(enum.Enum):
    """Disposition signalled by `_handle_hotkey`."""

    LOCAL = "local"  # state-only handler ran (e.g. /help, /clear); re-render
    EXPANDED = "expanded"  # the slash command produced an argv to execute
    QUIT = "quit"  # session should end
    UNKNOWN = "unknown"  # unrecognised slash command


# Hotkey table. Each entry maps a slash command to either a CLI argv
# template (for execution through the shared command dispatch) or to a
# local action (`help`, `clear`, `quit`). Templates use `{0}` for a
# single positional argument the operator supplies after the slash
# command.
_HOTKEY_TEMPLATES: dict[str, str] = {
    "capture": "capture {0} --candump",
    "save": "session save {0}",
    "load": "session load {0}",
    "dbc": "dbc inspect {0}",
    "doctor": "doctor --text",
    "config": "config show --text",
}
_HOTKEY_HELP_ROWS: list[tuple[str, str]] = [
    ("/help", "show this hotkey table"),
    ("/quit, /exit", "exit the TUI"),
    ("/clear", "reset all panes"),
    ("/capture <iface>", "start a candump-style live capture"),
    ("/save <name>", "save the current session context"),
    ("/load <name>", "load a saved session"),
    ("/dbc <ref>", "inspect a DBC (path or `opendbc:<name>`)"),
    ("/doctor", "run environment health checks"),
    ("/config", "show the effective configuration"),
]


@dataclass(slots=True)
class TuiState:
    active_command: str | None = None
    last_result: CommandResult | None = None
    alerts: list[str] = field(default_factory=list)
    live_traffic: list[str] = field(default_factory=list)
    decoded_signals: list[str] = field(default_factory=list)
    j1939_pgn_counts: Counter[int] = field(default_factory=Counter)
    j1939_source_addresses: Counter[int] = field(default_factory=Counter)
    j1939_recent: list[str] = field(default_factory=list)
    j1939_dm1_alerts: list[str] = field(default_factory=list)
    uds_recent: list[str] = field(default_factory=list)
    bus_status: list[str] = field(default_factory=lambda: ["interface: none", "mode: idle"])


_MAX_DECODED_SIGNAL_ROWS = 12
_MAX_J1939_RECENT_ROWS = 8
_MAX_J1939_DM1_ALERTS = 4
_J1939_TOP_PGN_COUNT = 3
_J1939_TOP_SOURCE_ADDRESS_COUNT = 4
_MAX_UDS_RECENT_ROWS = 8
_MAX_TRAFFIC_ROWS = 8


@dataclass(slots=True, frozen=True)
class BacklogCaps:
    """Per-pane backlog ceilings for the fold layer.

    The line-mode renderer and the existing snapshot tests rely on the
    historical caps, so those remain the defaults. The full-screen app
    passes a larger set (its DataTables provide the real scrollback and
    the fold cap becomes a safety ceiling the operator can grow/shrink).
    """

    decoded_signals: int = _MAX_DECODED_SIGNAL_ROWS
    j1939_recent: int = _MAX_J1939_RECENT_ROWS
    j1939_dm1_alerts: int = _MAX_J1939_DM1_ALERTS
    uds_recent: int = _MAX_UDS_RECENT_ROWS
    traffic: int = _MAX_TRAFFIC_ROWS


_DEFAULT_CAPS = BacklogCaps()


def _signal_value_text(value: object) -> str:
    """Render a signal value: floats to three trimmed decimals, else str."""

    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") or "0"
    return "(none)" if value is None else str(value)


def _signal_units_text(units: object) -> str:
    """Render a signal's units column (empty when absent)."""

    return "" if units in (None, "") else str(units)


#: Column headers for the Decoded Signals DataTable.
DECODED_SIGNAL_COLUMNS = ("message", "signal", "value", "units")


def _decoded_signal_tuples(result: CommandResult) -> list[tuple[str, str, str, str]]:
    """Extract Decoded Signals rows as `(message, signal, value, units)`.

    Reuses the existing canonical structures rather than inventing a
    parallel signal model. Supported sources:

    * `decoded_message` events (emitted by `canarchy decode --dbc ...`):
      one row per signal in the `payload.signals` dict.
    * `signal` events (emitted by some downstream tooling): one row per
      event.
    * `j1939_pgn` events with `payload.decoded_signals`: one row per
      decoded signal (used by `j1939 pgn --json` enrichment).
    * `j1939 spn` observations: one row per observation; the message
      name is the PGN.
    """

    def _row(message: object, signal: object, value: object, units: object):
        return (
            "" if message is None else str(message),
            str(signal),
            _signal_value_text(value),
            _signal_units_text(units),
        )

    rows: list[tuple[str, str, str, str]] = []
    for event in result.data.get("events", []) or []:
        event_type = event.get("event_type")
        payload = event.get("payload", {}) or {}
        if event_type == "decoded_message":
            message = payload.get("message_name", "")
            for signal_name, value in (payload.get("signals") or {}).items():
                rows.append(_row(message, signal_name, value, None))
        elif event_type == "signal":
            rows.append(
                _row(
                    payload.get("message_name") or "",
                    payload.get("signal_name", "(signal)"),
                    payload.get("value"),
                    payload.get("units"),
                )
            )
        elif event_type == "j1939_pgn":
            pgn_label = f"PGN {payload.get('pgn', '?')}"
            decoded = payload.get("decoded_signals")
            # `j1939 pgn` populates `decoded_signals` via
            # `pretty_j1939_support.describe_frame`, which returns a
            # `dict[str, str]` (signal name → value text). Other callers
            # may emit a list of `{name, value, units}` dicts. Handle
            # both shapes — iterating a dict and calling `.get` on the
            # string keys would otherwise raise AttributeError.
            if isinstance(decoded, dict):
                for signal_name, value in decoded.items():
                    rows.append(_row(pgn_label, signal_name, value, None))
            else:
                for entry in decoded or []:
                    if not isinstance(entry, dict):
                        continue
                    rows.append(
                        _row(
                            pgn_label,
                            entry.get("name", "(signal)"),
                            entry.get("value"),
                            entry.get("units"),
                        )
                    )

    # `canarchy j1939 spn` returns observations rather than wrapped events.
    if result.command == "j1939 spn":
        for observation in result.data.get("observations", []) or []:
            rows.append(
                _row(
                    f"PGN {observation.get('pgn', '?')}",
                    observation.get("name") or f"SPN {observation.get('spn', '?')}",
                    observation.get("value"),
                    observation.get("units"),
                )
            )

    return rows


def _decoded_signal_rows(result: CommandResult) -> list[str]:
    """Line-mode Decoded Signals rows, joined from the structured tuples."""

    lines: list[str] = []
    for message, signal, value_text, units in _decoded_signal_tuples(result):
        units_text = f" [{units}]" if units else ""
        msg = message or "(message)"
        lines.append(f"{msg}.{signal} = {value_text}{units_text}")
    return lines


#: Column headers for the J1939 recent-activity DataTable.
J1939_COLUMNS = ("pgn", "sa", "da", "prio", "data")


def _j1939_recent_tuple(payload: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Structured `(pgn, sa, da, prio, data)` row for a `j1939_pgn` event."""

    pgn = payload.get("pgn", "?")
    sa = payload.get("source_address")
    da = payload.get("destination_address")
    priority = payload.get("priority")
    data_hex = (payload.get("frame") or {}).get("data", "")
    sa_text = f"0x{sa:02X}" if isinstance(sa, int) else "?"
    da_text = "broadcast" if da == 0xFF or da is None else f"0x{da:02X}"
    prio_text = "" if priority is None else str(priority)
    return (str(pgn), sa_text, da_text, prio_text, data_hex)


def _j1939_row_tuples(result: CommandResult) -> list[tuple[str, str, str, str, str]]:
    """Structured J1939 rows for every `j1939_pgn` event in a result."""

    return [
        _j1939_recent_tuple(event.get("payload") or {})
        for event in result.data.get("events", []) or []
        if event.get("event_type") == "j1939_pgn"
    ]


def _format_j1939_recent(payload: dict[str, Any]) -> str:
    """One-row summary of a `j1939_pgn` event for the J1939 pane."""

    pgn, sa_text, da_text, prio_text, data_hex = _j1939_recent_tuple(payload)
    prio_field = f" prio={prio_text}" if prio_text else ""
    return f"pgn={pgn} sa={sa_text} da={da_text}{prio_field} data={data_hex}"


def _format_dm1_alert(message: dict[str, Any]) -> str:
    """One-row DM1 alert summary; only used when `active_dtc_count > 0`."""

    sa = message.get("source_address")
    sa_text = f"0x{sa:02X}" if isinstance(sa, int) else "?"
    transport = message.get("transport", "direct")
    active = message.get("active_dtc_count", 0)
    # The DM1 decoder emits `lamp_status` keyed by `mil`,
    # `amber_warning`, `protect`, and `red_stop` with `"on"`/`"off"`
    # string values. Fall back to the historical `lamp_summary` name
    # so a future renaming doesn't silently drop the indicator.
    lamp = message.get("lamp_status") or message.get("lamp_summary") or {}
    lit = sorted(
        name
        for name, state in lamp.items()
        if str(state).lower() not in ("off", "", "none", "false")
    )
    lamp_field = f" lamps={','.join(lit)}" if lit else ""
    dtcs = message.get("dtcs", []) or []
    sample = []
    for dtc in dtcs[:2]:
        spn = dtc.get("spn")
        fmi = dtc.get("fmi")
        sample.append(f"spn={spn}/fmi={fmi}")
    sample_text = f" [{', '.join(sample)}]" if sample else ""
    return f"DM1 sa={sa_text} transport={transport} active={active}{lamp_field}{sample_text}"


def _update_j1939_state(
    state: TuiState, result: CommandResult, caps: BacklogCaps = _DEFAULT_CAPS
) -> None:
    """Fold a command result into the J1939 pane state.

    Reads `j1939_pgn` events for PGN frequency, source-address activity,
    and recent-activity rows. Reads `j1939 dm1` messages for the alert
    ribbon when `active_dtc_count > 0`. Other commands leave the pane
    state untouched.
    """

    pgn_events: list[dict[str, Any]] = []
    for event in result.data.get("events", []) or []:
        if event.get("event_type") == "j1939_pgn":
            payload = event.get("payload") or {}
            pgn_events.append(payload)
            pgn = payload.get("pgn")
            sa = payload.get("source_address")
            if isinstance(pgn, int):
                state.j1939_pgn_counts[pgn] += 1
            if isinstance(sa, int):
                state.j1939_source_addresses[sa] += 1

    if pgn_events:
        # Newest-first within a batch: the last event the command
        # produced is the most recent observation on the bus, so put
        # it at the top of the pane.
        new_rows = [_format_j1939_recent(event) for event in reversed(pgn_events)]
        merged = new_rows + state.j1939_recent
        state.j1939_recent = merged[: caps.j1939_recent]

    # DM1 alerts come from the `j1939 dm1` command's structured output
    # (`data.messages`). `data.active_dtc_count` flags real fault
    # conditions (SPN>0, FMI != 0 / 31) so a capture full of no-fault
    # filler rows does not light up the ribbon.
    if result.command == "j1939 dm1":
        active_alerts: list[str] = []
        for message in result.data.get("messages", []) or []:
            if int(message.get("active_dtc_count", 0) or 0) > 0:
                active_alerts.append(_format_dm1_alert(message))
        if active_alerts:
            merged_alerts = active_alerts + state.j1939_dm1_alerts
            state.j1939_dm1_alerts = merged_alerts[: caps.j1939_dm1_alerts]


def _j1939_pane_lines(state: TuiState) -> list[str]:
    """Render the J1939 pane from accumulated state."""

    lines: list[str] = []
    if state.j1939_pgn_counts:
        top = state.j1939_pgn_counts.most_common(_J1939_TOP_PGN_COUNT)
        lines.append("top PGNs: " + ", ".join(f"{pgn}({count})" for pgn, count in top))
    if state.j1939_source_addresses:
        top_sa = state.j1939_source_addresses.most_common(_J1939_TOP_SOURCE_ADDRESS_COUNT)
        lines.append("source addresses: " + ", ".join(f"0x{sa:02X}({n})" for sa, n in top_sa))
    if state.j1939_dm1_alerts:
        lines.append("!! DM1 active faults !!")
        lines.extend(state.j1939_dm1_alerts)
    if state.j1939_recent:
        lines.append("recent:")
        lines.extend(state.j1939_recent)
    return lines


def _format_uds_transaction(payload: dict[str, Any]) -> str:
    """One-row summary of a `uds_transaction` event for the UDS pane.

    Columns mirror `docs/tui_plan.md#uds-transactions`: service (id +
    name), request id, response id, ECU address, response summary or
    NRC name. Truncated multi-frame responses (`complete=false`) are
    prefixed with `!!` so the operator notices ISO-TP reassembly that
    didn't finish.
    """

    service = payload.get("service")
    service_text = f"0x{service:02X}" if isinstance(service, int) else "?"
    service_name = payload.get("service_name") or ""
    request_id = payload.get("request_id")
    response_id = payload.get("response_id")
    req_text = f"0x{request_id:03X}" if isinstance(request_id, int) else "?"
    resp_text = f"0x{response_id:03X}" if isinstance(response_id, int) else "?"
    ecu = payload.get("ecu_address")
    ecu_text = "?" if ecu is None else (f"0x{ecu:02X}" if isinstance(ecu, int) else str(ecu))
    nrc_name = payload.get("negative_response_name")
    if nrc_name:
        outcome = f"NRC={nrc_name}"
    elif payload.get("response_summary"):
        outcome = f"resp={payload['response_summary']}"
    else:
        outcome = f"resp={payload.get('response_data', '')}"
    prefix = "!! incomplete " if payload.get("complete") is False else ""
    name_text = f" ({service_name})" if service_name else ""
    return (
        f"{prefix}service={service_text}{name_text} req={req_text}->{resp_text} "
        f"ecu={ecu_text} {outcome}"
    )


#: Column headers for the UDS transactions DataTable.
UDS_COLUMNS = ("service", "name", "req→resp", "ecu", "outcome")


def _uds_transaction_tuple(payload: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Structured `(service, name, req→resp, ecu, outcome)` UDS row.

    Incomplete ISO-TP reassembly (`complete=false`) is flagged with a
    leading `!!` in the outcome column, mirroring the line-mode prefix.
    """

    service = payload.get("service")
    service_text = f"0x{service:02X}" if isinstance(service, int) else "?"
    service_name = payload.get("service_name") or ""
    request_id = payload.get("request_id")
    response_id = payload.get("response_id")
    req_text = f"0x{request_id:03X}" if isinstance(request_id, int) else "?"
    resp_text = f"0x{response_id:03X}" if isinstance(response_id, int) else "?"
    ecu = payload.get("ecu_address")
    ecu_text = "?" if ecu is None else (f"0x{ecu:02X}" if isinstance(ecu, int) else str(ecu))
    nrc_name = payload.get("negative_response_name")
    if nrc_name:
        outcome = f"NRC={nrc_name}"
    elif payload.get("response_summary"):
        outcome = f"resp={payload['response_summary']}"
    else:
        outcome = f"resp={payload.get('response_data', '')}"
    if payload.get("complete") is False:
        outcome = f"!! incomplete {outcome}"
    return (service_text, service_name, f"{req_text}→{resp_text}", ecu_text, outcome)


def _uds_row_tuples(result: CommandResult) -> list[tuple[str, str, str, str, str]]:
    """Structured UDS rows for every `uds_transaction` event in a result."""

    return [
        _uds_transaction_tuple(event.get("payload") or {})
        for event in result.data.get("events", []) or []
        if event.get("event_type") == "uds_transaction"
    ]


def _update_uds_state(
    state: TuiState, result: CommandResult, caps: BacklogCaps = _DEFAULT_CAPS
) -> None:
    """Fold a command result into the UDS pane state.

    Reads `uds_transaction` events; ignores other event types. Keeps
    the newest `caps.uds_recent` transactions at the top.
    """

    new_rows: list[str] = []
    for event in result.data.get("events", []) or []:
        if event.get("event_type") != "uds_transaction":
            continue
        payload = event.get("payload") or {}
        new_rows.append(_format_uds_transaction(payload))
    if not new_rows:
        return
    # Newest event in the batch goes to the top of the pane.
    merged = list(reversed(new_rows)) + state.uds_recent
    state.uds_recent = merged[: caps.uds_recent]


def _uds_pane_lines(state: TuiState) -> list[str]:
    if not state.uds_recent:
        return []
    lines = ["recent:"]
    lines.extend(state.uds_recent)
    return lines


def _clear_panes(state: TuiState) -> None:
    """Reset every pane to its initial state. Triggered by `/clear`."""

    state.active_command = None
    state.last_result = None
    state.alerts = []
    state.live_traffic = []
    state.decoded_signals = []
    state.j1939_pgn_counts.clear()
    state.j1939_source_addresses.clear()
    state.j1939_recent = []
    state.j1939_dm1_alerts = []
    state.uds_recent = []
    state.bus_status = ["interface: none", "mode: idle"]


def _hotkey_help_lines() -> list[str]:
    width = max(len(name) for name, _ in _HOTKEY_HELP_ROWS) + 2
    return [f"  {name.ljust(width)}{description}" for name, description in _HOTKEY_HELP_ROWS]


def _handle_hotkey(
    line: str,
    state: TuiState,
    emit: Callable[[str], None] = print,
) -> tuple[_HotkeyResult, str | None]:
    """Dispatch a slash command.

    Returns `(disposition, expanded_argv_string)`. When the
    disposition is ``EXPANDED`` the caller runs ``expanded_argv_string``
    through the shared command path so the existing parser handles the rest.

    Diagnostic lines (help table, error hints) are written through
    ``emit`` — one call per line. It defaults to ``print`` so the
    fold-layer tests keep their stdout behaviour; the full-screen app
    passes a sink that routes the lines to its Alerts log instead of
    printing into the terminal surface.
    """

    parts = line.strip().split(None, 1)
    name = parts[0][1:].lower()  # strip the leading "/"
    arg = parts[1] if len(parts) > 1 else ""

    if name in ("quit", "exit"):
        return _HotkeyResult.QUIT, None
    if name == "help":
        emit("Hotkeys:")
        for row in _hotkey_help_lines():
            emit(row)
        return _HotkeyResult.LOCAL, None
    if name == "clear":
        _clear_panes(state)
        return _HotkeyResult.LOCAL, None
    template = _HOTKEY_TEMPLATES.get(name)
    if template is None:
        emit(f"unknown hotkey: /{name} (try /help)")
        return _HotkeyResult.UNKNOWN, None
    if "{0}" in template and not arg:
        emit(f"/{name} requires an argument; see /help")
        return _HotkeyResult.UNKNOWN, None
    return _HotkeyResult.EXPANDED, template.format(arg)


def run_tui(execute_command: Any) -> int:
    """Launch the full-screen CANarchy TUI.

    The TUI is an interactive, full-screen Textual application, so it
    requires a real terminal. When stdin/stdout are not a TTY (piped
    input, CI) it prints guidance and exits non-zero rather than hanging
    on a terminal it cannot drive — use the individual commands for
    non-interactive and scripted runs.
    """

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "canarchy tui requires an interactive terminal. "
            "Run the individual commands (capture, decode, j1939 ...) "
            "for non-interactive or scripted use.",
            file=sys.stderr,
        )
        return 1

    # Imported lazily so the lightweight fold-layer helpers in this module
    # can be used (and unit-tested) without importing the Textual runtime.
    from canarchy.tui_app import run_canarchy_tui

    return run_canarchy_tui(execute_command)


def _update_state(
    state: TuiState, result: CommandResult, caps: BacklogCaps = _DEFAULT_CAPS
) -> None:
    payload = result.to_payload()
    state.active_command = result.command
    state.last_result = result
    state.bus_status = [
        f"command: {result.command}",
        f"mode: {result.data.get('mode', 'unknown')}",
    ]
    if "interface" in result.data:
        state.bus_status.insert(1, f"interface: {result.data['interface']}")
    elif "file" in result.data:
        state.bus_status.insert(1, f"source: {result.data['file']}")
    elif result.command == "gateway":
        state.bus_status.insert(1, f"path: {result.data.get('src')} -> {result.data.get('dst')}")

    state.alerts = list(payload["warnings"])
    for error in payload["errors"]:
        state.alerts.append(f"error: {error['code']}: {error['message']}")
    # Pull `replay_event` activity into the alerts pane so the
    # operator sees what the replay plan actually emitted alongside
    # the rest of the canonical envelope's warnings/errors.
    for event in result.data.get("events", []) or []:
        if event.get("event_type") == "replay_event":
            event_payload = event.get("payload") or {}
            state.alerts.append(
                f"replay action={event_payload.get('action', '?')} "
                f"reason={event_payload.get('reason', '')}".strip()
            )

    state.live_traffic = _traffic_lines(result, caps.traffic)
    new_signal_rows = _decoded_signal_rows(result)
    if new_signal_rows:
        # Keep the most recent rows; older entries fall off the bottom of
        # the pane so the display stays bounded. Newest at the top.
        merged = new_signal_rows + state.decoded_signals
        state.decoded_signals = merged[: caps.decoded_signals]
    _update_j1939_state(state, result, caps)
    _update_uds_state(state, result, caps)


#: Column headers for the Live Traffic DataTable.
TRAFFIC_COLUMNS = ("time", "src", "kind", "id / pgn", "dlc", "data")


def _fmt_ts(ts: object) -> str:
    """Format an event timestamp as `HH:MM:SS.mmm` (empty when absent)."""

    if not isinstance(ts, (int, float)):
        return ""
    return time.strftime("%H:%M:%S", time.localtime(ts)) + f".{int((ts % 1) * 1000):03d}"


def _traffic_row_tuples(result: CommandResult) -> list[tuple[str, str, str, str, str, str]]:
    """Structured Live Traffic rows over the canonical event types.

    Columns are `TRAFFIC_COLUMNS`. Covers the streaming/observable event
    types (`frame`, `j1939_pgn`, `uds_transaction`, `replay_event`,
    `alert`); command-specific non-event fallbacks that `_traffic_lines`
    handles are surfaced through their dedicated panes instead.
    """

    rows: list[tuple[str, str, str, str, str, str]] = []
    for event in result.data.get("events", []) or []:
        event_type = event.get("event_type")
        payload = event.get("payload", {}) or {}
        src = str(event.get("source") or "")
        ts = _fmt_ts(event.get("timestamp"))
        if event_type == "frame":
            frame = payload.get("frame", {}) or {}
            arb = frame.get("arbitration_id")
            id_text = f"0x{arb:X}" if isinstance(arb, int) else "?"
            rows.append(
                (
                    ts or _fmt_ts(frame.get("timestamp")),
                    src or str(frame.get("interface") or ""),
                    "frame",
                    id_text,
                    str(frame.get("dlc", "")),
                    str(frame.get("data", "")),
                )
            )
        elif event_type == "j1939_pgn":
            frame = payload.get("frame", {}) or {}
            sa = payload.get("source_address")
            sa_text = f"0x{sa:02X}" if isinstance(sa, int) else "?"
            rows.append(
                (ts, src, "j1939", f"pgn={payload.get('pgn', '?')} sa={sa_text}", "",
                 str(frame.get("data", "")))
            )
        elif event_type == "uds_transaction":
            service = payload.get("service")
            svc_text = f"0x{service:02X}" if isinstance(service, int) else "?"
            rows.append(
                (ts, src, "uds", svc_text, "", str(payload.get("response_data", "")))
            )
        elif event_type == "replay_event":
            rows.append(
                (ts, src, "replay", str(payload.get("action", "?")), "",
                 str(payload.get("reason", "")))
            )
        elif event_type == "alert":
            rows.append(
                (ts, src, "alert", str(payload.get("level", "")), "",
                 str(payload.get("message", "")))
            )
    return rows


def _traffic_lines(result: CommandResult, cap: int = _MAX_TRAFFIC_ROWS) -> list[str]:
    lines: list[str] = []
    for event in result.data.get("events", []):
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        if event_type == "frame":
            frame = payload["frame"]
            lines.append(
                f"frame id=0x{frame['arbitration_id']:X} dlc={frame['dlc']} data={frame['data']}"
            )
        elif event_type == "j1939_pgn":
            lines.append(
                f"j1939 pgn={payload['pgn']} sa=0x{payload['source_address']:02X} data={payload['frame']['data']}"
            )
        elif event_type == "uds_transaction":
            lines.append(
                f"uds service=0x{payload['service']:02X} ecu={payload['ecu_address']} resp={payload['response_data']}"
            )
        elif event_type == "replay_event":
            lines.append(f"replay action={payload['action']}")
        elif event_type == "alert":
            lines.append(f"alert {payload['level']}: {payload['message']}")

    if not lines:
        if result.command == "j1939 spn":
            for observation in result.data.get("observations", []):
                lines.append(
                    f"spn {observation['spn']} value={observation['value']} {observation['units']}"
                )
        elif result.command == "j1939 tp sessions":
            for session in result.data.get("sessions", []):
                lines.append(
                    f"tp pgn={session['transfer_pgn']} packets={session['packet_count']}/{session['total_packets']}"
                )
        elif result.command == "j1939 dm1":
            for message in result.data.get("messages", []):
                lines.append(
                    f"dm1 sa=0x{message['source_address']:02X} dtcs={message['active_dtc_count']} transport={message['transport']}"
                )
    return lines[:cap]


def _render(state: TuiState) -> None:
    print("== CANarchy TUI ==")
    print("[Bus Status]")
    for line in state.bus_status:
        print(line)
    print("[Live Traffic]")
    for line in state.live_traffic or ["(no traffic)"]:
        print(line)
    print("[Decoded Signals]")
    for line in state.decoded_signals or ["(no decoded signals)"]:
        print(line)
    print("[J1939]")
    for line in _j1939_pane_lines(state) or ["(no J1939 activity)"]:
        print(line)
    print("[UDS]")
    for line in _uds_pane_lines(state) or ["(no UDS transactions)"]:
        print(line)
    print("[Alerts]")
    for line in state.alerts or ["(no alerts)"]:
        print(line)
    print("[Command Entry]")
    print("Enter existing CANarchy commands, or `/help` for hotkeys; `/quit` to exit.")
