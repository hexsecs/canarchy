"""Minimal text-mode TUI shell for CANarchy."""

from __future__ import annotations

import shlex
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from canarchy.completion import install_completion

if TYPE_CHECKING:
    from canarchy.cli import CommandResult


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
    bus_status: list[str] = field(default_factory=lambda: ["interface: none", "mode: idle"])


_MAX_DECODED_SIGNAL_ROWS = 12
_MAX_J1939_RECENT_ROWS = 8
_MAX_J1939_DM1_ALERTS = 4
_J1939_TOP_PGN_COUNT = 3
_J1939_TOP_SOURCE_ADDRESS_COUNT = 4


def _format_signal_row(*, message: str, signal: str, value: object, units: object) -> str:
    """Format one row for the Decoded Signals pane.

    Columns mirror `docs/tui_plan.md#decoded-signals`: message, signal,
    value, units. Values that are floats are rounded to three decimal
    places so the pane stays readable; everything else is stringified
    as-is.
    """

    if isinstance(value, float):
        value_text = f"{value:.3f}".rstrip("0").rstrip(".") or "0"
    else:
        value_text = "(none)" if value is None else str(value)
    units_text = "" if units in (None, "") else f" [{units}]"
    msg = message or "(message)"
    return f"{msg}.{signal} = {value_text}{units_text}"


def _decoded_signal_rows(result: CommandResult) -> list[str]:
    """Extract Decoded Signals pane rows from a command result.

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

    rows: list[str] = []
    for event in result.data.get("events", []) or []:
        event_type = event.get("event_type")
        payload = event.get("payload", {}) or {}
        if event_type == "decoded_message":
            message = payload.get("message_name", "")
            for signal_name, value in (payload.get("signals") or {}).items():
                rows.append(
                    _format_signal_row(message=message, signal=signal_name, value=value, units=None)
                )
        elif event_type == "signal":
            rows.append(
                _format_signal_row(
                    message=payload.get("message_name") or "",
                    signal=payload.get("signal_name", "(signal)"),
                    value=payload.get("value"),
                    units=payload.get("units"),
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
                    rows.append(
                        _format_signal_row(
                            message=pgn_label,
                            signal=signal_name,
                            value=value,
                            units=None,
                        )
                    )
            else:
                for entry in decoded or []:
                    if not isinstance(entry, dict):
                        continue
                    rows.append(
                        _format_signal_row(
                            message=pgn_label,
                            signal=entry.get("name", "(signal)"),
                            value=entry.get("value"),
                            units=entry.get("units"),
                        )
                    )

    # `canarchy j1939 spn` returns observations rather than wrapped events.
    if result.command == "j1939 spn":
        for observation in result.data.get("observations", []) or []:
            rows.append(
                _format_signal_row(
                    message=f"PGN {observation.get('pgn', '?')}",
                    signal=observation.get("name") or f"SPN {observation.get('spn', '?')}",
                    value=observation.get("value"),
                    units=observation.get("units"),
                )
            )

    return rows


def _format_j1939_recent(payload: dict[str, Any]) -> str:
    """One-row summary of a `j1939_pgn` event for the J1939 pane."""

    pgn = payload.get("pgn", "?")
    sa = payload.get("source_address")
    da = payload.get("destination_address")
    priority = payload.get("priority")
    data_hex = (payload.get("frame") or {}).get("data", "")
    sa_text = f"0x{sa:02X}" if isinstance(sa, int) else "?"
    da_text = "broadcast" if da == 0xFF or da is None else f"0x{da:02X}"
    prio_text = "" if priority is None else f" prio={priority}"
    return f"pgn={pgn} sa={sa_text} da={da_text}{prio_text} data={data_hex}"


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


def _update_j1939_state(state: TuiState, result: CommandResult) -> None:
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
        state.j1939_recent = merged[:_MAX_J1939_RECENT_ROWS]

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
            state.j1939_dm1_alerts = merged_alerts[:_MAX_J1939_DM1_ALERTS]


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


def run_tui(
    execute_command: Any,
    *,
    command: str | None = None,
) -> int:
    state = TuiState()
    _render(state)

    if command is not None:
        return _run_tui_command(command, state, execute_command)

    install_completion()

    while True:
        try:
            line = input("canarchy-tui> ")
        except EOFError:
            return 0
        except KeyboardInterrupt:
            # Ctrl+C at the prompt — clear the line and re-prompt.
            print()
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"exit", "quit"}:
            return 0
        _run_tui_command(stripped, state, execute_command)


def _run_tui_command(command: str, state: TuiState, execute_command: Any) -> int:
    argv = shlex.split(command)
    try:
        exit_code, result = execute_command(argv)
    except SystemExit:
        # --help and --version call sys.exit(); stay in the TUI.
        return 0
    except KeyboardInterrupt:
        # Ctrl+C during a command — print a newline and stay in the TUI.
        print()
        return 0
    if result is not None:
        _update_state(state, result)
        _render(state)
    return exit_code


def _update_state(state: TuiState, result: CommandResult) -> None:
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

    state.live_traffic = _traffic_lines(result)
    new_signal_rows = _decoded_signal_rows(result)
    if new_signal_rows:
        # Keep the most recent rows; older entries fall off the bottom of
        # the pane so the display stays bounded. Newest at the top.
        merged = new_signal_rows + state.decoded_signals
        state.decoded_signals = merged[:_MAX_DECODED_SIGNAL_ROWS]
    _update_j1939_state(state, result)


def _traffic_lines(result: CommandResult) -> list[str]:
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
    return lines[:8]


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
    print("[Alerts]")
    for line in state.alerts or ["(no alerts)"]:
        print(line)
    print("[Command Entry]")
    print("Enter existing CANarchy commands or `quit`.")
