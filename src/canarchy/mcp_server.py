"""MCP server — exposes CANarchy CLI commands as Model Context Protocol tools over stdio."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from canarchy.cli import execute_command

_SERVER_NAME = "canarchy"
_SERVER_VERSION = "0.1.0"

server = Server(_SERVER_NAME)

_TOOLS: list[types.Tool] = [
    types.Tool(
        name="capture",
        description="Capture CAN traffic from an interface (scaffold/live).",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "CAN interface name (e.g. can0)"},
            },
            "required": ["interface"],
        },
    ),
    types.Tool(
        name="send",
        description="Send a single CAN frame to an interface.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "CAN interface name"},
                "frame_id": {"type": "string", "description": "Frame ID as hex (e.g. 0x123 or 291)"},
                "data": {"type": "string", "description": "Payload as hex bytes (e.g. 11223344)"},
            },
            "required": ["interface", "frame_id", "data"],
        },
    ),
    types.Tool(
        name="generate",
        description="Generate CAN frames on an interface.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "CAN interface name"},
                "id": {"type": "string", "description": "Frame ID as hex or R for random", "default": "R"},
                "dlc": {"type": "string", "description": "Data length 0-8 or R for random", "default": "R"},
                "data": {"type": "string", "description": "Payload hex, R for random, I for incrementing", "default": "R"},
                "count": {"type": "integer", "description": "Number of frames to generate", "default": 1},
                "gap": {"type": "number", "description": "Inter-frame gap in milliseconds", "default": 200.0},
                "extended": {"type": "boolean", "description": "Force 29-bit extended IDs", "default": False},
            },
            "required": ["interface"],
        },
    ),
    types.Tool(
        name="gateway",
        description="Bridge CAN frames between two interfaces.",
        inputSchema={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source CAN interface"},
                "dst": {"type": "string", "description": "Destination CAN interface"},
                "src_backend": {"type": "string", "description": "python-can interface type for source"},
                "dst_backend": {"type": "string", "description": "python-can interface type for destination"},
                "bidirectional": {"type": "boolean", "description": "Also forward frames from dst to src", "default": False},
                "count": {"type": "integer", "description": "Stop after forwarding N frames"},
            },
            "required": ["src", "dst"],
        },
    ),
    types.Tool(
        name="replay",
        description="Replay recorded CAN traffic from a candump capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "rate": {"type": "number", "description": "Playback rate multiplier", "default": 1.0},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="filter",
        description="Filter CAN frames from a capture file by expression.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "expression": {"type": "string", "description": "Filter expression (e.g. id==0x123 or dlc>4)"},
            },
            "required": ["file", "expression"],
        },
    ),
    types.Tool(
        name="stats",
        description="Summarize traffic statistics from a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="decode",
        description="Decode CAN traffic from a capture file using a DBC database.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "dbc": {"type": "string", "description": "Path to DBC file"},
            },
            "required": ["file", "dbc"],
        },
    ),
    types.Tool(
        name="encode",
        description="Encode CAN signals into a frame payload using a DBC database.",
        inputSchema={
            "type": "object",
            "properties": {
                "dbc": {"type": "string", "description": "Path to DBC file"},
                "message": {"type": "string", "description": "Message name from the DBC"},
                "signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Signal assignments as key=value strings (e.g. RPM=1000)",
                    "default": [],
                },
            },
            "required": ["dbc", "message"],
        },
    ),
    types.Tool(
        name="export",
        description="Export session data or a capture file to a destination path.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source session name or file path"},
                "destination": {"type": "string", "description": "Destination file path"},
            },
            "required": ["source", "destination"],
        },
    ),
    types.Tool(
        name="session_save",
        description="Save a named CANarchy session with optional interface, DBC, and capture context.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Session name"},
                "interface": {"type": "string", "description": "CAN interface to associate"},
                "dbc": {"type": "string", "description": "DBC file to associate"},
                "capture": {"type": "string", "description": "Capture file to associate"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="session_load",
        description="Load a previously saved CANarchy session by name.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Session name to load"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="session_show",
        description="Show the current CANarchy session state.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="j1939_monitor",
        description="Monitor J1939 traffic on an interface or from the sample provider.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "CAN interface name (omit for sample data)"},
                "pgn": {"type": "integer", "description": "Filter to a specific PGN (0–262143)"},
            },
        },
    ),
    types.Tool(
        name="j1939_decode",
        description="Decode J1939 frames from a candump capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_pgn",
        description="Inspect a specific J1939 PGN within a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "pgn": {"type": "integer", "description": "J1939 PGN value (0–262143)"},
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["pgn", "file"],
        },
    ),
    types.Tool(
        name="j1939_spn",
        description="Inspect a specific J1939 SPN within a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "spn": {"type": "integer", "description": "J1939 SPN value (non-negative integer)"},
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["spn", "file"],
        },
    ),
    types.Tool(
        name="j1939_tp",
        description="Inspect J1939 transport protocol sessions in a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_dm1",
        description="Inspect J1939 DM1 diagnostic messages in a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="uds_scan",
        description="Scan for UDS responders on a CAN interface.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "CAN interface name"},
            },
            "required": ["interface"],
        },
    ),
    types.Tool(
        name="uds_trace",
        description="Trace UDS request/response transactions on a CAN interface.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "CAN interface name"},
            },
            "required": ["interface"],
        },
    ),
    types.Tool(
        name="uds_services",
        description="List the UDS service catalog with SIDs, names, and categories.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="config_show",
        description="Show the effective CANarchy transport configuration.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]

_TOOL_NAMES: frozenset[str] = frozenset(tool.name for tool in _TOOLS)


def _build_argv(tool_name: str, arguments: dict[str, Any]) -> list[str]:
    """Convert an MCP tool name and arguments into a CLI argv list."""
    a = arguments
    match tool_name:
        case "capture":
            return ["capture", a["interface"], "--json"]
        case "send":
            return ["send", a["interface"], a["frame_id"], a["data"], "--json"]
        case "generate":
            argv = ["generate", a["interface"]]
            if "id" in a:
                argv += ["--id", str(a["id"])]
            if "dlc" in a:
                argv += ["--dlc", str(a["dlc"])]
            if "data" in a:
                argv += ["--data", str(a["data"])]
            if "count" in a:
                argv += ["--count", str(a["count"])]
            if "gap" in a:
                argv += ["--gap", str(a["gap"])]
            if a.get("extended"):
                argv.append("--extended")
            return argv + ["--json"]
        case "gateway":
            argv = ["gateway", a["src"], a["dst"]]
            if a.get("src_backend"):
                argv += ["--src-backend", a["src_backend"]]
            if a.get("dst_backend"):
                argv += ["--dst-backend", a["dst_backend"]]
            if a.get("bidirectional"):
                argv.append("--bidirectional")
            if a.get("count") is not None:
                argv += ["--count", str(a["count"])]
            return argv + ["--json"]
        case "replay":
            argv = ["replay", a["file"]]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            return argv + ["--json"]
        case "filter":
            return ["filter", a["file"], a["expression"], "--json"]
        case "stats":
            return ["stats", a["file"], "--json"]
        case "decode":
            return ["decode", a["file"], "--dbc", a["dbc"], "--json"]
        case "encode":
            argv = ["encode", "--dbc", a["dbc"], a["message"]]
            argv += a.get("signals", [])
            return argv + ["--json"]
        case "export":
            return ["export", a["source"], a["destination"], "--json"]
        case "session_save":
            argv = ["session", "save", a["name"]]
            if a.get("interface"):
                argv += ["--interface", a["interface"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if a.get("capture"):
                argv += ["--capture", a["capture"]]
            return argv + ["--json"]
        case "session_load":
            return ["session", "load", a["name"], "--json"]
        case "session_show":
            return ["session", "show", "--json"]
        case "j1939_monitor":
            argv = ["j1939", "monitor"]
            if a.get("interface"):
                argv.append(a["interface"])
            if a.get("pgn") is not None:
                argv += ["--pgn", str(a["pgn"])]
            return argv + ["--json"]
        case "j1939_decode":
            return ["j1939", "decode", a["file"], "--json"]
        case "j1939_pgn":
            return ["j1939", "pgn", str(a["pgn"]), "--file", a["file"], "--json"]
        case "j1939_spn":
            return ["j1939", "spn", str(a["spn"]), "--file", a["file"], "--json"]
        case "j1939_tp":
            return ["j1939", "tp", a["file"], "--json"]
        case "j1939_dm1":
            return ["j1939", "dm1", a["file"], "--json"]
        case "uds_scan":
            return ["uds", "scan", a["interface"], "--json"]
        case "uds_trace":
            return ["uds", "trace", a["interface"], "--json"]
        case "uds_services":
            return ["uds", "services", "--json"]
        case "config_show":
            return ["config", "show", "--json"]
        case _:
            raise ValueError(f"Unknown tool: {tool_name!r}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _TOOLS


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    if name not in _TOOL_NAMES:
        raise ValueError(f"Unknown tool: {name!r}")
    argv = _build_argv(name, arguments or {})
    _, result = execute_command(argv)
    if result is None:
        payload: dict[str, Any] = {
            "ok": False,
            "command": name,
            "data": {},
            "warnings": [],
            "errors": [{"code": "NO_RESULT", "message": "Command returned no result"}],
        }
    else:
        payload = result.to_payload()
    return [types.TextContent(type="text", text=json.dumps(payload, sort_keys=True))]


def run_server() -> None:
    asyncio.run(_amain())


async def _amain() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=_SERVER_NAME,
                server_version=_SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
