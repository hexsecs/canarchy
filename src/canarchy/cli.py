"""CLI entry point for CANarchy."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import logging
import math
import os
import random
import shlex
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from canarchy import fuzzing
from canarchy.doctor import doctor_payload
from canarchy.dbc import (
    DbcError,
    convert_database,
    dbc_supports_spn,
    decode_frames,
    decode_j1939_spn,
    encode_message,
    generate_c_source,
    inspect_database,
    lookup_j1939_spn_metadata,
)
from canarchy import __version__
from canarchy.exporter import ExportError, export_artifact
from canarchy.j1587 import decode_events as decode_j1587_events
from canarchy.j1587 import iter_j1708_messages_from_file, j1587_pids_payload
from canarchy.j2497 import decode_events as decode_j2497_events
from canarchy.j2497 import iter_j2497_frames_from_file, j2497_mids_payload
from canarchy.j1939 import TP_CM_PGN, TP_DT_PGN, decompose_arbitration_id
from canarchy.j1939_decoder import get_j1939_decoder
from canarchy.j1939_metadata import pgn_lookup, source_address_lookup
from canarchy import pretty_j1939_support
from canarchy.models import (
    AlertEvent,
    CanFrame,
    FrameEvent,
    serialize_events,
)
from canarchy.replay import build_replay_plan
from canarchy.reverse_engineering import (
    ReferenceSeriesError,
    correlate_candidates,
    load_reference_series,
    score_dbc_candidates,
)
from canarchy.session import SessionError, SessionStore, build_session_context
from canarchy.shell_completion import SUPPORTED_SHELLS, render_completion
from canarchy.simulate import PROFILE_NAMES, simulate_frames
from canarchy.skills import SkillError
from canarchy.transport import (
    LocalTransport,
    TransportError,
    active_ack_required,
    candump_parse_warnings,
    config_show_payload,
    default_can_interface,
    default_j1939_dbc,
    generate_frames,
    reset_parse_reports,
)
from canarchy.tui import run_tui
from canarchy.doip import is_doip_target
from canarchy.fuzz_feedback import SIGNAL_CATEGORIES
from canarchy.uds import uds_decoder_backend, uds_services_payload
from canarchy.xcp import (
    XCP_DEFAULT_REQUEST_ID,
    XCP_DEFAULT_RESPONSE_ID,
    connect_request_frame,
    xcp_commands_payload,
)

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_TRANSPORT_ERROR = 2
EXIT_DECODE_ERROR = 3
EXIT_PARTIAL_SUCCESS = 4
TRANSPORT_COMMANDS = {"capture", "send", "filter", "stats", "generate", "simulate", "capture-info"}
DBC_COMMANDS = {"decode", "encode", "dbc inspect", "dbc signals", "dbc convert", "dbc generate-c"}
DBC_PROVIDER_COMMANDS = {
    "dbc provider list",
    "dbc search",
    "dbc fetch",
    "dbc cache list",
    "dbc cache prune",
    "dbc cache refresh",
}
SKILLS_COMMANDS = {
    "skills provider list",
    "skills search",
    "skills fetch",
    "skills cache list",
    "skills cache refresh",
}
PLUGINS_COMMANDS = {
    "plugins list",
    "plugins info",
    "plugins enable",
    "plugins disable",
}
DATASETS_COMMANDS = {
    "datasets provider list",
    "datasets search",
    "datasets inspect",
    "datasets fetch",
    "datasets cache list",
    "datasets cache refresh",
    "datasets convert",
    "datasets stream",
    "datasets replay",
}
J1939_COMMANDS = {
    "j1939 monitor",
    "j1939 decode",
    "j1939 pgn",
    "j1939 spn",
    "j1939 tp sessions",
    "j1939 tp compare",
    "j1939 dm1",
    "j1939 faults",
    "j1939 summary",
    "j1939 inventory",
    "j1939 compare",
    "j1939 map",
}
SESSION_COMMANDS = {"session save", "session load", "session show"}
UDS_COMMANDS = {"uds scan", "uds trace", "uds services"}
XCP_COMMANDS = {"xcp scan", "xcp trace", "xcp read", "xcp commands"}
J1587_COMMANDS = {"j1587 decode", "j1587 pids"}
J2497_COMMANDS = {"j2497 decode", "j2497 mids"}
CONFIG_COMMANDS = {"config show"}
DOCTOR_COMMANDS = {"doctor"}
RE_COMMANDS = {
    "re signals",
    "re counters",
    "re entropy",
    "re correlate",
    "re anomalies",
    "re match-dbc",
    "re shortlist-dbc",
    "re corpus",
    "re suggest",
}
CANNELLONI_COMMANDS = {"cannelloni decode", "cannelloni send"}

ACTIVE_TRANSMIT_COMMANDS = {
    "send",
    "generate",
    "simulate",
    "gateway",
    "cannelloni send",
    "uds scan",
    "xcp scan",
    "fuzz payload",
    "fuzz replay",
    "fuzz arbitration-id",
    "fuzz signal",
    "fuzz spn",
    "fuzz guided",
    "replay",
    "sequence replay",
}
FUZZ_COMMANDS = {
    "fuzz payload",
    "fuzz replay",
    "fuzz arbitration-id",
    "fuzz signal",
    "fuzz spn",
}
FUZZ_GUIDED_COMMANDS = {"fuzz guided"}
SEQUENCE_COMMANDS = {"sequence replay"}
IMPLEMENTED_COMMANDS = (
    TRANSPORT_COMMANDS
    | DBC_COMMANDS
    | DBC_PROVIDER_COMMANDS
    | SKILLS_COMMANDS
    | PLUGINS_COMMANDS
    | DATASETS_COMMANDS
    | J1939_COMMANDS
    | SESSION_COMMANDS
    | UDS_COMMANDS
    | XCP_COMMANDS
    | J1587_COMMANDS
    | J2497_COMMANDS
    | CONFIG_COMMANDS
    | DOCTOR_COMMANDS
    | RE_COMMANDS
    | FUZZ_COMMANDS
    | FUZZ_GUIDED_COMMANDS
    | SEQUENCE_COMMANDS
    | CANNELLONI_COMMANDS
    | {"mcp serve", "mcp install", "replay", "gateway", "shell", "export", "plot", "web serve"}
)


class CliUsageError(Exception):
    """Raised when the user input is invalid."""


@dataclass(slots=True)
class ErrorDetail:
    code: str
    message: str
    hint: str | None = None
    detail: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        if self.detail:
            payload["detail"] = self.detail
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
    group.add_argument("--text", action="store_true", help="emit human-readable text output")
    group.add_argument("--table", action="store_true", help=argparse.SUPPRESS)


def add_active_ack_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ack-active",
        action="store_true",
        help="require interactive confirmation before active transmission",
    )


def _add_xcp_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--request-id",
        default=hex(XCP_DEFAULT_REQUEST_ID),
        help=f"master request CAN id (default: {hex(XCP_DEFAULT_REQUEST_ID)})",
    )
    parser.add_argument(
        "--response-id",
        default=hex(XCP_DEFAULT_RESPONSE_ID),
        help=f"slave response CAN id (default: {hex(XCP_DEFAULT_RESPONSE_ID)})",
    )


def add_j1939_file_analysis_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="skip the first N frames from the capture file",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        help="limit analysis to the first N frames from the capture file",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        help="limit analysis to the first N seconds from the capture start timestamp",
    )


def _add_file_analysis_arguments(parser: argparse.ArgumentParser) -> None:
    """Shared --offset, --max-frames, and --seconds arguments for file-backed commands."""
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="skip the first N frames from the capture file",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        help="limit analysis to the first N frames (useful for large captures)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        help="limit analysis to the first N seconds from capture start",
    )


LOG_LEVEL_CHOICES = ("debug", "info", "warn", "error")


def configure_logging(*, log_level: str | None, quiet: bool) -> None:
    """Configure the root logger from the top-level CLI flags.

    Log records always go to stderr so that machine-readable stdout
    (``--json``, ``--jsonl``, ``--text``) is never contaminated. ``--quiet``
    suppresses every level except ``ERROR``. When the root logger already
    has handlers (for example pytest's caplog plugin), only the level is
    adjusted so test capture machinery is not torn down.
    """

    if quiet:
        level = logging.ERROR
    else:
        level_name = (log_level or "warn").lower()
        if level_name == "warn":
            level_name = "warning"
        level = getattr(logging, level_name.upper(), logging.WARNING)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
    else:
        logging.basicConfig(
            stream=sys.stderr,
            level=level,
            format="%(levelname)s %(name)s: %(message)s",
        )


def build_parser() -> CanarchyArgumentParser:
    parser = CanarchyArgumentParser(
        prog="canarchy", description="CLI-first CAN security research toolkit"
    )
    parser.add_argument("--version", action="version", version=f"canarchy {__version__}")
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        default="warn",
        help="set the stderr log level (default: warn); place before the subcommand",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress stderr logging below ERROR; place before the subcommand",
    )

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    capture = subparsers.add_parser("capture", help="capture CAN traffic")
    capture.add_argument("interface", nargs="?")
    capture.add_argument(
        "--candump",
        action="store_true",
        help="emit candump-style human output for live capture",
    )
    add_output_arguments(capture)
    capture.set_defaults(command="capture")

    send = subparsers.add_parser("send", help="send CAN frames")
    send.add_argument(
        "send_args",
        nargs="*",
        metavar="interface frame_id data",
        help="CAN interface plus frame ID and payload, or frame ID and payload when a default interface is configured",
    )
    send.add_argument("--dbc", help="DBC file path or provider ref (e.g. opendbc:name)")
    send.add_argument("--message", help="DBC message name to encode (requires --dbc)")
    send.add_argument(
        "--signals",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="signal values to encode, e.g. CoolantTemp=55 (requires --dbc and --message)",
    )
    send.add_argument(
        "--crc-algorithm",
        choices=("stellantis", "sae-j1850", "fca-giorgio"),
        default=None,
        help="CRC algorithm override for DBC encode (default: auto-detect from DBC filename)",
    )
    send.add_argument(
        "--rate",
        type=float,
        default=None,
        metavar="HZ",
        help="repeat rate in frames per second",
    )
    send.add_argument(
        "--count",
        type=int,
        default=1,
        help="number of frames to send (default: 1)",
    )
    send.add_argument(
        "--dry-run",
        action="store_true",
        help="print the encoded frame without transmitting",
    )
    add_active_ack_argument(send)
    add_output_arguments(send)
    send.set_defaults(command="send")

    generate = subparsers.add_parser("generate", help="generate CAN frames")
    generate.add_argument("interface", nargs="?")
    generate.add_argument("--id", default="R", help="frame ID as hex or R for random")
    generate.add_argument("--dlc", default="R", help="data length 0-8 or R for random")
    generate.add_argument(
        "--data", default="R", help="payload hex, R for random, I for incrementing"
    )
    generate.add_argument("--count", type=int, default=1, help="number of frames to generate")
    generate.add_argument(
        "--gap", type=float, default=200.0, help="inter-frame gap in milliseconds"
    )
    generate.add_argument("--extended", action="store_true", help="force 29-bit extended IDs")
    generate.add_argument(
        "--dry-run",
        action="store_true",
        help="plan generated frames without transmitting",
    )
    add_active_ack_argument(generate)
    add_output_arguments(generate)
    generate.set_defaults(command="generate")

    simulate = subparsers.add_parser(
        "simulate", help="simulate realistic CAN/J1939 traffic from a vehicle profile"
    )
    simulate.add_argument("interface", nargs="?")
    simulate.add_argument(
        "--profile",
        required=True,
        choices=list(PROFILE_NAMES),
        help="vehicle traffic profile to emit",
    )
    simulate.add_argument(
        "--rate", type=float, default=50.0, help="frame emission rate in Hz (default: 50)"
    )
    simulate.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="simulation duration in seconds (default: 10)",
    )
    simulate.add_argument(
        "--seed", type=int, default=0, help="random seed for deterministic output (default: 0)"
    )
    simulate.add_argument(
        "--dry-run",
        action="store_true",
        help="plan simulated frames without transmitting",
    )
    add_active_ack_argument(simulate)
    add_output_arguments(simulate)
    simulate.set_defaults(command="simulate")

    gateway = subparsers.add_parser("gateway", help="bridge frames between CAN interfaces")
    gateway.add_argument("src")
    gateway.add_argument("dst")
    gateway.add_argument("--src-backend", help="python-can interface type for the source bus")
    gateway.add_argument("--dst-backend", help="python-can interface type for the destination bus")
    gateway.add_argument(
        "--bidirectional", action="store_true", help="also forward frames from dst back to src"
    )
    gateway.add_argument("--count", type=int, help="stop after forwarding N frames")
    gateway.add_argument(
        "--dry-run",
        action="store_true",
        help="plan gateway forwarding without opening transport",
    )
    add_active_ack_argument(gateway)
    add_output_arguments(gateway)
    gateway.set_defaults(command="gateway")

    replay = subparsers.add_parser("replay", help="replay recorded traffic")
    replay.add_argument(
        "--file", required=True, help="path to candump capture file (use - for stdin)"
    )
    replay.add_argument("--rate", type=float, default=1.0)
    replay.add_argument(
        "--interface",
        help="target CAN interface for live transmission (omit for planning-only mode)",
    )
    replay.add_argument(
        "--dry-run", action="store_true", help="plan live transmission without sending frames"
    )
    add_active_ack_argument(replay)
    add_output_arguments(replay)
    replay.set_defaults(command="replay")

    sequence = subparsers.add_parser("sequence", help="sequence-based coordinated CAN transmit")
    sequence_subparsers = sequence.add_subparsers(dest="sequence_action", required=True)
    sequence_replay = sequence_subparsers.add_parser(
        "replay", help="replay a YAML/JSON sequence of DBC-encoded frames"
    )
    sequence_replay.add_argument("--file", required=True, help="path to YAML or JSON sequence file")
    sequence_replay.add_argument(
        "--interface", help="target CAN interface for live transmission (omit for dry-run)"
    )
    sequence_replay.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="time-scale factor: 2.0 plays back at 2× speed (default: 1.0)",
    )
    sequence_replay.add_argument(
        "--loop", action="store_true", help="repeat the sequence until interrupted"
    )
    sequence_replay.add_argument(
        "--dry-run",
        action="store_true",
        help="plan transmission without opening an interface",
    )
    add_active_ack_argument(sequence_replay)
    add_output_arguments(sequence_replay)
    sequence_replay.set_defaults(command="sequence replay")

    filter_parser = subparsers.add_parser("filter", help="filter recorded traffic")
    filter_parser.add_argument("expression", help="filter expression")
    filter_parser.add_argument("--file", help="path to candump capture file (use - for stdin)")
    filter_parser.add_argument(
        "--stdin", action="store_true", help="read JSONL FrameEvents from stdin"
    )
    _add_file_analysis_arguments(filter_parser)
    add_output_arguments(filter_parser)
    filter_parser.set_defaults(command="filter")

    stats = subparsers.add_parser("stats", help="summarize traffic statistics")
    stats.add_argument(
        "--file", required=True, help="path to candump capture file (use - for stdin)"
    )
    stats.add_argument(
        "--top",
        type=int,
        default=20,
        help="number of highest-frequency arbitration ids to detail (default: 20)",
    )
    stats.add_argument(
        "--pgn",
        type=lambda x: int(x, 0),
        default=None,
        help="filter to frames whose J1939 PGN matches",
    )
    stats.add_argument(
        "--sa",
        default=None,
        help="filter to frames whose J1939 source address matches (comma-separated hex or decimal)",
    )
    _add_file_analysis_arguments(stats)
    add_output_arguments(stats)
    stats.set_defaults(command="stats")

    capture_info = subparsers.add_parser(
        "capture-info", help="show capture file metadata without loading frames"
    )
    capture_info.add_argument(
        "--file", required=True, help="path to candump capture file (use - for stdin)"
    )
    add_output_arguments(capture_info)
    capture_info.set_defaults(command="capture-info")

    decode = subparsers.add_parser("decode", help="decode traffic using DBC")
    decode.add_argument("--file", help="path to candump capture file")
    decode.add_argument("--stdin", action="store_true", help="read JSONL FrameEvents from stdin")
    decode.add_argument("--dbc", required=True)
    _add_file_analysis_arguments(decode)
    add_output_arguments(decode)
    decode.set_defaults(command="decode")

    encode = subparsers.add_parser("encode", help="encode signals using DBC")
    encode.add_argument("--dbc", required=True)
    encode.add_argument("message")
    encode.add_argument("signals", nargs="*", help="key=value signal assignments")
    encode.add_argument(
        "--crc-algorithm",
        choices=("stellantis", "sae-j1850", "fca-giorgio"),
        default=None,
        help="CRC algorithm override (default: auto-detect from DBC filename)",
    )
    add_output_arguments(encode)
    encode.set_defaults(command="encode")

    dbc = subparsers.add_parser("dbc", help="inspect DBC metadata")
    dbc_subparsers = dbc.add_subparsers(dest="dbc_action", required=True)

    dbc_inspect = dbc_subparsers.add_parser(
        "inspect",
        help="inspect database, message, and signal metadata",
    )
    dbc_inspect.add_argument("dbc")
    dbc_inspect.add_argument("--message", help="restrict output to a single message name")
    dbc_inspect.add_argument(
        "--signals-only",
        action="store_true",
        help="emit signal-centric metadata instead of full message definitions",
    )
    dbc_inspect.add_argument(
        "--search",
        metavar="PATTERN",
        help="case-insensitive regex/substring filter on message and signal names",
    )
    dbc_inspect.add_argument(
        "--layout",
        action="store_true",
        help="include cantools-rendered bit layout, signal tree, and choice tables",
    )
    add_output_arguments(dbc_inspect)
    dbc_inspect.set_defaults(command="dbc inspect")

    dbc_signals = dbc_subparsers.add_parser(
        "signals",
        help="list and search signals from a DBC file",
    )
    dbc_signals.add_argument("dbc")
    dbc_signals.add_argument("--message", help="restrict output to a single message name")
    dbc_signals.add_argument(
        "--search",
        metavar="PATTERN",
        help="case-insensitive regex/substring filter on message and signal names",
    )
    add_output_arguments(dbc_signals)
    dbc_signals.set_defaults(command="dbc signals")

    dbc_convert = dbc_subparsers.add_parser(
        "convert",
        help="convert a database between DBC, KCD, and SYM formats",
    )
    dbc_convert.add_argument("dbc", help="source database (path or provider ref)")
    dbc_convert.add_argument(
        "--to",
        dest="target_format",
        required=True,
        choices=["dbc", "kcd", "sym"],
        help="target database format",
    )
    dbc_convert.add_argument(
        "--out",
        help="write the converted database to this path (default: stdout)",
    )
    add_output_arguments(dbc_convert)
    dbc_convert.set_defaults(command="dbc convert")

    dbc_generate_c = dbc_subparsers.add_parser(
        "generate-c",
        help="generate C source and header files from a database (via cantools)",
    )
    dbc_generate_c.add_argument("dbc", help="source database (path or provider ref)")
    dbc_generate_c.add_argument(
        "--out-dir",
        dest="out_dir",
        help="output directory (default: current directory)",
    )
    dbc_generate_c.add_argument(
        "--database-name",
        dest="database_name",
        help="database name used as a prefix in the generated C code (default: derived from the source filename)",
    )
    dbc_generate_c.add_argument(
        "--no-floating-point-numbers",
        dest="floating_point_numbers",
        action="store_false",
        default=True,
        help="disable floating point numbers in generated code",
    )
    dbc_generate_c.add_argument(
        "--bit-fields",
        dest="bit_fields",
        action="store_true",
        default=False,
        help="generate bit fields in structs",
    )
    dbc_generate_c.add_argument(
        "--use-float",
        dest="use_float",
        action="store_true",
        default=False,
        help="prefer float instead of double for floating point numbers",
    )
    dbc_generate_c.add_argument(
        "--node",
        dest="node_name",
        help="generate packers only for the specified node (unpackers for all others)",
    )
    dbc_generate_c.add_argument(
        "--use-round",
        dest="use_round",
        action="store_true",
        default=False,
        help="round to nearest integer instead of truncating when encoding",
    )
    add_output_arguments(dbc_generate_c)
    dbc_generate_c.set_defaults(command="dbc generate-c")

    dbc_provider = dbc_subparsers.add_parser("provider", help="manage DBC providers")
    dbc_provider_subparsers = dbc_provider.add_subparsers(dest="dbc_provider_action", required=True)

    dbc_provider_list = dbc_provider_subparsers.add_parser("list", help="list registered providers")
    add_output_arguments(dbc_provider_list)
    dbc_provider_list.set_defaults(command="dbc provider list")

    dbc_search = dbc_subparsers.add_parser("search", help="search for DBC files across providers")
    dbc_search.add_argument("query", help="search query (name, make, or keyword)")
    dbc_search.add_argument("--provider", help="restrict search to a specific provider")
    dbc_search.add_argument("--limit", type=int, default=20, help="maximum results (default: 20)")
    dbc_search.add_argument(
        "--verbose", action="store_true", help="show provider, version, and path details"
    )
    add_output_arguments(dbc_search)
    dbc_search.set_defaults(command="dbc search")

    dbc_fetch = dbc_subparsers.add_parser("fetch", help="fetch and cache a DBC file")
    dbc_fetch.add_argument("ref", help="DBC ref (e.g. opendbc:toyota_tnga_k_pt_generated)")
    add_output_arguments(dbc_fetch)
    dbc_fetch.set_defaults(command="dbc fetch")

    dbc_cache = dbc_subparsers.add_parser("cache", help="manage the local DBC cache")
    dbc_cache_subparsers = dbc_cache.add_subparsers(dest="dbc_cache_action", required=True)

    dbc_cache_list = dbc_cache_subparsers.add_parser("list", help="list cached providers")
    add_output_arguments(dbc_cache_list)
    dbc_cache_list.set_defaults(command="dbc cache list")

    dbc_cache_prune = dbc_cache_subparsers.add_parser("prune", help="remove stale cached commits")
    dbc_cache_prune.add_argument("--provider", help="restrict to a specific provider")
    add_output_arguments(dbc_cache_prune)
    dbc_cache_prune.set_defaults(command="dbc cache prune")

    dbc_cache_refresh = dbc_cache_subparsers.add_parser(
        "refresh", help="refresh catalog from upstream"
    )
    dbc_cache_refresh.add_argument(
        "--provider", default="opendbc", help="provider to refresh (default: opendbc)"
    )
    add_output_arguments(dbc_cache_refresh)
    dbc_cache_refresh.set_defaults(command="dbc cache refresh")

    skills = subparsers.add_parser("skills", help="manage repository-backed skills")
    skills_subparsers = skills.add_subparsers(dest="skills_action", required=True)

    skills_provider = skills_subparsers.add_parser("provider", help="manage skills providers")
    skills_provider_subparsers = skills_provider.add_subparsers(
        dest="skills_provider_action", required=True
    )
    skills_provider_list = skills_provider_subparsers.add_parser(
        "list", help="list registered skills providers"
    )
    add_output_arguments(skills_provider_list)
    skills_provider_list.set_defaults(command="skills provider list")

    skills_search = skills_subparsers.add_parser("search", help="search skills across providers")
    skills_search.add_argument("query", help="search query (name, tag, or keyword)")
    skills_search.add_argument("--provider", help="restrict search to a specific provider")
    skills_search.add_argument(
        "--limit", type=int, default=20, help="maximum results (default: 20)"
    )
    add_output_arguments(skills_search)
    skills_search.set_defaults(command="skills search")

    skills_fetch = skills_subparsers.add_parser("fetch", help="fetch and cache a skill")
    skills_fetch.add_argument("ref", help="skill ref (e.g. github:j1939_compare_triage)")
    add_output_arguments(skills_fetch)
    skills_fetch.set_defaults(command="skills fetch")

    skills_cache = skills_subparsers.add_parser("cache", help="manage the local skills cache")
    skills_cache_subparsers = skills_cache.add_subparsers(dest="skills_cache_action", required=True)
    skills_cache_list = skills_cache_subparsers.add_parser(
        "list", help="list cached skills providers"
    )
    add_output_arguments(skills_cache_list)
    skills_cache_list.set_defaults(command="skills cache list")
    skills_cache_refresh = skills_cache_subparsers.add_parser(
        "refresh", help="refresh skills catalog from upstream"
    )
    skills_cache_refresh.add_argument(
        "--provider", default="github", help="provider to refresh (default: github)"
    )
    add_output_arguments(skills_cache_refresh)
    skills_cache_refresh.set_defaults(command="skills cache refresh")

    plugins = subparsers.add_parser("plugins", help="inspect and toggle Python entry-point plugins")
    plugins_subparsers = plugins.add_subparsers(dest="plugins_action", required=True)

    plugins_list = plugins_subparsers.add_parser("list", help="list discovered plugins")
    add_output_arguments(plugins_list)
    plugins_list.set_defaults(command="plugins list")

    plugins_info = plugins_subparsers.add_parser("info", help="show plugin metadata")
    plugins_info.add_argument("name", help="registered plugin name")
    add_output_arguments(plugins_info)
    plugins_info.set_defaults(command="plugins info")

    plugins_enable = plugins_subparsers.add_parser("enable", help="enable a plugin in config")
    plugins_enable.add_argument("name", help="registered plugin name")
    add_output_arguments(plugins_enable)
    plugins_enable.set_defaults(command="plugins enable")

    plugins_disable = plugins_subparsers.add_parser("disable", help="disable a plugin in config")
    plugins_disable.add_argument("name", help="registered plugin name")
    add_output_arguments(plugins_disable)
    plugins_disable.set_defaults(command="plugins disable")

    datasets = subparsers.add_parser("datasets", help="discover and inspect public CAN datasets")
    datasets_subparsers = datasets.add_subparsers(dest="datasets_action", required=True)

    datasets_provider = datasets_subparsers.add_parser("provider", help="manage dataset providers")
    datasets_provider_subparsers = datasets_provider.add_subparsers(
        dest="datasets_provider_action", required=True
    )
    datasets_provider_list = datasets_provider_subparsers.add_parser(
        "list", help="list registered dataset providers"
    )
    add_output_arguments(datasets_provider_list)
    datasets_provider_list.set_defaults(command="datasets provider list")

    datasets_search = datasets_subparsers.add_parser(
        "search", help="search datasets across providers"
    )
    datasets_search.add_argument(
        "query", nargs="?", default="", help="search query (name, protocol, or keyword)"
    )
    datasets_search.add_argument("--provider", help="restrict search to a specific provider")
    datasets_search.add_argument(
        "--limit", type=int, default=20, help="maximum results (default: 20)"
    )
    datasets_search.add_argument(
        "--verbose", action="store_true", help="show detailed dataset search results"
    )
    add_output_arguments(datasets_search)
    datasets_search.set_defaults(command="datasets search")

    datasets_inspect = datasets_subparsers.add_parser(
        "inspect", help="show full metadata for a dataset"
    )
    datasets_inspect.add_argument("ref", help="dataset ref (e.g. catalog:road or just road)")
    add_output_arguments(datasets_inspect)
    datasets_inspect.set_defaults(command="datasets inspect")

    datasets_fetch = datasets_subparsers.add_parser("fetch", help="record provenance for a dataset")
    datasets_fetch.add_argument("ref", help="dataset ref (e.g. catalog:road)")
    add_output_arguments(datasets_fetch)
    datasets_fetch.set_defaults(command="datasets fetch")

    datasets_cache = datasets_subparsers.add_parser("cache", help="manage the local datasets cache")
    datasets_cache_subparsers = datasets_cache.add_subparsers(
        dest="datasets_cache_action", required=True
    )
    datasets_cache_list = datasets_cache_subparsers.add_parser(
        "list", help="list cached dataset providers"
    )
    add_output_arguments(datasets_cache_list)
    datasets_cache_list.set_defaults(command="datasets cache list")
    datasets_cache_refresh = datasets_cache_subparsers.add_parser(
        "refresh", help="refresh dataset catalog manifest"
    )
    datasets_cache_refresh.add_argument(
        "--provider", default="catalog", help="provider to refresh (default: catalog)"
    )
    add_output_arguments(datasets_cache_refresh)
    datasets_cache_refresh.set_defaults(command="datasets cache refresh")

    datasets_convert = datasets_subparsers.add_parser(
        "convert", help="convert a downloaded dataset file to candump or JSONL"
    )
    datasets_convert.add_argument("file", help="path to the downloaded dataset file")
    datasets_convert.add_argument(
        "--source-format",
        required=True,
        choices=["hcrl-csv", "candump", "comma-rlog"],
        help="source file format (hcrl-csv CSV, candump log, comma-rlog openpilot rlog.zst)",
    )
    datasets_convert.add_argument(
        "--format",
        dest="output_format",
        required=True,
        choices=["candump", "jsonl"],
        help="output format",
    )
    datasets_convert.add_argument(
        "--output", help="output file path (defaults to source path with new suffix)"
    )
    add_output_arguments(datasets_convert)
    datasets_convert.set_defaults(command="datasets convert")

    datasets_stream = datasets_subparsers.add_parser(
        "stream", help="stream a downloaded dataset file to candump or JSONL"
    )
    datasets_stream.add_argument("file", help="path to the downloaded dataset file")
    datasets_stream.add_argument(
        "--source-format",
        required=True,
        choices=["hcrl-csv", "candump", "comma-rlog"],
        help="source file format (hcrl-csv CSV, candump log, comma-rlog openpilot rlog.zst)",
    )
    datasets_stream.add_argument(
        "--format",
        dest="output_format",
        required=True,
        choices=["candump", "jsonl"],
        help="stream output format",
    )
    datasets_stream.add_argument("--output", help="output file path; omit or use '-' for stdout")
    datasets_stream.add_argument(
        "--chunk-size", type=int, default=1000, help="frames per metadata chunk (default: 1000)"
    )
    datasets_stream.add_argument("--max-frames", type=int, default=None, help="stop after N frames")
    datasets_stream.add_argument(
        "--provider-ref", help="dataset provider ref to preserve in JSONL provenance"
    )
    add_output_arguments(datasets_stream)
    datasets_stream.set_defaults(command="datasets stream")

    datasets_replay = datasets_subparsers.add_parser(
        "replay", help="Netflix-style streaming replay from a dataset ref or URL"
    )
    datasets_replay.add_argument(
        "source", help="dataset ref (e.g. catalog:candid) or remote candump URL"
    )
    datasets_replay.add_argument(
        "--format",
        dest="output_format",
        default="candump",
        choices=["candump", "jsonl"],
        help="stream output format (default: candump)",
    )
    datasets_replay.add_argument(
        "--rate", type=float, default=1.0, help="playback rate multiplier (default: 1.0 real-time)"
    )
    datasets_replay.add_argument(
        "--file", dest="replay_file", help="replay file id or name from the dataset manifest"
    )
    datasets_replay.add_argument(
        "--platform",
        help="dataset-specific platform filter for dynamic replay manifests (e.g. TESLA_MODEL_3)",
    )
    datasets_replay.add_argument(
        "--limit",
        dest="replay_limit",
        type=int,
        default=None,
        help="limit dynamic replay manifest entries when listing files",
    )
    datasets_replay.add_argument(
        "--list-files",
        action="store_true",
        help="list replayable files without opening a remote stream",
    )
    datasets_replay.add_argument("--max-frames", type=int, default=None, help="stop after N frames")
    datasets_replay.add_argument(
        "--max-seconds", type=float, default=None, help="stop after N seconds of capture time"
    )
    datasets_replay.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve replay source metadata without opening the stream",
    )
    datasets_replay.add_argument(
        "--interface", help="target CAN interface for live transmission (omit for stdout streaming)"
    )
    add_active_ack_argument(datasets_replay)
    add_output_arguments(datasets_replay)
    datasets_replay.set_defaults(command="datasets replay")

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
    j1939_decode.add_argument("--file", help="path to candump capture file")
    j1939_decode.add_argument(
        "--stdin", action="store_true", help="read JSONL FrameEvents from stdin"
    )
    j1939_decode.add_argument(
        "--dbc", help="enrich J1939 results with a local DBC path or provider ref"
    )
    add_j1939_file_analysis_arguments(j1939_decode)
    add_output_arguments(j1939_decode)
    j1939_decode.set_defaults(command="j1939 decode")

    j1939_pgn = j1939_subparsers.add_parser("pgn", help="inspect a J1939 PGN")
    j1939_pgn.add_argument("pgn", type=int)
    j1939_pgn.add_argument("--file", help="inspect the PGN within a capture file")
    j1939_pgn.add_argument(
        "--dbc", help="enrich J1939 results with a local DBC path or provider ref"
    )
    add_j1939_file_analysis_arguments(j1939_pgn)
    add_output_arguments(j1939_pgn)
    j1939_pgn.set_defaults(command="j1939 pgn")

    j1939_spn = j1939_subparsers.add_parser("spn", help="inspect a J1939 SPN")
    j1939_spn.add_argument("spn", type=int)
    j1939_spn.add_argument("--file", help="inspect the SPN within a capture file")
    j1939_spn.add_argument(
        "--dbc", help="enrich J1939 results with a local DBC path or provider ref"
    )
    add_j1939_file_analysis_arguments(j1939_spn)
    add_output_arguments(j1939_spn)
    j1939_spn.set_defaults(command="j1939 spn")

    j1939_tp = j1939_subparsers.add_parser("tp", help="inspect J1939 transport protocol sessions")
    j1939_tp_subparsers = j1939_tp.add_subparsers(dest="tp_action", required=True)

    j1939_tp_sessions = j1939_tp_subparsers.add_parser(
        "sessions", help="list reassembled TP sessions"
    )
    j1939_tp_sessions.add_argument("--file", required=True, help="path to candump capture file")
    j1939_tp_sessions.add_argument(
        "--pgn", type=lambda x: int(x, 0), default=None, help="filter by transfer PGN"
    )
    j1939_tp_sessions.add_argument(
        "--sa", default=None, help="filter by source address (comma-separated hex or decimal)"
    )
    add_j1939_file_analysis_arguments(j1939_tp_sessions)
    add_output_arguments(j1939_tp_sessions)
    j1939_tp_sessions.set_defaults(command="j1939 tp sessions")

    j1939_tp_compare = j1939_tp_subparsers.add_parser(
        "compare", help="compare TP sessions across source addresses"
    )
    j1939_tp_compare.add_argument("--file", required=True, help="path to candump capture file")
    j1939_tp_compare.add_argument(
        "--sa", required=True, help="comma-separated source addresses to compare (hex or decimal)"
    )
    j1939_tp_compare.add_argument(
        "--pgn", type=lambda x: int(x, 0), default=None, help="filter by transfer PGN"
    )
    add_j1939_file_analysis_arguments(j1939_tp_compare)
    add_output_arguments(j1939_tp_compare)
    j1939_tp_compare.set_defaults(command="j1939 tp compare")

    j1939_dm1 = j1939_subparsers.add_parser("dm1", help="inspect J1939 DM1 traffic")
    j1939_dm1.add_argument("--file", required=True, help="path to candump capture file")
    j1939_dm1.add_argument(
        "--dbc", help="enrich DM1 DTC names with a local DBC path or provider ref"
    )
    add_j1939_file_analysis_arguments(j1939_dm1)
    add_output_arguments(j1939_dm1)
    j1939_dm1.set_defaults(command="j1939 dm1")

    j1939_faults = j1939_subparsers.add_parser("faults", help="summarize J1939 DM1 faults by ECU")
    j1939_faults.add_argument("--file", required=True, help="path to candump capture file")
    j1939_faults.add_argument(
        "--dbc", help="enrich DTC names with a local DBC path or provider ref"
    )
    add_j1939_file_analysis_arguments(j1939_faults)
    add_output_arguments(j1939_faults)
    j1939_faults.set_defaults(command="j1939 faults")

    j1939_summary = j1939_subparsers.add_parser("summary", help="summarize J1939 capture content")
    j1939_summary.add_argument("--file", required=True, help="path to candump capture file")
    add_j1939_file_analysis_arguments(j1939_summary)
    add_output_arguments(j1939_summary)
    j1939_summary.set_defaults(command="j1939 summary")

    j1939_inventory = j1939_subparsers.add_parser(
        "inventory", help="build a J1939 ECU inventory from a capture"
    )
    j1939_inventory.add_argument("--file", required=True, help="path to candump capture file")
    add_j1939_file_analysis_arguments(j1939_inventory)
    add_output_arguments(j1939_inventory)
    j1939_inventory.set_defaults(command="j1939 inventory")

    j1939_compare = j1939_subparsers.add_parser(
        "compare", help="compare multiple J1939 capture files"
    )
    j1939_compare.add_argument("files", nargs="*", help="paths to candump capture files")
    j1939_compare.add_argument(
        "--file",
        dest="file_opt",
        action="append",
        metavar="PATH",
        help="capture file to compare (repeatable; equivalent to the positional form)",
    )
    add_j1939_file_analysis_arguments(j1939_compare)
    add_output_arguments(j1939_compare)
    j1939_compare.set_defaults(command="j1939 compare")

    j1939_map = j1939_subparsers.add_parser(
        "map", help="build a J1939 network-topology map (nodes/edges) from a capture"
    )
    j1939_map.add_argument("--file", required=True, help="path to candump capture file")
    add_j1939_file_analysis_arguments(j1939_map)
    add_output_arguments(j1939_map)
    j1939_map.set_defaults(command="j1939 map")

    uds = subparsers.add_parser("uds", help="UDS protocol workflows")
    uds_subparsers = uds.add_subparsers(dest="uds_action", required=True)

    uds_scan = uds_subparsers.add_parser("scan", help="scan for UDS responders")
    uds_scan.add_argument(
        "interface",
        nargs="?",
        help="CAN interface, or a doip://<host>:<port>?logical_address=0x0E80 endpoint",
    )
    add_active_ack_argument(uds_scan)
    add_output_arguments(uds_scan)
    uds_scan.set_defaults(command="uds scan")

    uds_trace = uds_subparsers.add_parser("trace", help="trace UDS transactions")
    uds_trace.add_argument(
        "interface",
        nargs="?",
        help="CAN interface, or a doip://<host>:<port>?logical_address=0x0E80 endpoint",
    )
    add_active_ack_argument(uds_trace)
    add_output_arguments(uds_trace)
    uds_trace.set_defaults(command="uds trace")

    uds_services = uds_subparsers.add_parser("services", help="list UDS services")
    add_output_arguments(uds_services)
    uds_services.set_defaults(command="uds services")

    xcp = subparsers.add_parser("xcp", help="XCP measurement/calibration workflows")
    xcp_subparsers = xcp.add_subparsers(dest="xcp_action", required=True)

    xcp_scan = xcp_subparsers.add_parser("scan", help="scan for XCP responders via CONNECT")
    xcp_scan.add_argument("interface", nargs="?")
    _add_xcp_id_arguments(xcp_scan)
    add_active_ack_argument(xcp_scan)
    xcp_scan.add_argument(
        "--dry-run",
        action="store_true",
        help="plan the CONNECT frame without opening the transport or transmitting",
    )
    add_output_arguments(xcp_scan)
    xcp_scan.set_defaults(command="xcp scan")

    xcp_trace = xcp_subparsers.add_parser("trace", help="trace XCP command/response transactions")
    xcp_trace.add_argument("interface", nargs="?")
    _add_xcp_id_arguments(xcp_trace)
    add_output_arguments(xcp_trace)
    xcp_trace.set_defaults(command="xcp trace")

    xcp_read = xcp_subparsers.add_parser("read", help="read DAQ measurement values from a capture")
    xcp_read.add_argument("interface", nargs="?")
    xcp_read.add_argument(
        "--response-id",
        default=hex(XCP_DEFAULT_RESPONSE_ID),
        help=f"slave response CAN id (default: {hex(XCP_DEFAULT_RESPONSE_ID)})",
    )
    add_output_arguments(xcp_read)
    xcp_read.set_defaults(command="xcp read")

    xcp_commands = xcp_subparsers.add_parser("commands", help="list the XCP command catalog")
    add_output_arguments(xcp_commands)
    xcp_commands.set_defaults(command="xcp commands")

    j1587 = subparsers.add_parser("j1587", help="J1587/J1708 legacy truck-bus workflows")
    j1587_subparsers = j1587.add_subparsers(dest="j1587_action", required=True)

    j1587_decode = j1587_subparsers.add_parser("decode", help="decode J1708 capture traffic")
    j1587_decode.add_argument("--file", required=True, help="path to a J1708 capture file")
    add_j1939_file_analysis_arguments(j1587_decode)
    add_output_arguments(j1587_decode)
    j1587_decode.set_defaults(command="j1587 decode")

    j1587_pids = j1587_subparsers.add_parser("pids", help="list the bundled J1587 PID catalog")
    add_output_arguments(j1587_pids)
    j1587_pids.set_defaults(command="j1587 pids")

    j2497 = subparsers.add_parser("j2497", help="J2497 (PLC4TRUCKS) trailer power-line workflows")
    j2497_subparsers = j2497.add_subparsers(dest="j2497_action", required=True)

    j2497_decode = j2497_subparsers.add_parser("decode", help="decode J2497 capture frames")
    j2497_decode.add_argument("--file", required=True, help="path to a J2497 capture file")
    add_j1939_file_analysis_arguments(j2497_decode)
    add_output_arguments(j2497_decode)
    j2497_decode.set_defaults(command="j2497 decode")

    j2497_mids = j2497_subparsers.add_parser("mids", help="list the bundled J2497 MID catalog")
    add_output_arguments(j2497_mids)
    j2497_mids.set_defaults(command="j2497 mids")

    re_parser = subparsers.add_parser("re", help="reverse engineering helpers")
    re_subparsers = re_parser.add_subparsers(dest="re_action", required=True)

    re_signals = re_subparsers.add_parser("signals", help="infer signal candidates")
    re_signals.add_argument("file", nargs="?", help="path to capture file")
    re_signals.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="path to capture file (equivalent to the positional form)",
    )
    add_output_arguments(re_signals)
    re_signals.set_defaults(command="re signals")

    re_counters = re_subparsers.add_parser("counters", help="detect counters")
    re_counters.add_argument("file", nargs="?", help="path to capture file")
    re_counters.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="path to capture file (equivalent to the positional form)",
    )
    add_output_arguments(re_counters)
    re_counters.set_defaults(command="re counters")

    re_entropy = re_subparsers.add_parser("entropy", help="rank signal entropy")
    re_entropy.add_argument("file", nargs="?", help="path to capture file")
    re_entropy.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="path to capture file (equivalent to the positional form)",
    )
    add_output_arguments(re_entropy)
    re_entropy.set_defaults(command="re entropy")

    re_correlate = re_subparsers.add_parser(
        "correlate", help="correlate signal candidates against a reference series"
    )
    re_correlate.add_argument("file", nargs="?", help="path to capture file")
    re_correlate.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="path to capture file (equivalent to the positional form)",
    )
    re_correlate.add_argument(
        "--reference",
        help="reference series file (.json or .jsonl) with timestamp and value fields",
    )
    add_output_arguments(re_correlate)
    re_correlate.set_defaults(command="re correlate")

    re_anomalies = re_subparsers.add_parser(
        "anomalies",
        help="flag inter-frame-timing outliers and unexpected arbitration IDs",
    )
    re_anomalies.add_argument("file", nargs="?", help="path to capture file")
    re_anomalies.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="path to capture file (equivalent to the positional form)",
    )
    re_anomalies.add_argument(
        "--baseline",
        help="reference capture to learn expected timing and ID coverage from",
    )
    re_anomalies.add_argument(
        "--dbc",
        help="database (DBC/ARXML/KCD/SYM or provider ref) whose cycle time and send "
        "type classify which messages are cyclic; authoritative over the CV guard",
    )
    re_anomalies.add_argument(
        "--z-threshold",
        type=float,
        default=3.0,
        help="minimum absolute z-score to flag a timing anomaly (default: 3.0)",
    )
    re_anomalies.add_argument(
        "--cv-max",
        type=float,
        default=0.5,
        help="max coefficient of variation for an ID to be treated as cyclic when "
        "no DBC is supplied; higher-variance IDs are treated as event-based (default: 0.5)",
    )
    re_anomalies.add_argument(
        "--min-samples",
        type=int,
        default=None,
        help="minimum inter-frame gaps required before an ID's timing is scored "
        "(default: 3 with a baseline, 10 without one; sparser IDs are reported "
        "as low-rate instead of ranked)",
    )
    _add_file_analysis_arguments(re_anomalies)
    add_output_arguments(re_anomalies)
    re_anomalies.set_defaults(command="re anomalies")

    re_match_dbc = re_subparsers.add_parser(
        "match-dbc", help="rank candidate DBCs against a capture"
    )
    re_match_dbc.add_argument("capture", nargs="?", help="capture file to analyse")
    re_match_dbc.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="capture file to analyse (equivalent to the positional form)",
    )
    re_match_dbc.add_argument(
        "--provider", default="opendbc", help="DBC provider catalog to search (default: opendbc)"
    )
    re_match_dbc.add_argument(
        "--limit", type=int, default=10, help="maximum candidates to return (default: 10)"
    )
    add_output_arguments(re_match_dbc)
    re_match_dbc.set_defaults(command="re match-dbc")

    re_shortlist_dbc = re_subparsers.add_parser(
        "shortlist-dbc", help="rank candidate DBCs filtered by vehicle make"
    )
    re_shortlist_dbc.add_argument("capture", nargs="?", help="capture file to analyse")
    re_shortlist_dbc.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="capture file to analyse (equivalent to the positional form)",
    )
    re_shortlist_dbc.add_argument(
        "--make", required=True, help="vehicle make to pre-filter candidates (e.g. toyota)"
    )
    re_shortlist_dbc.add_argument(
        "--provider", default="opendbc", help="DBC provider catalog to search (default: opendbc)"
    )
    re_shortlist_dbc.add_argument(
        "--limit", type=int, default=10, help="maximum candidates to return (default: 10)"
    )
    add_output_arguments(re_shortlist_dbc)
    re_shortlist_dbc.set_defaults(command="re shortlist-dbc")

    re_corpus = re_subparsers.add_parser(
        "corpus",
        help="cross-capture corpus analysis: ID coverage, cycle-time drift, signal stability",
    )
    re_corpus.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="candump or PCAP capture files to analyse",
    )
    re_corpus.add_argument(
        "--file",
        dest="file_opt",
        action="append",
        metavar="PATH",
        help="capture file to analyse (repeatable; equivalent to the positional form)",
    )
    re_corpus.add_argument(
        "--corpus-glob",
        metavar="PATTERN",
        help="shell glob pattern to expand into capture files (e.g. 'captures/*.candump')",
    )
    re_corpus.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="N",
        help="skip the first N frames from each capture file",
    )
    re_corpus.add_argument(
        "--max-frames",
        type=int,
        default=None,
        metavar="N",
        help="limit analysis to the first N frames per capture",
    )
    re_corpus.add_argument(
        "--seconds",
        type=float,
        default=None,
        metavar="T",
        help="limit analysis to the first T seconds of each capture",
    )
    add_output_arguments(re_corpus)
    re_corpus.set_defaults(command="re corpus")

    re_suggest = re_subparsers.add_parser(
        "suggest", help="propose names for ranked signal candidates"
    )
    re_suggest.add_argument("file", nargs="?", help="path to capture file")
    re_suggest.add_argument(
        "--file",
        dest="file_opt",
        metavar="PATH",
        help="path to capture file (equivalent to the positional form)",
    )
    re_suggest.add_argument(
        "--reference-dbc",
        help="DBC/ARXML/KCD/SYM file or provider ref whose signals seed name suggestions",
    )
    re_suggest.add_argument(
        "--limit",
        type=int,
        default=25,
        help="maximum ranked candidates to name (default: 25)",
    )
    re_suggest.add_argument(
        "--llm",
        metavar="PROVIDER",
        help="optional, off-by-default external LLM provider for name enrichment (e.g. anthropic)",
    )
    re_suggest.add_argument(
        "--llm-model",
        help="model id for the --llm provider (provider default otherwise)",
    )
    re_suggest.add_argument(
        "--yes",
        action="store_true",
        help="confirm the external --llm call without an interactive prompt",
    )
    add_output_arguments(re_suggest)
    re_suggest.set_defaults(command="re suggest")

    plot_parser = subparsers.add_parser(
        "plot", help="plot decoded signal time-series from a capture"
    )
    plot_parser.add_argument(
        "--signal",
        dest="signals",
        action="append",
        required=True,
        metavar="SIGNAL",
        help="signal name to plot (repeat for multiple signals)",
    )
    _add_file_analysis_arguments(plot_parser)
    plot_parser.add_argument("--file", required=True, help="capture file path")
    plot_parser.add_argument("--dbc", required=True, help="path to DBC file")
    plot_parser.add_argument("--out", required=True, help="output file path")
    plot_parser.add_argument(
        "--format",
        dest="plot_format",
        choices=["png", "svg", "html"],
        default="png",
        help="output format (default: png)",
    )
    add_output_arguments(plot_parser)
    plot_parser.set_defaults(command="plot")

    fuzz = subparsers.add_parser(
        "fuzz",
        help="active-transmit fuzzing (gated by docs/design/active-transmit-safety.md)",
    )
    fuzz_subparsers = fuzz.add_subparsers(dest="fuzz_action", required=True)

    fuzz_payload = fuzz_subparsers.add_parser(
        "payload", help="mutate a fixed-id payload through a strategy"
    )
    fuzz_payload.add_argument("interface", nargs="?")
    fuzz_payload.add_argument("--id", required=True, help="hex CAN ID (e.g. 0x123)")
    fuzz_payload.add_argument(
        "--strategy",
        required=True,
        choices=("bitflip", "random", "boundary", "havoc", "splice", "interesting"),
        help="mutation strategy",
    )
    fuzz_payload.add_argument(
        "--data",
        default=None,
        help="baseline hex payload for bitflip / havoc; defaults to 8 zero bytes",
    )
    fuzz_payload.add_argument(
        "--dlc",
        type=int,
        default=8,
        help="payload length for random / boundary / interesting (default 8)",
    )
    fuzz_payload.add_argument(
        "--corpus",
        default=None,
        help="candump capture supplying the seed corpus for the splice strategy",
    )
    fuzz_payload.add_argument(
        "--max", dest="max_frames_fuzz", type=int, default=64, help="maximum frames to emit"
    )
    fuzz_payload.add_argument("--rate", type=float, default=100.0, help="frames per second")
    fuzz_payload.add_argument("--seed", type=int, default=0, help="seed for the mutator")
    fuzz_payload.add_argument(
        "--extended", action="store_true", help="treat --id as a 29-bit extended CAN ID"
    )
    fuzz_payload.add_argument(
        "--dry-run", action="store_true", help="emit JSONL plan without transmitting"
    )
    fuzz_payload.add_argument(
        "--repair-crc", action="store_true", help="recompute CRC in the last byte after mutation"
    )
    fuzz_payload.add_argument(
        "--crc-algorithm",
        choices=("stellantis", "sae-j1850", "fca-giorgio"),
        default=None,
        help="CRC algorithm for --repair-crc (default: stellantis)",
    )
    fuzz_payload.add_argument(
        "--crc-address",
        type=lambda x: int(x, 0),
        default=None,
        help="CAN arbitration ID for CRC computation (required by some algorithms, e.g. fca-giorgio)",
    )
    fuzz_payload.add_argument(
        "--run-id", default=None, help="explicit run UUID (random if omitted)"
    )
    add_active_ack_argument(fuzz_payload)
    add_output_arguments(fuzz_payload)
    fuzz_payload.set_defaults(command="fuzz payload")

    fuzz_replay = fuzz_subparsers.add_parser(
        "replay", help="replay a recorded capture with mutation applied"
    )
    fuzz_replay.add_argument("--file", required=True, help="candump capture file to mutate-replay")
    fuzz_replay.add_argument(
        "--interface",
        default=None,
        help="target interface; required unless --dry-run",
    )
    fuzz_replay.add_argument(
        "--strategy",
        required=True,
        choices=("timing", "payload-bitflip"),
        help="mutation strategy",
    )
    fuzz_replay.add_argument(
        "--max", dest="max_frames_fuzz", type=int, default=None, help="cap on emitted frames"
    )
    fuzz_replay.add_argument(
        "--rate", type=float, default=100.0, help="frames per second (applies to live transmit)"
    )
    fuzz_replay.add_argument("--seed", type=int, default=0, help="seed for the mutator")
    fuzz_replay.add_argument(
        "--dry-run", action="store_true", help="emit JSONL plan without transmitting"
    )
    fuzz_replay.add_argument(
        "--repair-crc", action="store_true", help="recompute CRC in the last byte after mutation"
    )
    fuzz_replay.add_argument(
        "--crc-algorithm",
        choices=("stellantis", "sae-j1850", "fca-giorgio"),
        default=None,
        help="CRC algorithm for --repair-crc (default: stellantis)",
    )
    fuzz_replay.add_argument(
        "--crc-address",
        type=lambda x: int(x, 0),
        default=None,
        help="CAN arbitration ID for CRC computation (required by some algorithms, e.g. fca-giorgio)",
    )
    fuzz_replay.add_argument("--run-id", default=None, help="explicit run UUID (random if omitted)")
    add_active_ack_argument(fuzz_replay)
    add_output_arguments(fuzz_replay)
    fuzz_replay.set_defaults(command="fuzz replay")

    fuzz_arbid = fuzz_subparsers.add_parser(
        "arbitration-id",
        help="walk an arbitration-id range emitting one frame per ID",
    )
    fuzz_arbid.add_argument("interface", nargs="?")
    fuzz_arbid.add_argument(
        "--range",
        dest="id_range",
        required=True,
        help="start:end hex ID range, inclusive (e.g. 0x100:0x110)",
    )
    fuzz_arbid.add_argument(
        "--step", type=int, default=1, help="ID step within the range (default 1)"
    )
    fuzz_arbid.add_argument(
        "--data", default=None, help="payload hex for every frame; defaults to 8 zero bytes"
    )
    fuzz_arbid.add_argument("--rate", type=float, default=100.0, help="frames per second")
    fuzz_arbid.add_argument("--extended", action="store_true", help="emit 29-bit extended CAN IDs")
    fuzz_arbid.add_argument(
        "--dry-run", action="store_true", help="emit JSONL plan without transmitting"
    )
    fuzz_arbid.add_argument(
        "--repair-crc", action="store_true", help="recompute CRC in the last byte after mutation"
    )
    fuzz_arbid.add_argument(
        "--crc-algorithm",
        choices=("stellantis", "sae-j1850", "fca-giorgio"),
        default=None,
        help="CRC algorithm for --repair-crc (default: stellantis)",
    )
    fuzz_arbid.add_argument(
        "--crc-address",
        type=lambda x: int(x, 0),
        default=None,
        help="CAN arbitration ID for CRC computation (required by some algorithms, e.g. fca-giorgio)",
    )
    fuzz_arbid.add_argument("--run-id", default=None, help="explicit run UUID (random if omitted)")
    add_active_ack_argument(fuzz_arbid)
    add_output_arguments(fuzz_arbid)
    fuzz_arbid.set_defaults(command="fuzz arbitration-id")

    fuzz_signal = fuzz_subparsers.add_parser(
        "signal", help="mutate a single DBC signal within or beyond its declared bounds"
    )
    fuzz_signal.add_argument("interface", nargs="?")
    fuzz_signal.add_argument(
        "--dbc", required=True, help="DBC path or provider ref (e.g. opendbc:...)"
    )
    fuzz_signal.add_argument("--message", required=True, help="DBC message name")
    fuzz_signal.add_argument("--signal", required=True, help="signal name to mutate")
    fuzz_signal.add_argument(
        "--mode",
        required=True,
        choices=("in_bounds", "out_of_bounds", "boundary", "enum_gaps", "full_field"),
        help="mutation mode (full_field sweeps the whole signal field, ignoring DBC bounds)",
    )
    fuzz_signal.add_argument(
        "--count", type=int, default=64, help="maximum mutated frames to emit (default 64)"
    )
    fuzz_signal.add_argument("--rate", type=float, default=100.0, help="frames per second")
    fuzz_signal.add_argument("--seed", type=int, default=0, help="seed for the mutator")
    fuzz_signal.add_argument(
        "--dry-run", action="store_true", help="emit JSONL plan without transmitting"
    )
    fuzz_signal.add_argument("--run-id", default=None, help="explicit run UUID (random if omitted)")
    add_active_ack_argument(fuzz_signal)
    add_output_arguments(fuzz_signal)
    fuzz_signal.set_defaults(command="fuzz signal")

    fuzz_spn = fuzz_subparsers.add_parser(
        "spn", help="mutate a J1939 SPN across its operational range and sentinels"
    )
    fuzz_spn.add_argument("interface", nargs="?")
    fuzz_spn.add_argument("--spn", required=True, type=int, help="J1939 SPN to mutate")
    fuzz_spn.add_argument(
        "--pgn",
        type=lambda x: int(x, 0),
        default=None,
        help="expected PGN (validated against the SPN's PGN; derived if omitted)",
    )
    fuzz_spn.add_argument(
        "--mode",
        required=True,
        choices=("in_bounds", "not_available", "error", "out_of_bounds", "boundary"),
        help="mutation mode (not_available / error emit the J1939 sentinels)",
    )
    fuzz_spn.add_argument(
        "--count", type=int, default=64, help="maximum mutated frames to emit (default 64)"
    )
    fuzz_spn.add_argument("--rate", type=float, default=100.0, help="frames per second")
    fuzz_spn.add_argument("--seed", type=int, default=0, help="seed for the mutator")
    fuzz_spn.add_argument(
        "--dry-run", action="store_true", help="emit JSONL plan without transmitting"
    )
    fuzz_spn.add_argument("--run-id", default=None, help="explicit run UUID (random if omitted)")
    add_active_ack_argument(fuzz_spn)
    add_output_arguments(fuzz_spn)
    fuzz_spn.set_defaults(command="fuzz spn")

    fuzz_guided = fuzz_subparsers.add_parser(
        "guided", help="response-feedback guided fuzzing against an ECU target"
    )
    fuzz_guided.add_argument("interface", nargs="?")
    fuzz_guided.add_argument(
        "--id",
        dest="arbitration_id",
        required=True,
        help="arbitration id to transmit fuzzed payloads on (decimal or 0x hex)",
    )
    fuzz_guided.add_argument("--extended", action="store_true", help="send on a 29-bit extended id")
    fuzz_guided.add_argument(
        "--signals",
        default=",".join(SIGNAL_CATEGORIES),
        help=f"comma list of feedback signals to use (default: {','.join(SIGNAL_CATEGORIES)})",
    )
    fuzz_guided.add_argument(
        "--corpus", default=None, help="seed-corpus directory (persisted/reused)"
    )
    fuzz_guided.add_argument(
        "--seed-data", default=None, help="initial seed payload as hex (defaults to 8 zero bytes)"
    )
    fuzz_guided.add_argument(
        "--max-iterations", type=int, default=200, help="campaign iteration budget (default 200)"
    )
    fuzz_guided.add_argument(
        "--max-seconds", type=float, default=None, help="campaign wall-clock budget in seconds"
    )
    fuzz_guided.add_argument(
        "--max-corpus", type=int, default=64, help="maximum retained corpus seeds (default 64)"
    )
    fuzz_guided.add_argument("--rate", type=float, default=100.0, help="iterations per second")
    fuzz_guided.add_argument("--seed", type=int, default=0, help="deterministic RNG seed")
    add_active_ack_argument(fuzz_guided)
    fuzz_guided.add_argument(
        "--dry-run", action="store_true", help="plan the campaign without opening the transport"
    )
    add_output_arguments(fuzz_guided)
    fuzz_guided.set_defaults(command="fuzz guided")

    config = subparsers.add_parser("config", help="inspect CANarchy configuration")
    config_subparsers = config.add_subparsers(dest="config_action", required=True)
    config_show = config_subparsers.add_parser(
        "show", help="show effective transport configuration"
    )
    add_output_arguments(config_show)
    config_show.set_defaults(command="config show")

    doctor = subparsers.add_parser(
        "doctor",
        help="run environment health checks (Python, python-can, caches, MCP, config)",
    )
    add_output_arguments(doctor)
    doctor.set_defaults(command="doctor")

    completion = subparsers.add_parser(
        "completion",
        help="emit a shell completion script (bash, zsh, or fish)",
    )
    completion.add_argument(
        "shell",
        choices=SUPPORTED_SHELLS,
        help="target shell flavour for the completion script",
    )
    completion.set_defaults(command="completion")

    mcp = subparsers.add_parser("mcp", help="MCP server workflows")
    mcp_subparsers = mcp.add_subparsers(dest="mcp_action", required=True)
    mcp_serve = mcp_subparsers.add_parser("serve", help="start MCP server over stdio")
    mcp_serve.set_defaults(command="mcp serve")

    web = subparsers.add_parser("web", help="read-only browser dashboard")
    web_subparsers = web.add_subparsers(dest="web_action", required=True)
    web_serve = web_subparsers.add_parser(
        "serve", help="serve the read-only dashboard over HTTP + WebSocket"
    )
    web_serve.add_argument(
        "--file", required=True, help="capture file to stream over the dashboard"
    )
    web_serve.add_argument(
        "--dbc", help="database (path or provider ref) for decoded-signal events"
    )
    web_serve.add_argument(
        "--bind",
        default="127.0.0.1:8474",
        help="host:port to bind the dashboard to (default: 127.0.0.1:8474)",
    )
    web_serve.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="playback rate multiplier for the capture stream (default: 1.0)",
    )
    web_serve.add_argument(
        "--loop",
        action="store_true",
        help="restart the capture stream when it completes",
    )
    web_serve.add_argument(
        "--read-only",
        action="store_true",
        default=True,
        help="serve without any transmit endpoints (always on; v1 exposes no active surface)",
    )
    _add_file_analysis_arguments(web_serve)
    add_output_arguments(web_serve)
    web_serve.set_defaults(command="web serve")

    cannelloni = subparsers.add_parser(
        "cannelloni", help="cannelloni CAN-over-UDP wire-format interop"
    )
    cannelloni_subparsers = cannelloni.add_subparsers(dest="cannelloni_action", required=True)

    cannelloni_decode = cannelloni_subparsers.add_parser(
        "decode", help="decode a captured cannelloni datagram payload into frames"
    )
    cannelloni_decode.add_argument(
        "--file", required=True, help="path to a raw cannelloni datagram payload file"
    )
    add_output_arguments(cannelloni_decode)
    cannelloni_decode.set_defaults(command="cannelloni decode")

    cannelloni_send = cannelloni_subparsers.add_parser(
        "send", help="transmit a capture to a cannelloni endpoint as UDP datagrams"
    )
    cannelloni_send.add_argument("target", help="cannelloni endpoint as <host>:<port>")
    cannelloni_send.add_argument("--file", required=True, help="candump/PCAP capture to transmit")
    cannelloni_send.add_argument(
        "--seq-no", type=int, default=0, help="starting cannelloni sequence number (default: 0)"
    )
    cannelloni_send.add_argument(
        "--max-count",
        type=int,
        default=64,
        help="maximum CAN frames per UDP datagram (default: 64)",
    )
    cannelloni_send.add_argument(
        "--mtu",
        type=int,
        default=1500,
        help="maximum encoded bytes per UDP datagram so a peer's MTU is not "
        "overrun (default: 1500; 0 disables the byte cap)",
    )
    cannelloni_send.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="datagrams per second (0 = send as fast as possible; default: 0)",
    )
    add_active_ack_argument(cannelloni_send)
    cannelloni_send.add_argument(
        "--dry-run",
        action="store_true",
        help="plan the datagrams without opening a socket or transmitting",
    )
    _add_file_analysis_arguments(cannelloni_send)
    add_output_arguments(cannelloni_send)
    cannelloni_send.set_defaults(command="cannelloni send")

    mcp_install = mcp_subparsers.add_parser(
        "install", help="write the canarchy MCP server block into a client config"
    )
    mcp_install.add_argument(
        "--client",
        required=True,
        choices=("claude-desktop", "claude-code"),
        help="target MCP client",
    )
    mcp_install.add_argument(
        "--config-path",
        default=None,
        help="override the auto-detected client config path",
    )
    mcp_install.add_argument(
        "--command",
        dest="server_command",
        default="canarchy",
        help="command the client runs for the server (default: canarchy)",
    )
    mcp_install.add_argument(
        "--dry-run",
        action="store_true",
        help="print the would-write config without touching disk",
    )
    mcp_install.add_argument(
        "--ack",
        action="store_true",
        help="skip the confirmation prompt and write immediately",
    )
    add_output_arguments(mcp_install)
    mcp_install.set_defaults(command="mcp install")

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
    for name in ("json", "jsonl", "text"):
        if getattr(args, name, False):
            return name
    if getattr(args, "table", False):
        return "text"
    return "text"


def requested_output_format(argv: Sequence[str] | None) -> str:
    if argv is None:
        return "text"

    for name in ("json", "jsonl", "text"):
        if f"--{name}" in argv:
            return name
    if "--table" in argv:
        return "text"
    return "text"


def active_transmit_preflight_warning(args: argparse.Namespace) -> str:
    if args.command == "send":
        return (
            f"warning: `send` will transmit a CAN frame on interface `{args.interface}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "generate":
        return (
            f"warning: `generate` will transmit generated frames on interface `{args.interface}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "simulate":
        return (
            f"warning: `simulate` will transmit `{args.profile}` profile traffic on interface "
            f"`{args.interface}`; use intentionally on a controlled bus."
        )
    if _is_doip_active_command(args):
        return (
            f"warning: `{args.command}` will open a DoIP session and transmit diagnostic "
            f"requests to `{args.interface}`; use intentionally against a controlled endpoint."
        )
    if args.command == "uds scan":
        return (
            f"warning: `uds scan` will transmit diagnostic requests on interface `{args.interface}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "xcp scan":
        return (
            f"warning: `xcp scan` will transmit an XCP CONNECT request on interface "
            f"`{args.interface}`; use intentionally on a controlled bus."
        )
    if args.command == "gateway":
        return (
            f"warning: `gateway` will forward traffic from `{args.src}` to `{args.dst}`; "
            "use intentionally on a controlled bus."
        )
    if args.command in FUZZ_COMMANDS:
        target = getattr(args, "interface", None) or getattr(args, "file", "<input>")
        sub = args.command.removeprefix("fuzz ")
        return (
            f"warning: `fuzz {sub}` will transmit mutated frames on `{target}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "fuzz guided":
        return (
            f"warning: `fuzz guided` will transmit mutated frames on interface "
            f"`{args.interface}` and observe the target's responses; "
            "use intentionally on a controlled bus."
        )
    if args.command == "replay":
        return (
            f"warning: `replay` will transmit recorded frames on interface `{args.interface}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "sequence replay":
        return (
            f"warning: `sequence replay` will transmit DBC-encoded frames on interface `{args.interface}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "cannelloni send":
        return (
            f"warning: `cannelloni send` will transmit UDP datagrams to `{args.target}`; "
            "use intentionally against a controlled endpoint."
        )
    raise AssertionError(f"unsupported active transmit command: {args.command}")


def active_transmit_confirmation_prompt(args: argparse.Namespace) -> str:
    if args.command == "send":
        return f"confirm: type YES to send on `{args.interface}`: "
    if args.command == "generate":
        return f"confirm: type YES to generate frames on `{args.interface}`: "
    if args.command == "simulate":
        return f"confirm: type YES to simulate `{args.profile}` traffic on `{args.interface}`: "
    if _is_doip_active_command(args):
        return (
            f"confirm: type YES to run `{args.command}` against DoIP endpoint `{args.interface}`: "
        )
    if args.command == "uds scan":
        return f"confirm: type YES to run UDS scan on `{args.interface}`: "
    if args.command == "xcp scan":
        return f"confirm: type YES to run XCP scan on `{args.interface}`: "
    if args.command == "gateway":
        return f"confirm: type YES to forward traffic from `{args.src}` to `{args.dst}`: "
    if args.command in FUZZ_COMMANDS:
        target = getattr(args, "interface", None) or getattr(args, "file", "<input>")
        sub = args.command.removeprefix("fuzz ")
        return f"confirm: type YES to fuzz `{sub}` on `{target}`: "
    if args.command == "fuzz guided":
        return f"confirm: type YES to run guided fuzzing on `{args.interface}`: "
    if args.command == "replay":
        return f"confirm: type YES to replay frames on `{args.interface}`: "
    if args.command == "sequence replay":
        return f"confirm: type YES to transmit sequence on `{args.interface}`: "
    if args.command == "cannelloni send":
        return f"confirm: type YES to transmit cannelloni datagrams to `{args.target}`: "
    raise AssertionError(f"unsupported active transmit command: {args.command}")


INTERFACE_FALLBACK_COMMANDS = {
    "capture",
    "send",
    "generate",
    "simulate",
    "j1939 monitor",
    "uds scan",
    "uds trace",
    "xcp scan",
    "xcp trace",
    "xcp read",
    "fuzz guided",
    "fuzz payload",
    "fuzz replay",
    "fuzz arbitration-id",
    "fuzz signal",
    "fuzz spn",
}


# Commands that historically took a positional capture path also accept a
# `--file` flag form (#412); both forms map onto the original destination.
_FILE_FLAG_SINGLE_COMMANDS = {
    "re signals": "file",
    "re counters": "file",
    "re entropy": "file",
    "re correlate": "file",
    "re anomalies": "file",
    "re suggest": "file",
    "re match-dbc": "capture",
    "re shortlist-dbc": "capture",
}
_FILE_FLAG_MULTI_COMMANDS = {"re corpus", "j1939 compare"}


def _normalize_file_arguments(args: argparse.Namespace) -> None:
    """Merge the `--file` flag form into the positional capture destination."""
    command = getattr(args, "command", None)
    flag_value = getattr(args, "file_opt", None)
    if command in _FILE_FLAG_SINGLE_COMMANDS:
        dest = _FILE_FLAG_SINGLE_COMMANDS[command]
        positional = getattr(args, dest, None)
        if flag_value is not None and positional is not None and flag_value != positional:
            raise CommandError(
                command=command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="CONFLICTING_FILE_ARGUMENTS",
                        message=(
                            f"Both a positional capture path ({positional!r}) and --file "
                            f"({flag_value!r}) were supplied."
                        ),
                        hint="Pass the capture path once, either positionally or via --file.",
                    )
                ],
            )
        if positional is None and flag_value is not None:
            setattr(args, dest, flag_value)
        if getattr(args, dest, None) is None:
            raise CommandError(
                command=command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="CAPTURE_FILE_REQUIRED",
                        message="A capture file is required.",
                        hint=(
                            "Pass the capture path positionally "
                            f"(`canarchy {command} <file>`) or via `--file <file>`."
                        ),
                    )
                ],
            )
    elif command in _FILE_FLAG_MULTI_COMMANDS and flag_value:
        files = list(getattr(args, "files", []) or [])
        files += [value for value in flag_value if value not in files]
        args.files = files


def prepare_args(args: argparse.Namespace) -> None:
    _normalize_file_arguments(args)
    if args.command == "send":
        send_args = getattr(args, "send_args", [])
        dbc_mode = bool(getattr(args, "dbc", None))
        if dbc_mode:
            if len(send_args) == 1:
                args.interface = send_args[0]
            elif len(send_args) == 0:
                args.interface = None
            else:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_ARGUMENTS",
                            message="send --dbc accepts at most one positional argument: the CAN interface.",
                            hint="Usage: canarchy send [interface] --dbc <dbc> --message <msg> --signals KEY=VAL ...",
                        )
                    ],
                )
        elif len(send_args) == 3:
            args.interface, args.frame_id, args.data = send_args
        elif len(send_args) == 2:
            args.interface = None
            args.frame_id, args.data = send_args
        else:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_ARGUMENTS",
                        message="send requires either <interface> <frame_id> <data> or <frame_id> <data> with a configured default interface.",
                        hint="Pass an interface explicitly or set `[transport].default_interface` in `~/.canarchy/config.toml`.",
                    )
                ],
            )

    if args.command not in INTERFACE_FALLBACK_COMMANDS:
        return
    if getattr(args, "interface", None):
        args.interface_source = "cli"
        return
    configured = default_can_interface()
    if configured:
        args.interface = configured
        args.interface_source = "config"
        return
    args.interface_source = "missing"
    if args.command == "j1939 monitor":
        return
    if args.command == "fuzz replay":
        return
    if args.command in ("fuzz signal", "fuzz spn") and getattr(args, "dry_run", False):
        return
    if args.command == "generate" and getattr(args, "dry_run", False):
        return
    if args.command == "simulate" and getattr(args, "dry_run", False):
        return
    if args.command == "send" and getattr(args, "dry_run", False):
        return
    if args.command == "xcp scan" and getattr(args, "dry_run", False):
        return
    if args.command == "fuzz guided" and getattr(args, "dry_run", False):
        return
    raise CommandError(
        command=args.command,
        exit_code=EXIT_USER_ERROR,
        errors=[
            ErrorDetail(
                code="INTERFACE_REQUIRED",
                message=f"{args.command} requires a CAN interface.",
                hint="Pass an interface on the command line or set `[transport].default_interface` in `~/.canarchy/config.toml`.",
            )
        ],
    )


def _is_doip_active_command(args: argparse.Namespace) -> bool:
    """`uds scan` / `uds trace` over DoIP open a TCP session and transmit."""
    return args.command in ("uds scan", "uds trace") and is_doip_target(
        getattr(args, "interface", None)
    )


def enforce_active_transmit_safety(
    args: argparse.Namespace,
) -> None:
    if args.command not in ACTIVE_TRANSMIT_COMMANDS and not _is_doip_active_command(args):
        return

    print(active_transmit_preflight_warning(args), file=sys.stderr)
    ack_active = getattr(args, "ack_active", False)
    if active_ack_required() and not ack_active:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="ACTIVE_ACK_REQUIRED",
                    message="Active transmission acknowledgement is required before this command can proceed.",
                    hint="Re-run with `--ack-active` or disable `[safety].require_active_ack` in `~/.canarchy/config.toml`.",
                )
            ],
            data={"mode": "active"},
        )
    if not ack_active:
        return

    # Non-interactive callers (the MCP server, programmatic embeds, CI
    # harnesses that explicitly opt in) cannot answer a `YES` prompt —
    # and on the MCP path `sys.stdin` is the JSON-RPC protocol stream,
    # so reading from it would consume bytes we don't own. The env var
    # is the explicit signal that the surrounding context has already
    # authorised this invocation. Matches REQ-ATS-03 in
    # `docs/design/active-transmit-safety.md`.
    if os.environ.get("CANARCHY_MCP_NONINTERACTIVE_ACK") == "1":
        return

    print(active_transmit_confirmation_prompt(args), file=sys.stderr, end="", flush=True)
    confirmation = sys.stdin.readline().strip()
    if confirmation == "YES":
        return

    raise CommandError(
        command=args.command,
        exit_code=EXIT_USER_ERROR,
        errors=[
            ErrorDetail(
                code="ACTIVE_CONFIRMATION_DECLINED",
                message="Active transmission confirmation was not accepted.",
                hint="Re-run with `--ack-active` and reply `YES` to the confirmation prompt.",
            )
        ],
        data={"mode": "active"},
    )


def validate_args(args: argparse.Namespace) -> None:
    if args.command == "re correlate" and not getattr(args, "reference", None):
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="RE_REFERENCE_REQUIRED",
                    message="re correlate requires a --reference file.",
                    hint="Provide a JSON or JSONL reference series file with timestamp and value fields.",
                )
            ],
        )
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
    if args.command == "sequence replay" and (not math.isfinite(args.rate) or args.rate <= 0):
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_RATE",
                    message="Sequence replay rate must be a finite positive number.",
                    hint="Pass a positive value to --rate, such as 1.0 or 2.0.",
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
        if not getattr(args, "dbc", None):
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
        else:
            if not getattr(args, "message", None):
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="MISSING_MESSAGE",
                            message="--message is required when --dbc is specified.",
                            hint="Pass the DBC message name, e.g. `--message EngineStatus1`.",
                        )
                    ],
                )
            for assignment in getattr(args, "signals", []) or []:
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
            if getattr(args, "rate", None) is not None and (
                not math.isfinite(args.rate) or args.rate <= 0
            ):
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_RATE",
                            message="--rate must be greater than zero.",
                            hint="Pass a positive value such as `--rate 10`.",
                        )
                    ],
                    data={"rate": args.rate},
                )
            if args.count < 1:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="INVALID_COUNT",
                            message="--count must be a positive integer.",
                            hint="Pass a positive integer such as `--count 5`.",
                        )
                    ],
                    data={"count": args.count},
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

    if args.command == "j1939 spn" and args.spn not in get_j1939_decoder().supported_spns():
        dbc_ref = getattr(args, "dbc", None) or default_j1939_dbc()
        if dbc_ref and dbc_supports_spn(dbc_ref, args.spn):
            return
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="J1939_SPN_UNSUPPORTED",
                    message=f"J1939 SPN {args.spn} is not supported by the current decoder set.",
                    hint="Use a supported SPN, or provide a J1939 DBC via --dbc or CANARCHY_J1939_DBC that defines the requested SPN.",
                )
            ],
            data={"spn": args.spn},
        )

    if args.command in {
        "filter",
        "stats",
        "decode",
        "j1939 decode",
        "j1939 pgn",
        "j1939 spn",
        "j1939 tp sessions",
        "j1939 tp compare",
        "j1939 dm1",
        "j1939 faults",
        "j1939 summary",
        "j1939 inventory",
        "j1939 compare",
        "j1939 map",
        "j1587 decode",
        "j2497 decode",
    }:
        max_frames = getattr(args, "max_frames", None)
        seconds = getattr(args, "seconds", None)
        if max_frames is not None and max_frames < 1:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_MAX_FRAMES",
                        message="Maximum frame bound must be at least 1.",
                        hint="Pass a positive integer to --max-frames.",
                    )
                ],
                data={"max_frames": max_frames},
            )
        if seconds is not None and seconds < 0:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_ANALYSIS_SECONDS",
                        message="Analysis time bound must be zero or greater.",
                        hint="Pass a non-negative value to --seconds.",
                    )
                ],
                data={"seconds": seconds},
            )
        if getattr(args, "stdin", False) and (max_frames is not None or seconds is not None):
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="ANALYSIS_WINDOW_REQUIRES_FILE",
                        message="Bounded-analysis flags currently require a capture file.",
                        hint="Use a capture file for --max-frames or --seconds, or remove those flags when using --stdin.",
                    )
                ],
            )

    if args.command in {"j1939 tp sessions", "j1939 tp compare", "j1939 dm1", "j1939 faults"}:
        sa_arg = getattr(args, "sa", None)
        if sa_arg is not None:
            for token in sa_arg.split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    int(token, 0)
                except ValueError:
                    raise CommandError(
                        command=args.command,
                        exit_code=EXIT_USER_ERROR,
                        errors=[
                            ErrorDetail(
                                code="INVALID_SOURCE_ADDRESS",
                                message=f"Invalid source address value: {token!r}",
                                hint="Source addresses must be integers (e.g. 128, 0x80). Separate multiple values with commas.",
                            )
                        ],
                        data={"sa": sa_arg},
                    )

    if args.command == "j1939 compare" and len(args.files) < 2:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="J1939_COMPARE_REQUIRES_MULTIPLE_FILES",
                    message="J1939 capture comparison requires at least two capture files.",
                    hint="Pass two or more candump files to `canarchy j1939 compare`.",
                )
            ],
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


LARGE_FILE_AUTO_CAP_BYTES = 50 * 1024 * 1024
LARGE_FILE_AUTO_CAP_FRAMES = 500_000


def j1939_file_analysis_kwargs(args: argparse.Namespace) -> dict[str, int | float | None]:
    return {
        "offset": getattr(args, "offset", 0),
        "max_frames": getattr(args, "max_frames", None),
        "seconds": getattr(args, "seconds", None),
    }


def _large_file_kwargs(
    args: argparse.Namespace, file: str, warnings: list[str]
) -> dict[str, int | float | None]:
    """Apply auto-cap when the file exceeds the large-file threshold and no limit is set."""
    kwargs = j1939_file_analysis_kwargs(args)
    if kwargs["max_frames"] is None and kwargs["seconds"] is None:
        try:
            size = Path(file).stat().st_size
        except OSError:
            return kwargs
        if size >= LARGE_FILE_AUTO_CAP_BYTES:
            kwargs["max_frames"] = LARGE_FILE_AUTO_CAP_FRAMES
            warnings.append(
                f"Large file detected ({size // (1024 * 1024)} MB); analysis capped at "
                f"{LARGE_FILE_AUTO_CAP_FRAMES:,} frames. "
                "Use --max-frames or --seconds to override."
            )
    return kwargs


def _extract_printable_text(payload: bytes) -> str | None:
    stripped = payload.rstrip(b"\x00\xff ")
    if len(stripped) < 4:
        return None
    if not all(0x20 <= byte <= 0x7E for byte in stripped):
        return None
    text = stripped.decode("ascii", errors="ignore").strip()
    return text or None


def _top_counts(counter: Counter[int], *, limit: int = 5) -> list[dict[str, int]]:
    return [{"value": value, "frame_count": count} for value, count in counter.most_common(limit)]


def _tp_payload_label(transfer_pgn: int) -> str | None:
    labels = {
        65242: "software_identification",
        65259: "component_identification",
        65260: "vehicle_identification",
    }
    return labels.get(transfer_pgn)


def _enrich_tp_session(session: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(session)
    transfer_pgn = int(enriched["transfer_pgn"])
    enriched["payload_label"] = _tp_payload_label(transfer_pgn)
    enriched["payload_label_source"] = (
        "known_transfer_pgn" if enriched["payload_label"] is not None else None
    )
    enriched["decoded_text"] = None
    enriched["decoded_text_encoding"] = None
    enriched["decoded_text_heuristic"] = False
    enriched["payload_hash"] = None

    raw = enriched.get("reassembled_data")
    try:
        payload = bytes.fromhex(str(raw)) if raw else b""
    except ValueError:
        payload = b""

    if payload:
        enriched["payload_hash"] = hashlib.sha256(payload).hexdigest()

    if not bool(enriched.get("complete", False)):
        return enriched

    text = _extract_printable_text(payload)
    if text is None:
        return enriched

    enriched["decoded_text"] = text
    enriched["decoded_text_encoding"] = "ascii"
    enriched["decoded_text_heuristic"] = True
    return enriched


def _j1939_summary(
    frames: list[CanFrame], *, file: str, decoder: Any
) -> tuple[dict[str, Any], list[str]]:
    if not frames:
        return (
            {
                "mode": "passive",
                "file": file,
                "total_frames": 0,
                "interfaces": [],
                "unique_arbitration_ids": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "duration_seconds": 0.0,
                "j1939_frame_count": 0,
                "unique_pgns": 0,
                "top_pgns": [],
                "top_source_addresses": [],
                "dm1": {
                    "present": False,
                    "message_count": 0,
                    "active_dtc_count": 0,
                    "source_addresses": [],
                },
                "tp": {
                    "session_count": 0,
                    "complete_session_count": 0,
                    "session_types": {},
                    "printable_identifiers": [],
                },
            },
            ["No frames were found in the capture."],
        )

    identifiers = [
        decompose_arbitration_id(frame.arbitration_id) for frame in frames if frame.is_extended_id
    ]
    pgn_counts: Counter[int] = Counter(identifier.pgn for identifier in identifiers)
    source_counts: Counter[int] = Counter(identifier.source_address for identifier in identifiers)
    interfaces = sorted({frame.interface or "unknown" for frame in frames})
    timestamps = [frame.timestamp for frame in frames]
    dm1_messages = decoder.dm1_messages(frames)
    tp_sessions = [
        _enrich_tp_session(session) for session in decoder.transport_protocol_sessions(frames)
    ]
    session_types = Counter(str(session["session_type"]) for session in tp_sessions)
    # Repeated BAM broadcasts carry the same identifier once per session;
    # report distinct values with an occurrence count instead (#411), matching
    # the deduped shape `j1939 compare` uses.
    identifier_map: dict[tuple[object, ...], dict[str, object]] = {}
    for session in tp_sessions:
        if not bool(session.get("complete", False)):
            continue
        text = session.get("decoded_text")
        if text is None:
            continue
        source_address = int(session["source_address"])
        key = (
            text,
            int(session["transfer_pgn"]),
            source_address,
            session["destination_address"],
            str(session["session_type"]),
            session.get("payload_label"),
        )
        entry = identifier_map.get(key)
        if entry is None:
            identifier_map[key] = {
                "text": text,
                "transfer_pgn": int(session["transfer_pgn"]),
                "source_address": source_address,
                "source_address_name": source_address_lookup(source_address),
                "destination_address": session["destination_address"],
                "session_type": str(session["session_type"]),
                "payload_label": session.get("payload_label"),
                "heuristic": bool(session.get("decoded_text_heuristic", False)),
                "occurrence_count": 1,
            }
        else:
            entry["occurrence_count"] = int(entry["occurrence_count"]) + 1
    printable_identifiers = list(identifier_map.values())

    return (
        {
            "mode": "passive",
            "file": file,
            "total_frames": len(frames),
            "interfaces": interfaces,
            "unique_arbitration_ids": len({frame.arbitration_id for frame in frames}),
            "first_timestamp": timestamps[0],
            "last_timestamp": timestamps[-1],
            "duration_seconds": timestamps[-1] - timestamps[0],
            "j1939_frame_count": len(identifiers),
            "unique_pgns": len(pgn_counts),
            "top_pgns": [
                {"pgn": entry["value"], "frame_count": entry["frame_count"]}
                for entry in _top_counts(pgn_counts)
            ],
            "top_source_addresses": [
                {"source_address": entry["value"], "frame_count": entry["frame_count"]}
                for entry in _top_counts(source_counts)
            ],
            "dm1": {
                "present": bool(dm1_messages),
                "message_count": len(dm1_messages),
                "active_dtc_count": sum(
                    int(message["active_dtc_count"]) for message in dm1_messages
                ),
                "source_addresses": sorted(
                    {int(message["source_address"]) for message in dm1_messages}
                ),
            },
            "tp": {
                "session_count": len(tp_sessions),
                "complete_session_count": sum(
                    1 for session in tp_sessions if bool(session.get("complete", False))
                ),
                "session_types": dict(sorted(session_types.items())),
                "printable_identifiers": printable_identifiers,
            },
        },
        [],
    )


def _dedupe_inventory_identifiers(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for entry in sorted(
        entries,
        key=lambda item: (
            int(item["source_address"]),
            str(item["payload_label"]),
            str(item["text"]),
            float(item["timestamp"]),
        ),
    ):
        key = (int(entry["source_address"]), str(entry["payload_label"]), str(entry["text"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _j1939_inventory(
    frames: list[CanFrame], *, file: str, decoder: Any
) -> tuple[dict[str, Any], list[str]]:
    if not frames:
        return (
            {
                "mode": "passive",
                "file": file,
                "total_frames": 0,
                "interfaces": [],
                "unique_arbitration_ids": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "duration_seconds": 0.0,
                "j1939_frame_count": 0,
                "source_count": 0,
                "vehicle_identification_count": 0,
                "vehicle_identifications": [],
                "nodes": [],
            },
            ["No frames were found in the capture."],
        )

    interfaces = sorted({frame.interface or "unknown" for frame in frames})
    timestamps = [frame.timestamp for frame in frames]
    tp_sessions = [
        _enrich_tp_session(session) for session in decoder.transport_protocol_sessions(frames)
    ]
    dm1_messages = decoder.dm1_messages(frames)

    source_pgn_counts: defaultdict[int, Counter[int]] = defaultdict(Counter)
    source_frame_counts: Counter[int] = Counter()
    source_first_seen: dict[int, float] = {}
    source_last_seen: dict[int, float] = {}
    j1939_frame_count = 0

    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        j1939_frame_count += 1
        source_address = identifier.source_address
        source_frame_counts[source_address] += 1
        source_pgn_counts[source_address][identifier.pgn] += 1
        if source_address not in source_first_seen:
            source_first_seen[source_address] = frame.timestamp
        source_last_seen[source_address] = frame.timestamp

    raw_identifiers: list[dict[str, Any]] = []
    for session in tp_sessions:
        if not bool(session.get("complete", False)):
            continue
        label = session.get("payload_label")
        text = session.get("decoded_text")
        if label not in {"component_identification", "vehicle_identification"} or text is None:
            continue
        raw_identifiers.append(
            {
                "text": text,
                "transfer_pgn": int(session["transfer_pgn"]),
                "source_address": int(session["source_address"]),
                "destination_address": session["destination_address"],
                "session_type": str(session["session_type"]),
                "payload_label": str(label),
                "heuristic": bool(session.get("decoded_text_heuristic", False)),
                "timestamp": float(session["timestamp"]),
            }
        )
    identifiers = _dedupe_inventory_identifiers(raw_identifiers)

    component_ids_by_sa: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    vehicle_ids_by_sa: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in identifiers:
        if entry["payload_label"] == "component_identification":
            component_ids_by_sa[int(entry["source_address"])] += [entry]
        if entry["payload_label"] == "vehicle_identification":
            vehicle_ids_by_sa[int(entry["source_address"])] += [entry]

    dm1_by_sa: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for message in dm1_messages:
        dm1_by_sa[int(message["source_address"])] += [message]

    source_addresses = sorted(
        set(source_frame_counts)
        | set(component_ids_by_sa)
        | set(vehicle_ids_by_sa)
        | set(dm1_by_sa)
    )
    nodes: list[dict[str, Any]] = []
    for source_address in source_addresses:
        component_identifications = component_ids_by_sa[source_address]
        vehicle_identifications = vehicle_ids_by_sa[source_address]
        dm1_for_source = dm1_by_sa[source_address]
        display_pgn_counts = Counter(
            {
                pgn: count
                for pgn, count in source_pgn_counts[source_address].items()
                if pgn not in {TP_CM_PGN, TP_DT_PGN}
            }
        )
        if not display_pgn_counts:
            display_pgn_counts = source_pgn_counts[source_address]
        top_pgns = [
            {
                "pgn": pgn,
                "label": pgn_lookup(pgn)["label"] if pgn_lookup(pgn) else None,
                "frame_count": count,
            }
            for pgn, count in display_pgn_counts.most_common(5)
        ]
        nodes.append(
            {
                "source_address": source_address,
                "source_address_name": source_address_lookup(source_address),
                "frame_count": source_frame_counts[source_address],
                "first_timestamp": source_first_seen.get(source_address),
                "last_timestamp": source_last_seen.get(source_address),
                "unique_pgn_count": len(source_pgn_counts[source_address]),
                "top_pgns": top_pgns,
                "component_identifications": component_identifications,
                "vehicle_identifications": vehicle_identifications,
                "dm1": {
                    "present": bool(dm1_for_source),
                    "message_count": len(dm1_for_source),
                    "active_dtc_count": sum(
                        int(message["active_dtc_count"]) for message in dm1_for_source
                    ),
                },
            }
        )

    vehicle_identifications = [
        entry for entry in identifiers if entry["payload_label"] == "vehicle_identification"
    ]
    warnings: list[str] = []
    if not nodes:
        warnings.append("No J1939 source-address inventory could be built from the capture window.")
    return (
        {
            "mode": "passive",
            "file": file,
            "total_frames": len(frames),
            "interfaces": interfaces,
            "unique_arbitration_ids": len({frame.arbitration_id for frame in frames}),
            "first_timestamp": timestamps[0],
            "last_timestamp": timestamps[-1],
            "duration_seconds": timestamps[-1] - timestamps[0],
            "j1939_frame_count": j1939_frame_count,
            "source_count": len(nodes),
            "vehicle_identification_count": len(vehicle_identifications),
            "vehicle_identifications": vehicle_identifications,
            "nodes": nodes,
        },
        warnings,
    )


ADDRESS_CLAIMED_PGN = 0x00EE00


def _decode_j1939_name(data: bytes) -> dict[str, Any]:
    """Decode the 64-bit J1939 NAME carried by an Address Claimed (PGN 60928).

    The eight data bytes are a little-endian bit field (SAE J1939-81 §4.2).
    """
    value = int.from_bytes(data[:8], "little")
    return {
        "identity_number": value & 0x1FFFFF,
        "manufacturer_code": (value >> 21) & 0x7FF,
        "ecu_instance": (value >> 32) & 0x7,
        "function_instance": (value >> 35) & 0x1F,
        "function": (value >> 40) & 0xFF,
        "vehicle_system": (value >> 49) & 0x7F,
        "vehicle_system_instance": (value >> 56) & 0xF,
        "industry_group": (value >> 60) & 0x7,
        "arbitrary_address_capable": bool((value >> 63) & 0x1),
    }


def _j1939_map(
    frames: list[CanFrame], *, file: str, decoder: Any
) -> tuple[dict[str, Any], list[str]]:
    """Build a passive J1939 network map (nodes/edges) from a capture.

    Reuses the inventory machinery for per-source identification strings and
    layers in Address Claimed NAME fields plus observed PGN flows. No active
    probing: every value is derived purely from the captured frames.
    """
    inventory_data, warnings = _j1939_inventory(frames, file=file, decoder=decoder)

    # Address Claimed NAME fields, keyed by the claiming source address.
    name_by_sa: dict[int, dict[str, Any]] = {}
    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        if identifier.pgn != ADDRESS_CLAIMED_PGN or len(frame.data) < 8:
            continue
        # The latest claim wins; a node re-announces with the same NAME.
        name_by_sa[identifier.source_address] = _decode_j1939_name(bytes(frame.data[:8]))

    nodes: list[dict[str, Any]] = []
    for inv_node in inventory_data["nodes"]:
        source_address = int(inv_node["source_address"])
        nodes.append(
            {
                "source_address": source_address,
                "source_address_name": inv_node.get("source_address_name"),
                "frame_count": inv_node["frame_count"],
                "name": name_by_sa.get(source_address),
                "component_identifications": [
                    entry["text"] for entry in inv_node.get("component_identifications", [])
                ],
                "vehicle_identifications": [
                    entry["text"] for entry in inv_node.get("vehicle_identifications", [])
                ],
                "dm1_present": bool(inv_node["dm1"]["present"]),
            }
        )

    # Edges: observed PGN flows from a source address to a destination. PDU1
    # traffic addressed to the global address (0xFF) is a broadcast, the same
    # as every PDU2 message, so both collapse to destination=None.
    edge_counts: defaultdict[tuple[int, int | None, int], int] = defaultdict(int)
    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        destination = identifier.destination_address
        if destination == 0xFF:
            destination = None
        edge_counts[(identifier.source_address, destination, identifier.pgn)] += 1

    edges: list[dict[str, Any]] = []
    for (source_address, destination, pgn), count in sorted(
        edge_counts.items(),
        key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1], item[0][2]),
    ):
        meta = pgn_lookup(pgn)
        edges.append(
            {
                "source_address": source_address,
                "source_address_name": source_address_lookup(source_address),
                "destination_address": destination,
                "destination_address_name": (
                    source_address_lookup(destination) if destination is not None else None
                ),
                "broadcast": destination is None,
                "pgn": pgn,
                "pgn_label": meta["label"] if meta else None,
                "frame_count": count,
            }
        )

    data = {
        "mode": "passive",
        "file": file,
        "total_frames": inventory_data["total_frames"],
        "interfaces": inventory_data["interfaces"],
        "first_timestamp": inventory_data["first_timestamp"],
        "last_timestamp": inventory_data["last_timestamp"],
        "duration_seconds": inventory_data["duration_seconds"],
        "j1939_frame_count": inventory_data["j1939_frame_count"],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "address_claim_count": len(name_by_sa),
        "nodes": nodes,
        "edges": edges,
    }
    if not nodes and not edges:
        message = "No J1939 network map could be built from the capture window."
        if message not in warnings:
            warnings = [*warnings, message]
    return data, warnings


def _format_pgn_entry(pgn: int) -> dict[str, Any]:
    meta = pgn_lookup(pgn)
    return {
        "pgn": pgn,
        "label": meta["label"] if meta else None,
    }


def _format_source_address_entry(source_address: int) -> dict[str, Any]:
    return {
        "source_address": source_address,
        "source_address_name": source_address_lookup(source_address),
    }


def _j1939_compare_capture(
    frames: list[CanFrame], *, file: str, decoder: Any
) -> tuple[dict[str, Any], list[str]]:
    summary_data, summary_warnings = _j1939_summary(frames, file=file, decoder=decoder)
    inventory_data, inventory_warnings = _j1939_inventory(frames, file=file, decoder=decoder)
    dm1_messages = decoder.dm1_messages(frames)
    faults_data = _j1939_faults(dm1_messages, file=file)

    pgns = {entry["pgn"] for entry in summary_data.get("top_pgns", [])}
    source_addresses = {
        entry["source_address"] for entry in summary_data.get("top_source_addresses", [])
    }
    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        pgns.add(identifier.pgn)
        source_addresses.add(identifier.source_address)

    dm1_by_source: dict[int, dict[str, Any]] = {}
    for ecu in faults_data["ecus"]:
        faults = [
            {
                "spn": int(fault["spn"]),
                "fmi": int(fault["fmi"]),
                "name": fault.get("name"),
            }
            for fault in ecu.get("faults", [])
        ]
        dm1_by_source[int(ecu["source_address"])] = {
            "present": True,
            "message_count": int(ecu["message_count"]),
            "active_fault_count": int(ecu["fault_count"]),
            "lamp_summary": dict(ecu["lamp_summary"]),
            "faults": sorted(
                faults, key=lambda item: (item["spn"], item["fmi"], item.get("name") or "")
            ),
        }

    identifier_map: dict[tuple[int, str], list[str]] = {}
    for node in inventory_data.get("nodes", []):
        source_address = int(node["source_address"])
        for key in ("component_identifications", "vehicle_identifications"):
            texts = sorted({str(entry["text"]) for entry in node.get(key, [])})
            if texts:
                identifier_map[(source_address, key.removesuffix("s"))] = texts

    return (
        {
            "file": file,
            "file_name": Path(file).name,
            "total_frames": int(summary_data["total_frames"]),
            "j1939_frame_count": int(summary_data["j1939_frame_count"]),
            "unique_pgn_count": len(pgns),
            "unique_source_count": len(source_addresses),
            "pgns": [_format_pgn_entry(pgn) for pgn in sorted(pgns)],
            "source_addresses": [
                _format_source_address_entry(sa) for sa in sorted(source_addresses)
            ],
            "dm1_by_source": dm1_by_source,
            "identifiers": [
                {
                    "source_address": source_address,
                    "source_address_name": source_address_lookup(source_address),
                    "payload_label": payload_label,
                    "values": values,
                }
                for (source_address, payload_label), values in sorted(identifier_map.items())
            ],
            "printable_identifiers": summary_data.get("tp", {}).get("printable_identifiers", []),
            "vehicle_identifications": inventory_data.get("vehicle_identifications", []),
            "tp_session_count": int(summary_data.get("tp", {}).get("session_count", 0)),
        },
        summary_warnings + inventory_warnings,
    )


def _dm1_compare_signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    lamp = entry.get("lamp_summary", {})
    faults = tuple(
        (int(fault["spn"]), int(fault["fmi"]), fault.get("name"))
        for fault in entry.get("faults", [])
    )
    return (
        bool(entry.get("present", False)),
        int(entry.get("active_fault_count", 0)),
        lamp.get("mil"),
        lamp.get("red_stop"),
        lamp.get("amber_warning"),
        lamp.get("protect"),
        faults,
    )


def _j1939_compare(captures: list[dict[str, Any]]) -> dict[str, Any]:
    pgn_sets = [{int(entry["pgn"]) for entry in capture.get("pgns", [])} for capture in captures]
    source_sets = [
        {int(entry["source_address"]) for entry in capture.get("source_addresses", [])}
        for capture in captures
    ]

    common_pgns = set.intersection(*pgn_sets) if pgn_sets else set()
    common_sources = set.intersection(*source_sets) if source_sets else set()

    dm1_differences: list[dict[str, Any]] = []
    all_dm1_sources = sorted(
        {
            source_address
            for capture in captures
            for source_address in capture.get("dm1_by_source", {})
        }
    )
    for source_address in all_dm1_sources:
        capture_entries = []
        signatures = []
        for capture in captures:
            entry = capture.get("dm1_by_source", {}).get(
                source_address,
                {
                    "present": False,
                    "message_count": 0,
                    "active_fault_count": 0,
                    "lamp_summary": {
                        "mil": "off",
                        "red_stop": "off",
                        "amber_warning": "off",
                        "protect": "off",
                    },
                    "faults": [],
                },
            )
            signatures.append(_dm1_compare_signature(entry))
            capture_entries.append({"file": capture["file"], **entry})
        if len(set(signatures)) > 1:
            dm1_differences.append(
                {
                    "source_address": source_address,
                    "source_address_name": source_address_lookup(source_address),
                    "captures": capture_entries,
                }
            )

    identifier_differences: list[dict[str, Any]] = []
    identifier_keys = sorted(
        {
            (int(entry["source_address"]), str(entry["payload_label"]))
            for capture in captures
            for entry in capture.get("identifiers", [])
        }
    )
    for source_address, payload_label in identifier_keys:
        capture_entries = []
        signatures = []
        for capture in captures:
            values: list[str] = []
            for entry in capture.get("identifiers", []):
                if (
                    int(entry["source_address"]) == source_address
                    and str(entry["payload_label"]) == payload_label
                ):
                    values = list(entry.get("values", []))
                    break
            normalized = tuple(values)
            signatures.append(normalized)
            capture_entries.append({"file": capture["file"], "values": values})
        if len(set(signatures)) > 1:
            identifier_differences.append(
                {
                    "source_address": source_address,
                    "source_address_name": source_address_lookup(source_address),
                    "payload_label": payload_label,
                    "captures": capture_entries,
                }
            )

    return {
        "mode": "passive",
        "files": [capture["file"] for capture in captures],
        "capture_count": len(captures),
        "captures": captures,
        "common_pgns": [_format_pgn_entry(pgn) for pgn in sorted(common_pgns)],
        "unique_pgns": [
            {
                "file": capture["file"],
                "pgns": [
                    _format_pgn_entry(pgn)
                    for pgn in sorted(
                        {int(entry["pgn"]) for entry in capture.get("pgns", [])} - common_pgns
                    )
                ],
            }
            for capture in captures
        ],
        "common_source_addresses": [
            _format_source_address_entry(sa) for sa in sorted(common_sources)
        ],
        "unique_source_addresses": [
            {
                "file": capture["file"],
                "source_addresses": [
                    _format_source_address_entry(sa)
                    for sa in sorted(
                        {
                            int(entry["source_address"])
                            for entry in capture.get("source_addresses", [])
                        }
                        - common_sources
                    )
                ],
            }
            for capture in captures
        ],
        "dm1_differences": dm1_differences,
        "identifier_differences": identifier_differences,
    }


_LAMP_PRIORITY: dict[str, int] = {"on": 3, "error": 2, "not_available": 1, "off": 0}


def _j1939_faults(messages: list[dict[str, Any]], *, file: str) -> dict[str, Any]:
    by_sa: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for message in messages:
        by_sa[int(message["source_address"])].append(message)

    ecus: list[dict[str, Any]] = []
    total_fault_count = 0

    for sa in sorted(by_sa):
        sa_messages = by_sa[sa]

        fault_map: dict[tuple[int, int], dict[str, Any]] = {}
        for message in sa_messages:
            ts = message.get("timestamp")
            for dtc in message.get("dtcs", []):
                if int(dtc["spn"]) == 0 or int(dtc["fmi"]) in {0, 31}:
                    continue
                spn = int(dtc["spn"])
                fmi = int(dtc["fmi"])
                key = (spn, fmi)
                if key not in fault_map:
                    entry: dict[str, Any] = {
                        "spn": spn,
                        "name": dtc.get("name"),
                        "fmi": fmi,
                        "fmi_description": dtc.get("fmi_description"),
                        "occurrences": 0,
                        "first_seen": ts,
                        "last_seen": ts,
                        "suspicious": False,
                    }
                    for field in ("dbc_signal_name", "dbc_message_name", "units"):
                        if field in dtc:
                            entry[field] = dtc[field]
                    fault_map[key] = entry
                e = fault_map[key]
                e["occurrences"] += 1
                if ts is not None:
                    if e["first_seen"] is None or ts < e["first_seen"]:
                        e["first_seen"] = ts
                    if e["last_seen"] is None or ts > e["last_seen"]:
                        e["last_seen"] = ts
                if int(dtc.get("conversion_method", 0)) != 0:
                    e["suspicious"] = True

        def _worst_lamp(key: str) -> str:
            states = [m["lamp_status"][key] for m in sa_messages if "lamp_status" in m]
            return max(states, key=lambda s: _LAMP_PRIORITY.get(s, 0)) if states else "off"

        lamp_summary = {
            "mil": _worst_lamp("mil"),
            "red_stop": _worst_lamp("red_stop"),
            "amber_warning": _worst_lamp("amber_warning"),
            "protect": _worst_lamp("protect"),
        }

        timestamps = [m["timestamp"] for m in sa_messages if m.get("timestamp") is not None]
        faults = list(fault_map.values())
        total_fault_count += len(faults)

        ecus.append(
            {
                "source_address": sa,
                "source_address_name": source_address_lookup(sa),
                "message_count": len(sa_messages),
                "first_seen": min(timestamps) if timestamps else None,
                "last_seen": max(timestamps) if timestamps else None,
                "lamp_summary": lamp_summary,
                "fault_count": len(faults),
                "faults": faults,
            }
        )

    return {
        "mode": "passive",
        "file": file,
        "source_count": len(ecus),
        "total_fault_count": total_fault_count,
        "ecus": ecus,
    }


def _parse_sa_list(sa_arg: str | None) -> frozenset[int] | None:
    """Parse a comma-separated list of source addresses (hex or decimal) into a frozenset."""
    if not sa_arg:
        return None
    result: set[int] = set()
    for part in sa_arg.split(","):
        part = part.strip()
        if part:
            result.add(int(part, 0))
    return frozenset(result) if result else None


def _j1939_filter_payload(pgn: int | None, sa_filter: frozenset[int] | None) -> dict[str, Any]:
    """Echo applied J1939 filters into the payload for transparency."""
    payload: dict[str, Any] = {}
    if pgn is not None:
        payload["pgn_filter"] = pgn
    if sa_filter is not None:
        payload["sa_filter"] = sorted(sa_filter)
    return payload


def _filter_frames_by_j1939(
    frames: list[CanFrame],
    *,
    pgn: int | None,
    sa_filter: frozenset[int] | None,
) -> list[CanFrame]:
    """Filter frames by J1939 PGN and/or source address.

    Only extended-ID frames carry a J1939 identifier; standard frames are
    dropped whenever a J1939 filter is requested.
    """
    if pgn is None and sa_filter is None:
        return frames
    matched: list[CanFrame] = []
    for frame in frames:
        if not frame.is_extended_id:
            continue
        identifier = decompose_arbitration_id(frame.arbitration_id)
        if pgn is not None and identifier.pgn != pgn:
            continue
        if sa_filter is not None and identifier.source_address not in sa_filter:
            continue
        matched.append(frame)
    return matched


def _j1939_tp_compare(
    sessions: list[dict[str, Any]],
    *,
    source_addresses: list[int],
    pgn_filter: int | None,
    file: str,
) -> dict[str, Any]:
    by_pgn: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        by_pgn[int(session["transfer_pgn"])].append(session)

    groups: list[dict[str, Any]] = []
    for pgn in sorted(by_pgn):
        pgn_sessions = by_pgn[pgn]
        hashes = [s.get("payload_hash") for s in pgn_sessions]
        unique_hashes = {h for h in hashes if h is not None}
        timestamps = [s["timestamp"] for s in pgn_sessions if s.get("timestamp") is not None]
        sa_counts: Counter[int] = Counter(int(s["source_address"]) for s in pgn_sessions)
        repeated_sources = sorted(sa for sa, count in sa_counts.items() if count > 1)
        session_summaries = [
            {
                "source_address": int(s["source_address"]),
                "timestamp": s.get("timestamp"),
                "total_bytes": int(s["total_bytes"]),
                "complete": bool(s.get("complete", False)),
                "payload_hash": s.get("payload_hash"),
                "reassembled_data": s.get("reassembled_data"),
            }
            for s in sorted(pgn_sessions, key=lambda s: s.get("timestamp") or 0.0)
        ]
        groups.append(
            {
                "transfer_pgn": pgn,
                "session_count": len(pgn_sessions),
                "payloads_identical": len(unique_hashes) == 1 and None not in hashes,
                "unique_payload_count": len(unique_hashes),
                "timing_spread_seconds": round(max(timestamps) - min(timestamps), 6)
                if len(timestamps) >= 2
                else 0.0,
                "repeated_sources": repeated_sources,
                "sessions": session_summaries,
            }
        )

    return {
        "mode": "passive",
        "file": file,
        "source_addresses": source_addresses,
        "pgn_filter": pgn_filter,
        "group_count": len(groups),
        "groups": groups,
    }


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
        if getattr(args, "dbc", None):
            import time as _time
            from canarchy.dbc_provider import get_registry

            resolution = get_registry().resolve(args.dbc)
            dbc_path = str(resolution.local_path)
            dbc_source = _build_dbc_source(resolution)
            signals = parse_signal_assignments(args.signals or [])
            frame, _, encode_resolution = encode_message(
                dbc_path,
                args.message,
                signals,
                interface=args.interface,
                crc_algorithm=args.crc_algorithm,
            )
            send_warnings: list[str] = []
            if encode_resolution.get("filled_signals"):
                filled_values = ", ".join(
                    f"{entry['signal']}={entry['value']}"
                    for entry in encode_resolution["filled_signals"]
                )
                send_warnings.append(
                    f"Unsupplied signal(s) defaulted for transmission: {filled_values}. "
                    "Supply explicit values via --signals if these are not intended."
                )
            dry_run = getattr(args, "dry_run", False)
            count = args.count
            rate = args.rate
            base_data: dict[str, Any] = {
                "dbc": args.dbc,
                "dbc_source": dbc_source,
                "message": args.message,
                "signals": signals,
                "resolution": encode_resolution,
                "frame": frame.to_payload(),
                "count": count,
                "rate": rate,
                "interface": args.interface,
                **backend_metadata,
                "status": "implemented",
                "implementation": implementation,
            }
            if dry_run:
                base_data["mode"] = "dry_run"
                return (base_data, [], send_warnings)
            # The operator must see synthesized defaults BEFORE the
            # confirmation prompt / bus write, not just in the result
            # envelope after transmission.
            for warning in send_warnings:
                print(f"warning: {warning}", file=sys.stderr)
            enforce_active_transmit_safety(args)
            base_data["mode"] = "active"
            all_events: list[dict[str, Any]] = []
            for i in range(count):
                all_events.extend(transport.send_events(args.interface, frame))
                if rate and i < count - 1:
                    _time.sleep(1.0 / rate)
            return (base_data, all_events, send_warnings)
        frame = parse_send_frame(args)
        if getattr(args, "dry_run", False):
            return (
                {
                    "mode": "dry_run",
                    "interface": args.interface,
                    "frame": frame.to_payload(),
                    **backend_metadata,
                    "status": "implemented",
                    "implementation": implementation,
                },
                [],
                [],
            )
        enforce_active_transmit_safety(args)
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
            [],
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
        if getattr(args, "dry_run", False):
            frame_events = serialize_events(
                [
                    FrameEvent(
                        frame=frame,
                        source="generate",
                        timestamp=index * (args.gap / 1000.0),
                    ).to_event()
                    for index, frame in enumerate(frames)
                ]
            )
            return (
                {
                    "interface": args.interface,
                    "mode": "dry_run",
                    "dry_run": True,
                    "frame_count": len(frames),
                    "gap_ms": args.gap,
                    **backend_metadata,
                    "status": "implemented",
                    "implementation": implementation,
                },
                frame_events,
                [f"ACTIVE_TRANSMIT_DRY_RUN: {len(frames)} frames planned; no transport opened."],
            )
        enforce_active_transmit_safety(args)
        return (
            {
                "interface": args.interface,
                "mode": "active",
                "dry_run": False,
                "frame_count": len(frames),
                "gap_ms": args.gap,
                **backend_metadata,
                "status": "implemented",
                "implementation": implementation,
            },
            transport.generate_events(args.interface, frames, gap_ms=args.gap),
            [],
        )
    if args.command == "simulate":
        frames = simulate_frames(
            args.profile,
            interface=args.interface,
            rate=args.rate,
            duration=args.duration,
            seed=args.seed,
        )
        gap_ms = (1.0 / args.rate) * 1000.0
        if getattr(args, "dry_run", False):
            frame_events = serialize_events(
                [
                    FrameEvent(
                        frame=frame,
                        source="simulate",
                        timestamp=frame.timestamp,
                    ).to_event()
                    for frame in frames
                ]
            )
            return (
                {
                    "interface": args.interface,
                    "profile": args.profile,
                    "mode": "dry_run",
                    "dry_run": True,
                    "frame_count": len(frames),
                    "rate": args.rate,
                    "duration": args.duration,
                    "seed": args.seed,
                    **backend_metadata,
                    "status": "implemented",
                    "implementation": implementation,
                },
                frame_events,
                [f"ACTIVE_TRANSMIT_DRY_RUN: {len(frames)} frames planned; no transport opened."],
            )
        enforce_active_transmit_safety(args)
        return (
            {
                "interface": args.interface,
                "profile": args.profile,
                "mode": "active",
                "dry_run": False,
                "frame_count": len(frames),
                "rate": args.rate,
                "duration": args.duration,
                "seed": args.seed,
                **backend_metadata,
                "status": "implemented",
                "implementation": implementation,
            },
            transport.generate_events(args.interface, frames, gap_ms=gap_ms),
            [],
        )
    if args.command == "filter":
        if args.stdin:
            frames = frames_from_stdin(command=args.command)
            return (
                {
                    "mode": "passive",
                    "file": "-",
                    "expression": args.expression,
                    "status": "implemented",
                    "implementation": "stdin-analysis",
                    "input": "stdin-jsonl",
                },
                transport.filter_events("<stdin>", args.expression, frames=frames),
                [],
            )
        if args.file == "-":
            from canarchy.transport import iter_candump_file

            frames = list(
                iter_candump_file(
                    None, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
                )
            )
            return (
                {
                    "mode": "passive",
                    "file": "-",
                    "expression": args.expression,
                    "status": "implemented",
                    "implementation": "stdin-analysis",
                    "input": "stdin-candump",
                },
                transport.filter_events("<stdin>", args.expression, frames=frames),
                [],
            )
        frames = transport.frames_from_file(
            args.file, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
        )
        return (
            {
                "mode": "passive",
                "file": args.file,
                "expression": args.expression,
                "status": "implemented",
                "implementation": "file-backed analysis",
                "input": "file",
            },
            transport.filter_events(args.file, args.expression, frames=frames),
            [],
        )
    if args.command == "stats":
        if args.file == "-":
            from canarchy.transport import TransportStats, iter_candump_file

            frames = list(
                iter_candump_file(
                    None, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
                )
            )
            if not frames:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="CAPTURE_EMPTY",
                            message="No valid frames read from stdin.",
                            hint=(
                                "Confirm the upstream command emitted candump text "
                                "(for example `canarchy datasets replay <ref> | canarchy stats --file -`). "
                                "An empty stdin or zero-frame capture is the most common cause."
                            ),
                        )
                    ],
                )
            # Calculate stats
            from canarchy.transport import detailed_frame_stats

            sa_filter = _parse_sa_list(getattr(args, "sa", None))
            pgn_filter = getattr(args, "pgn", None)
            frames = _filter_frames_by_j1939(frames, pgn=pgn_filter, sa_filter=sa_filter)
            unique_ids = len(set(f.arbitration_id for f in frames))
            interfaces = list(set(f.interface for f in frames))
            stats = TransportStats(
                total_frames=len(frames), unique_arbitration_ids=unique_ids, interfaces=interfaces
            )
            return (
                {
                    "mode": "passive",
                    "file": "-",
                    "status": "implemented",
                    "implementation": "stdin-analysis",
                    **_j1939_filter_payload(pgn_filter, sa_filter),
                    **stats.to_payload(),
                    **detailed_frame_stats(frames, top=getattr(args, "top", 20)),
                },
                [],
                [],
            )
        from canarchy.transport import TransportStats as _TransportStats, detailed_frame_stats

        frames = transport.frames_from_file(
            args.file, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
        )
        sa_filter = _parse_sa_list(getattr(args, "sa", None))
        pgn_filter = getattr(args, "pgn", None)
        frames = _filter_frames_by_j1939(frames, pgn=pgn_filter, sa_filter=sa_filter)
        stats = _TransportStats(
            total_frames=len(frames),
            unique_arbitration_ids=len({frame.arbitration_id for frame in frames}),
            interfaces=sorted({frame.interface or "unknown" for frame in frames}),
        )
        return (
            {
                "mode": "passive",
                "file": args.file,
                **_j1939_filter_payload(pgn_filter, sa_filter),
                **stats.to_payload(),
                **detailed_frame_stats(frames, top=getattr(args, "top", 20)),
                "status": "implemented",
                "implementation": "file-backed analysis",
            },
            [],
            [],
        )
    if args.command == "capture-info":
        if args.file == "-":
            # Handle stdin
            from canarchy.transport import parse_candump_line

            frames = []
            for line_number, raw_line in enumerate(sys.stdin, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    frame = parse_candump_line(stripped, path=Path("-"), line_number=line_number)
                    frames.append(frame)
                except TransportError:
                    continue
            # Calculate simple metadata
            if not frames:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_USER_ERROR,
                    errors=[
                        ErrorDetail(
                            code="CAPTURE_EMPTY",
                            message="No valid frames read from stdin.",
                            hint=(
                                "Confirm the upstream command emitted candump text "
                                "(for example `canarchy datasets replay <ref> | canarchy capture-info --file -`). "
                                "An empty stdin or zero-frame capture is the most common cause."
                            ),
                        )
                    ],
                )
            timestamps = [f.timestamp for f in frames]
            unique_ids = len(set(f.arbitration_id for f in frames))
            interfaces = list(set(f.interface for f in frames))
            metadata_payload = {
                "frame_count": len(frames),
                "unique_ids": unique_ids,
                "interfaces": interfaces,
                "duration_seconds": max(timestamps) - min(timestamps)
                if len(timestamps) > 1
                else 0.0,
                "start_time": min(timestamps),
                "end_time": max(timestamps),
                "scan_mode": "stdin",
            }
            return (
                {
                    "mode": "passive",
                    "file": "-",
                    "status": "implemented",
                    "implementation": "stdin-metadata",
                    **metadata_payload,
                },
                [],
                [],
            )
        metadata = transport.capture_info(args.file)
        return (
            {
                "mode": "passive",
                "file": args.file,
                "status": "implemented",
                "implementation": "fast-metadata-scan",
                **metadata.to_payload(),
            },
            [],
            [],
        )
    raise AssertionError(f"unsupported transport command: {args.command}")


def j1939_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()

    def enrich_with_dbc(
        data: dict[str, Any], frames: list[CanFrame]
    ) -> tuple[dict[str, Any], list[str]]:
        dbc_ref = getattr(args, "dbc", None) or default_j1939_dbc()
        if not dbc_ref:
            return data, []

        from canarchy.dbc_provider import get_registry

        resolution = get_registry().resolve(dbc_ref)
        dbc_events = decode_frames(frames, str(resolution.local_path))
        warnings: list[str] = []
        if not dbc_events:
            warnings.append(
                "No frames in the J1939 selection matched messages from the selected DBC."
            )
        return (
            {
                **data,
                "dbc": dbc_ref,
                "dbc_source": _build_dbc_source(resolution),
                "dbc_events": dbc_events,
                "dbc_matched_messages": len(
                    [event for event in dbc_events if event["event_type"] == "decoded_message"]
                ),
            },
            warnings,
        )

    def enrich_dm1_with_dbc(
        data: dict[str, Any], messages: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[str]]:
        dbc_ref = getattr(args, "dbc", None) or default_j1939_dbc()
        if not dbc_ref:
            return data, []

        from canarchy.dbc_provider import get_registry

        resolution = get_registry().resolve(dbc_ref)
        enriched_messages: list[dict[str, Any]] = []
        matched_dtcs = 0
        for message in messages:
            dtcs = []
            for dtc in message["dtcs"]:
                enriched_dtc = dict(dtc)
                metadata = lookup_j1939_spn_metadata(str(resolution.local_path), int(dtc["spn"]))
                if metadata is not None:
                    matched_dtcs += 1
                    enriched_dtc["name"] = metadata["signal_name"]
                    enriched_dtc["dbc_signal_name"] = metadata["signal_name"]
                    enriched_dtc["dbc_message_name"] = metadata["message_name"]
                    enriched_dtc["units"] = metadata["units"]
                dtcs.append(enriched_dtc)
            enriched_messages.append({**message, "dtcs": dtcs})

        return (
            {
                **data,
                "dbc": dbc_ref,
                "dbc_source": _build_dbc_source(resolution),
                "dbc_spn_matches": matched_dtcs,
                "messages": enriched_messages,
            },
            [] if matched_dtcs else ["No DM1 DTCs matched SPNs from the selected DBC."],
        )

    def dm1_warnings(messages: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        if not messages:
            warnings.append("No J1939 DM1 messages were found in the capture.")
        if any(
            int(dtc.get("conversion_method", 0)) != 0
            for message in messages
            for dtc in message.get("dtcs", [])
        ):
            warnings.append(
                "One or more DM1 DTCs use deprecated SPN conversion modes; conversion details are reported in structured output."
            )
        return warnings

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
        decoder = get_j1939_decoder()
        dbc_ref = getattr(args, "dbc", None) or default_j1939_dbc()
        analysis_kwargs = j1939_file_analysis_kwargs(args)
        if args.stdin:
            frames = frames_from_stdin(command=args.command)
            events = decoder.decode_events(frames)
        elif dbc_ref:
            frames = transport.frames_from_file(args.file, **analysis_kwargs)
            events = decoder.decode_events(frames)
        else:
            events = decoder.decode_events(
                transport.iter_frames_from_file(args.file, **analysis_kwargs)
            )
            frames = []
        warnings = []
        if not events:
            warnings.append("No J1939 extended ID frames were found in the input.")
        data, dbc_warnings = enrich_with_dbc(
            {
                "mode": "passive",
                "file": args.file,
                "input": "stdin" if args.stdin else "file",
            },
            frames,
        )
        warnings.extend(dbc_warnings)
        return (
            data,
            serialize_events(events),
            warnings,
        )
    if args.command == "j1939 pgn":
        decoder = get_j1939_decoder()
        event_objects = decoder.decode_pgn_events(
            transport.iter_frames_from_file(args.file, **j1939_file_analysis_kwargs(args)),
            args.pgn,
        )
        matched_frames = [
            frame
            for frame in (getattr(event, "frame", None) for event in event_objects)
            if frame is not None
        ]
        data, dbc_warnings = enrich_with_dbc(
            {"mode": "passive", "pgn": args.pgn, "file": args.file},
            matched_frames,
        )
        describer = pretty_j1939_support.get_describer()
        serialized: list[dict[str, Any]] = []
        for event in event_objects:
            event_dict = event.to_payload()
            frame_payload = event_dict.get("payload", {}).get("frame")
            if frame_payload:
                decoded = pretty_j1939_support.describe_frame(
                    describer, frame_payload["arbitration_id"], frame_payload["data"]
                )
                if decoded:
                    event_dict["payload"]["decoded_signals"] = decoded
            serialized.append(event_dict)
        return (
            data,
            serialized,
            dbc_warnings,
        )
    if args.command == "j1939 spn":
        decoder = get_j1939_decoder()
        dbc_ref = getattr(args, "dbc", None) or default_j1939_dbc()
        analysis_kwargs = j1939_file_analysis_kwargs(args)
        if args.spn in decoder.supported_spns() and not dbc_ref:
            observations = decoder.spn_observations(
                transport.iter_frames_from_file(args.file, **analysis_kwargs), args.spn
            )
            decoder_name = "curated_spn_map"
            matching_frames: list[Any] = []
        else:
            frames = transport.frames_from_file(args.file, **analysis_kwargs)
            if args.spn in decoder.supported_spns():
                observations = decoder.spn_observations(frames, args.spn)
                decoder_name = "curated_spn_map"
            elif dbc_ref:
                observations = decode_j1939_spn(frames, dbc_ref, args.spn)
                decoder_name = "dbc_spn_map"
            else:
                observations = []
                decoder_name = "curated_spn_map"
            matched_pgns = {int(observation["pgn"]) for observation in observations}
            matching_frames = [
                frame
                for frame in frames
                if frame.is_extended_id
                and decompose_arbitration_id(frame.arbitration_id).pgn in matched_pgns
            ]
        warnings = []
        if not observations:
            warnings.append("No observations for the selected SPN were found in the capture.")
        data, dbc_warnings = enrich_with_dbc(
            {
                "mode": "passive",
                "spn": args.spn,
                "file": args.file,
                "decoder": decoder_name,
                "observation_count": len(observations),
                "observations": observations,
            },
            matching_frames,
        )
        warnings.extend(dbc_warnings)
        return (
            data,
            [],
            warnings,
        )
    if args.command == "j1939 tp sessions":
        decoder = get_j1939_decoder()
        pgn_filter = getattr(args, "pgn", None)
        sa_filter = _parse_sa_list(getattr(args, "sa", None))
        sessions = [
            _enrich_tp_session(session)
            for session in decoder.transport_protocol_sessions(
                transport.iter_frames_from_file(args.file, **j1939_file_analysis_kwargs(args))
            )
            if (pgn_filter is None or int(session["transfer_pgn"]) == pgn_filter)
            and (sa_filter is None or int(session["source_address"]) in sa_filter)
        ]
        warnings = []
        if not sessions:
            warnings.append("No J1939 transport protocol sessions were found in the capture.")
        data: dict[str, Any] = {
            "mode": "passive",
            "file": args.file,
            "session_count": len(sessions),
            "sessions": sessions,
        }
        if pgn_filter is not None:
            data["pgn_filter"] = pgn_filter
        if sa_filter is not None:
            data["sa_filter"] = sorted(sa_filter)
        return (data, [], warnings)
    if args.command == "j1939 tp compare":
        decoder = get_j1939_decoder()
        sa_filter = _parse_sa_list(args.sa)
        pgn_filter = getattr(args, "pgn", None)
        all_sessions = [
            _enrich_tp_session(session)
            for session in decoder.transport_protocol_sessions(
                transport.iter_frames_from_file(args.file, **j1939_file_analysis_kwargs(args))
            )
            if int(session["source_address"]) in sa_filter
            and (pgn_filter is None or int(session["transfer_pgn"]) == pgn_filter)
        ]
        return (
            _j1939_tp_compare(
                all_sessions,
                source_addresses=sorted(sa_filter),
                pgn_filter=pgn_filter,
                file=args.file,
            ),
            [],
            [],
        )
    if args.command == "j1939 dm1":
        auto_warnings: list[str] = []
        decoder = get_j1939_decoder()
        messages = decoder.dm1_messages(
            transport.iter_frames_from_file(
                args.file, **_large_file_kwargs(args, args.file, auto_warnings)
            )
        )
        warnings = auto_warnings + dm1_warnings(messages)
        data, dbc_warnings = enrich_dm1_with_dbc(
            {
                "mode": "passive",
                "file": args.file,
                "message_count": len(messages),
                "messages": messages,
                "source_count": len({message["source_address"] for message in messages}),
            },
            messages,
        )
        warnings.extend(dbc_warnings)
        return (
            data,
            [],
            warnings,
        )
    if args.command == "j1939 faults":
        auto_warnings = []
        decoder = get_j1939_decoder()
        messages = decoder.dm1_messages(
            transport.iter_frames_from_file(
                args.file, **_large_file_kwargs(args, args.file, auto_warnings)
            )
        )
        warnings = auto_warnings + dm1_warnings(messages)
        enriched_data, dbc_warnings = enrich_dm1_with_dbc(
            {
                "mode": "passive",
                "file": args.file,
                "message_count": len(messages),
                "messages": messages,
                "source_count": len({m["source_address"] for m in messages}),
            },
            messages,
        )
        warnings.extend(dbc_warnings)
        faults_data = _j1939_faults(enriched_data["messages"], file=args.file)
        for key in ("dbc", "dbc_source", "dbc_spn_matches"):
            if key in enriched_data:
                faults_data[key] = enriched_data[key]
        return (
            faults_data,
            [],
            warnings,
        )
    if args.command == "j1939 summary":
        auto_warnings = []
        decoder = get_j1939_decoder()
        data, warnings = _j1939_summary(
            transport.frames_from_file(
                args.file, **_large_file_kwargs(args, args.file, auto_warnings)
            ),
            file=args.file,
            decoder=decoder,
        )
        return (data, [], auto_warnings + warnings)
    if args.command == "j1939 inventory":
        auto_warnings = []
        decoder = get_j1939_decoder()
        data, warnings = _j1939_inventory(
            transport.frames_from_file(
                args.file, **_large_file_kwargs(args, args.file, auto_warnings)
            ),
            file=args.file,
            decoder=decoder,
        )
        return (data, [], auto_warnings + warnings)
    if args.command == "j1939 compare":
        decoder = get_j1939_decoder()
        captures: list[dict[str, Any]] = []
        warnings: list[str] = []
        for file in args.files:
            file_kwargs = _large_file_kwargs(args, file, warnings)
            capture_data, capture_warnings = _j1939_compare_capture(
                transport.frames_from_file(file, **file_kwargs),
                file=file,
                decoder=decoder,
            )
            captures.append(capture_data)
            warnings.extend(f"{Path(file).name}: {warning}" for warning in capture_warnings)
        return (_j1939_compare(captures), [], warnings)
    if args.command == "j1939 map":
        auto_warnings = []
        decoder = get_j1939_decoder()
        data, warnings = _j1939_map(
            transport.frames_from_file(
                args.file, **_large_file_kwargs(args, args.file, auto_warnings)
            ),
            file=args.file,
            decoder=decoder,
        )
        return (data, [], auto_warnings + warnings)
    raise AssertionError(f"unsupported j1939 command: {args.command}")


def _build_dbc_source(resolution: Any) -> dict[str, Any]:
    from canarchy.dbc_runtime import detect_database_format

    d = resolution.descriptor
    return {
        "provider": d.provider,
        "name": d.name,
        "version": d.version,
        "path": str(resolution.local_path),
        "kind": detect_database_format(str(resolution.local_path)),
    }


def _filter_dbc_events_by_search(
    events: list[dict[str, Any]],
    filtered_payload: dict[str, Any],
    *,
    signals_only: bool,
) -> list[dict[str, Any]]:
    if signals_only:
        kept = {(s["message_name"], s["name"]) for s in filtered_payload.get("signals", [])}
        result = []
        for event in events:
            if event["event_type"] == "dbc_database":
                result.append(event)
            elif event["event_type"] == "dbc_signal":
                p = event["payload"]
                if (p.get("message_name"), p.get("name")) in kept:
                    result.append(event)
        return result

    kept_msgs = {msg["name"] for msg in filtered_payload.get("messages", [])}
    kept_sigs = {
        (msg["name"], sig["name"])
        for msg in filtered_payload.get("messages", [])
        for sig in msg.get("signals", [])
    }
    result = []
    for event in events:
        if event["event_type"] == "dbc_database":
            result.append(event)
        elif event["event_type"] == "dbc_message":
            if event["payload"].get("name") in kept_msgs:
                result.append(event)
        elif event["event_type"] == "dbc_signal":
            p = event["payload"]
            if (p.get("message_name"), p.get("name")) in kept_sigs:
                result.append(event)
    return result


def _filter_dbc_payload_by_search(
    payload: dict[str, Any],
    pattern: str,
    *,
    signals_only: bool,
) -> dict[str, Any]:
    import re as _re

    try:
        regex = _re.compile(pattern, _re.IGNORECASE)
    except _re.error:
        regex = _re.compile(_re.escape(pattern), _re.IGNORECASE)

    if signals_only:
        filtered = [
            sig
            for sig in payload.get("signals", [])
            if regex.search(sig["name"]) or regex.search(sig["message_name"])
        ]
        return {**payload, "signals": filtered, "signal_count": len(filtered)}

    filtered_messages = []
    for msg in payload.get("messages", []):
        if regex.search(msg["name"]):
            filtered_messages.append(msg)
        else:
            matching_signals = [sig for sig in msg.get("signals", []) if regex.search(sig["name"])]
            if matching_signals:
                filtered_messages.append(
                    {**msg, "signals": matching_signals, "signal_count": len(matching_signals)}
                )
    return {**payload, "messages": filtered_messages}


def dbc_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.dbc_provider import get_registry

    transport = LocalTransport()
    resolution = get_registry().resolve(args.dbc)
    dbc_path = str(resolution.local_path)
    dbc_source = _build_dbc_source(resolution)

    if args.command == "decode":
        frames = (
            frames_from_stdin(command=args.command)
            if args.stdin
            else transport.frames_from_file(
                args.file, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
            )
        )

        events = decode_frames(frames, dbc_path)
        warnings = []
        if not events:
            warnings.append("No frames in the capture matched messages from the selected DBC.")
        matched_messages = len(
            [event for event in events if event["event_type"] == "decoded_message"]
        )
        return (
            {
                "dbc": args.dbc,
                "dbc_source": dbc_source,
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
        frame, events, resolution = encode_message(
            dbc_path, args.message, signals, crc_algorithm=args.crc_algorithm
        )
        encode_warnings = [
            "Encoding prepares an active transmit frame; send it intentionally via a transmit workflow."
        ]
        message_resolution = resolution.get("message", {})
        if message_resolution.get("via") not in (None, "exact"):
            encode_warnings.append(
                f"Message '{args.message}' resolved to DBC message "
                f"'{message_resolution.get('resolved')}' via {message_resolution.get('via')}."
            )
        for alias in resolution.get("signal_aliases", []):
            encode_warnings.append(
                f"Signal '{alias['requested']}' resolved to DBC signal "
                f"'{alias['resolved']}' via {alias['via']}."
            )
        if resolution.get("filled_signals"):
            filled_names = ", ".join(entry["signal"] for entry in resolution["filled_signals"])
            encode_warnings.append(
                f"Unsupplied signal(s) defaulted for encoding: {filled_names}. "
                "Review data.resolution.filled_signals before transmitting."
            )
        return (
            {
                "crc_algorithm": args.crc_algorithm or "auto",
                "dbc": args.dbc,
                "dbc_source": dbc_source,
                "frame": frame.to_payload(),
                "message": args.message,
                "resolved_message": message_resolution.get("resolved", args.message),
                "resolution": resolution,
                "mode": "active",
                "signals": signals,
            },
            events,
            encode_warnings,
        )
    if args.command == "dbc inspect":
        data, events = inspect_database(
            dbc_path,
            message_name=args.message,
            signals_only=args.signals_only,
            include_layout=getattr(args, "layout", False),
        )
        search = getattr(args, "search", None)
        if search:
            signals_only = bool(args.signals_only)
            data = _filter_dbc_payload_by_search(data, search, signals_only=signals_only)
            events = _filter_dbc_events_by_search(events, data, signals_only=signals_only)
        data["dbc_source"] = dbc_source
        return (data, events, [])
    if args.command == "dbc signals":
        data, events = inspect_database(
            dbc_path,
            message_name=args.message,
            signals_only=True,
        )
        search = getattr(args, "search", None)
        if search:
            data = _filter_dbc_payload_by_search(data, search, signals_only=True)
            events = _filter_dbc_events_by_search(events, data, signals_only=True)
        data["dbc_source"] = dbc_source
        return (data, events, [])
    if args.command == "dbc convert":
        content, written, message_count, signal_count = convert_database(
            dbc_path, args.target_format, out=args.out
        )
        data = {
            "dbc": args.dbc,
            "dbc_source": dbc_source,
            "target_format": args.target_format,
            "out": written,
            "message_count": message_count,
            "signal_count": signal_count,
        }
        if written is None:
            data["content"] = content
        # No event is attached: for a conversion the envelope itself is the
        # payload. Emitting an event here would make --jsonl stream only the
        # event and drop the conversion result (content / out / counts).
        return (data, [], [])
    if args.command == "dbc generate-c":
        result = generate_c_source(
            dbc_path,
            out_dir=args.out_dir,
            database_name=args.database_name,
            floating_point_numbers=args.floating_point_numbers,
            bit_fields=args.bit_fields,
            use_float=args.use_float,
            node_name=args.node_name,
            use_round=args.use_round,
        )
        data = {
            "dbc": args.dbc,
            "dbc_source": dbc_source,
            "out_dir": result["out_dir"],
            "database_name": result["database_name"],
            "files": result["files"],
            "file_count": result["file_count"],
        }
        return (data, [], [])
    raise AssertionError(f"unsupported dbc command: {args.command}")


def dbc_provider_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.dbc_provider import get_registry
    from canarchy.dbc_cache import cache_list, cache_prune

    if args.command == "dbc provider list":
        registry = get_registry()
        providers = registry.list_providers()
        return ({"providers": providers}, [], [])

    if args.command == "dbc search":
        registry = get_registry()
        provider_filter = [args.provider] if getattr(args, "provider", None) else None
        limit = getattr(args, "limit", 20)
        results = registry.search(args.query, providers=provider_filter)[:limit]
        items = [
            {
                "provider": d.provider,
                "name": d.name,
                "version": d.version,
                "source_ref": d.source_ref,
                "metadata": d.metadata,
            }
            for d in results
        ]
        warnings: list[str] = []
        if not items:
            warnings.append(
                "No DBC files matched the query. Try `canarchy dbc cache refresh --provider opendbc` to populate the catalog."
            )
        return ({"query": args.query, "count": len(items), "results": items}, [], warnings)

    if args.command == "dbc fetch":
        registry = get_registry()
        resolution = registry.resolve(args.ref)
        return (
            {
                "ref": args.ref,
                "provider": resolution.descriptor.provider,
                "name": resolution.descriptor.name,
                "version": resolution.descriptor.version,
                "local_path": str(resolution.local_path),
                "is_cached": resolution.is_cached,
            },
            [],
            [],
        )

    if args.command == "dbc cache list":
        entries = cache_list()
        return ({"entries": entries, "count": len(entries)}, [], [])

    if args.command == "dbc cache prune":
        provider_filter = getattr(args, "provider", None)
        removed = cache_prune(provider_filter)
        return ({"removed": removed, "count": len(removed)}, [], [])

    if args.command == "dbc cache refresh":
        provider_name = getattr(args, "provider", "opendbc")
        registry = get_registry()
        provider = registry.get_provider(provider_name)
        if provider is None:
            from canarchy.dbc import DbcError

            raise DbcError(
                code="DBC_PROVIDER_NOT_FOUND",
                message=f"Provider '{provider_name}' is not registered.",
                hint=f"Available providers: {', '.join(p['name'] for p in registry.list_providers())}.",
            )
        descriptors = provider.refresh()
        return (
            {
                "provider": provider_name,
                "dbc_count": len(descriptors),
            },
            [],
            [],
        )

    raise AssertionError(f"unsupported dbc provider command: {args.command}")


def skills_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.skills_cache import cache_list
    from canarchy.skills_provider import get_registry

    registry = get_registry()

    if args.command == "skills provider list":
        return ({"providers": registry.list_providers()}, [], [])

    if args.command == "skills search":
        provider_filter = [args.provider] if getattr(args, "provider", None) else None
        limit = getattr(args, "limit", 20)
        results = registry.search(args.query, providers=provider_filter)[:limit]
        items = [
            {
                "provider": descriptor.provider,
                "name": descriptor.name,
                "publisher": descriptor.publisher,
                "version": descriptor.version,
                "source_ref": descriptor.source_ref,
                "metadata": descriptor.metadata,
            }
            for descriptor in results
        ]
        warnings: list[str] = []
        if not items:
            warnings.append(
                "No skills matched the query. Try `canarchy skills cache refresh --provider github` to populate the catalog."
            )
        return ({"query": args.query, "count": len(items), "results": items}, [], warnings)

    if args.command == "skills fetch":
        resolution = registry.resolve(args.ref)
        return (
            {
                "ref": args.ref,
                "provider": resolution.descriptor.provider,
                "name": resolution.descriptor.name,
                "publisher": resolution.descriptor.publisher,
                "version": resolution.descriptor.version,
                "local_manifest_path": str(resolution.local_manifest_path),
                "local_entry_path": str(resolution.local_entry_path),
                "is_cached": resolution.is_cached,
            },
            [],
            [],
        )

    if args.command == "skills cache list":
        entries = cache_list()
        return ({"entries": entries, "count": len(entries)}, [], [])

    if args.command == "skills cache refresh":
        provider_name = getattr(args, "provider", "github")
        provider = registry.get_provider(provider_name)
        if provider is None:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_DECODE_ERROR,
                errors=[
                    ErrorDetail(
                        code="SKILL_PROVIDER_NOT_FOUND",
                        message=f"Provider '{provider_name}' is not registered.",
                        hint=f"Available providers: {', '.join(p['name'] for p in registry.list_providers())}.",
                    )
                ],
            )
        descriptors = provider.refresh()
        return ({"provider": provider_name, "skill_count": len(descriptors)}, [], [])

    raise AssertionError(f"unsupported skills command: {args.command}")


def _plugin_config_path() -> Path:
    return Path.home() / ".canarchy" / "config.toml"


def _load_plugin_config() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Return the full config and normalized ``[plugins.<name>]`` tables."""
    import tomllib

    config_path = _plugin_config_path()
    if not config_path.exists():
        return {}, {}
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except Exception as exc:
        raise CommandError(
            command="plugins",
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="PLUGIN_CONFIG_INVALID",
                    message=f"Could not parse `{config_path}` as TOML: {exc}.",
                    hint="Repair ~/.canarchy/config.toml before toggling plugins.",
                )
            ],
        ) from exc
    plugins = raw.get("plugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
    plugin_tables = {
        name: value
        for name, value in plugins.items()
        if isinstance(name, str) and isinstance(value, dict)
    }
    return raw, plugin_tables


def _plugin_enabled(plugin_name: str, plugin_tables: dict[str, dict[str, Any]]) -> bool:
    enabled = plugin_tables.get(plugin_name, {}).get("enabled")
    return bool(enabled) if isinstance(enabled, bool) else True


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    return json.dumps(str(value))


def _toml_table_name(parts: Sequence[str]) -> str:
    return ".".join(
        json.dumps(part) if not part.replace("_", "").isalnum() else part for part in parts
    )


def _render_toml_table(table: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[str]:
    lines: list[str] = []
    scalars = {key: value for key, value in table.items() if not isinstance(value, dict)}
    children = {key: value for key, value in table.items() if isinstance(value, dict)}
    if prefix:
        lines.append(f"[{_toml_table_name(prefix)}]")
    for key in sorted(scalars):
        lines.append(f"{key} = {_toml_scalar(scalars[key])}")
    for key in sorted(children):
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(_render_toml_table(children[key], (*prefix, key)))
    return lines


def _write_plugin_enabled(name: str, enabled: bool) -> Path:
    config, _ = _load_plugin_config()
    plugins = config.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
        config["plugins"] = plugins
    plugin_table = plugins.setdefault(name, {})
    if not isinstance(plugin_table, dict):
        plugin_table = {}
        plugins[name] = plugin_table
    plugin_table["enabled"] = enabled

    config_path = _plugin_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rendered = "\n".join(_render_toml_table(config)).rstrip() + "\n"
        config_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise CommandError(
            command="plugins enable" if enabled else "plugins disable",
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="PLUGIN_CONFIG_WRITE_FAILED",
                    message=f"Could not write `{config_path}`: {exc}.",
                    hint="Check permissions on ~/.canarchy/config.toml.",
                )
            ],
        ) from exc
    return config_path


def _plugin_entries_with_config() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    from canarchy.plugins import get_registry

    _, plugin_tables = _load_plugin_config()
    entries = []
    for entry in get_registry().list_plugins():
        configured = dict(plugin_tables.get(entry["name"], {}))
        entry = dict(entry)
        entry["enabled"] = _plugin_enabled(entry["name"], plugin_tables)
        entry["configured_options"] = {
            key: value for key, value in configured.items() if key != "enabled"
        }
        entries.append(entry)
    return entries, plugin_tables


def plugins_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    entries, plugin_tables = _plugin_entries_with_config()
    config_path = _plugin_config_path()
    if args.command == "plugins list":
        return (
            {
                "mode": "passive",
                "plugin_count": len(entries),
                "plugins": entries,
                "config_file": str(config_path),
                "config_file_found": config_path.exists(),
            },
            [],
            [],
        )

    matches = [entry for entry in entries if entry["name"] == args.name]
    if not matches:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="PLUGIN_NOT_FOUND",
                    message=f"Plugin '{args.name}' is not registered.",
                    hint="Run `canarchy plugins list --json` to inspect discovered plugins.",
                )
            ],
        )

    configured_options = {
        key: value for key, value in plugin_tables.get(args.name, {}).items() if key != "enabled"
    }
    if args.command == "plugins info":
        return (
            {
                "mode": "passive",
                "name": args.name,
                "match_count": len(matches),
                "plugins": matches,
                "enabled": _plugin_enabled(args.name, plugin_tables),
                "configured_options": configured_options,
                "config_file": str(config_path),
                "config_file_found": config_path.exists(),
            },
            [],
            [],
        )

    if args.command in {"plugins enable", "plugins disable"}:
        enabled = args.command == "plugins enable"
        written_path = _write_plugin_enabled(args.name, enabled)
        for match in matches:
            match["enabled"] = enabled
        return (
            {
                "mode": "passive",
                "name": args.name,
                "enabled": enabled,
                "persisted": True,
                "config_file": str(written_path),
                "plugins": matches,
            },
            [],
            [],
        )
    raise AssertionError(f"unsupported plugins command: {args.command}")


def datasets_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.dataset_cache import cache_list
    from canarchy.dataset_provider import DatasetError, get_registry

    registry = get_registry()

    if args.command == "datasets provider list":
        return ({"providers": registry.list_providers()}, [], [])

    if args.command == "datasets search":
        query = getattr(args, "query", "") or ""
        provider_filter = [args.provider] if getattr(args, "provider", None) else None
        limit = getattr(args, "limit", 20)
        results = registry.search(query, providers=provider_filter, limit=limit)
        items = [dataset_descriptor_payload(d, include_metadata=False) for d in results]
        warns: list[str] = []
        if not items:
            warns.append("No datasets matched the query.")
        return ({"query": query, "count": len(items), "results": items}, [], warns)

    if args.command == "datasets inspect":
        try:
            descriptor = registry.inspect(args.ref)
        except DatasetError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        return (dataset_descriptor_payload(descriptor, include_metadata=True), [], [])

    if args.command == "datasets fetch":
        try:
            resolution = registry.fetch(args.ref)
        except DatasetError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc

        # Determine if this is a curated index
        metadata = (
            resolution.descriptor.metadata
            if isinstance(resolution.descriptor.metadata, dict)
            else {}
        )
        source_type = metadata.get("source_type") if isinstance(metadata, dict) else None
        is_index = source_type == "curated-index" or "catalog" in resolution.descriptor.formats

        # Build appropriate instructions
        if is_index:
            index_instructions = (
                f"Curated index entry. Visit the index page to discover datasets: "
                f"{resolution.descriptor.source_url}"
                + (
                    f" — Note: {resolution.descriptor.access_notes}"
                    if resolution.descriptor.access_notes
                    else ""
                )
                + "\n  Use `canarchy datasets search` to find specific datasets from this index."
            )
            download_instructions = index_instructions
        else:
            download_instructions = (
                f"Dataset provenance recorded. Download the data manually from: "
                f"{resolution.descriptor.source_url}"
                + (
                    f" — Note: {resolution.descriptor.access_notes}"
                    if resolution.descriptor.access_notes
                    else ""
                )
            )

        return (
            {
                "ref": args.ref,
                "provider": resolution.descriptor.provider,
                "name": resolution.descriptor.name,
                "cache_path": str(resolution.cache_path),
                "is_cached": resolution.is_cached,
                "provenance": resolution.provenance,
                "source_url": resolution.descriptor.source_url,
                "is_index": is_index,
                "index_instructions": index_instructions if is_index else None,
                "download_instructions": download_instructions,
            },
            [],
            [],
        )

    if args.command == "datasets cache list":
        entries = cache_list()
        return ({"entries": entries, "count": len(entries)}, [], [])

    if args.command == "datasets cache refresh":
        provider_name = getattr(args, "provider", "catalog")
        provider = registry.get_provider(provider_name)
        if provider is None:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="DATASET_PROVIDER_NOT_FOUND",
                        message=f"Provider '{provider_name}' is not registered.",
                        hint=f"Available providers: {', '.join(p['name'] for p in registry.list_providers())}.",
                    )
                ],
            )
        descriptors = provider.refresh()
        return ({"provider": provider_name, "dataset_count": len(descriptors)}, [], [])

    if args.command == "datasets convert":
        from canarchy.dataset_convert import ConversionError, convert_file

        try:
            result = convert_file(
                args.file,
                source_format=args.source_format,
                output_format=args.output_format,
                destination=getattr(args, "output", None),
            )
        except ConversionError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        return (result, [], [])

    if args.command == "datasets stream":
        from canarchy.dataset_convert import ConversionError, stream_file

        destination = getattr(args, "output", None)
        if destination in (None, "-"):
            destination = None if not getattr(args, "json", False) else None
        try:
            if getattr(args, "json", False) and destination is None:
                import os

                destination = os.devnull
            result = stream_file(
                args.file,
                source_format=args.source_format,
                output_format=args.output_format,
                destination=destination,
                chunk_size=getattr(args, "chunk_size", 1000),
                max_frames=getattr(args, "max_frames", None),
                provider_ref=getattr(args, "provider_ref", None),
            )
        except ConversionError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        return (result, [], [])

    if args.command == "datasets replay":
        from canarchy.dataset_convert import ConversionError, stream_replay

        try:
            replay_source = resolve_dataset_replay_source(
                args.source,
                registry,
                replay_file=getattr(args, "replay_file", None),
                platform=getattr(args, "platform", None),
                limit=getattr(args, "replay_limit", None),
                list_files=getattr(args, "list_files", False),
            )
            if getattr(args, "list_files", False):
                return (dataset_replay_files_payload(replay_source), [], [])
            validate_dataset_replay_options(args, replay_source)
            if getattr(args, "dry_run", False):
                return (dataset_replay_plan(args, replay_source), [], [])
            interface = getattr(args, "interface", None)
            live_mode = interface is not None
            if live_mode:
                enforce_active_transmit_safety(args)
            if replay_source.get("dynamic_manifest") == "comma-car-segments":
                from canarchy.comma_segments import resolve_lfs_url

                replay_source["download_url"] = resolve_lfs_url(replay_source["download_url"])
            result = stream_replay(
                replay_source["download_url"],
                source_format=replay_source["source_format"],
                output_format=args.output_format,
                rate=args.rate,
                max_frames=getattr(args, "max_frames", None),
                max_seconds=getattr(args, "max_seconds", None),
                provenance=dataset_replay_provenance(replay_source),
                emit_frames=False,
                send_interface=interface,
            )
        except ConversionError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        except DatasetError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        return ({**result, **replay_source}, [], [])

    raise AssertionError(f"unsupported datasets command: {args.command}")


def resolve_dataset_replay_source(
    source: str,
    registry: Any,
    *,
    replay_file: str | None = None,
    platform: str | None = None,
    limit: int | None = None,
    list_files: bool = False,
) -> dict[str, Any]:
    """Resolve a replay source from either a direct URL or dataset descriptor metadata."""
    if source.startswith(("http://", "https://")):
        return {
            "source": source,
            "source_type": "url",
            "is_replayable": True,
            "is_index": False,
            "default_replay_file": None,
            "download_url_available": True,
            "download_url": source,
            "source_format": "candump",
            "replay_file": None,
        }

    from canarchy.dataset_provider import DatasetError

    descriptor = registry.inspect(source)
    replay = descriptor.metadata.get("replay") if isinstance(descriptor.metadata, dict) else None
    if isinstance(replay, dict) and replay.get("dynamic") == "comma-car-segments":
        return resolve_comma_car_segments_replay_source(
            source,
            descriptor,
            replay,
            replay_file=replay_file,
            platform=platform,
            limit=limit,
            list_files=list_files,
        )
    if not isinstance(replay, dict) or not replay.get("download_url"):
        machine = dataset_machine_fields(descriptor)
        if machine["is_index"]:
            raise DatasetError(
                code="DATASET_INDEX_NOT_REPLAYABLE",
                message=f"Dataset index '{source}' does not define a replayable remote file.",
                hint="Use `canarchy datasets inspect <ref>` to review linked dataset sources, then pass a replayable dataset ref or direct candump URL.",
            )
        raise DatasetError(
            code="DATASET_REPLAY_UNAVAILABLE",
            message=f"Dataset '{source}' does not define a replayable remote file.",
            hint="Use `canarchy datasets inspect <ref>` to review available metadata, or pass a direct candump download URL.",
        )

    files = replay_files(replay)
    selected_file = select_replay_file(files, replay_file or replay.get("default_file"), source)
    download_url = selected_file.get("source_url") or replay["download_url"]
    source_format = selected_file.get("format") or replay.get("source_format", "candump")
    return {
        "source": source,
        "source_type": "dataset_ref",
        "is_replayable": True,
        "is_index": False,
        "provider": descriptor.provider,
        "name": descriptor.name,
        "ref": f"{descriptor.provider}:{descriptor.name}",
        "default_file": replay.get("default_file"),
        "default_replay_file": replay.get("default_file"),
        "download_url_available": True,
        "download_url": download_url,
        "source_format": source_format,
        "replay_file": selected_file.get("name"),
        "replay_file_id": selected_file.get("id"),
        "replay_files": files,
    }


def resolve_comma_car_segments_replay_source(
    source: str,
    descriptor: Any,
    replay: dict[str, Any],
    *,
    replay_file: str | None,
    platform: str | None,
    limit: int | None,
    list_files: bool,
) -> dict[str, Any]:
    """Resolve dynamic commaCarSegments replay metadata."""
    from canarchy.comma_segments import segment_entries
    from canarchy.dataset_provider import DatasetError

    if limit is not None and limit < 1:
        raise DatasetError(
            code="INVALID_LIMIT",
            message=f"Replay file list limit must be positive, got {limit}.",
            hint="Use `--limit` with a positive integer.",
        )
    effective_limit = limit
    if effective_limit is None and list_files:
        effective_limit = 50
    if effective_limit is None and replay_file is None:
        effective_limit = 1
    files = segment_entries(platform=platform, limit=effective_limit)
    if not files:
        raise DatasetError(
            code="COMMA_SEGMENTS_MANIFEST_EMPTY",
            message="commaCarSegments did not return any replayable segment entries.",
            hint="Try a different `--platform`, remove `--limit`, or check the upstream dataset manifest.",
        )
    selected_file = select_replay_file(files, replay_file, source) if replay_file else files[0]
    raw_download_url = selected_file.get("source_url")
    return {
        "source": source,
        "source_type": "dataset_ref",
        "is_replayable": True,
        "is_index": False,
        "provider": descriptor.provider,
        "name": descriptor.name,
        "ref": f"{descriptor.provider}:{descriptor.name}",
        "default_file": replay.get("default_file"),
        "default_replay_file": replay.get("default_file"),
        "download_url_available": bool(raw_download_url),
        "download_url": raw_download_url,
        "source_format": "comma-rlog",
        "replay_file": selected_file.get("name"),
        "replay_file_id": selected_file.get("id"),
        "replay_files": files,
        "platform": selected_file.get("platform"),
        "route": selected_file.get("route"),
        "segment": selected_file.get("segment"),
        "dynamic_manifest": "comma-car-segments",
    }


def replay_files(replay: dict[str, Any]) -> list[dict[str, Any]]:
    """Return stable replayable file entries from replay metadata."""
    files = replay.get("files") if isinstance(replay, dict) else None
    if isinstance(files, list) and files:
        return [dict(file) for file in files if isinstance(file, dict)]
    default_file = replay.get("default_file") if isinstance(replay, dict) else None
    download_url = replay.get("download_url") if isinstance(replay, dict) else None
    source_format = (
        replay.get("source_format", "candump") if isinstance(replay, dict) else "candump"
    )
    return [
        {
            "id": default_file,
            "name": default_file,
            "format": source_format,
            "size_bytes": None,
            "source_url": download_url,
        }
    ]


def select_replay_file(
    files: list[dict[str, Any]], requested: str | None, source: str
) -> dict[str, Any]:
    """Select a replay file by stable id or name."""
    if not files:
        from canarchy.dataset_provider import DatasetError

        raise DatasetError(
            code="DATASET_REPLAY_FILE_NOT_FOUND",
            message=f"Dataset '{source}' does not define replayable files.",
            hint="Use `canarchy datasets inspect <ref>` to review replay metadata.",
        )
    if requested is None:
        return files[0]
    for file in files:
        if requested in {str(file.get("id")), str(file.get("name"))}:
            return file
    from canarchy.dataset_provider import DatasetError

    raise DatasetError(
        code="DATASET_REPLAY_FILE_NOT_FOUND",
        message=f"Replay file '{requested}' was not found for dataset '{source}'.",
        hint="Use `canarchy datasets replay <ref> --list-files --json` to list replayable file ids.",
    )


def dataset_replay_files_payload(replay_source: dict[str, Any]) -> dict[str, Any]:
    """Return replay file manifest metadata without opening the remote stream."""
    files = replay_source.get("replay_files") or []
    return {
        "source": replay_source.get("source"),
        "source_type": replay_source.get("source_type"),
        "ref": replay_source.get("ref"),
        "default_replay_file": replay_source.get("default_replay_file"),
        "selected_file": replay_source.get("replay_file"),
        "count": len(files),
        "files": files,
        "streamed": False,
    }


def dataset_machine_fields(descriptor: Any) -> dict[str, Any]:
    """Return stable machine fields for dataset catalog results."""
    metadata = descriptor.metadata if isinstance(descriptor.metadata, dict) else {}
    replay = metadata.get("replay") if isinstance(metadata, dict) else None
    replay_download_url = replay.get("download_url") if isinstance(replay, dict) else None
    default_replay_file = replay.get("default_file") if isinstance(replay, dict) else None
    source_type = metadata.get("source_type") if isinstance(metadata, dict) else None
    is_index = source_type == "curated-index" or "catalog" in descriptor.formats
    return {
        "ref": f"{descriptor.provider}:{descriptor.name}",
        "is_replayable": bool(replay_download_url),
        "is_index": is_index,
        "default_replay_file": default_replay_file,
        "download_url_available": bool(replay_download_url),
        "source_type": source_type or ("index" if is_index else "dataset"),
    }


def dataset_descriptor_payload(descriptor: Any, *, include_metadata: bool) -> dict[str, Any]:
    """Return JSON-stable dataset descriptor fields for search and inspect."""
    payload = {
        **dataset_machine_fields(descriptor),
        "provider": descriptor.provider,
        "name": descriptor.name,
        "version": descriptor.version,
        "protocol_family": descriptor.protocol_family,
        "formats": list(descriptor.formats),
        "size_description": descriptor.size_description,
        "license": descriptor.license,
        "source_url": descriptor.source_url,
        "description": descriptor.description,
        "conversion_targets": list(descriptor.conversion_targets),
        "access_notes": descriptor.access_notes,
    }
    if include_metadata:
        payload["metadata"] = descriptor.metadata
    return payload


def dataset_replay_plan(args: argparse.Namespace, replay_source: dict[str, Any]) -> dict[str, Any]:
    """Return replay source resolution metadata without opening the remote stream."""
    return {
        **replay_source,
        "dry_run": True,
        "is_replayable": True,
        "output_format": args.output_format,
        "rate": args.rate,
        "max_frames": getattr(args, "max_frames", None),
        "max_seconds": getattr(args, "max_seconds", None),
        "streamed": False,
        "would_stream": True,
    }


def dataset_replay_provenance(replay_source: dict[str, Any]) -> dict[str, Any]:
    """Return JSONL provenance metadata for replayed dataset frames."""
    return {
        "provider_ref": replay_source.get("ref") or replay_source.get("source"),
        "source_url": replay_source.get("download_url"),
        "replay_file": replay_source.get("replay_file") or replay_source.get("default_replay_file"),
        "default_replay_file": replay_source.get("default_replay_file"),
        "source_type": replay_source.get("source_type"),
    }


def validate_dataset_replay_options(
    args: argparse.Namespace, replay_source: dict[str, Any]
) -> None:
    """Validate replay options that dry-run plans claim would be streamable."""
    from canarchy.dataset_convert import ConversionError

    source_format = replay_source.get("source_format", "candump")
    if source_format not in {"candump", "comma-rlog"}:
        raise ConversionError(
            code="UNSUPPORTED_SOURCE_FORMAT",
            message=f"Streaming replay only supports candump or comma-rlog format, got '{source_format}'.",
            hint="Use source_format='candump' or source_format='comma-rlog' for streaming replay.",
        )
    if args.rate <= 0:
        raise ConversionError(
            code="INVALID_RATE",
            message=f"Replay rate must be positive, got {args.rate}.",
            hint="Use a positive rate like 1.0 (real-time) or 0.5 (half-speed).",
        )
    max_seconds = getattr(args, "max_seconds", None)
    if max_seconds is not None and max_seconds <= 0:
        raise ConversionError(
            code="INVALID_MAX_SECONDS",
            message=f"Replay max seconds must be positive, got {max_seconds}.",
            hint="Use `--max-seconds` with a positive duration.",
        )


def _doip_uds_payload(
    args: argparse.Namespace, target: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.doip import (
        DoipError,
        doip_scan_events,
        doip_trace_events,
        parse_doip_target,
    )

    try:
        doip_target = parse_doip_target(target)
    except DoipError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
        ) from exc

    # Both scan and trace open a TCP session and transmit over DoIP, so the
    # active-transmit safety gate runs before any socket is opened.
    enforce_active_transmit_safety(args)

    try:
        if args.command == "uds scan":
            events = doip_scan_events(doip_target)
            count_field = {"responder_count": len(events)}
        else:  # uds trace
            events = doip_trace_events(doip_target)
            count_field = {"transaction_count": len(events)}
    except DoipError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_TRANSPORT_ERROR,
            errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            data={"mode": "active", "transport": "doip", "target": target},
        ) from exc

    return (
        {
            "interface": target,
            "target": target,
            "transport": "doip",
            "host": doip_target.host,
            "port": doip_target.port,
            "logical_address": doip_target.logical_address,
            "source_address": doip_target.source_address,
            "mode": "active",
            "protocol_decoder": uds_decoder_backend(),
            **count_field,
        },
        events,
        [],
    )


def uds_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    target = getattr(args, "interface", None)
    if args.command in ("uds scan", "uds trace") and is_doip_target(target):
        return _doip_uds_payload(args, target)
    transport = LocalTransport()
    backend_metadata = transport.backend_metadata()
    implementation = (
        "transport-backed"
        if backend_metadata["transport_backend"] != "scaffold"
        else "sample/reference provider"
    )
    if args.command == "uds scan":
        enforce_active_transmit_safety(args)
        events = transport.uds_scan_events(args.interface)
        return (
            {
                "interface": args.interface,
                "mode": "active",
                "protocol_decoder": uds_decoder_backend(),
                "responder_count": len(events),
                **backend_metadata,
                "implementation": implementation,
            },
            events,
            [],
        )
    if args.command == "uds trace":
        events = transport.uds_trace_events(args.interface)
        return (
            {
                "interface": args.interface,
                "mode": "passive",
                "protocol_decoder": uds_decoder_backend(),
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


def _parse_can_id(value: str, *, command: str, name: str, code: str = "XCP_INVALID_ID") -> int:
    try:
        parsed = int(str(value), 0)
    except ValueError as exc:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code=code,
                    message=f"{name} {value!r} is not a valid CAN id.",
                    hint="Pass a decimal or 0x-prefixed hex CAN id (e.g. 0x3E0).",
                )
            ],
        ) from exc
    if parsed < 0 or parsed > 0x1FFFFFFF:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code=code,
                    message=f"{name} 0x{parsed:X} is outside the 29-bit CAN id range.",
                    hint="CAN ids are 0x000-0x1FFFFFFF.",
                )
            ],
        )
    return parsed


def xcp_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    backend_metadata = transport.backend_metadata()
    implementation = (
        "transport-backed"
        if backend_metadata["transport_backend"] != "scaffold"
        else "sample/reference provider"
    )

    if args.command == "xcp commands":
        commands = xcp_commands_payload()
        return (
            {"mode": "reference", "command_count": len(commands), "commands": commands},
            [],
            [],
        )

    response_id = _parse_can_id(
        getattr(args, "response_id", hex(XCP_DEFAULT_RESPONSE_ID)),
        command=args.command,
        name="--response-id",
    )

    if args.command == "xcp read":
        events = transport.xcp_read_events(args.interface, response_id=response_id)
        return (
            {
                "interface": args.interface,
                "mode": "passive",
                "response_id": response_id,
                "measurement_count": len(events),
                **backend_metadata,
                "implementation": implementation,
            },
            events,
            [],
        )

    request_id = _parse_can_id(
        getattr(args, "request_id", hex(XCP_DEFAULT_REQUEST_ID)),
        command=args.command,
        name="--request-id",
    )

    if args.command == "xcp scan":
        if getattr(args, "dry_run", False):
            frame = connect_request_frame(args.interface, request_id)
            return (
                {
                    "interface": args.interface,
                    "mode": "dry_run",
                    "request_id": request_id,
                    "response_id": response_id,
                    "responder_count": 0,
                    "planned_frame": {
                        "arbitration_id": frame.arbitration_id,
                        "is_extended_id": frame.is_extended_id,
                        "data": frame.data.hex(),
                    },
                },
                [],
                [
                    f"ACTIVE_TRANSMIT_DRY_RUN: planned XCP CONNECT to id "
                    f"0x{request_id:X} on `{args.interface}`; no frame sent."
                ],
            )
        enforce_active_transmit_safety(args)
        events = transport.xcp_scan_events(
            args.interface, request_id=request_id, response_id=response_id
        )
        return (
            {
                "interface": args.interface,
                "mode": "active",
                "request_id": request_id,
                "response_id": response_id,
                "responder_count": len(events),
                **backend_metadata,
                "implementation": implementation,
            },
            events,
            [],
        )

    if args.command == "xcp trace":
        events = transport.xcp_trace_events(
            args.interface, request_id=request_id, response_id=response_id
        )
        return (
            {
                "interface": args.interface,
                "mode": "passive",
                "request_id": request_id,
                "response_id": response_id,
                "transaction_count": len(events),
                **backend_metadata,
                "implementation": implementation,
            },
            events,
            [],
        )

    raise AssertionError(f"unsupported xcp command: {args.command}")


def j1587_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    if args.command == "j1587 pids":
        pids = j1587_pids_payload()
        return ({"mode": "reference", "pid_count": len(pids), "pids": pids}, [], [])

    try:
        messages = list(
            iter_j1708_messages_from_file(args.file, **j1939_file_analysis_kwargs(args))
        )
    except TransportError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        ) from exc

    events = decode_j1587_events(messages)
    warnings: list[str] = []
    if not messages:
        warnings.append("No J1708 messages were found in the input.")
    checksum_failures = sum(1 for message in messages if not message.checksum_valid)
    return (
        {
            "mode": "passive",
            "file": args.file,
            "message_count": len(messages),
            "parameter_count": len(events),
            "checksum_failures": checksum_failures,
        },
        serialize_events(events),
        warnings,
    )


def j2497_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    if args.command == "j2497 mids":
        mids = j2497_mids_payload()
        return ({"mode": "reference", "mid_count": len(mids), "mids": mids}, [], [])

    try:
        messages = list(iter_j2497_frames_from_file(args.file, **j1939_file_analysis_kwargs(args)))
    except TransportError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        ) from exc

    events = decode_j2497_events(messages)
    warnings: list[str] = []
    if not messages:
        warnings.append("No J2497 frames were found in the input.")
    checksum_failures = sum(1 for message in messages if not message.checksum_valid)
    return (
        {
            "mode": "passive",
            "file": args.file,
            "frame_count": len(messages),
            "checksum_failures": checksum_failures,
        },
        serialize_events(events),
        warnings,
    )


def gateway_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    if getattr(args, "dry_run", False):
        return (
            {
                "mode": "dry_run",
                "dry_run": True,
                "src": args.src,
                "dst": args.dst,
                "src_backend": args.src_backend,
                "dst_backend": args.dst_backend,
                "bidirectional": args.bidirectional,
                "count": args.count,
                "forwarded_frames": 0,
                "would_forward": True,
                "status": "implemented",
                "implementation": "live transport gateway",
            },
            [],
            ["ACTIVE_TRANSMIT_DRY_RUN: gateway planned; no transport opened."],
        )
    enforce_active_transmit_safety(args)
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
            "dry_run": False,
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


def plot_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.plot import PlotDependencyError, decode_signal_series, plot_signals

    # Resolve the database ref through the provider registry so `plot` accepts
    # `opendbc:<name>` shorthand like decode/encode (#427). A bad ref raises
    # DbcError here — outside the broad PLOT_ERROR handler below — so it surfaces
    # as the canonical DBC_* envelope via the global handler.
    from canarchy.dbc_provider import get_registry

    resolution = get_registry().resolve(args.dbc)
    dbc_path = str(resolution.local_path)
    dbc_source = _build_dbc_source(resolution)

    try:
        series = decode_signal_series(
            args.file,
            dbc_path,
            args.signals,
            offset=getattr(args, "offset", 0) or 0,
            max_frames=getattr(args, "max_frames", None),
            seconds=getattr(args, "seconds", None),
        )
        stats = plot_signals(
            series,
            output_path=args.out,
            output_format=args.plot_format,
            title=f"CANarchy: {', '.join(args.signals)}",
        )
    except PlotDependencyError as exc:
        dep = exc.dependency
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="PLOT_DEPENDENCY_MISSING",
                    message=f"{dep} is required for this output format.",
                    hint="Install it with: pip install canarchy[plot]",
                )
            ],
        )
    except Exception as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="PLOT_ERROR",
                    message=str(exc),
                    hint="Check that the capture file and DBC are valid and that the signal names match the DBC.",
                )
            ],
        )

    empty_signals = [s for s in args.signals if not series.get(s)]
    warnings = [f"No data found for signal '{s}' in capture." for s in empty_signals]

    return (
        {
            "file": args.file,
            "dbc": args.dbc,
            "dbc_source": dbc_source,
            "signals": args.signals,
            "out": args.out,
            "format": args.plot_format,
            **stats,
        },
        [],
        warnings,
    )


def _parse_fuzz_hex_id(value: str, *, command: str) -> int:
    """Parse a hex CAN ID flag, raising a structured error on failure."""
    try:
        return int(value, 16)
    except (TypeError, ValueError) as exc:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FRAME_ID",
                    message=f"Could not parse `{value}` as a hex CAN ID.",
                    hint="Use hex form, prefixed or unprefixed (`0x123` or `123`).",
                )
            ],
        ) from exc


_CAN_STANDARD_ID_MAX = 0x7FF
_CAN_EXTENDED_ID_MAX = 0x1FFFFFFF


def _resolve_can_frame_extended(
    arbitration_id: int, explicit_extended: bool, *, command: str, name: str, code: str
) -> bool:
    """Validate a CAN id and decide whether its frame is extended.

    Like ``parse_send_frame`` / ``xcp.connect_request_frame``, an id above the
    11-bit standard range implies an extended frame, so a 29-bit id is never
    built as an (invalid) standard frame. An id outside the 29-bit range is
    reported as a structured user error instead of leaking the ``CanFrame``
    ``ValueError`` as an uncaught traceback.
    """
    if arbitration_id < 0 or arbitration_id > _CAN_EXTENDED_ID_MAX:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code=code,
                    message=f"{name} {arbitration_id} is outside the 29-bit CAN id range.",
                    hint="CAN ids are 0x000-0x1FFFFFFF; pass --extended to force a 29-bit frame.",
                )
            ],
        )
    return explicit_extended or arbitration_id > _CAN_STANDARD_ID_MAX


def _parse_fuzz_payload_data(value: str | None, *, default_dlc: int, command: str) -> bytes:
    if value is None:
        return b"\x00" * default_dlc
    try:
        return bytes.fromhex(value)
    except (TypeError, ValueError) as exc:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FRAME_DATA",
                    message=f"Could not parse `{value}` as a hex payload.",
                    hint="Use pairs of hex digits without separators, such as `11223344`.",
                )
            ],
        ) from exc


def _parse_fuzz_id_range(value: str, *, command: str) -> tuple[int, int]:
    if ":" not in value:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FUZZ_RANGE",
                    message=f"Could not parse `{value}` as a start:end ID range.",
                    hint="Use `<start>:<end>` with hex bounds, e.g. `0x100:0x110`.",
                )
            ],
        )
    start_text, end_text = value.split(":", 1)
    start = _parse_fuzz_hex_id(start_text, command=command)
    end = _parse_fuzz_hex_id(end_text, command=command)
    return start, end


def _resolve_fuzz_run_id(args: argparse.Namespace) -> str:
    explicit = getattr(args, "run_id", None)
    if explicit is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(explicit))
    except (TypeError, ValueError) as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="ACTIVE_TRANSMIT_INVALID_RUN_ID",
                    message=f"`{explicit}` is not a valid UUID for --run-id.",
                    hint=(
                        "Use a UUID4 such as `0193bf6e-1e3e-7a8c-b6b1-d0e7d3a8f4f0`, "
                        "or omit `--run-id` to have one generated."
                    ),
                )
            ],
        ) from exc


def _validate_fuzz_rate(rate: float, command: str) -> None:
    if rate is not None and rate <= 0:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_RATE",
                    message="--rate must be greater than zero.",
                    hint="Pass a positive value such as 100 or 250.",
                )
            ],
        )


def _wrap_fuzz_value_error(args: argparse.Namespace, exc: ValueError) -> CommandError:
    """Translate a `ValueError` from `canarchy.fuzzing` into a `CommandError`.

    The mutators validate their inputs (DLC range, negative count,
    inverted ID bounds, etc.) and raise `ValueError` for misuse. The CLI
    must translate those into the canonical structured-error envelope
    instead of letting a traceback escape `execute_command`.
    """

    return CommandError(
        command=args.command,
        exit_code=EXIT_USER_ERROR,
        errors=[
            ErrorDetail(
                code="INVALID_ARGUMENTS",
                message=str(exc),
                hint=(
                    "Check the fuzz strategy's bounds: --dlc must be in [0, 64], "
                    "--max must be non-negative, and arbitration-id ranges must fit "
                    "the 11-/29-bit address space."
                ),
            )
        ],
    )


def _load_fuzz_corpus(args: argparse.Namespace) -> list[bytes]:
    """Load the seed corpus (frame payloads) for the splice strategy."""
    if not args.corpus:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="MISSING_INPUT",
                    message="`fuzz payload --strategy splice` requires --corpus <capture>.",
                    hint="Pass a candump capture whose frame payloads seed the splice corpus.",
                )
            ],
        )
    transport_backend = LocalTransport()
    try:
        frames = transport_backend.frames_from_file(args.corpus)
    except TransportError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        ) from exc
    return [frame.data for frame in frames]


def _build_fuzz_payload_frames(args: argparse.Namespace) -> list[CanFrame]:
    arbitration_id = _parse_fuzz_hex_id(args.id, command=args.command)
    extended = _resolve_can_frame_extended(
        arbitration_id,
        bool(args.extended),
        command=args.command,
        name="--id",
        code="INVALID_FRAME_ID",
    )
    # For bitflip we mutate the explicit (or default-8-byte-zero) baseline
    # in place — DLC is inherited from the baseline payload.
    # For random / boundary the user's --dlc takes precedence; --data is
    # ignored because those strategies generate full payloads from
    # scratch.
    # The mutators are generators that validate their inputs only on
    # first iteration, so the iteration itself must run inside the
    # try/except in order to translate the engine's `ValueError`
    # signals (negative DLC, negative count, …) into structured
    # `INVALID_ARGUMENTS` envelopes instead of leaking a traceback.
    try:
        if args.strategy == "bitflip":
            baseline = _parse_fuzz_payload_data(args.data, default_dlc=8, command=args.command)
            payloads = fuzzing.bitflip_payload(
                baseline, seed=args.seed, max_mutations=args.max_frames_fuzz
            )
        elif args.strategy == "random":
            payloads = fuzzing.random_payload(
                dlc=args.dlc, seed=args.seed, count=args.max_frames_fuzz
            )
        elif args.strategy == "havoc":
            baseline = _parse_fuzz_payload_data(args.data, default_dlc=8, command=args.command)
            payloads = fuzzing.havoc_payload(baseline, seed=args.seed, count=args.max_frames_fuzz)
        elif args.strategy == "splice":
            corpus = _load_fuzz_corpus(args)
            payloads = fuzzing.splice_payload(corpus, seed=args.seed, count=args.max_frames_fuzz)
        elif args.strategy == "interesting":
            payloads = fuzzing.interesting_values_payload(dlc=args.dlc)
        else:  # boundary
            payloads = fuzzing.boundary_payload(dlc=args.dlc)
        materialised = list(itertools.islice(payloads, args.max_frames_fuzz))
        # `havoc` and `splice` can grow a payload beyond the input length
        # (block insertion, prefix+suffix joins), and the engine only caps
        # at the 64-byte CAN FD ceiling. `fuzz payload` emits classic CAN
        # frames, which top out at 8 bytes, so clamp these strategies to a
        # classic DLC before building frames.
        if args.strategy in ("havoc", "splice"):
            materialised = [payload[:8] for payload in materialised]
    except ValueError as exc:
        raise _wrap_fuzz_value_error(args, exc) from exc
    return [
        CanFrame(
            arbitration_id=arbitration_id,
            data=payload,
            is_extended_id=extended,
            timestamp=i / args.rate if args.rate else None,
        )
        for i, payload in enumerate(materialised)
    ]


def _build_fuzz_replay_frames(args: argparse.Namespace) -> list[CanFrame]:
    transport_backend = LocalTransport()
    try:
        raw_frames = transport_backend.frames_from_file(args.file)
    except TransportError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        ) from exc
    try:
        mutated = list(fuzzing.mutate_replay(raw_frames, strategy=args.strategy, seed=args.seed))
    except ValueError as exc:
        raise _wrap_fuzz_value_error(args, exc) from exc
    if args.max_frames_fuzz is not None:
        mutated = mutated[: args.max_frames_fuzz]
    return mutated


def _build_fuzz_arbid_frames(args: argparse.Namespace) -> list[CanFrame]:
    start, end = _parse_fuzz_id_range(args.id_range, command=args.command)
    payload = _parse_fuzz_payload_data(args.data, default_dlc=8, command=args.command)
    try:
        ids = list(fuzzing.arbitration_id_range(start, end, extended=args.extended, step=args.step))
    except ValueError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FUZZ_RANGE",
                    message=str(exc),
                    hint="Use a non-empty range within the 11-bit or 29-bit CAN ID space.",
                )
            ],
        ) from exc
    return [
        CanFrame(
            arbitration_id=arbid,
            data=payload,
            is_extended_id=args.extended,
            timestamp=i / args.rate if args.rate else None,
        )
        for i, arbid in enumerate(ids)
    ]


def _build_fuzz_signal_frames(args: argparse.Namespace) -> list[CanFrame]:
    from canarchy.dbc import DbcError
    from canarchy.dbc_runtime import load_runtime_database

    try:
        database = load_runtime_database(args.dbc)
    except DbcError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        ) from exc

    try:
        message = database.get_message_by_name(args.message)
    except KeyError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="DBC_MESSAGE_NOT_FOUND",
                    message=f"DBC message '{args.message}' was not found.",
                    hint="Use a message name that exists in the selected DBC.",
                )
            ],
        ) from exc

    try:
        payloads = list(
            itertools.islice(
                fuzzing.signal_payload(
                    message=message,
                    signal=args.signal,
                    mode=args.mode,
                    seed=args.seed,
                    count=args.count,
                ),
                args.count,
            )
        )
    except ValueError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FUZZ_SIGNAL",
                    message=str(exc),
                    hint=(
                        "Check that --signal exists on --message, --count is non-negative, "
                        "and that --mode enum_gaps is only used on a signal with a value table."
                    ),
                )
            ],
        ) from exc

    return [
        CanFrame(
            arbitration_id=int(message.frame_id),
            data=payload,
            is_extended_id=bool(message.is_extended_frame),
            timestamp=i / args.rate if args.rate else None,
        )
        for i, payload in enumerate(payloads)
    ]


def _build_fuzz_spn_frames(args: argparse.Namespace) -> list[CanFrame]:
    from canarchy.j1939 import compose_arbitration_id
    from canarchy.j1939_metadata import spn_lookup

    # `spn_payload` validates that the SPN exists, has complete layout
    # metadata, and that any supplied --pgn matches — raising ValueError
    # which we translate to a structured error. Generating first means we
    # never dereference incomplete metadata (e.g. a name-only SPN).
    try:
        payloads = list(
            itertools.islice(
                fuzzing.spn_payload(
                    spn=args.spn,
                    mode=args.mode,
                    seed=args.seed,
                    count=args.count,
                    pgn=args.pgn,
                ),
                args.count,
            )
        )
    except ValueError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="INVALID_FUZZ_SPN",
                    message=str(exc),
                    hint=(
                        "Use an SPN with complete built-in J1939 metadata (see `j1939 spn`); "
                        "--count must be non-negative and any --pgn must match the SPN's PGN."
                    ),
                )
            ],
        ) from exc

    # Safe: a successful spn_payload guarantees complete metadata, so the
    # PGN field is present.
    spn_pgn = int(spn_lookup(args.spn)["pgn"])
    arbitration_id = compose_arbitration_id(spn_pgn)
    return [
        CanFrame(
            arbitration_id=arbitration_id,
            data=payload,
            is_extended_id=True,
            timestamp=i / args.rate if args.rate else None,
        )
        for i, payload in enumerate(payloads)
    ]


def fuzz_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Build the (data, events, warnings) tuple for any `canarchy fuzz *` command."""

    rate = getattr(args, "rate", None)
    _validate_fuzz_rate(rate, args.command)
    run_id = _resolve_fuzz_run_id(args)
    dry_run = bool(getattr(args, "dry_run", False))

    if args.command == "fuzz payload":
        frames = _build_fuzz_payload_frames(args)
        target = args.interface
    elif args.command == "fuzz replay":
        if not dry_run and not args.interface:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="MISSING_INPUT",
                        message="`fuzz replay` requires --interface unless --dry-run is set.",
                        hint="Pass `--interface <iface>` or run with `--dry-run` for planning.",
                    )
                ],
            )
        frames = _build_fuzz_replay_frames(args)
        target = args.interface or args.file
    elif args.command == "fuzz arbitration-id":
        frames = _build_fuzz_arbid_frames(args)
        target = args.interface
    elif args.command == "fuzz signal":
        frames = _build_fuzz_signal_frames(args)
        target = args.interface
    elif args.command == "fuzz spn":
        frames = _build_fuzz_spn_frames(args)
        target = args.interface
    else:  # pragma: no cover — guarded by IMPLEMENTED_COMMANDS
        raise AssertionError(f"unexpected fuzz command: {args.command}")

    if getattr(args, "repair_crc", False):
        from dataclasses import replace as dc_replace

        from canarchy.checksum import CrcAlgorithm, repair_crc

        crc_algorithm_map: dict[str, CrcAlgorithm] = {
            "stellantis": CrcAlgorithm.STELLANTIS,
            "sae-j1850": CrcAlgorithm.SAE_J1850,
            "fca-giorgio": CrcAlgorithm.FCA_GIORGIO,
        }
        algo_str = getattr(args, "crc_algorithm", None) or "stellantis"
        algo = crc_algorithm_map[algo_str]
        explicit_address = getattr(args, "crc_address", None)
        if explicit_address is not None:
            frames = [
                dc_replace(frame, data=repair_crc(frame.data, algo, address=explicit_address))
                for frame in frames
            ]
        else:
            frames = [
                dc_replace(frame, data=repair_crc(frame.data, algo, address=frame.arbitration_id))
                for frame in frames
            ]

    if not dry_run:
        enforce_active_transmit_safety(args)
        # Live transmission. Matches the existing `generate` model: build
        # frames, walk the list and call `LocalTransport.send` for each,
        # honouring the requested rate as inter-frame spacing. SIGINT is
        # raised by Python's default handler and converts to a clean
        # KeyboardInterrupt exit from main(); finer-grained
        # `KILL_SWITCH_TRIGGERED` provenance is a documented follow-up
        # (per `docs/design/active-transmit-safety.md` REQ-ATS-09).
        live_backend = LocalTransport()
        live_target = target
        if live_target is None:  # pragma: no cover — guarded above
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="MISSING_INPUT",
                        message="Live fuzz requires a target interface.",
                        hint="Pass `--interface <iface>` or run with `--dry-run`.",
                    )
                ],
            )
        gap_s = 1.0 / rate if rate and rate > 0 else 0.0
        for i, frame in enumerate(frames):
            if i > 0 and gap_s > 0:
                time.sleep(gap_s)
            try:
                live_backend.send(live_target, frame)
            except TransportError as exc:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_TRANSPORT_ERROR,
                    errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
                ) from exc

    sub = args.command.removeprefix("fuzz ")
    source = f"fuzz.{sub}"
    events: list[dict[str, Any]] = [
        {
            "event_type": "alert",
            "source": source,
            "timestamp": 0.0,
            "payload": {
                "level": "warning",
                "code": "ACTIVE_TRANSMIT",
                "message": (
                    "Active fuzz transmission planned"
                    if not dry_run
                    else "Dry-run fuzz plan; no transport opened"
                ),
                "run_id": run_id,
                "dry_run": dry_run,
            },
        }
    ]
    for frame in frames:
        events.append(
            {
                "event_type": "frame",
                "source": source,
                "timestamp": frame.timestamp,
                "payload": {
                    "frame": {**frame.to_payload(), "dry_run": dry_run},
                    "run_id": run_id,
                    "dry_run": dry_run,
                },
            }
        )

    data: dict[str, Any] = {
        "mode": "dry_run" if dry_run else "active",
        "run_id": run_id,
        "frame_count": len(frames),
        "strategy": getattr(args, "strategy", None),
        "rate_hz": rate,
        "seed": getattr(args, "seed", None),
        "dry_run": dry_run,
        "target": target,
        "status": "implemented",
        "implementation": "fuzzing engine + active-transmit safety gate",
    }
    if args.command == "fuzz signal":
        data["signal_mode"] = args.mode
        data["dbc"] = args.dbc
        data["message"] = args.message
        data["signal"] = args.signal
    if args.command == "fuzz spn":
        from canarchy.j1939_metadata import spn_lookup

        data["spn_mode"] = args.mode
        data["spn"] = args.spn
        spn_meta = spn_lookup(args.spn) or {}
        data["pgn"] = int(spn_meta["pgn"]) if "pgn" in spn_meta else args.pgn
    warnings: list[str] = []
    if dry_run:
        warnings.append(
            f"ACTIVE_TRANSMIT_DRY_RUN: {len(frames)} frames planned; no transport opened."
        )
    return data, events, warnings


def _fuzz_guided_initial_seeds(args: argparse.Namespace) -> list[bytes]:
    from canarchy.fuzz_guided import load_corpus

    seeds: list[bytes] = []
    if getattr(args, "corpus", None):
        seeds.extend(load_corpus(args.corpus))
    seed_data = getattr(args, "seed_data", None)
    if seed_data:
        try:
            seeds.append(bytes.fromhex(seed_data))
        except ValueError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="FUZZ_GUIDED_INVALID_SEED",
                        message=f"--seed-data {seed_data!r} is not valid hex.",
                        hint="Pass an even-length hex string, e.g. 0011223344556677.",
                    )
                ],
            ) from exc
    return seeds or [bytes(8)]


def fuzz_guided_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.fuzz_feedback import SIGNAL_CATEGORIES, ResponseObservation
    from canarchy.fuzz_guided import run_guided_fuzz, save_corpus

    rate = getattr(args, "rate", None)
    _validate_fuzz_rate(rate, args.command)

    signal_tokens = [token.strip() for token in str(args.signals).split(",") if token.strip()]
    unknown = [token for token in signal_tokens if token not in SIGNAL_CATEGORIES]
    if unknown or not signal_tokens:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="FUZZ_GUIDED_INVALID_SIGNALS",
                    message=f"Unknown feedback signal(s): {', '.join(unknown) or '(none given)'}.",
                    hint=f"Choose from: {', '.join(SIGNAL_CATEGORIES)}.",
                )
            ],
        )
    signals = tuple(signal_tokens)

    if args.max_corpus < 1:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="FUZZ_GUIDED_INVALID_MAX_CORPUS",
                    message=f"--max-corpus must be at least 1; got {args.max_corpus}.",
                    hint="Pass a positive --max-corpus (default 64).",
                )
            ],
        )

    arbitration_id = _parse_can_id(
        args.arbitration_id, command=args.command, name="--id", code="FUZZ_GUIDED_INVALID_ID"
    )
    extended = _resolve_can_frame_extended(
        arbitration_id,
        bool(getattr(args, "extended", False)),
        command=args.command,
        name="--id",
        code="FUZZ_GUIDED_INVALID_ID",
    )
    # Classic CAN frames carry at most 8 payload bytes; clamp seeds/mutations.
    max_payload = 8
    seeds = [seed[:max_payload] for seed in _fuzz_guided_initial_seeds(args)]
    dry_run = bool(getattr(args, "dry_run", False))

    base = {
        "interface": args.interface,
        "arbitration_id": arbitration_id,
        "extended": extended,
        "signals": list(signals),
        "max_iterations": args.max_iterations,
        "max_seconds": args.max_seconds,
        "max_corpus": args.max_corpus,
        "rate_hz": rate,
        "seed": args.seed,
        "corpus": getattr(args, "corpus", None),
        "initial_seed_count": len(seeds),
    }

    if dry_run:
        from canarchy.fuzz_guided import default_mutator

        rng = random.Random(args.seed)
        planned = [
            default_mutator(seeds[0], rng, seeds)[:max_payload].hex()
            for _ in range(min(3, args.max_iterations))
        ]
        data = {**base, "mode": "dry_run", "planned_mutations": planned}
        return (
            data,
            [],
            [
                f"ACTIVE_TRANSMIT_DRY_RUN: guided campaign planned ({len(seeds)} seed(s), "
                f"up to {args.max_iterations} iterations); no transport opened."
            ],
        )

    enforce_active_transmit_safety(args)

    transport = LocalTransport()
    gap_s = 1.0 / rate if rate and rate > 0 else 0.0

    def responder(payload: bytes) -> ResponseObservation:
        frame = CanFrame(arbitration_id=arbitration_id, data=payload, is_extended_id=extended)
        started = time.monotonic()
        try:
            # A single send+receive transaction keeps the receive path active
            # before the probe is transmitted, so a fast response is not missed
            # and recorded as false silence.
            frames = transport.transaction(args.interface, frame)
        except TransportError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_TRANSPORT_ERROR,
                errors=[
                    ErrorDetail(
                        code="FUZZ_GUIDED_TRANSPORT_FAILED", message=str(exc), hint=exc.hint
                    )
                ],
            ) from exc
        elapsed = time.monotonic() - started
        return ResponseObservation(frames=tuple(frames), elapsed=elapsed, silent=not frames)

    result = run_guided_fuzz(
        seeds,
        responder,
        signals=signals,
        max_iterations=args.max_iterations,
        max_seconds=args.max_seconds,
        max_corpus=args.max_corpus,
        max_payload=max_payload,
        rng_seed=args.seed,
        pace_seconds=gap_s,
    )

    if getattr(args, "corpus", None):
        save_corpus(args.corpus, result.seeds)

    events = [finding.to_payload() for finding in result.findings]
    data = {
        **base,
        "mode": "active",
        "iterations": result.iterations,
        "new_behaviour_count": result.new_behaviour_count,
        "corpus_size": result.corpus_size,
        "unique_markers": result.unique_markers,
        "stop_reason": result.stop_reason,
        "findings": events,
    }
    return data, events, []


def _parse_host_port(target: str, command: str) -> tuple[str, int]:
    host, _, port_text = target.rpartition(":")
    if not host or not port_text:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="CANNELLONI_INVALID_TARGET",
                    message=f"Target {target!r} is not in <host>:<port> form.",
                    hint="Pass the endpoint as host:port, e.g. 127.0.0.1:20000.",
                )
            ],
        )
    try:
        port = int(port_text)
    except ValueError as exc:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="CANNELLONI_INVALID_TARGET",
                    message=f"Target port {port_text!r} is not an integer.",
                    hint="Pass the endpoint as host:port, e.g. 127.0.0.1:20000.",
                )
            ],
        ) from exc
    if not 1 <= port <= 65535:
        raise CommandError(
            command=command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="CANNELLONI_INVALID_TARGET",
                    message=f"Target port {port} is outside 1..65535.",
                    hint="Pass a port between 1 and 65535.",
                )
            ],
        )
    return host, port


def cannelloni_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    import socket

    from canarchy.cannelloni import (
        DEFAULT_MTU,
        CannelloniError,
        encode_packets,
        frames_from_bytes,
    )

    if args.command == "cannelloni decode":
        try:
            payload = Path(args.file).read_bytes()
        except OSError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_TRANSPORT_ERROR,
                errors=[
                    ErrorDetail(
                        code="CANNELLONI_FILE_UNREADABLE",
                        message=f"Could not read cannelloni payload file: {exc}.",
                        hint="Pass a path to a raw cannelloni datagram payload.",
                    )
                ],
            ) from exc
        try:
            frames = frames_from_bytes(payload)
        except CannelloniError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_TRANSPORT_ERROR,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ) from exc
        events = serialize_events(
            [FrameEvent(frame=frame, source="cannelloni.decode").to_event() for frame in frames]
        )
        warnings = [] if frames else ["No CAN frames were decoded from the cannelloni payload."]
        return (
            {
                "mode": "passive",
                "file": args.file,
                "frame_count": len(frames),
                "events": events,
            },
            events,
            warnings,
        )

    # cannelloni send
    host, port = _parse_host_port(args.target, args.command)
    transport = LocalTransport()
    frames = transport.frames_from_file(
        args.file,
        offset=getattr(args, "offset", 0) or 0,
        max_frames=getattr(args, "max_frames", None),
        seconds=getattr(args, "seconds", None),
    )
    # mtu <= 0 disables the byte cap (frame-count chunking only).
    mtu = getattr(args, "mtu", DEFAULT_MTU)
    max_bytes = mtu if mtu and mtu > 0 else None
    try:
        datagrams = encode_packets(
            frames, seq_no=args.seq_no, max_count=args.max_count, max_bytes=max_bytes
        )
    except CannelloniError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
        ) from exc

    dry_run = getattr(args, "dry_run", False)
    data: dict[str, Any] = {
        "target": args.target,
        "host": host,
        "port": port,
        "file": args.file,
        "frame_count": len(frames),
        "datagram_count": len(datagrams),
        "max_count": args.max_count,
        "mtu": mtu,
        "seq_no": args.seq_no,
    }
    if dry_run:
        data["mode"] = "dry_run"
        data["datagrams"] = [datagram.hex() for datagram in datagrams]
        return (
            data,
            [],
            [
                f"ACTIVE_TRANSMIT_DRY_RUN: {len(datagrams)} datagram(s) planned for "
                f"{args.target}; no socket opened."
            ],
        )

    enforce_active_transmit_safety(args)
    gap = 1.0 / args.rate if args.rate and args.rate > 0 else 0.0
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for index, datagram in enumerate(datagrams):
            if index > 0 and gap > 0:
                time.sleep(gap)
            udp.sendto(datagram, (host, port))
    except OSError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_TRANSPORT_ERROR,
            errors=[
                ErrorDetail(
                    code="CANNELLONI_SEND_FAILED",
                    message=f"Could not send cannelloni datagrams to {args.target}: {exc}.",
                    hint="Confirm the endpoint host/port and that UDP egress is permitted.",
                )
            ],
        ) from exc
    finally:
        udp.close()
    data["mode"] = "active"
    return (data, [], [])


def replay_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
    frames = transport.frames_from_file(args.file)
    plan = build_replay_plan(frames, rate=args.rate)

    interface = getattr(args, "interface", None)
    dry_run = getattr(args, "dry_run", False)
    live_mode = interface is not None and not dry_run

    if live_mode:
        from canarchy.transport import TransportError

        enforce_active_transmit_safety(args)
        last_timestamp: float | None = None
        for i, frame in enumerate(frames):
            if (
                i > 0
                and last_timestamp is not None
                and frame.timestamp is not None
                and frame.timestamp > last_timestamp
            ):
                delay = (frame.timestamp - last_timestamp) / args.rate
                if delay > 0:
                    time.sleep(min(delay, 1.0))
            last_timestamp = frame.timestamp if frame.timestamp is not None else last_timestamp
            try:
                transport.send(interface, frame)
            except TransportError as exc:
                raise CommandError(
                    command=args.command,
                    exit_code=EXIT_TRANSPORT_ERROR,
                    errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
                ) from exc

    data: dict[str, Any] = {
        "duration": plan.duration,
        "file": args.file,
        "frame_count": plan.frame_count,
        "rate": plan.rate,
    }
    if interface is not None:
        data["interface"] = interface
        data["mode"] = "dry_run" if dry_run else "active"
    else:
        data["mode"] = "active"

    warnings: list[str] = []
    if dry_run and interface is not None:
        warnings.append(
            f"ACTIVE_TRANSMIT_DRY_RUN: {plan.frame_count} frames planned; no transport opened."
        )
    return data, plan.events, warnings


def sequence_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.sequence import SequenceError, encode_sequence, load_sequence

    try:
        seq = load_sequence(args.file)
    except SequenceError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="SEQUENCE_LOAD_ERROR",
                    message=str(exc),
                    hint="Ensure the file exists, is valid YAML or JSON, and follows the sequence schema.",
                )
            ],
        ) from exc

    try:
        encoded_steps = encode_sequence(seq)
    except SequenceError as exc:
        raise CommandError(
            command=args.command,
            exit_code=EXIT_USER_ERROR,
            errors=[
                ErrorDetail(
                    code="SEQUENCE_ENCODE_ERROR",
                    message=str(exc),
                    hint="Check that the DBC file is accessible and each frame id matches a message in the DBC.",
                )
            ],
        ) from exc

    interface = getattr(args, "interface", None)
    dry_run = getattr(args, "dry_run", False)
    rate = getattr(args, "rate", 1.0)
    loop = getattr(args, "loop", False)
    live_mode = interface is not None and not dry_run

    if live_mode:
        enforce_active_transmit_safety(args)

    events: list[dict[str, Any]] = [
        {
            "event_type": "sequence_step",
            "source": "sequence.replay",
            "timestamp": None,
            "payload": step,
        }
        for step in encoded_steps
    ]

    if live_mode:
        from canarchy.models import CanFrame

        def _transmit_once() -> None:
            for step in encoded_steps:
                effective_delay_s = step["delay_ms"] / rate / 1000.0
                if effective_delay_s > 0:
                    time.sleep(effective_delay_s)
                for frame_data in step["frames"]:
                    frame = CanFrame(
                        arbitration_id=frame_data["frame_id"],
                        data=bytes.fromhex(frame_data["data"]),
                        is_extended_id=frame_data["is_extended_id"],
                        interface=interface,
                        timestamp=0.0,
                    )
                    try:
                        LocalTransport().send(interface, frame)
                    except TransportError as exc:
                        raise CommandError(
                            command=args.command,
                            exit_code=EXIT_TRANSPORT_ERROR,
                            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
                        ) from exc

        if loop:
            try:
                while True:
                    _transmit_once()
            except KeyboardInterrupt:
                pass
        else:
            _transmit_once()

    total_frames = sum(s["frame_count"] for s in encoded_steps)
    data: dict[str, Any] = {
        "file": args.file,
        "step_count": len(encoded_steps),
        "frame_count": total_frames,
        "rate": rate,
        "loop": loop,
    }
    if interface is not None:
        data["interface"] = interface
        data["mode"] = "dry_run" if dry_run else "active"
    else:
        data["mode"] = "plan"

    warnings: list[str] = []
    if dry_run:
        warnings.append(
            f"ACTIVE_TRANSMIT_DRY_RUN: {total_frames} frames planned; no transport opened."
        )
    return data, events, warnings


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


def _build_match_catalog(
    provider_name: str,
    make_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Build a catalog of {name, source_ref, message_ids} from cached DBC files.

    Only entries with a cached DBC file on disk are included — no network calls.
    """
    from pathlib import Path as _Path
    import cantools as _cantools
    from canarchy.dbc_cache import load_manifest, cached_file_path
    from canarchy.dbc_opendbc import _infer_brand

    manifest = load_manifest(provider_name)
    if manifest is None:
        return []

    commit = manifest.get("commit", "")
    catalog_entries: list[dict[str, str]] = manifest.get("dbcs", [])

    result: list[dict[str, Any]] = []
    for entry in catalog_entries:
        name = entry["name"]

        if make_filter:
            brand = _infer_brand(name)
            if brand != make_filter.lower():
                continue

        filename = _Path(entry["path"]).name
        cached = cached_file_path(provider_name, commit, filename)
        if not cached.exists():
            continue

        try:
            db = _cantools.database.load_file(str(cached))
            message_ids = [int(msg.frame_id) for msg in db.messages]
        except Exception:
            continue

        result.append(
            {
                "name": name,
                "source_ref": f"{provider_name}:{name}",
                "message_ids": message_ids,
                "metadata": {"brand": _infer_brand(name)},
            }
        )

    return result


def _confirm_llm_enrichment(args: argparse.Namespace, provider: str) -> None:
    """Gate the external `--llm` call behind an explicit operator confirmation."""
    if getattr(args, "yes", False):
        return
    if os.environ.get("CANARCHY_LLM_NONINTERACTIVE") == "1":
        return
    print(
        f"warning: `re suggest --llm {provider}` will send candidate metadata to the external "
        f"LLM provider `{provider}` (ids, bit ranges, observed ranges; no payload bytes).",
        file=sys.stderr,
    )
    print(
        f"confirm: type YES to call the external LLM provider `{provider}`: ",
        file=sys.stderr,
        end="",
        flush=True,
    )
    if sys.stdin.readline().strip() == "YES":
        return
    raise CommandError(
        command=args.command,
        exit_code=EXIT_USER_ERROR,
        errors=[
            ErrorDetail(
                code="LLM_CONFIRMATION_DECLINED",
                message="External LLM enrichment was not confirmed.",
                hint="Re-run with --yes (or set CANARCHY_LLM_NONINTERACTIVE=1) to authorise the call.",
            )
        ],
    )


def _re_suggest_payload(
    args: argparse.Namespace, processor: Any
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.re_suggest import suggest_names

    transport = LocalTransport()
    frames = transport.frames_from_file(args.file)
    result = processor.process(frames)
    candidates = list(result.candidates)[: max(args.limit, 0)]

    dbc_signals_by_id: dict[int, list[dict[str, Any]]] | None = None
    reference_dbc = getattr(args, "reference_dbc", None)
    if reference_dbc:
        from canarchy.dbc_runtime import load_runtime_database

        database = load_runtime_database(reference_dbc)
        dbc_signals_by_id = {
            int(message.frame_id): [
                {
                    "name": signal.name,
                    "length": int(signal.length),
                    "start": int(signal.start),
                    "byte_order": str(signal.byte_order),
                    "unit": signal.unit or None,
                }
                for signal in message.signals
            ]
            for message in database.messages
        }

    named = suggest_names(candidates, dbc_signals_by_id)
    warnings = list(result.warnings)
    data: dict[str, Any] = {
        "mode": "passive",
        "file": args.file,
        "reference_dbc": reference_dbc,
        "candidate_count": len(named),
        "candidates": named,
        "events": [],
    }

    provider = getattr(args, "llm", None)
    if provider:
        _confirm_llm_enrichment(args, provider)
        from canarchy.llm_suggest import LlmError, enrich_with_llm

        try:
            named = enrich_with_llm(provider, named, model=getattr(args, "llm_model", None))
        except LlmError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR
                if exc.code == "LLM_PROVIDER_UNSUPPORTED"
                else EXIT_TRANSPORT_ERROR,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ) from exc
        data["candidates"] = named
        data["candidate_count"] = len(named)
        data["external_enrichment"] = {
            "provider": provider,
            "confirmed": True,
            "note": (
                "Candidate metadata (arbitration ids, bit ranges, observed value ranges, and "
                f"heuristic names; no payload bytes) was sent to the external LLM provider "
                f"'{provider}'."
            ),
        }
        warnings.append(
            f"EXTERNAL_SERVICE_CALLED: signal-name suggestions were enriched via the external "
            f"LLM provider '{provider}'."
        )

    return (data, [], warnings)


def reverse_engineering_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.plugins import get_registry

    transport = LocalTransport()
    if args.command == "re suggest":
        processor = get_registry().get_processor("signal-analysis")
        if processor is None:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="PLUGIN_NOT_FOUND",
                        message="Built-in processor 'signal-analysis' is not registered.",
                        hint="Ensure the plugin registry has not been modified.",
                    )
                ],
            )
        return _re_suggest_payload(args, processor)
    if args.command == "re signals":
        frames = transport.frames_from_file(args.file)
        processor = get_registry().get_processor("signal-analysis")
        if processor is None:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="PLUGIN_NOT_FOUND",
                        message="Built-in processor 'signal-analysis' is not registered.",
                        hint="Ensure the plugin registry has not been modified.",
                    )
                ],
            )
        result = processor.process(frames)
        return (
            {
                "mode": "passive",
                "file": args.file,
                **result.metadata,
                "candidates": result.candidates,
            },
            [],
            result.warnings,
        )
    if args.command == "re counters":
        frames = transport.frames_from_file(args.file)
        processor = get_registry().get_processor("counter-candidates")
        if processor is None:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="PLUGIN_NOT_FOUND",
                        message="Built-in processor 'counter-candidates' is not registered.",
                        hint="Ensure the plugin registry has not been modified.",
                    )
                ],
            )
        result = processor.process(frames)
        return (
            {
                "mode": "passive",
                "file": args.file,
                **result.metadata,
                "candidates": result.candidates,
            },
            [],
            result.warnings,
        )
    if args.command == "re entropy":
        frames = transport.frames_from_file(args.file)
        processor = get_registry().get_processor("entropy-candidates")
        if processor is None:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="PLUGIN_NOT_FOUND",
                        message="Built-in processor 'entropy-candidates' is not registered.",
                        hint="Ensure the plugin registry has not been modified.",
                    )
                ],
            )
        result = processor.process(frames)
        return (
            {
                "mode": "passive",
                "file": args.file,
                **result.metadata,
                "candidates": result.candidates,
            },
            [],
            result.warnings,
        )
    if args.command in {"re match-dbc", "re shortlist-dbc"}:
        capture_file = args.capture
        provider_name = getattr(args, "provider", "opendbc")
        limit = getattr(args, "limit", 10)
        make_filter = getattr(args, "make", None)

        frames = transport.frames_from_file(capture_file)
        capture_id_counts: dict[int, int] = {}
        for frame in frames:
            if not frame.is_remote_frame and not frame.is_error_frame:
                capture_id_counts[frame.arbitration_id] = (
                    capture_id_counts.get(frame.arbitration_id, 0) + 1
                )

        catalog = _build_match_catalog(provider_name, make_filter=make_filter)
        candidates = score_dbc_candidates(capture_id_counts, catalog)[:limit]

        warnings: list[str] = []
        if not catalog:
            warnings.append(
                f"No cached DBC files found for provider '{provider_name}'. "
                "Run `canarchy dbc cache refresh --provider opendbc` then fetch DBCs with `canarchy dbc fetch`."
            )
        elif not candidates:
            filter_note = f" matching make '{make_filter}'" if make_filter else ""
            warnings.append(
                f"No candidate DBCs{filter_note} scored above zero against this capture."
            )

        data: dict[str, Any] = {
            "capture": capture_file,
            "provider": provider_name,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "events": [],
        }
        if make_filter:
            data["make"] = make_filter
        return (data, [], warnings)

    if args.command == "re correlate":
        frames = transport.frames_from_file(args.file)
        try:
            ref = load_reference_series(args.reference)
        except ReferenceSeriesError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        try:
            analysis = correlate_candidates(frames, ref)
        except ReferenceSeriesError as exc:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ) from exc
        corr_warnings: list[str] = []
        if analysis["candidate_count"] == 0:
            corr_warnings.append(
                "No fields met the minimum sample overlap threshold for correlation."
            )
        return (
            {
                "mode": "passive",
                "file": args.file,
                "reference": args.reference,
                "reference_name": ref.name,
                "analysis": "correlation",
                "candidate_count": analysis["candidate_count"],
                "candidates": analysis["candidates"],
                "implementation": "file-backed correlation analysis",
            },
            [],
            corr_warnings,
        )
    if args.command == "re anomalies":
        from canarchy.reverse_engineering import anomaly_candidates

        frames = transport.frames_from_file(
            args.file, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
        )
        baseline_frames = None
        if getattr(args, "baseline", None):
            baseline_frames = transport.frames_from_file(args.baseline)
        dbc_timing = None
        if getattr(args, "dbc", None):
            from canarchy.dbc import database_timing_map

            dbc_timing = database_timing_map(args.dbc)
        analysis = anomaly_candidates(
            frames,
            baseline=baseline_frames,
            z_threshold=args.z_threshold,
            cv_max=args.cv_max,
            dbc_timing=dbc_timing,
            min_samples=getattr(args, "min_samples", None),
        )
        anomaly_warnings: list[str] = []
        if analysis["candidate_count"] == 0:
            anomaly_warnings.append(
                "No timing or arbitration-id anomalies met the current threshold."
            )
        if analysis["mode"] == "self-consistency":
            anomaly_warnings.append(
                "No baseline supplied: anomalies are scored against this capture's own "
                "statistics. Diffing against a known-good capture via --baseline gives "
                "far more reliable results."
            )
        return (
            {
                "mode": analysis["mode"],
                "file": args.file,
                "baseline": getattr(args, "baseline", None),
                "dbc": getattr(args, "dbc", None),
                "z_threshold": analysis["z_threshold"],
                "cv_max": analysis["cv_max"],
                "min_samples": analysis["min_samples"],
                "timing_source": analysis["timing_source"],
                "analysis": "anomalies",
                "candidate_count": analysis["candidate_count"],
                "candidates": analysis["candidates"],
                "cyclic_ids": analysis["cyclic_ids"],
                "event_ids": analysis["event_ids"],
                "low_rate_ids": analysis["low_rate_ids"],
                "classifications": analysis["classifications"],
                "implementation": "file-backed anomaly detection",
            },
            [],
            anomaly_warnings,
        )
    if args.command == "re corpus":
        import glob as _glob

        from canarchy.corpus import corpus_analysis

        files: list[str] = list(getattr(args, "files", []) or [])
        if getattr(args, "corpus_glob", None):
            files += sorted(_glob.glob(args.corpus_glob))
        if not files:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="CORPUS_NO_FILES",
                        message="No capture files specified.",
                        hint="Pass capture file paths as positional arguments or use --corpus-glob.",
                    )
                ],
            )
        offset = getattr(args, "offset", 0) or 0
        max_frames = getattr(args, "max_frames", None)
        seconds = getattr(args, "seconds", None)
        if offset < 0:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_ANALYSIS_OFFSET",
                        message="Frame offset must be zero or greater.",
                        hint="Pass a non-negative integer to --offset.",
                    )
                ],
            )
        if max_frames is not None and max_frames < 1:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_MAX_FRAMES",
                        message="Maximum frame bound must be at least 1.",
                        hint="Pass a positive integer to --max-frames.",
                    )
                ],
            )
        if seconds is not None and seconds < 0:
            raise CommandError(
                command=args.command,
                exit_code=EXIT_USER_ERROR,
                errors=[
                    ErrorDetail(
                        code="INVALID_ANALYSIS_SECONDS",
                        message="Analysis time bound must be zero or greater.",
                        hint="Pass a non-negative value to --seconds.",
                    )
                ],
            )
        result = corpus_analysis(
            files,
            offset=offset,
            max_frames=max_frames,
            seconds=seconds,
        )
        corpus_warnings: list[str] = []
        if result["capture_count"] < 2:
            corpus_warnings.append(
                "Corpus analysis is most useful with 2+ captures; cycle-time drift will not be computed."
            )
        return (result, [], corpus_warnings)
    raise AssertionError(f"unsupported reverse-engineering command: {args.command}")


def build_events(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command in TRANSPORT_COMMANDS:
        _, events, _ = transport_payload(args)
        return events
    if args.command in DBC_COMMANDS:
        _, events, _ = dbc_payload(args)
        return events
    if args.command in DBC_PROVIDER_COMMANDS:
        _, events, _ = dbc_provider_payload(args)
        return events
    if args.command in SKILLS_COMMANDS:
        _, events, _ = skills_payload(args)
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
    if args.command in XCP_COMMANDS:
        _, events, _ = xcp_payload(args)
        return events
    if args.command in J1587_COMMANDS:
        _, events, _ = j1587_payload(args)
        return events
    if args.command in J2497_COMMANDS:
        _, events, _ = j2497_payload(args)
        return events
    if args.command in RE_COMMANDS:
        _, events, _ = reverse_engineering_payload(args)
        return events
    if args.command in CANNELLONI_COMMANDS:
        _, events, _ = cannelloni_payload(args)
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
    parse_reports = reset_parse_reports()
    warnings = (
        []
        if args.command in IMPLEMENTED_COMMANDS
        else ["Command implementation is not complete yet."]
    )
    data = {
        key: value
        for key, value in vars(args).items()
        if not key.endswith("_action")
        and key
        not in {
            "command",
            "command_name",
            "json",
            "jsonl",
            "text",
            "table",
            "ack_active",
            "send_args",
            "interface_source",
            "log_level",
            "quiet",
            "file_opt",
        }
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
    elif args.command in SEQUENCE_COMMANDS:
        seq_data, seq_events, seq_warnings = sequence_payload(args)
        data.update(seq_data)
        data["events"] = seq_events
        warnings.extend(seq_warnings)
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
    elif args.command in DBC_PROVIDER_COMMANDS:
        prov_data, prov_events, prov_warnings = dbc_provider_payload(args)
        data.update(prov_data)
        data["events"] = prov_events
        warnings.extend(prov_warnings)
    elif args.command in SKILLS_COMMANDS:
        skills_data, skills_events, skills_warnings = skills_payload(args)
        data.update(skills_data)
        data["events"] = skills_events
        warnings.extend(skills_warnings)
    elif args.command in PLUGINS_COMMANDS:
        plugins_data, plugins_events, plugins_warnings = plugins_payload(args)
        data.update(plugins_data)
        data["events"] = plugins_events
        warnings.extend(plugins_warnings)
    elif args.command in DATASETS_COMMANDS:
        datasets_data, datasets_events, datasets_warnings = datasets_payload(args)
        data.update(datasets_data)
        data["events"] = datasets_events
        warnings.extend(datasets_warnings)
    elif args.command in UDS_COMMANDS:
        uds_data, uds_events, uds_warnings = uds_payload(args)
        data.update(uds_data)
        data["events"] = uds_events
        warnings.extend(uds_warnings)
    elif args.command in XCP_COMMANDS:
        xcp_data, xcp_events, xcp_warnings = xcp_payload(args)
        data.update(xcp_data)
        data["events"] = xcp_events
        warnings.extend(xcp_warnings)
    elif args.command in J1587_COMMANDS:
        j1587_data, j1587_events, j1587_warnings = j1587_payload(args)
        data.update(j1587_data)
        data["events"] = j1587_events
        warnings.extend(j1587_warnings)
    elif args.command in J2497_COMMANDS:
        j2497_data, j2497_events, j2497_warnings = j2497_payload(args)
        data.update(j2497_data)
        data["events"] = j2497_events
        warnings.extend(j2497_warnings)
    elif args.command in RE_COMMANDS:
        re_data, re_events, re_warnings = reverse_engineering_payload(args)
        data.update(re_data)
        data["events"] = re_events
        warnings.extend(re_warnings)
    elif args.command in CANNELLONI_COMMANDS:
        can_data, can_events, can_warnings = cannelloni_payload(args)
        data.update(can_data)
        data["events"] = can_events
        warnings.extend(can_warnings)
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
    elif args.command == "plot":
        plot_data, plot_events, plot_warnings = plot_payload(args)
        data.update(plot_data)
        data["events"] = plot_events
        warnings.extend(plot_warnings)
    elif args.command in J1939_COMMANDS:
        protocol_data, protocol_events, protocol_warnings = j1939_payload(args)
        data.update(protocol_data)
        data["events"] = protocol_events
        warnings.extend(protocol_warnings)
    elif args.command in CONFIG_COMMANDS:
        data.update(config_show_payload())
    elif args.command in DOCTOR_COMMANDS:
        data.update(doctor_payload())
    elif args.command in FUZZ_COMMANDS:
        fuzz_data, fuzz_events, fuzz_warnings = fuzz_payload(args)
        data.update(fuzz_data)
        data["events"] = fuzz_events
        warnings.extend(fuzz_warnings)
    elif args.command in FUZZ_GUIDED_COMMANDS:
        guided_data, guided_events, guided_warnings = fuzz_guided_payload(args)
        data.update(guided_data)
        data["events"] = guided_events
        warnings.extend(guided_warnings)
    else:
        data["events"] = build_events(args)
    if args.command not in IMPLEMENTED_COMMANDS:
        data["status"] = "planned"
        data["implementation"] = "command surface scaffold"
    warnings.extend(candump_parse_warnings(parse_reports))
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

    if result.command == "j1939 tp sessions":
        lines.append(f"file: {result.data['file']}")
        if "pgn_filter" in result.data:
            lines.append(f"pgn_filter: {result.data['pgn_filter']}")
        if "sa_filter" in result.data:
            lines.append("sa_filter: " + ",".join(f"0x{sa:02X}" for sa in result.data["sa_filter"]))
        lines.append("sessions:")
        sessions = result.data.get("sessions", [])
        if not sessions:
            lines.append("- no transport sessions")
            return lines
        for session in sessions:
            destination = session["destination_address"]
            destination_text = f"0x{destination:02X}" if destination is not None else "broadcast"
            decoded_text = session.get("decoded_text")
            decoded_suffix = f" text={decoded_text}" if decoded_text else ""
            label = session.get("payload_label")
            label_suffix = f" label={label}" if label else ""
            hash_val = session.get("payload_hash")
            hash_suffix = f" hash={hash_val[:12]}..." if hash_val else ""
            lines.append(
                "- "
                f"type={session['session_type']} "
                f"pgn={session['transfer_pgn']} "
                f"sa=0x{session['source_address']:02X} "
                f"da={destination_text} "
                f"bytes={session['total_bytes']} "
                f"packets={session['packet_count']}/{session['total_packets']} "
                f"complete={session['complete']}"
                f"{label_suffix}"
                f"{decoded_suffix}"
                f"{hash_suffix}"
            )
        return lines

    if result.command == "j1939 tp compare":
        lines.append(f"file: {result.data['file']}")
        sa_hex = " ".join(f"0x{sa:02X}" for sa in result.data.get("source_addresses", []))
        lines.append(f"source_addresses: {sa_hex}")
        if result.data.get("pgn_filter") is not None:
            lines.append(f"pgn_filter: {result.data['pgn_filter']}")
        lines.append(f"groups: {result.data['group_count']}")
        groups = result.data.get("groups", [])
        if not groups:
            lines.append("- no sessions found for selected source addresses")
            return lines
        for group in groups:
            identical_flag = " [identical]" if group["payloads_identical"] else ""
            repeated = group.get("repeated_sources", [])
            repeated_suffix = (
                " repeated=" + ",".join(f"0x{sa:02X}" for sa in repeated) if repeated else ""
            )
            lines.append(
                f"pgn={group['transfer_pgn']} "
                f"sessions={group['session_count']} "
                f"unique_payloads={group['unique_payload_count']} "
                f"spread={group['timing_spread_seconds']}s"
                f"{identical_flag}"
                f"{repeated_suffix}"
            )
            for s in group["sessions"]:
                hash_val = s.get("payload_hash")
                hash_text = hash_val[:12] + "..." if hash_val else "none"
                lines.append(
                    f"  sa=0x{s['source_address']:02X} "
                    f"bytes={s['total_bytes']} "
                    f"complete={s['complete']} "
                    f"hash={hash_text}"
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
            dtc_text = (
                ",".join(f"spn={dtc['spn']}/fmi={dtc['fmi']}" for dtc in message["dtcs"]) or "none"
            )
            sa = message["source_address"]
            sa_name = source_address_lookup(sa)
            sa_label = f" [{sa_name}]" if sa_name else ""
            lines.append(
                "- "
                f"sa=0x{sa:02X}{sa_label} "
                f"transport={message['transport']} "
                f"dtcs={message['active_dtc_count']} "
                f"mil={message['lamp_status']['mil']} "
                f"amber={message['lamp_status']['amber_warning']} "
                f"codes={dtc_text}"
            )
        return lines

    if result.command == "j1939 faults":
        lines.append(f"file: {result.data['file']}")
        lines.append(
            f"sources: {result.data['source_count']}  total_faults: {result.data['total_fault_count']}"
        )
        ecus = result.data.get("ecus", [])
        if not ecus:
            lines.append("- no dm1 fault activity")
            return lines
        for ecu in ecus:
            sa = ecu["source_address"]
            sa_name = ecu.get("source_address_name")
            sa_label = f" [{sa_name}]" if sa_name else ""
            lamp = ecu["lamp_summary"]
            lines.append(
                f"sa=0x{sa:02X}{sa_label} "
                f"messages={ecu['message_count']} "
                f"faults={ecu['fault_count']} "
                f"mil={lamp['mil']} "
                f"amber={lamp['amber_warning']}"
            )
            for fault in ecu["faults"]:
                name = fault.get("name") or "unknown"
                suspicious_flag = " [suspicious]" if fault.get("suspicious") else ""
                lines.append(
                    f"  spn={fault['spn']} fmi={fault['fmi']} "
                    f"name={name} "
                    f"occurrences={fault['occurrences']}{suspicious_flag}"
                )
        return lines

    if result.command == "j1939 summary":
        lines.append(f"file: {result.data['file']}")
        lines.append(f"total_frames: {result.data['total_frames']}")
        lines.append(f"interfaces: {', '.join(result.data['interfaces']) or 'none'}")
        lines.append(f"unique_arbitration_ids: {result.data['unique_arbitration_ids']}")
        lines.append(f"j1939_frames: {result.data['j1939_frame_count']}")
        lines.append(
            f"timestamps: {result.data['first_timestamp']}..{result.data['last_timestamp']}"
        )
        lines.append(
            f"dm1: present={result.data['dm1']['present']} messages={result.data['dm1']['message_count']} active_dtcs={result.data['dm1']['active_dtc_count']}"
        )
        lines.append(
            f"tp: sessions={result.data['tp']['session_count']} complete={result.data['tp']['complete_session_count']}"
        )
        lines.append("top_pgns:")
        top_pgns = result.data.get("top_pgns", [])
        if not top_pgns:
            lines.append("- no j1939 pgn activity")
        else:
            for entry in top_pgns:
                pgn = entry["pgn"]
                pgn_meta = pgn_lookup(pgn)
                pgn_label = f" [{pgn_meta['label']}]" if pgn_meta else ""
                lines.append(f"- pgn={pgn}{pgn_label} frames={entry['frame_count']}")
        lines.append("top_source_addresses:")
        top_sources = result.data.get("top_source_addresses", [])
        if not top_sources:
            lines.append("- no j1939 source-address activity")
        else:
            for entry in top_sources:
                sa = entry["source_address"]
                sa_name = source_address_lookup(sa)
                sa_label = f" [{sa_name}]" if sa_name else ""
                lines.append(f"- sa=0x{sa:02X}{sa_label} frames={entry['frame_count']}")
        lines.append("printable_identifiers:")
        printable_identifiers = result.data.get("tp", {}).get("printable_identifiers", [])
        if not printable_identifiers:
            lines.append("- none")
        else:
            for entry in printable_identifiers:
                destination = entry["destination_address"]
                destination_text = (
                    f"0x{destination:02X}" if destination is not None else "broadcast"
                )
                lines.append(
                    "- "
                    f"text={entry['text']} "
                    f"pgn={entry['transfer_pgn']} "
                    f"sa=0x{entry['source_address']:02X} "
                    f"da={destination_text}"
                )
        return lines

    if result.command == "j1939 inventory":
        lines.append(f"file: {result.data['file']}")
        lines.append(f"sources: {result.data['source_count']}")
        vehicle_identifiers = result.data.get("vehicle_identifications", [])
        if vehicle_identifiers:
            lines.append(
                "vehicle_identifications: "
                + ", ".join(entry["text"] for entry in vehicle_identifiers)
            )
        else:
            lines.append("vehicle_identifications: none")
        lines.append("nodes:")
        nodes = result.data.get("nodes", [])
        if not nodes:
            lines.append("- no j1939 inventory nodes")
            return lines
        for node in nodes:
            source_address = node["source_address"]
            source_name = node.get("source_address_name")
            source_label = f" [{source_name}]" if source_name else ""
            component_text = (
                ",".join(entry["text"] for entry in node.get("component_identifications", []))
                or "none"
            )
            vehicle_text = (
                ",".join(entry["text"] for entry in node.get("vehicle_identifications", []))
                or "none"
            )
            top_pgns = (
                ",".join(
                    f"{entry['pgn']}" + (f"[{entry['label']}]" if entry.get("label") else "")
                    for entry in node.get("top_pgns", [])
                )
                or "none"
            )
            lines.append(
                "- "
                f"sa=0x{source_address:02X}{source_label} "
                f"frames={node['frame_count']} "
                f"dm1_present={node['dm1']['present']} "
                f"component_ids={component_text} "
                f"vehicle_ids={vehicle_text} "
                f"top_pgns={top_pgns}"
            )
        return lines

    if result.command == "j1939 map":
        lines.append(f"file: {result.data['file']}")
        lines.append(
            f"nodes: {result.data['node_count']} "
            f"edges: {result.data['edge_count']} "
            f"address_claims: {result.data['address_claim_count']}"
        )
        nodes = result.data.get("nodes", [])
        edges = result.data.get("edges", [])
        lines.append("nodes:")
        if not nodes:
            lines.append("- no j1939 nodes")
        for node in nodes:
            source_address = node["source_address"]
            source_name = node.get("source_address_name")
            source_label = f" [{source_name}]" if source_name else ""
            name = node.get("name")
            if name:
                name_text = (
                    f"mfr={name['manufacturer_code']} "
                    f"fn={name['function']} "
                    f"id={name['identity_number']}"
                )
            else:
                name_text = "none"
            component_text = ",".join(node.get("component_identifications", [])) or "none"
            vehicle_text = ",".join(node.get("vehicle_identifications", [])) or "none"
            lines.append(
                "- "
                f"sa=0x{source_address:02X}{source_label} "
                f"frames={node['frame_count']} "
                f"name={name_text} "
                f"component_ids={component_text} "
                f"vehicle_ids={vehicle_text}"
            )
        lines.append("edges:")
        if not edges:
            lines.append("- no j1939 edges")
        for edge in edges:
            destination = edge["destination_address"]
            destination_text = "broadcast" if edge["broadcast"] else f"0x{destination:02X}"
            pgn_label = f"[{edge['pgn_label']}]" if edge.get("pgn_label") else ""
            lines.append(
                "- "
                f"sa=0x{edge['source_address']:02X} "
                f"da={destination_text} "
                f"pgn={edge['pgn']}{pgn_label} "
                f"frames={edge['frame_count']}"
            )
        return lines

    if result.command == "j1939 compare":
        lines.append("files:")
        for file in result.data.get("files", []):
            lines.append(f"- {file}")
        lines.append("common_pgns:")
        common_pgns = result.data.get("common_pgns", [])
        if not common_pgns:
            lines.append("- none")
        else:
            for entry in common_pgns:
                label = f" [{entry['label']}]" if entry.get("label") else ""
                lines.append(f"- pgn={entry['pgn']}{label}")
        lines.append("unique_pgns:")
        for capture in result.data.get("unique_pgns", []):
            pgn_text = (
                ", ".join(
                    f"{entry['pgn']}" + (f"[{entry['label']}]" if entry.get("label") else "")
                    for entry in capture.get("pgns", [])
                )
                or "none"
            )
            lines.append(f"- {capture['file']}: {pgn_text}")
        lines.append("common_source_addresses:")
        common_sources = result.data.get("common_source_addresses", [])
        if not common_sources:
            lines.append("- none")
        else:
            for entry in common_sources:
                label = (
                    f" [{entry['source_address_name']}]" if entry.get("source_address_name") else ""
                )
                lines.append(f"- sa=0x{entry['source_address']:02X}{label}")
        lines.append("unique_source_addresses:")
        for capture in result.data.get("unique_source_addresses", []):
            sa_text = (
                ", ".join(
                    f"0x{entry['source_address']:02X}"
                    + (
                        f"[{entry['source_address_name']}]"
                        if entry.get("source_address_name")
                        else ""
                    )
                    for entry in capture.get("source_addresses", [])
                )
                or "none"
            )
            lines.append(f"- {capture['file']}: {sa_text}")
        lines.append("dm1_differences:")
        dm1_differences = result.data.get("dm1_differences", [])
        if not dm1_differences:
            lines.append("- none")
        else:
            for difference in dm1_differences:
                sa = difference["source_address"]
                label = (
                    f" [{difference['source_address_name']}]"
                    if difference.get("source_address_name")
                    else ""
                )
                lines.append(f"- sa=0x{sa:02X}{label}")
                for capture in difference.get("captures", []):
                    faults = (
                        ", ".join(
                            f"spn={fault['spn']}/fmi={fault['fmi']}"
                            for fault in capture.get("faults", [])
                        )
                        or "none"
                    )
                    lines.append(
                        f"  {capture['file']}: present={capture['present']} active_faults={capture['active_fault_count']} faults={faults}"
                    )
        lines.append("identifier_differences:")
        identifier_differences = result.data.get("identifier_differences", [])
        if not identifier_differences:
            lines.append("- none")
        else:
            for difference in identifier_differences:
                sa = difference["source_address"]
                label = (
                    f" [{difference['source_address_name']}]"
                    if difference.get("source_address_name")
                    else ""
                )
                lines.append(f"- sa=0x{sa:02X}{label} label={difference['payload_label']}")
                for capture in difference.get("captures", []):
                    values = ", ".join(capture.get("values", [])) or "none"
                    lines.append(f"  {capture['file']}: {values}")
        return lines

    lines.append("observations:")
    if not events:
        lines.append("- no j1939 observations")
        return lines

    describer = pretty_j1939_support.get_describer()
    for event in events:
        payload = event["payload"]
        frame = payload["frame"]
        pgn = payload["pgn"]
        sa = payload["source_address"]
        destination = payload["destination_address"]
        destination_text = f"0x{destination:02X}" if destination is not None else "broadcast"
        pgn_meta = pgn_lookup(pgn)
        pgn_label = f" [{pgn_meta['label']}]" if pgn_meta else ""
        sa_name = source_address_lookup(sa)
        sa_label = f" [{sa_name}]" if sa_name else ""
        lines.append(
            "- "
            f"pgn={pgn}{pgn_label} "
            f"sa=0x{sa:02X}{sa_label} "
            f"da={destination_text} "
            f"prio={payload['priority']} "
            f"id=0x{frame['arbitration_id']:08X} "
            f"data={frame['data']}"
        )
        decoded = pretty_j1939_support.describe_frame(
            describer, frame["arbitration_id"], frame["data"]
        )
        if decoded:
            for field_name, field_value in decoded.items():
                lines.append(f"  {field_name}: {field_value}")
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
    if result.data.get("protocol_decoder"):
        lines.append(f"protocol_decoder: {result.data['protocol_decoder']}")
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
            f"complete={payload.get('complete', True)} "
            f"req={payload['request_data']} "
            f"resp={payload['response_data']}"
        )
        if payload.get("negative_response_name"):
            code = payload.get("negative_response_code")
            code_text = f"0x{code:02X}" if isinstance(code, int) else "unknown"
            lines.append(f"  nrc={code_text} name={payload['negative_response_name']}")
        if payload.get("response_summary"):
            lines.append(f"  response_summary: {payload['response_summary']}")
    return lines


def format_xcp_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "xcp commands":
        lines.append(f"commands: {result.data.get('command_count', 0)}")
        lines.append("catalog:")
        commands = result.data.get("commands", [])
        if not commands:
            lines.append("- no xcp commands")
            return lines
        for command in commands:
            lines.append(
                f"- code=0x{command['code']:02X} name={command['name']} "
                f"category={command['category']}"
            )
        return lines

    lines.append(f"interface: {result.data.get('interface', 'unknown')}")
    if result.data.get("request_id") is not None:
        lines.append(f"request_id: 0x{result.data['request_id']:03X}")
    lines.append(f"response_id: 0x{result.data.get('response_id', 0):03X}")
    events = result.data.get("events", [])

    if result.command == "xcp read":
        lines.append(f"measurements: {result.data.get('measurement_count', 0)}")
        if not events:
            lines.append("- no xcp measurements")
            return lines
        for event in events:
            payload = event["payload"]
            lines.append(
                f"- pid=0x{payload['pid']:02X} "
                f"resp_id=0x{payload['response_id']:03X} "
                f"data={payload['data']}"
            )
        return lines

    if result.command == "xcp scan":
        lines.append(f"responders: {result.data.get('responder_count', 0)}")
    else:
        lines.append(f"transactions: {result.data.get('transaction_count', 0)}")
    lines.append("transactions:")
    if not events:
        lines.append("- no xcp transactions")
        return lines
    for event in events:
        payload = event["payload"]
        lines.append(
            "- "
            f"command=0x{payload['command']:02X} "
            f"name={payload['command_name']} "
            f"req_id=0x{payload['request_id']:03X} "
            f"resp_id=0x{payload['response_id']:03X} "
            f"positive={payload['positive']} "
            f"req={payload['request_data']} "
            f"resp={payload['response_data']}"
        )
        if payload.get("error_name"):
            code = payload.get("error_code")
            code_text = f"0x{code:02X}" if isinstance(code, int) else "unknown"
            lines.append(f"  error={code_text} name={payload['error_name']}")
        if payload.get("connect_info"):
            info = payload["connect_info"]
            resources = ",".join(info.get("resources", [])) or "none"
            lines.append(
                f"  connect: resources={resources} "
                f"max_cto={info.get('max_cto')} max_dto={info.get('max_dto')} "
                f"proto_layer={info.get('protocol_layer_version')}"
            )
    return lines


def format_j1587_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "j1587 pids":
        lines.append(f"pids: {result.data.get('pid_count', 0)}")
        lines.append("catalog:")
        pids = result.data.get("pids", [])
        if not pids:
            lines.append("- no j1587 pids")
            return lines
        for pid in pids:
            lines.append(
                f"- pid={pid['pid']} name={pid['name']} units={pid['units']} length={pid['length']}"
            )
        return lines

    lines.append(f"file: {result.data['file']}")
    lines.append(f"messages: {result.data.get('message_count', 0)}")
    lines.append(f"checksum_failures: {result.data.get('checksum_failures', 0)}")
    events = result.data.get("events", [])
    lines.append("parameters:")
    if not events:
        lines.append("- no j1587 parameters")
        return lines
    for event in events:
        payload = event["payload"]
        name = payload["name"] or "unknown"
        units_suffix = f" units={payload['units']}" if payload["units"] else ""
        checksum_suffix = "" if payload["checksum_valid"] else " checksum=invalid"
        lines.append(
            f"- mid={payload['mid']} pid={payload['pid']} name={name} "
            f"value={payload['value']}{units_suffix} raw={payload['raw']}{checksum_suffix}"
        )
    return lines


def format_j2497_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "j2497 mids":
        lines.append(f"mids: {result.data.get('mid_count', 0)}")
        lines.append("catalog:")
        mids = result.data.get("mids", [])
        if not mids:
            lines.append("- no j2497 mids")
            return lines
        for mid in mids:
            lines.append(f"- mid={mid['mid']} name={mid['name']}")
        return lines

    lines.append(f"file: {result.data['file']}")
    lines.append(f"frames: {result.data.get('frame_count', 0)}")
    lines.append(f"checksum_failures: {result.data.get('checksum_failures', 0)}")
    events = result.data.get("events", [])
    lines.append("frames:")
    if not events:
        lines.append("- no j2497 frames")
        return lines
    for event in events:
        payload = event["payload"]
        name = payload["name"] or "unknown"
        checksum_suffix = "" if payload["checksum_valid"] else " checksum=invalid"
        lines.append(f"- mid={payload['mid']} name={name} data={payload['data']}{checksum_suffix}")
    return lines


def format_fuzz_guided_table(result: CommandResult) -> list[str]:
    data = result.data
    lines = [f"command: {result.command}"]
    lines.append(f"interface: {data.get('interface', 'unknown')}")
    arb = data.get("arbitration_id")
    lines.append(f"id: 0x{arb:X}" if isinstance(arb, int) else "id: unknown")
    lines.append(f"signals: {','.join(data.get('signals', []))}")
    lines.append(f"mode: {data.get('mode')}")
    if data.get("mode") == "dry_run":
        lines.append(f"initial_seeds: {data.get('initial_seed_count', 0)}")
        for index, mutation in enumerate(data.get("planned_mutations", [])):
            lines.append(f"  planned[{index}]: {mutation}")
        return lines
    lines.append(f"iterations: {data.get('iterations', 0)}")
    lines.append(f"new_behaviours: {data.get('new_behaviour_count', 0)}")
    lines.append(f"corpus_size: {data.get('corpus_size', 0)}")
    lines.append(f"unique_markers: {data.get('unique_markers', 0)}")
    lines.append(f"stop_reason: {data.get('stop_reason')}")
    findings = data.get("findings", [])
    if findings:
        lines.append("findings:")
        for finding in findings[:25]:
            markers = ",".join(finding.get("new_markers", []))
            lines.append(
                f"  iter={finding.get('iteration')} gen={finding.get('generation')} "
                f"gain={finding.get('gain')} markers={markers}"
            )
    return lines


def format_re_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]

    if result.command == "re suggest":
        lines.append(f"file: {result.data.get('file')}")
        if result.data.get("reference_dbc"):
            lines.append(f"reference_dbc: {result.data['reference_dbc']}")
        if result.data.get("external_enrichment"):
            lines.append(f"llm_provider: {result.data['external_enrichment']['provider']}")
        lines.append(f"candidate_count: {result.data.get('candidate_count', 0)}")
        lines.append("suggestions:")
        candidates = result.data.get("candidates", [])
        if not candidates:
            lines.append("- no signal candidates")
            return lines
        for candidate in candidates:
            names = " | ".join(
                f"{s['name']}[{s['source']}:{s['confidence']}]"
                for s in candidate.get("suggestions", [])
            )
            lines.append(
                "- "
                f"id=0x{candidate['arbitration_id']:X} "
                f"start={candidate['start_bit']} "
                f"len={candidate['bit_length']} "
                f"=> {candidate.get('suggested_name')} ({candidate.get('suggested_source')})"
            )
            if names:
                lines.append(f"  candidates: {names}")
        return lines

    if result.command == "re corpus":
        data = result.data
        lines.append(f"captures: {data.get('capture_count', 0)}")
        lines.append(f"total_frames: {data.get('total_frames', 0)}")
        summary = data.get("summary", {})
        lines.append(f"unique_ids: {summary.get('unique_ids', 0)}")
        lines.append(f"stable_ids: {summary.get('stable_ids', 0)}")
        lines.append(f"drifting_ids: {summary.get('drifting_ids', 0)}")
        lines.append(f"new_ids: {summary.get('new_ids', 0)}")
        changes = data.get("id_set_changes", {})
        sometimes = changes.get("sometimes_present", [])
        only_one = changes.get("only_in_one", [])
        if sometimes or only_one:
            lines.append("id_set_changes:")
            for arb_id in sorted(sometimes):
                lines.append(f"  0x{arb_id:03X}  sometimes-present")
            for arb_id in sorted(only_one):
                lines.append(f"  0x{arb_id:03X}  only-in-one")
        return lines

    if result.command == "re correlate":
        lines.append(f"file: {result.data.get('file')}")
        lines.append(f"reference: {result.data.get('reference')}")
        if result.data.get("reference_name"):
            lines.append(f"reference_name: {result.data['reference_name']}")
        lines.append(f"candidate_count: {result.data.get('candidate_count', 0)}")
        lines.append("candidates:")
        candidates = result.data.get("candidates", [])
        if not candidates:
            lines.append("- no correlation candidates")
            return lines
        for candidate in candidates:
            lines.append(
                "- "
                f"id=0x{candidate['arbitration_id']:X} "
                f"start={candidate['start_bit']} "
                f"len={candidate['bit_length']} "
                f"pearson_r={candidate['pearson_r']} "
                f"spearman_r={candidate['spearman_r']} "
                f"samples={candidate['sample_count']} "
                f"lag_ms={candidate['lag_ms']}"
            )
        return lines

    if result.command == "re anomalies":
        lines.append(f"file: {result.data.get('file')}")
        if result.data.get("baseline"):
            lines.append(f"baseline: {result.data['baseline']}")
        if result.data.get("dbc"):
            lines.append(f"dbc: {result.data['dbc']}")
        lines.append(f"mode: {result.data.get('mode')}")
        lines.append(f"timing_source: {result.data.get('timing_source')}")
        event_ids = result.data.get("event_ids", [])
        if event_ids:
            lines.append(
                "event_ids (timing skipped): " + ", ".join(f"0x{arb_id:X}" for arb_id in event_ids)
            )
        lines.append(f"candidate_count: {result.data.get('candidate_count', 0)}")
        lines.append("anomalies:")
        candidates = result.data.get("candidates", [])
        if not candidates:
            lines.append("- no anomalies detected")
            return lines
        for candidate in candidates:
            lines.append(
                "- "
                f"id={candidate['arbitration_id_hex']} "
                f"kind={candidate['kind']} "
                f"score={candidate['score']} "
                f"z={candidate['z_score']} "
                f"samples={candidate['sample_count']} "
                f"ts={candidate['timestamp']} "
                f"why={candidate['rationale']}"
            )
        return lines

    if result.command in {"re match-dbc", "re shortlist-dbc"}:
        lines.append(f"capture: {result.data.get('capture')}")
        lines.append(f"provider: {result.data.get('provider')}")
        if result.command == "re shortlist-dbc":
            lines.append(f"make: {result.data.get('make')}")
        lines.append(f"candidate_count: {result.data.get('candidate_count', 0)}")
        lines.append("candidates:")
        candidates = result.data.get("candidates", [])
        if not candidates:
            lines.append("- no matching candidates")
            return lines
        for candidate in candidates:
            lines.append(
                "- "
                f"name={candidate['name']} "
                f"score={candidate['score']} "
                f"matched={candidate['matched_ids']}/{candidate['total_capture_ids']} "
                f"ref={candidate['source_ref']}"
            )
        return lines

    lines.append(f"file: {result.data.get('file')}")
    lines.append(f"analysis: {result.data.get('analysis')}")
    lines.append(f"candidate_count: {result.data.get('candidate_count', 0)}")
    lines.append("candidates:")
    candidates = result.data.get("candidates", [])
    if not candidates:
        if result.command == "re entropy":
            lines.append("- no entropy candidates")
        elif result.command == "re signals":
            lines.append("- no likely signals")
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
        if result.command == "re signals":
            lines.append(
                "- "
                f"id=0x{candidate['arbitration_id']:X} "
                f"start={candidate['start_bit']} "
                f"len={candidate['bit_length']} "
                f"score={candidate['score']} "
                f"change_rate={candidate['change_rate']} "
                f"samples={candidate['sample_count']} "
                f"range={candidate['observed_min']}..{candidate['observed_max']} "
                f"why={candidate['rationale']}"
            )
            continue
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


def format_dbc_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    db = result.data.get("database", {})
    if db:
        lines.append(f"path: {db.get('path', '')}")
        if result.data.get("signals_only") or result.command == "dbc signals":
            lines.append(f"signals: {result.data.get('signal_count', 0)}")
            for signal in result.data.get("signals", []):
                unit = f"  [{signal['unit']}]" if signal.get("unit") else ""
                lines.append(
                    f"  {signal['message_name']}.{signal['name']}"
                    f"  bit={signal['start_bit']}"
                    f"  len={signal['length']}"
                    f"  {signal.get('byte_order', '')}"
                    f"  scale={signal.get('scale')}"
                    f"  offset={signal.get('offset')}"
                    f"  {signal.get('minimum')}..{signal.get('maximum')}"
                    f"{unit}"
                )
            return lines
        lines.append(f"messages: {db.get('message_count', 0)}")
        lines.append(f"signals: {db.get('signal_count', 0)}")
    for message in result.data.get("messages", []):
        lines.append(
            f"  [{message.get('arbitration_id_hex', '')}] {message.get('name', '')} "
            f"({message.get('signal_count', 0)} signals, {message.get('length', 0)} bytes)"
        )
        for signal in message.get("signals", []):
            unit = f" [{signal['unit']}]" if signal.get("unit") else ""
            lines.append(
                f"    {signal['name']}: {signal.get('byte_order', '')} {signal.get('length', '')}bit{unit}"
            )
        if result.data.get("layout") or message.get("layout") is not None:
            if message.get("layout"):
                lines.append("    layout:")
                lines.extend(f"      {line}" for line in message["layout"].splitlines())
            if message.get("signal_tree"):
                lines.append("    signal_tree:")
                lines.extend(f"      {line}" for line in message["signal_tree"].splitlines())
            if message.get("signal_choices"):
                lines.append("    signal_choices:")
                lines.extend(f"      {line}" for line in message["signal_choices"].splitlines())
    return lines


def format_dbc_provider_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "dbc provider list":
        for p in result.data.get("providers", []):
            lines.append(f"  {p['name']}")
    elif result.command == "dbc search":
        lines.append(f"query: {result.data.get('query', '')}")
        lines.append(f"results: {result.data.get('count', 0)}")
        for item in result.data.get("results", []):
            brand = item.get("metadata", {}).get("brand", "")
            if result.data.get("verbose"):
                lines.append(f"  {item['source_ref']}")
                lines.append(f"    provider: {item.get('provider', '')}")
                if item.get("version"):
                    lines.append(f"    version:  {item['version'][:12]}")
                if brand:
                    lines.append(f"    brand:    {brand}")
            else:
                brand_text = f" ({brand})" if brand else ""
                lines.append(f"  {item['source_ref']}{brand_text}")
    elif result.command == "dbc fetch":
        lines.append(f"ref: {result.data.get('ref', '')}")
        lines.append(f"name: {result.data.get('name', '')}")
        lines.append(f"version: {result.data.get('version', '')}")
        lines.append(f"path: {result.data.get('local_path', '')}")
    elif result.command == "dbc cache list":
        for entry in result.data.get("entries", []):
            lines.append(
                f"  {entry['provider']}  commit={entry.get('commit', 'unknown')[:12]}  "
                f"dbcs={entry.get('dbc_count', 0)}"
            )
    elif result.command == "dbc cache prune":
        removed = result.data.get("removed", [])
        lines.append(f"removed: {len(removed)}")
        for path in removed:
            lines.append(f"  {path}")
    elif result.command == "dbc cache refresh":
        lines.append(f"provider: {result.data.get('provider', '')}")
        lines.append(f"dbc_count: {result.data.get('dbc_count', 0)}")
    return lines


def format_skills_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "skills provider list":
        for provider in result.data.get("providers", []):
            lines.append(f"  {provider['name']}")
    elif result.command == "skills search":
        lines.append(f"query: {result.data.get('query', '')}")
        lines.append(f"results: {result.data.get('count', 0)}")
        for item in result.data.get("results", []):
            tags = ",".join(item.get("metadata", {}).get("tags", []))
            tag_text = f" [{tags}]" if tags else ""
            lines.append(f"  {item['source_ref']} ({item.get('publisher', '')}){tag_text}")
    elif result.command == "skills fetch":
        lines.append(f"ref: {result.data.get('ref', '')}")
        lines.append(f"name: {result.data.get('name', '')}")
        lines.append(f"publisher: {result.data.get('publisher', '')}")
        lines.append(f"version: {result.data.get('version', '')}")
        lines.append(f"manifest: {result.data.get('local_manifest_path', '')}")
        lines.append(f"entry: {result.data.get('local_entry_path', '')}")
    elif result.command == "skills cache list":
        for entry in result.data.get("entries", []):
            lines.append(
                f"  {entry['provider']}  commit={entry.get('commit', 'unknown')[:12]}  skills={entry.get('skill_count', 0)}"
            )
    elif result.command == "skills cache refresh":
        lines.append(f"provider: {result.data.get('provider', '')}")
        lines.append(f"skill_count: {result.data.get('skill_count', 0)}")
    return lines


def format_plugins_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]
    if result.command == "plugins list":
        lines.append(f"plugins: {result.data.get('plugin_count', 0)}")
        for plugin in result.data.get("plugins", []):
            enabled = "enabled" if plugin.get("enabled", True) else "disabled"
            version = plugin.get("version") or "unknown"
            source = plugin.get("source_distribution") or "unknown"
            lines.append(
                f"  {plugin['name']}  kind={plugin['kind']}  version={version}  {enabled}  source={source}"
            )
        return lines

    if result.command == "plugins info":
        lines.append(f"name: {result.data.get('name', '')}")
        lines.append(f"enabled: {result.data.get('enabled', True)}")
        lines.append(f"matches: {result.data.get('match_count', 0)}")
        lines.append("metadata:")
        for plugin in result.data.get("plugins", []):
            lines.append(
                f"  kind={plugin['kind']} api_version={plugin['api_version']} "
                f"version={plugin.get('version') or 'unknown'} "
                f"source={plugin.get('source_distribution') or 'unknown'}"
            )
            if plugin.get("entry_point_group"):
                lines.append(f"    entry_point_group={plugin['entry_point_group']}")
        options = result.data.get("configured_options", {})
        lines.append(f"configured_options: {options if options else '{}'}")
        return lines

    lines.append(f"name: {result.data.get('name', '')}")
    lines.append(f"enabled: {result.data.get('enabled')}")
    lines.append(f"config_file: {result.data.get('config_file', '')}")
    return lines


def format_dataset_inspect(result: CommandResult) -> list[str]:
    """Format human-readable output for datasets inspect."""
    data = result.data
    lines = []
    ref = data.get("ref", "")
    is_replayable = data.get("is_replayable", False)
    is_index = data.get("is_index", False)

    # Title with type indicators
    type_labels = []
    if is_index:
        type_labels.append("INDEX")
    if is_replayable:
        type_labels.append("REPLAYABLE")
    type_str = f" [{', '.join(type_labels)}]" if type_labels else ""
    lines.append(f"Dataset: {ref}{type_str}")
    lines.append("")

    # Basic info
    lines.append("Basic information")
    lines.append(f"  Provider: {data.get('provider', '')}")
    lines.append(f"  Name: {data.get('name', '')}")
    lines.append(f"  Version: {data.get('version', '')}")
    lines.append(f"  Protocol: {data.get('protocol_family', '').upper()}")
    lines.append(f"  License: {data.get('license', '')}")
    lines.append(f"  Size: {data.get('size_description', '')}")
    lines.append(f"  Description: {data.get('description', '')}")
    lines.append("")

    # Format support
    lines.append("Format support")
    lines.append(f"  Source formats: {', '.join(data.get('formats', [])) or '-'}")
    lines.append(f"  Output formats: {', '.join(data.get('conversion_targets', [])) or '-'}")
    lines.append("")

    # Source URLs section
    lines.append("Source information")
    lines.append(f"  Source URL: {data.get('source_url', '')}")
    if is_replayable:
        metadata = data.get("metadata", {})
        replay = metadata.get("replay", {}) if isinstance(metadata, dict) else {}
        download_url = replay.get("download_url") if isinstance(replay, dict) else None
        default_file = replay.get("default_file") if isinstance(replay, dict) else None
        if download_url:
            lines.append(f"  Replay download URL: {download_url}")
        if default_file:
            lines.append(f"  Default replay file: {default_file}")
        if replay and isinstance(replay, dict) and "files" in replay:
            lines.append("  Replay files:")
            for f in replay["files"]:
                f_id = f.get("id", "")
                f_name = f.get("name", "")
                f_format = f.get("format", "")
                lines.append(f"    {f_id} ({f_format}): {f_name}")
    if is_index:
        lines.append("  Note: This is a curated index, not directly replayable.")
        lines.append(
            "  Use `canarchy datasets search <keyword>` to find specific datasets from this index."
        )
    if data.get("access_notes"):
        lines.append(f"  Access notes: {data['access_notes']}")
    lines.append("")

    return lines


def format_datasets_fetch(result: CommandResult) -> list[str]:
    """Format human-readable output for datasets fetch."""
    data = result.data
    lines = []
    ref = data.get("ref", "")
    is_index = data.get("is_index", False)

    type_str = " [INDEX]" if is_index else ""
    lines.append(f"Dataset: {ref}{type_str}")
    lines.append("")

    lines.append("Provenance")
    lines.append(f"  Ref: {ref}")
    lines.append(f"  Provider: {data.get('provider', '')}")
    lines.append(f"  Name: {data.get('name', '')}")
    lines.append(f"  Source URL: {data.get('source_url', '')}")
    lines.append(f"  Cache path: {data.get('cache_path', '')}")
    lines.append(f"  Cached: {'Yes' if data.get('is_cached') else 'No'}")
    lines.append("")

    lines.append("Next steps")
    instruction = (
        data.get("index_instructions") if is_index else data.get("download_instructions", "")
    )
    for part in (instruction or "").split("\n"):
        lines.append(f"  {part}" if part.strip() else "")
    lines.append("")

    return lines


def format_datasets_replay_dry_run(result: CommandResult) -> list[str]:
    """Format human-readable output for datasets replay --dry-run."""
    data = result.data
    lines = []
    ref = data.get("ref") or data.get("source", "")

    lines.append(f"Replay plan (dry run): {ref}")
    lines.append("")

    lines.append("Source")
    lines.append(f"  Ref: {ref}")
    source_type = data.get("source_type") or "dataset"
    lines.append(f"  Type: {source_type}")
    if data.get("download_url"):
        lines.append(f"  Download URL: {data['download_url']}")
    lines.append("")

    replay_file = data.get("replay_file") or data.get("default_replay_file", "")
    source_format = data.get("source_format", "")
    lines.append("Selected replay file")
    lines.append(f"  File: {replay_file}")
    if source_format:
        lines.append(f"  Format: {source_format}")
    lines.append("")

    lines.append("Limits")
    rate = data.get("rate")
    lines.append(f"  Rate: {rate} fps" if rate is not None else "  Rate: (default)")
    max_frames = data.get("max_frames")
    lines.append(
        f"  Max frames: {max_frames}" if max_frames is not None else "  Max frames: (none)"
    )
    max_seconds = data.get("max_seconds")
    lines.append(
        f"  Max seconds: {max_seconds}" if max_seconds is not None else "  Max seconds: (none)"
    )
    lines.append("")

    lines.append("Replay plan")
    lines.append(f"  Output format: {data.get('output_format', '')}")
    lines.append(f"  Would stream: {'yes' if data.get('would_stream') else 'no'}")
    lines.append("")

    return lines


def format_datasets_table(result: CommandResult) -> list[str]:
    if result.command == "datasets provider list":
        lines = ["Dataset providers"]
        for provider in result.data.get("providers", []):
            status = "registered" if provider.get("registered") else "unregistered"
            lines.append(f"  {provider['name']} ({status})")
        return lines

    if result.command != "datasets search":
        return [f"command: {result.command}"]

    query = result.data.get("query", "")
    count = result.data.get("count", 0)
    results = result.data.get("results", [])
    is_empty_query = not query
    title_query = "All datasets" if is_empty_query else f'"{query}"'
    title = (
        f"All datasets ({count})"
        if is_empty_query
        else f"Datasets matching {title_query} ({count})"
    )

    if result.data.get("verbose"):
        lines = [title, ""]
        for item in results:
            ref = f"{item['provider']}:{item['name']}"
            is_replayable = item.get("is_replayable", False)
            is_index = item.get("is_index", False)
            type_labels = []
            if is_index:
                type_labels.append("INDEX")
            if is_replayable:
                type_labels.append("REPLAYABLE")
            type_str = f" [{', '.join(type_labels)}]" if type_labels else ""
            lines.append(f"{ref}{type_str}")
            lines.append(f"  Protocol: {item.get('protocol_family', '').upper()}")
            lines.append(f"  Formats: {', '.join(item.get('formats', [])) or '-'}")
            lines.append(f"  Outputs: {', '.join(item.get('conversion_targets', [])) or '-'}")
            lines.append(f"  License: {item.get('license', '')}")
            lines.append(f"  Size: {item.get('size_description', '')}")
            lines.append(f"  Description: {item.get('description', '')}")
            lines.append(f"  Source: {item.get('source_url', '')}")
            if is_replayable and item.get("default_replay_file"):
                lines.append(f"  Default replay file: {item['default_replay_file']}")
            if is_index:
                lines.append("  Note: This is a curated index, not directly replayable.")
            if item.get("access_notes"):
                lines.append(f"  Access: {item['access_notes']}")
            lines.append("")
        lines.append("")
        lines.append("TYPE: INDEX=curated index, PLAY=replayable")
        lines.append("Use `canarchy datasets inspect <ref>` for full metadata.")
        return lines

    # Compact table output
    rows = []
    for item in results:
        is_replayable = item.get("is_replayable", False)
        is_index = item.get("is_index", False)
        if is_index:
            type_indicator = "INDEX"
        elif is_replayable:
            type_indicator = "PLAY"
        else:
            type_indicator = "-"
        rows.append(
            {
                "ref": f"{item['provider']}:{item['name']}",
                "protocol": item.get("protocol_family", "").upper(),
                "format": ",".join(item.get("formats", [])) or "-",
                "outputs": ",".join(item.get("conversion_targets", [])) or "-",
                "license": item.get("license", ""),
                "size": item.get("size_description", ""),
                "type": type_indicator,
            }
        )
    columns = [
        ("REF", "ref"),
        ("PROTOCOL", "protocol"),
        ("FORMAT", "format"),
        ("OUTPUTS", "outputs"),
        ("LICENSE", "license"),
        ("SIZE", "size"),
        ("TYPE", "type"),
    ]
    widths = {
        key: max([len(header), *(len(row[key]) for row in rows)] or [len(header)])
        for header, key in columns
    }
    lines = [title, ""]
    lines.append("  ".join(header.ljust(widths[key]) for header, key in columns))
    for row in rows:
        lines.append("  ".join(row[key].ljust(widths[key]) for _, key in columns))
    lines.append("")
    lines.append("TYPE: INDEX=curated index, PLAY=replayable")
    lines.append("Use `canarchy datasets inspect <ref>` for full metadata.")
    return lines


def emit_live_capture(args: argparse.Namespace, output_format: str) -> int:
    """Stream live capture frames until Ctrl+C, honouring *output_format*.

    All formats stream continuously rather than returning a fixed batch:

    * ``text`` / ``table`` / ``candump`` — candump-style text line per frame
    * ``json`` / ``jsonl`` — one ``json.dumps(event)`` line per frame
    """
    transport = LocalTransport()
    text_mode = output_format == "text"
    try:
        for event in transport.capture_stream_events(args.interface):
            if event.get("event_type") != "frame":
                continue
            if text_mode:
                frame = event["payload"]["frame"]
                interface = frame["interface"] or args.interface
                timestamp = event.get("timestamp")
                timestamp_text = (
                    f"({timestamp:0.6f})" if isinstance(timestamp, (int, float)) else "(0.000000)"
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
    return emit_live_capture(args, "text")


def emit_live_gateway(args: argparse.Namespace) -> int:
    transport = LocalTransport()
    enforce_active_transmit_safety(args)
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


def emit_dataset_stream(args: argparse.Namespace) -> int:
    from canarchy.dataset_convert import ConversionError, stream_file

    try:
        stream_file(
            args.file,
            source_format=args.source_format,
            output_format=args.output_format,
            destination=getattr(args, "output", None),
            chunk_size=getattr(args, "chunk_size", 1000),
            max_frames=getattr(args, "max_frames", None),
            provider_ref=getattr(args, "provider_ref", None),
        )
    except ConversionError as exc:
        result = error_result(
            args.command,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        )
        emit_result(result, "json")
        return EXIT_USER_ERROR
    return EXIT_OK


def emit_dataset_replay(args: argparse.Namespace) -> int:
    """Handle datasets replay command - stream frames from a dataset ref or URL."""
    from canarchy.dataset_provider import DatasetError, get_registry
    from canarchy.dataset_convert import ConversionError, stream_replay

    try:
        replay_source = resolve_dataset_replay_source(
            args.source, get_registry(), replay_file=getattr(args, "replay_file", None)
        )
        result = stream_replay(
            replay_source["download_url"],
            source_format=replay_source["source_format"],
            output_format=args.output_format,
            rate=args.rate,
            max_frames=getattr(args, "max_frames", None),
            max_seconds=getattr(args, "max_seconds", None),
            provenance=dataset_replay_provenance(replay_source),
        )
    except ConversionError as exc:
        result = error_result(
            args.command,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        )
        emit_result(result, "json")
        return EXIT_USER_ERROR
    except DatasetError as exc:
        result = error_result(
            args.command,
            errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
        )
        emit_result(result, "json")
        return EXIT_USER_ERROR
    return EXIT_OK


def _emit_warnings_jsonl(payload: dict[str, Any], result: CommandResult) -> None:
    for warning in payload["warnings"]:
        print(
            json.dumps(
                AlertEvent(
                    level="warning",
                    message=warning,
                    source=f"cli.{result.command}",
                )
                .to_event()
                .to_payload(),
                sort_keys=True,
            )
        )


def _flatten_frame_event(event: dict[str, Any]) -> dict[str, Any]:
    frame = event.get("payload", {}).get("frame", {})
    return {
        "timestamp": event.get("timestamp"),
        "interface": frame.get("interface"),
        "arbitration_id": frame.get("arbitration_id"),
        "data": frame.get("data"),
        "dlc": frame.get("dlc"),
        "is_extended_id": frame.get("is_extended_id"),
    }


def emit_completion_script(args: argparse.Namespace, output_format: str) -> int:
    """Render the shell completion script for ``args.shell`` to stdout.

    Completion output is the script itself — raw, suitable for
    ``eval "$(canarchy completion bash)"`` — and intentionally not wrapped
    in the canonical envelope. Unsupported shells are rejected upstream
    by argparse's ``choices``; this helper assumes the value is valid.
    """

    del output_format  # completion has no output-format flag
    script = render_completion(args.shell)
    print(script, end="")
    return EXIT_OK


def emit_mcp_install(args: argparse.Namespace, output_format: str) -> int:
    """Write the canarchy MCP server block into a client config file."""
    from canarchy import mcp_install as mi

    def _fail(code: str, message: str, hint: str, *, data: dict[str, Any] | None = None) -> int:
        emit_result(
            error_result(
                "mcp install",
                errors=[ErrorDetail(code=code, message=message, hint=hint)],
                data=data,
            ),
            output_format,
        )
        return EXIT_USER_ERROR

    config_path = mi.resolve_config_path(args.client, override=args.config_path)
    base_data: dict[str, Any] = {
        "client": args.client,
        "config_path": str(config_path),
        "command": args.server_command,
    }

    existing_text: str | None = None
    if config_path.exists():
        if config_path.is_dir():
            return _fail(
                "MCP_INSTALL_INVALID_CONFIG",
                f"Config path `{config_path}` is a directory.",
                "Pass --config-path pointing at the client's JSON config file.",
                data=dict(base_data),
            )
        try:
            existing_text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            return _fail(
                "MCP_INSTALL_READ_FAILED",
                f"Could not read `{config_path}`: {exc}.",
                "Check file permissions, or pass --config-path to a readable file.",
                data=dict(base_data),
            )
    elif not config_path.parent.exists():
        return _fail(
            "MCP_INSTALL_DIR_MISSING",
            f"Config directory `{config_path.parent}` does not exist.",
            "Install the client first, or pass --config-path to an existing directory.",
            data=dict(base_data),
        )

    try:
        plan = mi.plan_install(existing_text, command=args.server_command)
    except mi.McpInstallError as exc:
        return _fail(exc.code, exc.message, exc.hint, data=dict(base_data))

    rendered = json.dumps(plan.config, indent=2, sort_keys=True) + "\n"
    data = dict(base_data)
    data["server_block"] = plan.block

    if args.dry_run:
        data["action"] = "planned" if plan.action != "unchanged" else "unchanged"
        data["preview"] = rendered
        emit_result(
            CommandResult(
                command="mcp install",
                data=data,
                warnings=[f"MCP_INSTALL_DRY_RUN: would write `{config_path}`; no file changed."],
            ),
            output_format,
        )
        return EXIT_OK

    if plan.action == "unchanged":
        data["action"] = "unchanged"
        emit_result(
            CommandResult(
                command="mcp install",
                data=data,
                warnings=[f"canarchy MCP block already present in `{config_path}`; no change."],
            ),
            output_format,
        )
        return EXIT_OK

    if not args.ack and os.environ.get("CANARCHY_MCP_NONINTERACTIVE_ACK") != "1":
        print(
            f"confirm: type YES to write the canarchy MCP block to `{config_path}`: ",
            file=sys.stderr,
            end="",
            flush=True,
        )
        if sys.stdin.readline().strip() != "YES":
            return _fail(
                "MCP_INSTALL_DECLINED",
                "MCP install confirmation was not accepted.",
                "Re-run with --ack to skip the prompt, or reply `YES`.",
                data=dict(data, action=plan.action),
            )

    try:
        config_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        return _fail(
            "MCP_INSTALL_WRITE_FAILED",
            f"Could not write `{config_path}`: {exc}.",
            "Check directory permissions, or pass --config-path to a writable location.",
            data=dict(data, action=plan.action),
        )

    data["action"] = plan.action
    data["written"] = True
    emit_result(
        CommandResult(
            command="mcp install",
            data=data,
            warnings=[],
        ),
        output_format,
    )
    return EXIT_OK


def emit_web_serve(args: argparse.Namespace, output_format: str) -> int:
    """Start the read-only web dashboard and serve until interrupted."""
    from canarchy.dbc import DbcError
    from canarchy.web import WebDashboardServer, WebDependencyError, build_dashboard_events

    transport = LocalTransport()
    try:
        frames = transport.frames_from_file(
            args.file,
            offset=getattr(args, "offset", 0) or 0,
            max_frames=getattr(args, "max_frames", None),
            seconds=getattr(args, "seconds", None),
        )
    except TransportError as exc:
        emit_result(
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
            output_format,
        )
        return EXIT_TRANSPORT_ERROR

    dbc_path: str | None = None
    dbc_source: dict[str, Any] | None = None
    try:
        if getattr(args, "dbc", None):
            from canarchy.dbc_provider import get_registry

            resolution = get_registry().resolve(args.dbc)
            dbc_path = str(resolution.local_path)
            dbc_source = _build_dbc_source(resolution)

        events = build_dashboard_events(frames, dbc_path=dbc_path)
    except DbcError as exc:
        emit_result(
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=exc.message, hint=exc.hint)],
            ),
            output_format,
        )
        return EXIT_DECODE_ERROR

    source: dict[str, Any] = {"file": args.file, "dbc": getattr(args, "dbc", None)}
    if dbc_source is not None:
        source["dbc_source"] = dbc_source
    try:
        server = WebDashboardServer(
            args.bind,
            events=events,
            source=source,
            rate=args.rate,
            loop=bool(getattr(args, "loop", False)),
        )
    except WebDependencyError as exc:
        emit_result(
            error_result(
                args.command,
                errors=[ErrorDetail(code=exc.code, message=str(exc), hint=exc.hint)],
            ),
            output_format,
        )
        return EXIT_USER_ERROR

    emit_result(
        CommandResult(
            command=args.command,
            data={
                "url": server.url,
                "bind": args.bind,
                "read_only": True,
                "source": source,
                "event_count": len(events),
                "frame_count": len(frames),
                "rate": args.rate,
                "loop": bool(getattr(args, "loop", False)),
                "mode": "passive",
            },
            warnings=[
                "The dashboard is read-only: no active-transmit endpoints are exposed.",
                "Press Ctrl+C to stop the server.",
            ],
        ),
        output_format,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return EXIT_OK


def emit_result(result: CommandResult, output_format: str) -> None:
    payload = result.to_payload()
    _J1939_SESSION_COMMANDS = {
        "j1939 tp sessions",
        "j1939 tp compare",
        "j1939 dm1",
        "j1939 summary",
        "j1939 inventory",
        "j1939 compare",
        "j1939 map",
    }
    if output_format == "json":
        data = payload.get("data", {})
        if result.command == "filter" and result.ok:
            # Only successful results carry the frames block: an error
            # envelope with `frame_count: 0` reads as "no matches" instead
            # of "bad query" (#414).
            events = data.pop("events", [])
            flat = [_flatten_frame_event(e) for e in events if e.get("event_type") == "frame"]
            data["frame_count"] = len(flat)
            data["frames"] = flat
        elif result.command in _J1939_SESSION_COMMANDS and "events" in data and not data["events"]:
            del data["events"]
        print(json.dumps(payload, sort_keys=True))
        return

    if output_format == "jsonl":
        data = payload.get("data", {})
        events = data.get("events")
        if result.ok and isinstance(events, list) and events:
            for event in events:
                print(json.dumps(event, sort_keys=True))
            _emit_warnings_jsonl(payload, result)
            return
        observations = data.get("observations")
        if result.ok and isinstance(observations, list) and observations:
            for observation in observations:
                print(json.dumps(observation, sort_keys=True))
            _emit_warnings_jsonl(payload, result)
            return
        sessions = data.get("sessions")
        if result.ok and isinstance(sessions, list) and sessions:
            for session in sessions:
                print(json.dumps(session, sort_keys=True))
            _emit_warnings_jsonl(payload, result)
            return
        messages = data.get("messages")
        if result.ok and isinstance(messages, list) and messages:
            for message in messages:
                print(json.dumps(message, sort_keys=True))
            _emit_warnings_jsonl(payload, result)
            return
        print(json.dumps(payload, sort_keys=True))
        return

    if (
        output_format == "text"
        and result.ok
        and result.command == "capture"
        and result.data.get("display") == "candump"
    ):
        for line in format_candump_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "gateway":
        for line in format_gateway_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in J1939_COMMANDS:
        for line in format_j1939_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in {"dbc inspect", "dbc signals"}:
        for line in format_dbc_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "dbc convert":
        out = result.data.get("out")
        if out:
            target = result.data.get("target_format", "")
            print(f"converted {result.data.get('dbc')} -> {out} ({target})")
        else:
            content = result.data.get("content", "")
            print(content, end="" if content.endswith("\n") else "\n")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "dbc generate-c":
        files = result.data.get("files", [])
        dbc_name = result.data.get("dbc", "")
        out_dir = result.data.get("out_dir", ".")
        print(f"generated C source from {dbc_name} in {out_dir}:")
        for f in files:
            print(f"  {f['kind']:20s} {f['path']} ({f['size_bytes']} bytes)")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in DBC_PROVIDER_COMMANDS:
        for line in format_dbc_provider_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in SKILLS_COMMANDS:
        for line in format_skills_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in PLUGINS_COMMANDS:
        for line in format_plugins_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if (
        output_format == "text"
        and result.ok
        and result.command in {"datasets provider list", "datasets search"}
    ):
        for line in format_datasets_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "datasets inspect":
        for line in format_dataset_inspect(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "datasets fetch":
        for line in format_datasets_fetch(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if (
        output_format == "text"
        and result.ok
        and result.command == "datasets replay"
        and result.data.get("dry_run")
    ):
        for line in format_datasets_replay_dry_run(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in UDS_COMMANDS:
        for line in format_uds_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in XCP_COMMANDS:
        for line in format_xcp_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in J1587_COMMANDS:
        for line in format_j1587_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in J2497_COMMANDS:
        for line in format_j2497_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command in RE_COMMANDS:
        for line in format_re_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "fuzz guided":
        for line in format_fuzz_guided_table(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "generate":
        print(f"command: {result.command}")
        print(f"interface: {result.data.get('interface', 'unknown')}")
        print(f"frames: {result.data.get('frame_count', 0)}")
        for line in format_candump_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "simulate":
        print(f"command: {result.command}")
        print(f"interface: {result.data.get('interface', 'unknown')}")
        print(f"profile: {result.data.get('profile', 'unknown')}")
        print(f"frames: {result.data.get('frame_count', 0)}")
        for line in format_candump_lines(result):
            print(line)
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "config show":
        sources = result.data.get("sources", {})
        print("Effective transport configuration:")
        for field in (
            "backend",
            "interface",
            "default_interface",
            "capture_limit",
            "capture_timeout",
        ):
            src = sources.get(field, "?")
            print(f"  {field}: {result.data.get(field)}  [{src}]")
        print(
            "  require_active_ack: "
            f"{result.data.get('require_active_ack')}  [{sources.get('require_active_ack', '?')}]"
        )
        print(f"  j1939_dbc: {result.data.get('j1939_dbc')}  [{sources.get('j1939_dbc', '?')}]")
        config_file = result.data.get("config_file", "")
        found = result.data.get("config_file_found", False)
        status = "found" if found else "not found"
        print(f"config file: {config_file}  [{status}]")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "doctor":
        print(f"command: {result.command}")
        print(f"summary: {result.data.get('summary', '')}")
        print("checks:")
        for check in result.data.get("checks", []):
            status = str(check.get("status", "")).upper()
            label = f"[{status}]".ljust(7)
            name = check.get("name", "")
            detail = check.get("detail", "")
            print(f"- {label} {name}: {detail}")
            hint = check.get("hint")
            if hint:
                print(f"           hint: {hint}")
        for warning in payload["warnings"]:
            print(f"warning: {warning}")
        return

    if output_format == "text" and result.ok and result.command == "plot":
        print(f"command: {result.command}")
        print(f"file: {result.data.get('file', '')}")
        print(f"dbc: {result.data.get('dbc', '')}")
        print(f"signals: {', '.join(result.data.get('signals', []))}")
        print(f"out: {result.data.get('out', '')}")
        print(f"format: {result.data.get('format', '')}")
        print(f"signals_plotted: {result.data.get('signals_plotted', 0)}")
        print(f"data_points: {result.data.get('data_points', 0)}")
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
        prepare_args(args)
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
                errors=[
                    ErrorDetail(
                        code=exc.code, message=exc.message, hint=exc.hint, detail=exc.detail
                    )
                ],
            ),
        )
    except SkillError as exc:
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
    configure_logging(
        log_level=getattr(args, "log_level", None),
        quiet=bool(getattr(args, "quiet", False)),
    )
    output_format = format_name(args)
    try:
        prepare_args(args)
    except CommandError as exc:
        emit_result(
            error_result(exc.command, errors=exc.errors, data=exc.data, warnings=exc.warnings),
            output_format,
        )
        return exc.exit_code
    if args.command == "completion":
        return emit_completion_script(args, output_format)
    if args.command == "mcp serve":
        from canarchy.mcp_server import run_server

        run_server()
        return EXIT_OK
    if args.command == "web serve":
        return emit_web_serve(args, output_format)
    if args.command == "mcp install":
        return emit_mcp_install(args, output_format)
    if args.command == "shell":
        return run_shell(args.shell_command)
    if args.command == "tui":
        return run_tui(execute_command, command=args.tui_command)
    if args.command == "capture":
        return emit_live_capture(args, output_format)
    if (
        args.command == "gateway"
        and output_format == "text"
        and not getattr(args, "dry_run", False)
    ):
        return emit_live_gateway(args)
    if args.command == "datasets stream" and not args.json:
        return emit_dataset_stream(args)
    if (
        args.command == "datasets replay"
        and not args.json
        and not getattr(args, "dry_run", False)
        and not getattr(args, "list_files", False)
        and not getattr(args, "interface", None)
    ):
        return emit_dataset_replay(args)

    exit_code, result = execute_command(argv)
    if result is not None:
        emit_result(result, output_format)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
