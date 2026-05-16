"""CLI entry point for CANarchy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from canarchy.dbc import (
    DbcError,
    dbc_supports_spn,
    decode_frames,
    decode_j1939_spn,
    encode_message,
    inspect_database,
    lookup_j1939_spn_metadata,
)
from canarchy import __version__
from canarchy.exporter import ExportError, export_artifact
from canarchy.j1939 import TP_CM_PGN, TP_DT_PGN, decompose_arbitration_id
from canarchy.j1939_decoder import get_j1939_decoder
from canarchy.j1939_metadata import pgn_lookup, source_address_lookup
from canarchy import pretty_j1939_support
from canarchy.models import (
    AlertEvent,
    CanFrame,
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
from canarchy.skills import SkillError
from canarchy.transport import (
    LocalTransport,
    TransportError,
    active_ack_required,
    config_show_payload,
    default_j1939_dbc,
    generate_frames,
)
from canarchy.tui import run_tui
from canarchy.uds import uds_decoder_backend, uds_services_payload

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_TRANSPORT_ERROR = 2
EXIT_DECODE_ERROR = 3
EXIT_PARTIAL_SUCCESS = 4
TRANSPORT_COMMANDS = {"capture", "send", "filter", "stats", "generate", "capture-info"}
DBC_COMMANDS = {"decode", "encode", "dbc inspect"}
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
}
SESSION_COMMANDS = {"session save", "session load", "session show"}
UDS_COMMANDS = {"uds scan", "uds trace", "uds services"}
CONFIG_COMMANDS = {"config show"}
RE_COMMANDS = {
    "re signals",
    "re counters",
    "re entropy",
    "re correlate",
    "re match-dbc",
    "re shortlist-dbc",
}
ACTIVE_TRANSMIT_COMMANDS = {"send", "generate", "gateway", "uds scan"}
IMPLEMENTED_COMMANDS = (
    TRANSPORT_COMMANDS
    | DBC_COMMANDS
    | DBC_PROVIDER_COMMANDS
    | SKILLS_COMMANDS
    | DATASETS_COMMANDS
    | J1939_COMMANDS
    | SESSION_COMMANDS
    | UDS_COMMANDS
    | CONFIG_COMMANDS
    | RE_COMMANDS
    | {"mcp serve", "replay", "gateway", "shell", "export"}
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
    add_active_ack_argument(send)
    add_output_arguments(send)
    send.set_defaults(command="send")

    generate = subparsers.add_parser("generate", help="generate CAN frames")
    generate.add_argument("interface")
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
    add_active_ack_argument(generate)
    add_output_arguments(generate)
    generate.set_defaults(command="generate")

    gateway = subparsers.add_parser("gateway", help="bridge frames between CAN interfaces")
    gateway.add_argument("src")
    gateway.add_argument("dst")
    gateway.add_argument("--src-backend", help="python-can interface type for the source bus")
    gateway.add_argument("--dst-backend", help="python-can interface type for the destination bus")
    gateway.add_argument(
        "--bidirectional", action="store_true", help="also forward frames from dst back to src"
    )
    gateway.add_argument("--count", type=int, help="stop after forwarding N frames")
    add_active_ack_argument(gateway)
    add_output_arguments(gateway)
    gateway.set_defaults(command="gateway")

    replay = subparsers.add_parser("replay", help="replay recorded traffic")
    replay.add_argument(
        "--file", required=True, help="path to candump capture file (use - for stdin)"
    )
    replay.add_argument("--rate", type=float, default=1.0)
    add_output_arguments(replay)
    replay.set_defaults(command="replay")

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
    add_output_arguments(dbc_inspect)
    dbc_inspect.set_defaults(command="dbc inspect")

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
        choices=["hcrl-csv"],
        help="source file format (hcrl-csv: HCRL Timestamp,ID,DLC,Data CSV)",
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
        choices=["hcrl-csv", "candump"],
        help="source file format (hcrl-csv: HCRL Timestamp,ID,DLC,Data CSV; candump: can-utils log)",
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
    j1939_compare.add_argument("files", nargs="+", help="paths to candump capture files")
    add_j1939_file_analysis_arguments(j1939_compare)
    add_output_arguments(j1939_compare)
    j1939_compare.set_defaults(command="j1939 compare")

    uds = subparsers.add_parser("uds", help="UDS protocol workflows")
    uds_subparsers = uds.add_subparsers(dest="uds_action", required=True)

    uds_scan = uds_subparsers.add_parser("scan", help="scan for UDS responders")
    uds_scan.add_argument("interface")
    add_active_ack_argument(uds_scan)
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

    re_correlate = re_subparsers.add_parser(
        "correlate", help="correlate signal candidates against a reference series"
    )
    re_correlate.add_argument("file")
    re_correlate.add_argument(
        "--reference",
        help="reference series file (.json or .jsonl) with timestamp and value fields",
    )
    add_output_arguments(re_correlate)
    re_correlate.set_defaults(command="re correlate")

    re_match_dbc = re_subparsers.add_parser(
        "match-dbc", help="rank candidate DBCs against a capture"
    )
    re_match_dbc.add_argument("capture", help="capture file to analyse")
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
    re_shortlist_dbc.add_argument("capture", help="capture file to analyse")
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

    config = subparsers.add_parser("config", help="inspect CANarchy configuration")
    config_subparsers = config.add_subparsers(dest="config_action", required=True)
    config_show = config_subparsers.add_parser(
        "show", help="show effective transport configuration"
    )
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
    if args.command == "uds scan":
        return (
            f"warning: `uds scan` will transmit diagnostic requests on interface `{args.interface}`; "
            "use intentionally on a controlled bus."
        )
    if args.command == "gateway":
        return (
            f"warning: `gateway` will forward traffic from `{args.src}` to `{args.dst}`; "
            "use intentionally on a controlled bus."
        )
    raise AssertionError(f"unsupported active transmit command: {args.command}")


def active_transmit_confirmation_prompt(args: argparse.Namespace) -> str:
    if args.command == "send":
        return f"confirm: type YES to send on `{args.interface}`: "
    if args.command == "generate":
        return f"confirm: type YES to generate frames on `{args.interface}`: "
    if args.command == "uds scan":
        return f"confirm: type YES to run UDS scan on `{args.interface}`: "
    if args.command == "gateway":
        return f"confirm: type YES to forward traffic from `{args.src}` to `{args.dst}`: "
    raise AssertionError(f"unsupported active transmit command: {args.command}")


def enforce_active_transmit_safety(
    args: argparse.Namespace,
) -> None:
    if args.command not in ACTIVE_TRANSMIT_COMMANDS:
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
    printable_identifiers: list[dict[str, object]] = []
    for session in tp_sessions:
        if not bool(session.get("complete", False)):
            continue
        text = session.get("decoded_text")
        if text is None:
            continue
        printable_identifiers.append(
            {
                "text": text,
                "transfer_pgn": int(session["transfer_pgn"]),
                "source_address": int(session["source_address"]),
                "destination_address": session["destination_address"],
                "session_type": str(session["session_type"]),
                "payload_label": session.get("payload_label"),
                "heuristic": bool(session.get("decoded_text_heuristic", False)),
            }
        )

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
        frame = parse_send_frame(args)
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
        enforce_active_transmit_safety(args)
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
                            code="CAPTURE_EMPTY", message="No valid frames read from stdin."
                        )
                    ],
                )
            # Calculate stats
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
                    **stats.to_payload(),
                },
                [],
                [],
            )
        stats = transport.stats(
            args.file, offset=args.offset, max_frames=args.max_frames, seconds=args.seconds
        )
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
    if args.command == "capture-info":
        if args.file == "-":
            # Handle stdin
            import sys
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
                            code="CAPTURE_EMPTY", message="No valid frames read from stdin."
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
    raise AssertionError(f"unsupported j1939 command: {args.command}")


def _build_dbc_source(resolution: Any) -> dict[str, Any]:
    d = resolution.descriptor
    return {
        "provider": d.provider,
        "name": d.name,
        "version": d.version,
        "path": str(resolution.local_path),
    }


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
        frame, events = encode_message(dbc_path, args.message, signals)
        return (
            {
                "dbc": args.dbc,
                "dbc_source": dbc_source,
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
    if args.command == "dbc inspect":
        data, events = inspect_database(
            dbc_path,
            message_name=args.message,
            signals_only=args.signals_only,
        )
        data["dbc_source"] = dbc_source
        return (data, events, [])
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
                args.source, registry, replay_file=getattr(args, "replay_file", None)
            )
            if getattr(args, "list_files", False):
                return (dataset_replay_files_payload(replay_source), [], [])
            validate_dataset_replay_options(args, replay_source)
            if getattr(args, "dry_run", False):
                return (dataset_replay_plan(args, replay_source), [], [])
            result = stream_replay(
                replay_source["download_url"],
                source_format=replay_source["source_format"],
                output_format=args.output_format,
                rate=args.rate,
                max_frames=getattr(args, "max_frames", None),
                max_seconds=getattr(args, "max_seconds", None),
                provenance=dataset_replay_provenance(replay_source),
                emit_frames=False,
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
    source: str, registry: Any, *, replay_file: str | None = None
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
    if source_format != "candump":
        raise ConversionError(
            code="UNSUPPORTED_SOURCE_FORMAT",
            message=f"Streaming replay only supports candump format, got '{source_format}'.",
            hint="Use source_format='candump' for streaming replay.",
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


def uds_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
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


def gateway_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    transport = LocalTransport()
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
        [],
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


def reverse_engineering_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    from canarchy.plugins import get_registry

    transport = LocalTransport()
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


def format_re_table(result: CommandResult) -> list[str]:
    lines = [f"command: {result.command}"]

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
        if result.data.get("signals_only"):
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


def emit_result(result: CommandResult, output_format: str) -> None:
    payload = result.to_payload()
    _J1939_SESSION_COMMANDS = {
        "j1939 tp sessions",
        "j1939 tp compare",
        "j1939 dm1",
        "j1939 summary",
        "j1939 inventory",
        "j1939 compare",
    }
    if output_format == "json":
        data = payload.get("data", {})
        if result.command == "filter":
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

    if output_format == "text" and result.ok and result.command == "dbc inspect":
        for line in format_dbc_table(result):
            print(line)
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

    if output_format == "text" and result.ok and result.command in RE_COMMANDS:
        for line in format_re_table(result):
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

    if output_format == "text" and result.ok and result.command == "config show":
        sources = result.data.get("sources", {})
        print("Effective transport configuration:")
        for field in ("backend", "interface", "capture_limit", "capture_timeout"):
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
    if args.command == "gateway" and output_format == "text":
        return emit_live_gateway(args)
    if args.command == "datasets stream" and not args.json:
        return emit_dataset_stream(args)
    if (
        args.command == "datasets replay"
        and not args.json
        and not getattr(args, "dry_run", False)
        and not getattr(args, "list_files", False)
    ):
        return emit_dataset_replay(args)

    exit_code, result = execute_command(argv)
    if result is not None:
        emit_result(result, output_format)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
