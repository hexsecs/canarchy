"""Minimal text-mode TUI shell for CANarchy."""

from __future__ import annotations

import shlex
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
    bus_status: list[str] = field(default_factory=lambda: ["interface: none", "mode: idle"])


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

        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"exit", "quit"}:
            return 0
        _run_tui_command(stripped, state, execute_command)


def _run_tui_command(command: str, state: TuiState, execute_command: Any) -> int:
    argv = shlex.split(command)
    exit_code, result = execute_command(argv)
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
        elif result.command == "j1939 tp":
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
    print("[Alerts]")
    for line in state.alerts or ["(no alerts)"]:
        print(line)
    print("[Command Entry]")
    print("Enter existing CANarchy commands or `quit`.")
