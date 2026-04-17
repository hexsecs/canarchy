"""CLI entry point for CANarchy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from canarchy.dbc import DbcError, decode_frames, encode_message
from canarchy.models import (
    AlertEvent,
    CanFrame,
    ReplayActionEvent,
    serialize_events,
)
from canarchy.replay import build_replay_plan
from canarchy.transport import LocalTransport, TransportError

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_TRANSPORT_ERROR = 2
EXIT_DECODE_ERROR = 3
EXIT_PARTIAL_SUCCESS = 4
TRANSPORT_COMMANDS = {"capture", "send", "filter", "stats"}
DBC_COMMANDS = {"decode", "encode"}
J1939_COMMANDS = {"j1939 monitor", "j1939 decode", "j1939 pgn"}
UDS_COMMANDS = {"uds scan", "uds trace"}


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
    parser.add_argument("--version", action="version", version="canarchy 0.1.0")

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    capture = subparsers.add_parser("capture", help="capture CAN traffic")
    capture.add_argument("interface")
    add_output_arguments(capture)
    capture.set_defaults(command="capture")

    send = subparsers.add_parser("send", help="send CAN frames")
    send.add_argument("interface")
    send.add_argument("frame_id")
    send.add_argument("data")
    add_output_arguments(send)
    send.set_defaults(command="send")

    replay = subparsers.add_parser("replay", help="replay recorded traffic")
    replay.add_argument("file")
    replay.add_argument("--rate", type=float, default=1.0)
    add_output_arguments(replay)
    replay.set_defaults(command="replay")

    filter_parser = subparsers.add_parser("filter", help="filter recorded traffic")
    filter_parser.add_argument("file")
    filter_parser.add_argument("expression")
    add_output_arguments(filter_parser)
    filter_parser.set_defaults(command="filter")

    stats = subparsers.add_parser("stats", help="summarize traffic statistics")
    stats.add_argument("file")
    add_output_arguments(stats)
    stats.set_defaults(command="stats")

    decode = subparsers.add_parser("decode", help="decode traffic using DBC")
    decode.add_argument("file")
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
    j1939_monitor.add_argument("--pgn", type=int)
    add_output_arguments(j1939_monitor)
    j1939_monitor.set_defaults(command="j1939 monitor")

    j1939_decode = j1939_subparsers.add_parser("decode", help="decode J1939 traffic")
    j1939_decode.add_argument("file")
    add_output_arguments(j1939_decode)
    j1939_decode.set_defaults(command="j1939 decode")

    j1939_pgn = j1939_subparsers.add_parser("pgn", help="inspect a J1939 PGN")
    j1939_pgn.add_argument("pgn", type=int)
    add_output_arguments(j1939_pgn)
    j1939_pgn.set_defaults(command="j1939 pgn")

    j1939_spn = j1939_subparsers.add_parser("spn", help="inspect a J1939 SPN")
    j1939_spn.add_argument("spn", type=int)
    add_output_arguments(j1939_spn)
    j1939_spn.set_defaults(command="j1939 spn")

    j1939_tp = j1939_subparsers.add_parser("tp", help="inspect J1939 transport protocol")
    add_output_arguments(j1939_tp)
    j1939_tp.set_defaults(command="j1939 tp")

    j1939_dm1 = j1939_subparsers.add_parser("dm1", help="inspect J1939 DM1 traffic")
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

    shell = subparsers.add_parser("shell", help="start the interactive shell")
    add_output_arguments(shell)
    shell.set_defaults(command="shell")

    tui = subparsers.add_parser("tui", help="start the TUI")
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
    if args.command == "capture":
        return (
            {"mode": "passive", "interface": args.interface},
            transport.capture_events(args.interface),
            [],
        )
    if args.command == "send":
        frame = parse_send_frame(args)
        return (
            {"mode": "active", "interface": args.interface, "frame": frame.to_payload()},
            transport.send_events(args.interface, frame),
            ["Active transmission is intentionally distinct from passive monitoring workflows."],
        )
    if args.command == "filter":
        return (
            {"mode": "passive", "file": args.file, "expression": args.expression},
            transport.filter_events(args.file, args.expression),
            [],
        )
    if args.command == "stats":
        stats = transport.stats(args.file)
        return (
            {"mode": "passive", "file": args.file, **stats.to_payload()},
            [],
            [],
        )
    raise AssertionError(f"unsupported transport command: {args.command}")


def j1939_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    if args.command == "j1939 monitor":
        return (
            {"mode": "passive", "pgn_filter": args.pgn},
            transport.j1939_monitor_events(args.pgn),
            [],
        )
    if args.command == "j1939 decode":
        return (
            {"mode": "passive", "file": args.file},
            transport.j1939_decode_events(args.file),
            [],
        )
    if args.command == "j1939 pgn":
        return (
            {"mode": "passive", "pgn": args.pgn},
            transport.j1939_decode_events("capture.log", args.pgn),
            [],
        )
    raise AssertionError(f"unsupported j1939 command: {args.command}")


def dbc_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    if args.command == "decode":
        frames = transport.frames_from_file(args.file)
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
    if args.command == "uds scan":
        events = transport.uds_scan_events(args.interface)
        return (
            {
                "interface": args.interface,
                "mode": "active",
                "responder_count": len(events),
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
            },
            events,
            [],
        )
    raise AssertionError(f"unsupported uds command: {args.command}")


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
    if args.command in UDS_COMMANDS:
        _, events, _ = uds_payload(args)
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
    warnings = ["Command implementation is not complete yet."]
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
    elif args.command in J1939_COMMANDS:
        protocol_data, protocol_events, protocol_warnings = j1939_payload(args)
        data.update(protocol_data)
        data["events"] = protocol_events
        warnings.extend(protocol_warnings)
    else:
        data["events"] = build_events(args)
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


def emit_result(result: CommandResult, output_format: str) -> None:
    payload = result.to_payload()
    if output_format in {"json", "jsonl"}:
        print(json.dumps(payload, sort_keys=True))
        return

    if output_format == "raw":
        if result.ok:
            print(result.command)
        elif payload["errors"]:
            print(payload["errors"][0]["message"])
        return

    if output_format == "table" and result.ok and result.command in J1939_COMMANDS:
        for line in format_j1939_table(result):
            print(line)
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    output_format = requested_output_format(argv)
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
    try:
        validate_args(args)
        result = build_result(args)
        emit_result(result, output_format)
        return EXIT_OK
    except DbcError as exc:
        result = error_result(
            args.command,
            errors=[
                ErrorDetail(
                    code=exc.code,
                    message=exc.message,
                    hint=exc.hint,
                )
            ],
        )
        emit_result(result, output_format)
        return EXIT_DECODE_ERROR
    except TransportError as exc:
        result = error_result(
            args.command,
            errors=[
                ErrorDetail(
                    code=exc.code,
                    message=exc.message,
                    hint=exc.hint,
                )
            ],
        )
        emit_result(result, output_format)
        return EXIT_TRANSPORT_ERROR
    except CommandError as exc:
        result = error_result(
            exc.command,
            errors=exc.errors,
            data=exc.data,
            warnings=exc.warnings,
        )
        emit_result(result, output_format)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
