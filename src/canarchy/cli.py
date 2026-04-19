"""CLI entry point for CANarchy."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from canarchy.dbc import DbcError, decode_frames, encode_message
from canarchy import __version__
from canarchy.exporter import ExportError, export_artifact
from canarchy.j1939 import SUPPORTED_SPN_DEFINITIONS, dm1_messages, spn_observations, transport_protocol_sessions, decompose_arbitration_id
from canarchy.models import (
    AlertEvent,
    CanFrame,
    J1939ObservationEvent,
    ReplayActionEvent,
    serialize_events,
)
from canarchy.replay import build_replay_plan
from canarchy.reverse_engineering import counter_candidates, entropy_candidates
from canarchy.session import SessionError, SessionStore, build_session_context
from canarchy.transport import LocalTransport, TransportError, config_show_payload, generate_frames
from canarchy.tui import run_tui
from canarchy.uds import uds_services_payload

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_TRANSPORT_ERROR = 2
EXIT_DECODE_ERROR = 3
EXIT_PARTIAL_SUCCESS = 4
TRANSPORT_COMMANDS = {"capture", "send", "filter", "stats", "generate"}
DBC_COMMANDS = {"decode", "encode"}
J1939_COMMANDS = {"j1939 monitor", "j1939 decode", "j1939 pgn", "j1939 spn", "j1939 tp", "j1939 dm1"}
SESSION_COMMANDS = {"session save", "session load", "session show"}
UDS_COMMANDS = {"uds scan", "uds trace", "uds services"}
CONFIG_COMMANDS = {"config show"}
RE_COMMANDS = {"re counters", "re entropy"}
IMPLEMENTED_COMMANDS = TRANSPORT_COMMANDS | DBC_COMMANDS | J1939_COMMANDS | SESSION_COMMANDS | UDS_COMMANDS | CONFIG_COMMANDS | RE_COMMANDS | {"mcp serve", "replay", "gateway", "shell", "export"}


class CliUsageError(Exception):
    """Raised when the user input is invalid."""


@dataclass(slots=True)
class ErrorDetail:
    code: str
    message: str
    hint: str | None = None

    def to_payload(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        return payload


class CommandError(Exception):
    """Raised for structured command failures."""

    def __init__(
        self,
        *,
        command: str,
        exit_code: int,
        errors: list[ErrorDetail],
        data: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__(errors[0].message)
        self.command = command
        self.exit_code = exit_code
        self.errors = errors
        self.data = data or {}
        self.warnings = warnings or []


class CanarchyArgumentParser(argparse.ArgumentParser):
    """Argument parser that maps usage errors to the project's exit codes."""

    def error(self, message: str) -> None:
        raise CliUsageError(message)


@dataclass(slots=True)
class CommandResult:
    command: str
    data: dict[str, Any]
    warnings: list[str] | None = None
    errors: list[dict[str, str]] | None = None
    ok: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "data": self.data,
            "warnings": self.warnings or [],
            "errors": self.errors or [],
        }


def error_result(
    command: str,
    *,
    errors: list[ErrorDetail],
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> CommandResult:
    return CommandResult(
        ok=False,
        command=command,
        data=data or {},
        warnings=warnings,
        errors=[error.to_payload() for error in errors],
    )


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="emit JSON output")
    group.add_argument("--jsonl", action="store_true", help="emit JSONL output")
    group.add_argument("--table", action="store_true", help="emit table output")
    group.add_argument("--raw", action="store_true", help="emit raw output")


def build_parser() -> CanarchyArgumentParser:
    parser = CanarchyArgumentParser(
        prog="canarchy", description="CLI-first CAN security research toolkit"
    )
    parser.add_argument("--version", action="version", version=f"canarchy {__version__}")

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    capture = subparsers.add_parser("capture", help="capture CAN traffic")
    capture.add_argument("interface")
    capture.add_argument(
        "--candump",
        action="store_true",
        help="emit candump-style human output for live capture",
    )
    add_output_arguments(capture)
    capture.set_defaults(command="capture")

    send = subparsers.add_parser("send", help="send CAN frames")
    send.add_argument("interface")
    send.add_argument("frame_id")
    send.add_argument("data")
    add_output_arguments(send)
    send.set_defaults(command="send")

    generate = subparsers.add_parser("generate", help="generate CAN frames")
    generate.add_argument("interface")
    generate.add_argument("--id", default="R", help="frame ID as hex or R for random")
    generate.add_argument("--dlc", default="R", help="data length 0-8 or R for random")
    generate.add_argument("--data", default="R", help="payload hex, R for random, I for incrementing")
    generate.add_argument("--count", type=int, default=1, help="number of frames to generate")
    generate.add_argument("--gap", type=float, default=200.0, help="inter-frame gap in milliseconds")
    generate.add_argument("--extended", action="store_true", help="force 29-bit extended IDs")
    add_output_arguments(generate)
    generate.set_defaults(command="generate")

    gateway = subparsers.add_parser("gateway", help="bridge frames between CAN interfaces")
    gateway.add_argument("src")
    gateway.add_argument("dst")
    gateway.add_argument("--src-backend", help="python-can interface type for the source bus")
    gateway.add_argument("--dst-backend", help="python-can interface type for the destination bus")
    gateway.add_argument("--bidirectional", action="store_true", help="also forward frames from dst back to src")
    gateway.add_argument("--count", type=int, help="stop after forwarding N frames")
    add_output_arguments(gateway)
    gateway.set_defaults(command="gateway")

    replay = subparsers.add_parser("replay", help="replay recorded traffic")
    replay.add_argument("file")
    replay.add_argument("--rate", type=float, default=1.0)
    add_output_arguments(replay)
    replay.set_defaults(command="replay")

    filter_parser = subparsers.add_parser("filter", help="filter recorded traffic")
    filter_parser.add_argument("file", nargs="?", default=None)
    filter_parser.add_argument("--stdin", action="store_true", help="read JSONL FrameEvents from stdin")
    filter_parser.add_argument("expression")
    add_output_arguments(filter_parser)
    filter_parser.set_defaults(command="filter")

    stats = subparsers.add_parser("stats", help="summarize traffic statistics")
    stats.add_argument("file")
    add_output_arguments(stats)
    stats.set_defaults(command="stats")

    decode = subparsers.add_parser("decode", help="decode traffic using DBC")
    decode.add_argument("file", nargs="?", default=None)
    decode.add_argument("--stdin", action="store_true", help="read JSONL FrameEvents from stdin")
    decode.add_argument("--dbc", required=True)
    add_output_arguments(decode)
    decode.set_defaults(command="decode")

    encode = subparsers.add_parser("encode", help="encode signals using DBC")
    encode.add_argument("--dbc", required=True)
    encode.add_argument("message")
    encode.add_argument("signals", nargs="*", help="key=value signal assignments")
    add_output_arguments(encode)
    encode.set_defaults(command="encode")

    export = subparsers.add_parser("export", help="export session data")
    export.add_argument("source")
    export.add_argument("destination")
    add_output_arguments(export)
    export.set_defaults(command="export")

    session = subparsers.add_parser("session", help="manage saved sessions")
    session_subparsers = session.add_subparsers(dest="session_action", required=True)

    session_save = session_subparsers.add_parser("save", help="save a session")
    session_save.add_argument("name")
    session_save.add_argument("--interface")
    session_save.add_argument("--dbc")
    session_save.add_argument("--capture")
    add_output_arguments(session_save)
    session_save.set_defaults(command="session save")

    session_load = session_subparsers.add_parser("load", help="load a session")
    session_load.add_argument("name")
    add_output_arguments(session_load)
    session_load.set_defaults(command="session load")

    session_show = session_subparsers.add_parser("show", help="show session state")
    add_output_arguments(session_show)
    session_show.set_defaults(command="session show")

    j1939 = subparsers.add_parser("j1939", help="J1939 protocol workflows")
    j1939_subparsers = j1939.add_subparsers(dest="j1939_action", required=True)

    j1939_monitor = j1939_subparsers.add_parser("monitor", help="monitor J1939 traffic")
    j1939_monitor.add_argument("interface", nargs="?", default=None)
    j1939_monitor.add_argument("--pgn", type=int)
    add_output_arguments(j1939_monitor)
    j1939_monitor.set_defaults(command="j1939 monitor")

    j1939_decode = j1939_subparsers.add_parser("decode", help="decode J1939 traffic")
    j1939_decode.add_argument("file", nargs="?", default=None)
    j1939_decode.add_argument("--stdin", action="store_true", help="read JSONL FrameEvents from stdin")
    add_output_arguments(j1939_decode)
    j1939_decode.set_defaults(command="j1939 decode")

    j1939_pgn = j1939_subparsers.add_parser("pgn", help="inspect a J1939 PGN")
    j1939_pgn.add_argument("pgn", type=int)
    j1939_pgn.add_argument("--file", help="inspect the PGN within a capture file")
    add_output_arguments(j1939_pgn)
    j1939_pgn.set_defaults(command="j1939 pgn")

    j1939_spn = j1939_subparsers.add_parser("spn", help="inspect a J1939 SPN")
    j1939_spn.add_argument("spn", type=int)
    j1939_spn.add_argument("--file", help="inspect the SPN within a capture file")
    add_output_arguments(j1939_spn)
    j1939_spn.set_defaults(command="j1939 spn")

    j1939_tp = j1939_subparsers.add_parser("tp", help="inspect J1939 transport protocol")
    j1939_tp.add_argument("file")
    add_output_arguments(j1939_tp)
    j1939_tp.set_defaults(command="j1939 tp")

    j1939_dm1 = j1939_subparsers.add_parser("dm1", help="inspect J1939 DM1 traffic")
    j1939_dm1.add_argument("file")
    add_output_arguments(j1939_dm1)
    j1939_dm1.set_defaults(command="j1939 dm1")

    uds = subparsers.add_parser("uds", help="UDS protocol workflows")
    uds_subparsers = uds.add_subparsers(dest="uds_action", required=True)

    uds_scan = uds_subparsers.add_parser("scan", help="scan for UDS responders")
    uds_scan.add_argument("interface")
    add_output_arguments(uds_scan)
    uds_scan.set_defaults(command="uds scan")

    uds_trace = uds_subparsers.add_parser("trace", help="trace UDS transactions")
    uds_trace.add_argument("interface")
    add_output_arguments(uds_trace)
    uds_trace.set_defaults(command="uds trace")

    uds_services = uds_subparsers.add_parser("services", help="list UDS services")
    add_output_arguments(uds_services)
    uds_services.set_defaults(command="uds services")

    re_parser = subparsers.add_parser("re", help="reverse engineering helpers")
    re_subparsers = re_parser.add_subparsers(dest="re_action", required=True)

    re_signals = re_subparsers.add_parser("signals", help="infer signal candidates")
    re_signals.add_argument("file")
    add_output_arguments(re_signals)
    re_signals.set_defaults(command="re signals")

    re_counters = re_subparsers.add_parser("counters", help="detect counters")
    re_counters.add_argument("file")
    add_output_arguments(re_counters)
    re_counters.set_defaults(command="re counters")

    re_entropy = re_subparsers.add_parser("entropy", help="rank signal entropy")
    re_entropy.add_argument("file")
    add_output_arguments(re_entropy)
    re_entropy.set_defaults(command="re entropy")

    re_correlate = re_subparsers.add_parser("correlate", help="correlate signal candidates")
    re_correlate.add_argument("file")
    add_output_arguments(re_correlate)
    re_correlate.set_defaults(command="re correlate")

    fuzz = subparsers.add_parser("fuzz", help="active fuzzing workflows")
    fuzz_subparsers = fuzz.add_subparsers(dest="fuzz_action", required=True)

    fuzz_replay = fuzz_subparsers.add_parser("replay", help="fuzz replay traffic")
    fuzz_replay.add_argument("file")
    add_output_arguments(fuzz_replay)
    fuzz_replay.set_defaults(command="fuzz replay")

    fuzz_mutate = fuzz_subparsers.add_parser("mutate", help="mutate captured traffic")
    fuzz_mutate.add_argument("file")
    add_output_arguments(fuzz_mutate)
    fuzz_mutate.set_defaults(command="fuzz mutate")

    fuzz_id = fuzz_subparsers.add_parser("id", help="fuzz arbitration IDs")
    fuzz_id.add_argument("interface")
    add_output_arguments(fuzz_id)
    fuzz_id.set_defaults(command="fuzz id")

    config = subparsers.add_parser("config", help="inspect CANarchy configuration")
    config_subparsers = config.add_subparsers(dest="config_action", required=True)
    config_show = config_subparsers.add_parser("show", help="show effective transport configuration")
    add_output_arguments(config_show)
    config_show.set_defaults(command="config show")

    mcp = subparsers.add_parser("mcp", help="MCP server workflows")
    mcp_subparsers = mcp.add_subparsers(dest="mcp_action", required=True)
    mcp_serve = mcp_subparsers.add_parser("serve", help="start MCP server over stdio")
    mcp_serve.set_defaults(command="mcp serve")

    shell = subparsers.add_parser("shell", help="start the interactive shell")
    shell.add_argument("--command", dest="shell_command", help="run a single shell command")
    add_output_arguments(shell)
    shell.set_defaults(command="shell")

    tui = subparsers.add_parser("tui", help="start the TUI")
    tui.add_argument("--command", dest="tui_command", help="run a single TUI command and exit")
    add_output_arguments(tui)
    tui.set_defaults(command="tui")

    return parser


def format_name(args: argparse.Namespace) -> str:
    for name in ("json", "jsonl", "table", "raw"):
        if getattr(args, name, False):
            return name
    return "table"


def requested_output_format(argv: Sequence[str] | None) -> str:
    if argv is None:
        return "table"

    for name in ("json", "jsonl", "table", "raw"):
        if f"--{name}" in argv:
            return name
    return "table"


def validate_args(args: argparse.Namespace) -> None:
    if args.command == "replay" and args.rate <= 0:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_RATE",
                    message="Replay rate must be greater than zero.",
                    hint="Pass a positive value to --rate, such as 1.0 or 0.5.",
                )
            ],
            data={"rate": args.rate},
        )

    # Validate stdin usage for commands that support it
    stdin_commands = {"decode", "filter", "j1939 decode"}
    if args.command in stdin_commands:
        if getattr(args, "stdin", False):
            if getattr(args, "file", None) is not None:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="STDIN_AND_FILE_SPECIFIED",
                            message="Cannot specify both --stdin and a capture file",
                            hint="Use either --stdin to read from pipe or provide a capture file.",
                        )
                    ],
                )
        else:
            if getattr(args, "file", None) is None:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="MISSING_INPUT",
                            message="Either a capture file or --stdin must be specified",
                            hint="Provide a capture file path or use --stdin to read from pipe.",
                        )
                    ],
                )

    if args.command == "send":
        try:
            int(args.frame_id, 0)
        except ValueError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_FRAME_ID",
                        message="Frame ID must be an integer such as 0x123 or 291.",
                        hint="Pass a standard or extended CAN identifier.",
                    )
                ],
                data={"frame_id": args.frame_id},
            ) from exc

        if len(args.data) % 2 != 0:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_FRAME_DATA",
                        message="Frame data must contain an even number of hex characters.",
                        hint="Use pairs of hex digits such as 11223344.",
                    )
                ],
                data={"data": args.data},
            )

    if args.command == "generate":
        if args.id.upper() != "R":
            try:
                int(args.id, 16)
            except ValueError as exc:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_FRAME_ID",
                            message="Frame ID must be a hex value such as 0x123 or R for random.",
                            hint="Pass a standard or extended CAN identifier, or R.",
                        )
                    ],
                    data={"id": args.id},
                ) from exc

        if args.dlc.upper() != "R":
            try:
                dlc = int(args.dlc)
                if dlc < 0 or dlc > 8:
                    raise ValueError
            except ValueError as exc:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_DLC",
                            message="DLC must be an integer between 0 and 8, or R for random.",
                            hint="Use a value from 0 to 8, or R.",
                        )
                    ],
                    data={"dlc": args.dlc},
                ) from exc

        if args.data.upper() not in {"R", "I"}:
            if len(args.data) % 2 != 0:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_FRAME_DATA",
                            message="Frame data must contain an even number of hex characters.",
                            hint="Use pairs of hex digits such as 11223344, or R or I.",
                        )
                    ],
                    data={"data": args.data},
                )

        if args.count < 1:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_COUNT",
                        message="Frame count must be at least 1.",
                        hint="Pass a positive integer to --count.",
                    )
                ],
                data={"count": args.count},
            )

        if args.gap < 0:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_GAP",
                        message="Inter-frame gap must be zero or greater.",
                        hint="Pass a non-negative millisecond value to --gap.",
                    )
                ],
                data={"gap": args.gap},
            )

    if args.command == "gateway" and args.count is not None and args.count < 1:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_COUNT",
                    message="Frame count must be at least 1.",
                    hint="Pass a positive integer to --count.",
                )
            ],
            data={"count": args.count},
        )

    if args.command in {"j1939 monitor", "j1939 pgn"} and getattr(args, "pgn", None) is not None:
        if args.pgn < 0 or args.pgn > 262143:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_PGN",
                        message="J1939 PGN must be between 0 and 262143.",
                        hint="Use a valid 18-bit PGN value.",
                    )
                ],
                data={"pgn": args.pgn},
            )

    if args.command == "j1939 pgn" and not getattr(args, "file", None):
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="CAPTURE_FILE_REQUIRED",
                    message="J1939 PGN inspection requires a capture file.",
                    hint="Pass `--file <capture.candump>` to inspect a PGN in recorded traffic.",
                )
            ],
            data={"pgn": args.pgn},
        )

    if args.command == "j1939 spn" and args.spn < 0:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_SPN",
                    message="J1939 SPN must be zero or greater.",
                    hint="Use a non-negative SPN value.",
                )
            ],
            data={"spn": args.spn},
        )

    if args.command == "j1939 spn" and not getattr(args, "file", None):
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="CAPTURE_FILE_REQUIRED",
                    message="J1939 SPN inspection requires a capture file.",
                    hint="Pass `--file <capture.candump>` to inspect SPN values in recorded traffic.",
                )
            ],
            data={"spn": args.spn},
        )

    if args.command == "j1939 spn" and args.spn not in SUPPORTED_SPN_DEFINITIONS:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="J1939_SPN_UNSUPPORTED",
                    message=f"J1939 SPN {args.spn} is not supported by the current decoder set.",
                    hint="Use one of the currently supported SPNs or extend the curated decoder map.",
                )
            ],
            data={"spn": args.spn},
        )

    if args.command == "encode":
        for assignment in args.signals:
            if "=" not in assignment:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_SIGNAL_ASSIGNMENT",
                            message="Signal assignments must use key=value syntax.",
                            hint="Pass signal values like `CoolantTemp=55`.",
                        )
                    ],
                    data={"signal": assignment},
                )

    if args.command in {"session save", "session load"}:
        if "/" in args.name or args.name in {".", ".."}:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_SESSION_NAME",
                        message="Session names must not contain path separators.",
                        hint="Use a simple name such as `lab-a` or `truck-session`.",
                    )
                ],
                data={"name": args.name},
                )


def frame_from_stream_event(event: dict[str, Any], *, command: str, line_num: int) -> CanFrame:
    if event.get("event_type") != "frame":
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_STREAM_EVENT",
                    message=f"Expected frame event, got {event.get('event_type')} at line {line_num}",
                    hint="Input stream must contain JSONL FrameEvents.",
                )
            ],
        )

    try:
        frame_data = event["payload"]["frame"]
        return CanFrame(
            arbitration_id=frame_data["arbitration_id"],
            data=bytes.fromhex(frame_data["data"]),
            timestamp=frame_data.get("timestamp"),
            interface=frame_data.get("interface"),
            is_extended_id=frame_data.get("is_extended_id", False),
            is_remote_frame=frame_data.get("is_remote_frame", False),
            is_error_frame=frame_data.get("is_error_frame", False),
            bitrate_switch=frame_data.get("bitrate_switch", False),
            error_state_indicator=frame_data.get("error_state_indicator", False),
            frame_format=frame_data.get("frame_format", "can"),
        )
    except (KeyError, ValueError) as exc:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_STREAM_EVENT",
                    message=f"Invalid frame event at line {line_num}: {str(exc)}",
                    hint="Frame event must have valid frame payload.",
                )
            ],
        ) from exc


def frames_from_stdin(*, command: str) -> list[CanFrame]:
    frames: list[CanFrame] = []
    for line_num, line in enumerate(sys.stdin, 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise CommandError(
                command=command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_STREAM_EVENT",
                        message=f"Invalid JSON at line {line_num}: {str(exc)}",
                        hint="Each line must be a valid JSON object.",
                    )
                ],
            ) from exc
        frames.append(frame_from_stream_event(event, command=command, line_num=line_num))

    if not frames:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="NO_STREAM_EVENTS",
                    message="No valid frame events found in stdin",
                    hint="Provide JSONL FrameEvents via stdin or use a capture file.",
                )
            ],
        )
    return frames


def sample_frame(*, interface: str | None = None, frame_format: str = "can") -> CanFrame:
    data = bytes.fromhex("11223344") if frame_format == "can" else bytes.fromhex("1122334455667788")
    return CanFrame(
        arbitration_id=0x18FEEE31,
        data=data,
        frame_format=frame_format,
        interface=interface,
        is_extended_id=True,
        timestamp=0.0,
    )


def parse_send_frame(args: argparse.Namespace) -> CanFrame:
    frame_id = int(args.frame_id, 0)
    is_extended_id = frame_id > 0x7FF
    try:
        data = bytes.fromhex(args.data)
    except ValueError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FRAME_DATA",
                    message="Frame data must be valid hexadecimal bytes.",
                    hint="Use hex byte pairs without separators, such as 11223344.",
                )
            ],
            data={"data": args.data},
        ) from exc

    try:
        return CanFrame(
            arbitration_id=frame_id,
            data=data,
            interface=args.interface,
            is_extended_id=is_extended_id,
            timestamp=0.0,
        )
    except ValueError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FRAME",
                    message=str(exc),
                    hint="Check the frame identifier, payload length, and frame format.",
                )
            ],
            data={"frame_id": args.frame_id, "data": args.data},
        ) from exc


def parse_signal_assignments(assignments: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for assignment in assignments:
        key, raw_value = assignment.split("=", 1)
        value: Any = raw_value
        lowered = raw_value.lower()
        if lowered in {"true", "false"}:
            value = lowered == "true"
        else:
            try:
                if any(char in raw_value for char in (".", "e", "E")):
                    value = float(raw_value)
                else:
                    value = int(raw_value, 0)
            except ValueError:
                value = raw_value
        parsed[key] = value
    return parsed


def transport_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    backend_metadata = transport.backend_metadata()
    implementation = (
        "live transport"
        if backend_metadata["transport_backend"] != "scaffold"
        else "scaffold transport"
    )
    if args.command == "capture":
        if args.candump and backend_metadata["transport_backend"] == "scaffold":
            raise TransportError(
                "CANDUMP_LIVE_BACKEND_REQUIRED",
                "Candump mode requires a live CAN backend.",
                "Set `CANARCHY_TRANSPORT_BACKEND=python-can` to use live candump capture.",
            )
        return (
            {
                "display": "candump" if args.candump else "structured",
                "mode": "passive",
                "interface": args.interface,
                **backend_metadata,
                "status": "implemented",
                "implementation": implementation,
            },
            transport.capture_events(args.interface),
            [],
        )
    if args.command == "send":
        frame = parse_send_frame(args)
        return (
            {
                "mode": "active",
                "interface": args.interface,
                "frame": frame.to_payload(),
                **backend_metadata,
                "status": "implemented",
                "implementation": implementation,
            },
            transport.send_events(args.interface, frame),
            ["Active transmission is intentionally distinct from passive monitoring workflows."],
        )
    if args.command == "generate":
        frames = generate_frames(
            args.interface,
            id_spec=args.id,
            dlc_spec=args.dlc,
            data_spec=args.data,
            count=args.count,
            gap_ms=args.gap,
            extended=args.extended,
        )
        return (
            {
                "interface": args.interface,
                "mode": "active",
                "frame_count": len(frames),
                "gap_ms": args.gap,
                **backend_metadata,
                "status": "implemented",
                "implementation": implementation,
            },
            transport.generate_events(args.interface, frames, gap_ms=args.gap),
            ["Frame generation is an active transmission workflow; use intentionally on a controlled bus."],
        )
    if args.command == "filter":
        frames = frames_from_stdin(command=args.command) if args.stdin else transport.frames_from_file(args.file)
        return (
            {
                "mode": "passive",
                "file": args.file,
                "expression": args.expression,
                "status": "implemented",
                "implementation": "file-backed analysis",
                "input": "stdin" if args.stdin else "file",
            },
            transport.filter_events(args.file if not args.stdin else "<stdin>", args.expression, frames=frames),
            [],
        )
    if args.command == "stats":
        stats = transport.stats(args.file)
        return (
            {
                "mode": "passive",
                "file": args.file,
                **stats.to_payload(),
                "status": "implemented",
                "implementation": "file-backed analysis",
            },
            [],
            [],
        )
    raise AssertionError(f"unsupported transport command: {args.command}")


def j1939_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    if args.command == "j1939 monitor":
        implementation = "transport-backed" if args.interface else "sample/reference provider"
        return (
            {
                "mode": "passive",
                "interface": args.interface,
                "pgn_filter": args.pgn,
                "implementation": implementation,
            },
            transport.j1939_monitor_events(args.pgn, interface=args.interface),
            [],
        )
    if args.command == "j1939 decode":
        frames = frames_from_stdin(command=args.command) if args.stdin else transport.frames_from_file(args.file)

        # Filter to only extended ID frames for J1939
        j1939_frames = [frame for frame in frames if frame.is_extended_id]
        
        # Build J1939 events from our frames
        events = []
        for frame in j1939_frames:
            identifier = decompose_arbitration_id(frame.arbitration_id)
            events.append(
                J1939ObservationEvent(
                    pgn=identifier.pgn,
                    source_address=identifier.source_address,
                    destination_address=identifier.destination_address,
                    priority=identifier.priority,
                    frame=frame,
                    source="transport.j1939.decode",
                )
            )
        
        warnings = []
        if not events:
            warnings.append("No J1939 extended ID frames were found in the input.")
        return (
            {
                "mode": "passive",
                "file": args.file,
                "input": "stdin" if args.stdin else "file",
            },
            serialize_events(events),
            warnings,
        )
    if args.command == "j1939 pgn":
        return (
            {"mode": "passive", "pgn": args.pgn, "file": args.file},
            transport.j1939_decode_events(args.file, args.pgn),
            [],
        )
    if args.command == "j1939 spn":
        observations = spn_observations(transport.frames_from_file(args.file), args.spn)
        warnings = []
        if not observations:
            warnings.append("No observations for the selected SPN were found in the capture.")
        return (
            {
                "mode": "passive",
                "spn": args.spn,
                "file": args.file,
                "decoder": "curated_spn_map",
                "observation_count": len(observations),
                "observations": observations,
            },
            [],
            warnings,
        )
    if args.command == "j1939 tp":
        sessions = transport_protocol_sessions(transport.frames_from_file(args.file))
        warnings = []
        if not sessions:
            warnings.append("No J1939 transport protocol sessions were found in the capture.")
        return (
            {
                "mode": "passive",
                "file": args.file,
                "session_count": len(sessions),
                "sessions": sessions,
            },
            [],
            warnings,
        )
    if args.command == "j1939 dm1":
        messages = dm1_messages(transport.frames_from_file(args.file))
        warnings = []
        if not messages:
            warnings.append("No J1939 DM1 messages were found in the capture.")
        return (
            {
                "mode": "passive",
                "file": args.file,
                "message_count": len(messages),
                "messages": messages,
                "source_count": len({message["source_address"] for message in messages}),
            },
            [],
            warnings,
        )
    raise AssertionError(f"unsupported j1939 command: {args.command}")


def dbc_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    if args.command == "decode":
        frames = frames_from_stdin(command=args.command) if args.stdin else transport.frames_from_file(args.file)
        
        events = decode_frames(frames, args.dbc)
        warnings = []
        if not events:
            warnings.append("No frames in the capture matched messages from the selected DBC.")
        matched_messages = len(
            [event for event in events if event["event_type"] == "decoded_message"]
        )
        return (
            {
                "dbc": args.dbc,
                "file": args.file,
                "matched_messages": matched_messages,
                "mode": "passive",
                "input": "stdin" if args.stdin else "file",
            },
            events,
            warnings,
        )
    if args.command == "encode":
        signals = parse_signal_assignments(args.signals)
        frame, events = encode_message(args.dbc, args.message, signals)
        return (
            {
                "dbc": args.dbc,
                "frame": frame.to_payload(),
                "message": args.message,
                "mode": "active",
                "signals": signals,
            },
            events,
            [
                "Encoding prepares an active transmit frame; send it intentionally via a transmit workflow."
            ],
        )
    raise AssertionError(f"unsupported dbc command: {args.command}")


def uds_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    backend_metadata = transport.backend_metadata()
    implementation = (
        "transport-backed"
        if backend_metadata["transport_backend"] != "scaffold"
        else "sample/reference provider"
    )
    if args.command == "uds scan":
        events = transport.uds_scan_events(args.interface)
        return (
            {
                "interface": args.interface,
                "mode": "active",
                "responder_count": len(events),
                **backend_metadata,
                "implementation": implementation,
            },
            events,
            ["UDS scanning is active and should be used intentionally on a controlled bus."],
        )
    if args.command == "uds trace":
        events = transport.uds_trace_events(args.interface)
        return (
            {
                "interface": args.interface,
                "mode": "passive",
                "transaction_count": len(events),
                **backend_metadata,
                "implementation": implementation,
            },
            events,
            [],
        )
    if args.command == "uds services":
        services = uds_services_payload()
        return (
            {
                "mode": "reference",
                "service_count": len(services),
                "services": services,
            },
            [],
            [],
        )
    raise AssertionError(f"unsupported uds command: {args.command}")


def gateway_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    events = transport.gateway_events(
        args.src,
        args.dst,
        src_backend=args.src_backend,
        dst_backend=args.dst_backend,
        bidirectional=args.bidirectional,
        count=args.count,
    )
    return (
        {
            "mode": "active",
            "src": args.src,
            "dst": args.dst,
            "src_backend": args.src_backend,
            "dst_backend": args.dst_backend,
            "bidirectional": args.bidirectional,
            "count": args.count,
            "forwarded_frames": len(events),
            "status": "implemented",
            "implementation": "live transport gateway",
        },
        events,
        [],
    )


def export_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    export_data = export_artifact(args.source, args.destination)
    return (
        {
            "mode": "stateful",
            **export_data,
            "status": "implemented",
            "implementation": "structured artifact export",
        },
        [],
        [],
    )


def replay_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    frames = transport.frames_from_file(args.file)
    plan = build_replay_plan(frames, rate=args.rate)
    return (
        {
            "duration": plan.duration,
            "file": args.file,
            "frame_count": plan.frame_count,
            "mode": "active",
            "rate": plan.rate,
        },
        plan.events,
        ["Replay schedules active frame transmission; use it intentionally on a controlled bus."],
    )


def session_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    store = SessionStore()
    if args.command == "session save":
        record = store.save(args.name, build_session_context(args))
        return (
            {
                "mode": "stateful",
                "session": record.to_payload(),
            },
            [],
            [],
        )
    if args.command == "session load":
        record = store.load(args.name)
        return (
            {
                "mode": "stateful",
                "session": record.to_payload(),
            },
            [],
            [],
        )
    if args.command == "session show":
        payload = store.show()
        payload["mode"] = "stateful"
        return (payload, [], [])
    raise AssertionError(f"unsupported session command: {args.command}")


def reverse_engineering_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    if args.command == "re counters":
        frames = transport.frames_from_file(args.file)
        candidates = counter_candidates(frames)
        warnings: list[str] = []
        if not candidates:
            warnings.append("No likely counters met the current heuristic threshold.")
        return (
            {
                "mode": "passive",
                "file": args.file,
                "analysis": "counter_detection",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "implementation": "file-backed heuristic analysis",
            },
            [],
            warnings,
        )
    if args.command == "re entropy":
        frames = transport.frames_from_file(args.file)
        candidates = entropy_candidates(frames)
        warnings: list[str] = []
        if not candidates:
            warnings.append("No arbitration IDs with payload bytes were found for entropy analysis.")
        return (
            {
                "mode": "passive",
                "file": args.file,
                "analysis": "entropy_ranking",
                "candidate_count": len(candidates),
                "candidates": candidates,
                "implementation": "file-backed heuristic analysis",
            },
            [],
            warnings,
        )
    raise AssertionError(f"unsupported reverse-engineering command: {args.command}")


def build_events(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command in TRANSPORT_COMMANDS:
        _, events, _ = transport_payload(args)
        return events
    if args.command in DBC_COMMANDS:
        _, events, _ = dbc_payload(args)
        return events
    if args.command in J1939_COMMANDS:
        _, events, _ = j1939_payload(args)
        return events
    if args.command in SESSION_COMMANDS:
        _, events, _ = session_payload(args)
        return events
    if args.command in UDS_COMMANDS:
        _, events, _ = uds_payload(args)
        return events
    if args.command in RE_COMMANDS:
        _, events, _ = reverse_engineering_payload(args)
        return events
    if args.command == "export":
        _, events, _ = export_payload(args)
        return events
    if args.command == "gateway":
        _, events, _ = gateway_payload(args)
        return events
    if args.command == "replay":
        _, events, _ = replay_payload(args)
        return events
    else:
        events = [
            AlertEvent(
                level="info",
                code="COMMAND_PLANNED",
                message="Command implementation is not complete yet.",
                source="cli",
            ).to_event()
        ]

    return serialize_events(events)


def build_result(args: argparse.Namespace) -> CommandResult:
    warnings = [] if args.command in IMPLEMENTED_COMMANDS else ["Command implementation is not complete yet."]
    data = {
        key: value
        for key, value in vars(args).items()
        if not key.endswith("_action")
        and key not in {"command", "command_name", "json", "jsonl", "table", "raw"}
        and value is not None
    }
    if args.command in TRANSPORT_COMMANDS:
        transport_data, transport_events, transport_warnings = transport_payload(args)
        data.update(transport_data)
        data["events"] = transport_events
        warnings.extend(transport_warnings)
    elif args.command == "replay":
        replay_data, replay_events, replay_warnings = replay_payload(args)
        data.update(replay_data)
        data["events"] = replay_events
        warnings.extend(replay_warnings)
    elif args.command in SESSION_COMMANDS:
        session_data, session_events, session_warnings = session_payload(args)
        data.update(session_data)
        data["events"] = session_events
        warnings.extend(session_warnings)
    elif args.command in DBC_COMMANDS:
        decode_data, decode_events, decode_warnings = dbc_payload(args)
        data.update(decode_data)
        data["events"] = decode_events
        warnings.extend(decode_warnings)
    elif args.command in UDS_COMMANDS:
        uds_data, uds_events, uds_warnings = uds_payload(args)
        data.update(uds_data)
        data["events"] = uds_events
        warnings.extend(uds_warnings)
    elif args.command in RE_COMMANDS:
        re_data, re_events, re_warnings = reverse_engineering_payload(args)
        data.update(re_data)
        data["events"] = re_events
        warnings.extend(re_warnings)
    elif args.command == "export":
        export_data, export_events, export_warnings = export_payload(args)
        data.update(export_data)
        data["events"] = export_events
        warnings.extend(export_warnings)
    elif args.command == "gateway":
        gateway_data, gateway_events, gateway_warnings = gateway_payload(args)
        data.update(gateway_data)
        data["events"] = gateway_events
        warnings.extend(gateway_warnings)
    elif args.command in J1939_COMMANDS:
        protocol_data, protocol_events, protocol_warnings = j1939_payload(args)
        data.update(protocol_data)
        data["events"] = protocol_events
        warnings.extend(protocol_warnings)
    elif args.command in CONFIG_COMMANDS:
        data.update(config_show_payload())
    else:
        data["events"] = build_events(args)
    if args.command not in IMPLEMENTED_COMMANDS:
        data["status"] = "planned"
        data["implementation"] = "command surface scaffold"
    return CommandResult(
        command=args.command,
        data=data,
        warnings=warnings,
    )


def format_j1939_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    events = result.data.get("events", [])
    if result.command == "j1939 monitor" and result.data.get("pgn_filter") is not None:
        lines.append(f"pgn_filter: {result.data['pgn_filter']}")
    if result.command == "j1939 decode":
        lines.append(f"file: {result.data['file']}")
    if result.command == "j1939 pgn":
        lines.append(f"pgn: {result.data['pgn']}")

    if result.command == "j1939 spn":
        lines.append(f"spn: {result.data['spn']}")
        lines.append(f"file: {result.data['file']}")
        lines.append("observations:")
        observations = result.data.get("observations", [])
        if not observations:
            lines.append("- no spn observations")
            return lines
        for observation in observations:
            destination = observation["destination_address"]
            destination_text = f"0x{destination:02X}" if destination is not None else "broadcast"
            lines.append(
                "- "
                f"spn={observation['spn']} "
                f"name={observation['name']} "
                f"value={observation['value']} "
                f"units={observation['units']} "
                f"pgn={observation['pgn']} "
                f"sa=0x{observation['source_address']:02X} "
                f"da={destination_text}"
            )
        return lines

    if result.command == "j1939 tp":
        lines.append(f"file: {result.data['file']}")
        lines.append("sessions:")
        sessions = result.data.get("sessions", [])
        if not sessions:
            lines.append("- no transport sessions")
            return lines
        for session in sessions:
            destination = session["destination_address"]
            destination_text = f"0x{destination:02X}" if destination is not None else "broadcast"
            lines.append(
                "- "
                f"type={session['session_type']} "
                f"pgn={session['transfer_pgn']} "
                f"sa=0x{session['source_address']:02X} "
                f"da={destination_text} "
                f"bytes={session['total_bytes']} "
                f"packets={session['packet_count']}/{session['total_packets']} "
                f"complete={session['complete']}"
            )
        return lines

    if result.command == "j1939 dm1":
        lines.append(f"file: {result.data['file']}")
        lines.append("messages:")
        messages = result.data.get("messages", [])
        if not messages:
            lines.append("- no dm1 messages")
            return lines
        for message in messages:
            dtc_text = ",".join(
                f"spn={dtc['spn']}/fmi={dtc['fmi']}" for dtc in message["dtcs"]
            ) or "none"
            lines.append(
                "- "
                f"sa=0x{message['source_address']:02X} "
                f"transport={message['transport']} "
                f"dtcs={message['active_dtc_count']} "
                f"mil={message['lamp_status']['mil']} "
                f"amber={message['lamp_status']['amber_warning']} "
                f"codes={dtc_text}"
            )
        return lines

    lines.append("observations:")
    if not events:
        lines.append("- no j1939 observations")
        return lines

    for event in events:
        payload = event["payload"]
        frame = payload["frame"]
        destination = payload["destination_address"]
        destination_text = f"0x{destination:02X}" if destination is not None else "broadcast"
        lines.append(
            "- "
            f"pgn={payload['pgn']} "
            f"sa=0x{payload['source_address']:02X} "
            f"da={destination_text} "
            f"prio={payload['priority']} "
            f"id=0x{frame['arbitration_id']:08X} "
            f"data={frame['data']}"
        )
    return lines


def format_uds_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "uds services":
        lines.append(f"services: {result.data.get('service_count', 0)}")
        lines.append("catalog:")
        services = result.data.get("services", [])
        if not services:
            lines.append("- no uds services")
            return lines
        for service in services:
            lines.append(
                "- "
                f"sid=0x{service['service']:02X} "
                f"name={service['name']} "
                f"positive=0x{service['positive_response_service']:02X} "
                f"category={service['category']} "
                f"subfunction={service['requires_subfunction']}"
            )
        return lines

    lines.append(f"interface: {result.data.get('interface', 'unknown')}")
    events = result.data.get("events", [])
    if result.command == "uds scan":
        lines.append(f"responders: {result.data.get('responder_count', 0)}")
    else:
        lines.append(f"transactions: {result.data.get('transaction_count', 0)}")

    lines.append("transactions:")
    if not events:
        lines.append("- no uds transactions")
        return lines

    for event in events:
        payload = event["payload"]
        ecu = payload["ecu_address"]
        ecu_text = f"0x{ecu:02X}" if ecu is not None else "unknown"
        lines.append(
            "- "
            f"service=0x{payload['service']:02X} "
            f"name={payload['service_name']} "
            f"ecu={ecu_text} "
            f"req_id=0x{payload['request_id']:03X} "
            f"resp_id=0x{payload['response_id']:03X} "
            f"req={payload['request_data']} "
            f"resp={payload['response_data']}"
        )
    return lines


def format_re_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    lines.append(f"file: {result.data.get('file')}")
    lines.append(f"analysis: {result.data.get('analysis')}")
    lines.append(f"candidate_count: {result.data.get('candidate_count', 0)}")
    lines.append("candidates:")
    candidates = result.data.get("candidates", [])
    if not candidates:
        if result.command == "re entropy":
            lines.append("- no entropy candidates")
        else:
            lines.append("- no likely counters")
        return lines

    if result.command == "re entropy":
        for candidate in candidates:
            lines.append(
                "- "
                f"id=0x{candidate['arbitration_id']:X} "
                f"frames={candidate['frame_count']} "
                f"mean={candidate['mean_byte_entropy']} "
                f"max={candidate['max_byte_entropy']} "
                f"low_sample={candidate['low_sample']} "
                f"why={candidate['rationale']}"
            )
            for byte_summary in candidate["byte_entropies"]:
                lines.append(
                    "  "
                    f"byte={byte_summary['byte_position']} "
                    f"entropy={byte_summary['entropy']} "
                    f"unique={byte_summary['unique_values']}"
                )
        return lines

    for candidate in candidates:
        lines.append(
            "- "
            f"id=0x{candidate['arbitration_id']:X} "
            f"start={candidate['start_bit']} "
            f"len={candidate['bit_length']} "
            f"score={candidate['score']} "
            f"ratio={candidate['monotonicity_ratio']} "
            f"rollover={candidate['rollover_detected']} "
            f"samples={candidate['sample_count']} "
            f"range={candidate['observed_min']}..{candidate['observed_max']} "
            f"why={candidate['rationale']}"
        )
    return lines


def format_candump_lines(result: CommandResult) -> list[str]:
    lines: list[str] = []
    for event in result.data.get("events", []):
        if event.get("event_type") != "frame":
            continue
        frame = event["payload"]["frame"]
        interface = frame["interface"] or result.data.get("interface") or "can0"
        timestamp = event.get("timestamp")
        timestamp_text = (
            f"({timestamp:0.6f})" if isinstance(timestamp, (int, float)) else "(0.000000)"
        )
        line = f"{timestamp_text} {interface} {format_candump_frame(frame)}"
        if isinstance(event.get("source"), str) and event["source"].startswith("gateway."):
            direction = event["source"].removeprefix("gateway.")
            line = f"{line}  [{direction}]"
        lines.append(line)
    if not lines:
        lines.append("(no frames captured)")
    return lines


def format_gateway_lines(result: CommandResult) -> list[str]:
    lines = [f"gateway: src={result.data.get('src')} dst={result.data.get('dst')}"]
    lines.extend(format_candump_lines(result))
    return lines


def format_candump_frame(frame: dict[str, Any]) -> str:
    arbitration_id = frame["arbitration_id"]
    if frame["is_error_frame"]:
        frame_id = f"{(0x20000000 | arbitration_id):08X}"
        return f"{frame_id}#{frame['data'].upper()}"

    frame_id = f"{arbitration_id:08X}" if frame["is_extended_id"] else f"{arbitration_id:03X}"
    if frame["frame_format"] == "can_fd":
        flags = 0
        if frame["bitrate_switch"]:
            flags |= 0x1
        if frame["error_state_indicator"]:
            flags |= 0x2
        return f"{frame_id}##{flags:X}{frame['data'].upper()}"
    if frame["is_remote_frame"]:
        return f"{frame_id}#R"
    return f"{frame_id}#{frame['data'].upper()}"


def emit_live_capture(args: argparse.Namespace, output_format: str) -> int:
    """Stream live capture frames until Ctrl+C, honouring *output_format*.

    All formats stream continuously rather than returning a fixed batch:

    * ``table`` / ``raw`` / ``candump`` — candump-style text line per frame
    * ``json`` / ``jsonl`` — one ``json.dumps(event)`` line per frame
    """
    transport = LocalTransport()
    text_mode = output_format in {"table", "raw"}
    try:
        for event in transport.capture_stream_events(args.interface):
            if event.get("event_type") != "frame":
                continue
            if text_mode:
                frame = event["payload"]["frame"]
                interface = frame["interface"] or args.interface
                timestamp = event.get("timestamp")
                timestamp_text = (
                    f"({timestamp:0.6f})"
                    if isinstance(timestamp, (int, float))
                    else "(0.000000)"
                )
                print(f"{timestamp_text} {interface} {format_candump_frame(frame)}")
            else:
                print(json.dumps(event, sort_keys=True))
    except TransportError as exc:
        emit_result(
            error_result(
                "capture",
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
            output_format,
        )
        return EXIT_TRANSPORT_ERROR
    except KeyboardInterrupt:
        return EXIT_OK
    return EXIT_OK


def emit_live_candump(args: argparse.Namespace) -> int:
    """Backwards-compatible wrapper — delegates to emit_live_capture."""
    return emit_live_capture(args, "table")


def emit_live_gateway(args: argparse.Namespace) -> int:
    transport = LocalTransport()
    print(f"gateway: src={args.src} dst={args.dst}")
    try:
        for event in transport.gateway_stream_events(
            args.src,
            args.dst,
            src_backend=args.src_backend,
            dst_backend=args.dst_backend,
            bidirectional=args.bidirectional,
            count=args.count,
        ):
            frame = event["payload"]["frame"]
            interface = frame["interface"] or args.src
            timestamp = event.get("timestamp")
            timestamp_text = (
                f"({timestamp:0.6f})" if isinstance(timestamp, (int, float)) else "(0.000000)"
            )
            direction = str(event["source"]).removeprefix("gateway.")
            print(f"{timestamp_text} {interface} {format_candump_frame(frame)}  [{direction}]")
    except KeyboardInterrupt:
        return EXIT_OK
    return EXIT_OK


def emit_result(result: CommandResult, output_format: str) -> None:
    payload = result.to_payload()
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True))
        return

    if output_format == "jsonl":
        events = payload.get("data", {}).get("events")
        if result.ok and isinstance(events, list) and events:
            for event in events:
                print(json.dumps(event, sort_keys=True))
            for warning in payload["warnings"]:
                print(
                    json.dumps(
                        AlertEvent(
                            level="warning",
                            message=warning,
                            source=f"cli.{result.command}",
                        ).to_event().to_payload(),
                        sort_keys=True,
                    )
                )
            return
        print(json.dumps(payload, sort_keys=True))
        return

    if output_format == "raw":
        if result.ok and result.command == "gateway":
            for line in format_gateway_lines(result):
                print(line)
            return
        if result.ok and result.command == "capture" and result.data.get("display") == "candump":
            for line in format_candump_lines(result):
                print(line)
            return
        if result.ok:
            print(result.command)
        elif payload["errors"]:
            print(payload["errors"][0]["message"])
        return

    if (
        output_format == "table"
        and result.ok
        and result.command == "capture"
        and result.data.get("display") == "candump"
    ):
        for line in format_candump_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "table" and result.ok and result.command == "gateway":
        for line in format_gateway_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "table" and result.ok and result.command in J1939_COMMANDS:
        for line in format_j1939_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "table" and result.ok and result.command in UDS_COMMANDS:
        for line in format_uds_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "table" and result.ok and result.command in RE_COMMANDS:
        for line in format_re_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "table" and result.ok and result.command == "generate":
        print(f"command: {result.command}")
        print(f"interface: {result.data.get('interface', 'unknown')}")
        print(f"frames: {result.data.get('frame_count', 0)}")
        for line in format_candump_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "table" and result.ok and result.command == "config show":
        sources = result.data.get("sources", {})
        print("Effective transport configuration:")
        for field in ("backend", "interface", "capture_limit", "capture_timeout"):
            src = sources.get(field, "?")
            print(f"  {field}: {result.data.get(field)}  [{src}]")
        config_file = result.data.get("config_file", "")
        found = result.data.get("config_file_found", False)
        status = "found" if found else "not found"
        print(f"config file: {config_file}  [{status}]")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    stream = None
    if result.ok:
        print(f"command: {result.command}", file=stream)
    else:
        print(f"command: {result.command}", file=stream)

    for key, value in result.data.items():
        print(f"{key}: {value}", file=stream)
    for warning in payload["warnings"]:
        print(f"warning: {warning}", file=stream)
    for error in payload["errors"]:
        print(f"error: {error['code']}: {error['message']}", file=stream)
        if "hint" in error:
            print(f"hint: {error['hint']}", file=stream)


def run_shell(shell_command: str | None) -> int:
    if shell_command is not None:
        return main(shlex.split(shell_command))

    from canarchy.completion import install_completion
    install_completion()

    while True:
        try:
            line = input("canarchy> ")
        except EOFError:
            return EXIT_OK
        except KeyboardInterrupt:
            # Ctrl+C at the prompt — clear the line and re-prompt.
            print()
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"exit", "quit"}:
            return EXIT_OK
        try:
            main(shlex.split(stripped))
        except SystemExit:
            # --help and --version call sys.exit(); stay in the shell.
            pass
        except KeyboardInterrupt:
            # Ctrl+C during a command — print a newline and re-prompt.
            print()


def execute_command(argv: Sequence[str] | None = None) -> tuple[int, CommandResult | None]:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliUsageError as exc:
        return (
            EXIT_USER_ERROR,
            error_result(
                "cli",
                errors=[
                    ErrorDetail(
                        code="INVALID_ARGUMENTS",
                        message=str(exc),
                        hint="Run `canarchy --help` to inspect the available commands and flags.",
                    )
                ],
            ),
        )

    try:
        validate_args(args)
        if args.command in {"shell", "tui"}:
            return (
                EXIT_USER_ERROR,
                error_result(
                    args.command,
                    errors=[
                        ErrorDetail(
                            code="TUI_COMMAND_UNSUPPORTED",
                            message="The TUI command entry does not support nested interactive front ends.",
                            hint="Run domain commands like `capture`, `decode`, or `j1939 monitor` from the TUI.",
                        )
                    ],
                ),
            )
        return EXIT_OK, build_result(args)
    except SessionError as exc:
        return (
            EXIT_USER_ERROR,
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
        )
    except DbcError as exc:
        return (
            EXIT_DECODE_ERROR,
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
        )
    except TransportError as exc:
        return (
            EXIT_TRANSPORT_ERROR,
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
        )
    except ExportError as exc:
        return (
            EXIT_USER_ERROR,
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
        )
    except CommandError as exc:
        return (
            exc.exit_code,
            error_result(exc.command, errors=exc.errors, data=exc.data, warnings=exc.warnings),
        )


def main(argv: Sequence[str] | None = None) -> int:
    output_format = requested_output_format(argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliUsageError as exc:
        result = error_result(
            "cli",
            errors=[
                ErrorDetail(
                    code="INVALID_ARGUMENTS",
                    message=str(exc),
                    hint="Run `canarchy --help` to inspect the available commands and flags.",
                )
            ],
        )
        emit_result(result, output_format)
        return EXIT_USER_ERROR
    output_format = format_name(args)
    if args.command == "mcp serve":
        from canarchy.mcp_server import run_server
        run_server()
        return EXIT_OK
    if args.command == "shell":
        return run_shell(args.shell_command)
    if args.command == "tui":
        return run_tui(execute_command, command=args.tui_command)
    if args.command == "capture":
        return emit_live_capture(args, output_format)
    if args.command == "gateway" and output_format in {"table", "raw"}:
        return emit_live_gateway(args)

    exit_code, result = execute_command(argv)
    if result is not None:
        emit_result(result, output_format)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
