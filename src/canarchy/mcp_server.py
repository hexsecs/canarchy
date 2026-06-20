"""MCP server — exposes CANarchy CLI commands as Model Context Protocol tools over stdio."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import signal
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from canarchy import __version__
from canarchy.cli import execute_command
from canarchy.simulate import PROFILE_NAMES

_SERVER_NAME = "canarchy"
_SERVER_VERSION = __version__

server = Server(_SERVER_NAME)

_TOOLS: list[types.Tool] = [
    types.Tool(
        name="capture",
        description="Capture CAN traffic from an interface (scaffold/live).",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name (e.g. can0); omit to use configured default",
                },
            },
        },
    ),
    types.Tool(
        name="send",
        description=(
            "Send a single CAN frame to an interface. Mandatory `ack_active=true`; "
            "`dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
                "frame_id": {
                    "type": "string",
                    "description": "Frame ID as hex (e.g. 0x123 or 291)",
                },
                "data": {"type": "string", "description": "Payload as hex bytes (e.g. 11223344)"},
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory acknowledgement for active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan without transmitting (default: true for MCP)",
                    "default": True,
                },
            },
            "required": ["frame_id", "data", "ack_active"],
        },
    ),
    types.Tool(
        name="generate",
        description=(
            "Generate CAN frames on an interface. Mandatory `ack_active=true`; "
            "`dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
                "id": {
                    "type": "string",
                    "description": "Frame ID as hex or R for random",
                    "default": "R",
                },
                "dlc": {
                    "type": "string",
                    "description": "Data length 0-8 or R for random",
                    "default": "R",
                },
                "data": {
                    "type": "string",
                    "description": "Payload hex, R for random, I for incrementing",
                    "default": "R",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of frames to generate",
                    "default": 1,
                },
                "gap": {
                    "type": "number",
                    "description": "Inter-frame gap in milliseconds",
                    "default": 200.0,
                },
                "extended": {
                    "type": "boolean",
                    "description": "Force 29-bit extended IDs",
                    "default": False,
                },
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory acknowledgement for active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan without transmitting (default: true for MCP)",
                    "default": True,
                },
            },
            "required": ["ack_active"],
        },
    ),
    types.Tool(
        name="simulate",
        description=(
            "Simulate realistic CAN/J1939 traffic from a data-driven vehicle profile. "
            "Mandatory `ack_active=true`; `dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "enum": list(PROFILE_NAMES),
                    "description": "Vehicle traffic profile to emit",
                },
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
                "rate": {
                    "type": "number",
                    "description": "Frame emission rate in Hz",
                    "default": 50.0,
                },
                "duration": {
                    "type": "number",
                    "description": "Simulation duration in seconds",
                    "default": 10.0,
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for deterministic output",
                    "default": 0,
                },
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory acknowledgement for active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan without transmitting (default: true for MCP)",
                    "default": True,
                },
            },
            "required": ["profile", "ack_active"],
        },
    ),
    types.Tool(
        name="gateway",
        description=(
            "Bridge CAN frames between two interfaces. Mandatory `ack_active=true`; "
            "`dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source CAN interface"},
                "dst": {"type": "string", "description": "Destination CAN interface"},
                "src_backend": {
                    "type": "string",
                    "description": "python-can interface type for source",
                },
                "dst_backend": {
                    "type": "string",
                    "description": "python-can interface type for destination",
                },
                "bidirectional": {
                    "type": "boolean",
                    "description": "Also forward frames from dst to src",
                    "default": False,
                },
                "count": {"type": "integer", "description": "Stop after forwarding N frames"},
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory acknowledgement for active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan without transmitting (default: true for MCP)",
                    "default": True,
                },
            },
            "required": ["src", "dst", "ack_active"],
        },
    ),
    types.Tool(
        name="replay",
        description="Replay recorded CAN traffic from a candump capture file onto a live interface or return a replay plan.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "rate": {
                    "type": "number",
                    "description": "Playback rate multiplier",
                    "default": 1.0,
                },
                "interface": {
                    "type": "string",
                    "description": "Target CAN interface for live transmission (omit for planning-only)",
                },
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory acknowledgement for live transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan without transmitting (default: true for MCP)",
                    "default": True,
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="sequence_replay",
        description="Replay a YAML/JSON sequence of DBC-encoded CAN frames with configurable timing.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Path to the YAML or JSON sequence file",
                },
                "interface": {
                    "type": "string",
                    "description": "Target CAN interface for live transmission (omit for dry-run)",
                },
                "rate": {
                    "type": "number",
                    "description": "Time-scale factor: 2.0 plays at 2× speed (default: 1.0)",
                    "default": 1.0,
                },
                "loop": {
                    "type": "boolean",
                    "description": "Repeat the sequence until interrupted",
                    "default": False,
                },
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory acknowledgement for live transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan without transmitting (default: true for MCP)",
                    "default": True,
                },
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
                "expression": {
                    "type": "string",
                    "description": "Filter expression (e.g. id==0x123 or dlc>4)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first N seconds from capture start",
                },
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
                "top": {
                    "type": "integer",
                    "description": "Number of highest-frequency arbitration ids to detail "
                    "(default: 20)",
                },
                "pgn": {"type": "integer", "description": "Filter by transfer PGN"},
                "sa": {
                    "type": "string",
                    "description": "Filter by source address (comma-separated hex or decimal)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first N seconds from capture start",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="capture_info",
        description="Show capture file metadata (frame count, duration, IDs) without loading frames.",
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
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first N seconds from capture start",
                },
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
        name="dbc_inspect",
        description="Inspect CAN database metadata from a DBC file.",
        inputSchema={
            "type": "object",
            "properties": {
                "dbc": {"type": "string", "description": "Path to DBC file"},
                "message": {
                    "type": "string",
                    "description": "Restrict results to a single message name",
                },
                "signals_only": {
                    "type": "boolean",
                    "description": "Return signal-centric metadata without full message definitions",
                    "default": False,
                },
                "search": {
                    "type": "string",
                    "description": "Case-insensitive regex/substring filter on message and signal names",
                },
                "layout": {
                    "type": "boolean",
                    "description": "Include cantools-rendered bit layout, signal tree, and choice tables",
                    "default": False,
                },
            },
            "required": ["dbc"],
        },
    ),
    types.Tool(
        name="dbc_signals",
        description="List and search signals from a DBC file (signal-centric view).",
        inputSchema={
            "type": "object",
            "properties": {
                "dbc": {"type": "string", "description": "Path to DBC file or provider ref"},
                "message": {
                    "type": "string",
                    "description": "Restrict results to a single message name",
                },
                "search": {
                    "type": "string",
                    "description": "Case-insensitive regex/substring filter on message and signal names",
                },
            },
            "required": ["dbc"],
        },
    ),
    types.Tool(
        name="dbc_convert",
        description=(
            "Convert a CAN database between DBC, KCD, and SYM formats using the "
            "cantools serializers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "dbc": {
                    "type": "string",
                    "description": "Source database path or provider ref",
                },
                "to": {
                    "type": "string",
                    "enum": ["dbc", "kcd", "sym"],
                    "description": "Target database format",
                },
                "out": {
                    "type": "string",
                    "description": (
                        "Write the converted database to this path; omit to return the "
                        "serialized content in the response envelope"
                    ),
                },
            },
            "required": ["dbc", "to"],
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
                "interface": {
                    "type": "string",
                    "description": "CAN interface name (omit for sample data)",
                },
                "pgn": {"type": "integer", "description": "Filter to a specific PGN (0–262143)"},
            },
        },
    ),
    types.Tool(
        name="j1939_decode",
        description="Decode J1939 frames from a candump capture file. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "dbc": {
                    "type": "string",
                    "description": "Enrich results with a local DBC path or provider ref (e.g. opendbc:toyota_tnga_k_pt_generated)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_pgn",
        description="Inspect a specific J1939 PGN. Omit `file` for a built-in reference lookup (name/label/description and catalogued SPNs); pass `file` to inspect the PGN within a capture. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "pgn": {"type": "integer", "description": "J1939 PGN value (0–262143)"},
                "file": {
                    "type": "string",
                    "description": "Path to candump capture file "
                    "(omit for a built-in reference lookup)",
                },
                "dbc": {
                    "type": "string",
                    "description": "Enrich results with a local DBC path or provider ref",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["pgn"],
        },
    ),
    types.Tool(
        name="j1939_spn",
        description="Inspect a specific J1939 SPN. Omit `file` for a built-in reference lookup (name, PGN, units, resolution, bit layout); pass `file` to inspect SPN values within a capture. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "spn": {"type": "integer", "description": "J1939 SPN value (non-negative integer)"},
                "file": {
                    "type": "string",
                    "description": "Path to candump capture file "
                    "(omit for a built-in reference lookup)",
                },
                "dbc": {
                    "type": "string",
                    "description": "Enrich results with a local DBC path or provider ref",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["spn"],
        },
    ),
    types.Tool(
        name="j1939_tp",
        description="Inspect J1939 transport protocol sessions in a capture file. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_tp_compare",
        description="Compare J1939 transport protocol sessions across source addresses in a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "sa": {
                    "type": "string",
                    "description": "Comma-separated source addresses to compare (hex or decimal)",
                },
                "pgn": {"type": "integer", "description": "Filter by transfer PGN"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file", "sa"],
        },
    ),
    types.Tool(
        name="j1939_dm1",
        description="Inspect J1939 DM1 diagnostic messages in a capture file. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "dbc": {
                    "type": "string",
                    "description": "Enrich DM1 DTC names with a local DBC path or provider ref",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_faults",
        description="Summarize J1939 DM1 faults by ECU from a capture file. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "dbc": {
                    "type": "string",
                    "description": "Enrich DTC names with a local DBC path or provider ref",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_summary",
        description="Summarize J1939 capture content: PGN distribution, source addresses, and transport sessions. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_inventory",
        description="Build a J1939 ECU inventory from a capture file, including VINs, component IDs, source addresses, and top PGNs. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1939_compare",
        description="Compare two or more J1939 capture files for PGN, source-address, TP, and fault differences.",
        inputSchema={
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Two or more candump capture files to compare",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from each capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames per capture",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of each capture",
                },
            },
            "required": ["files"],
        },
    ),
    types.Tool(
        name="j1939_map",
        description="Build a passive J1939 network-topology map from a capture file: nodes (source addresses with SA names, Address Claimed NAME fields, and identification strings) and edges (observed PGN flows from source to destination/broadcast). No active probing. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
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
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
            },
        },
    ),
    types.Tool(
        name="uds_trace",
        description="Trace UDS request/response transactions on a CAN interface.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
            },
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
        name="xcp_scan",
        description=(
            "Scan for XCP responders on a CAN interface via the CONNECT command. "
            "Active transmit: mandatory `ack_active=true`; `dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
                "request_id": {
                    "type": "string",
                    "description": "Master request CAN id (decimal or 0x hex; default 0x3E0)",
                },
                "response_id": {
                    "type": "string",
                    "description": "Slave response CAN id (decimal or 0x hex; default 0x3E1)",
                },
                "ack_active": {
                    "type": "boolean",
                    "description": "Must be true to authorise transmitting the CONNECT frame",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Plan the CONNECT without transmitting (defaults to true)",
                },
            },
            "required": ["ack_active"],
        },
    ),
    types.Tool(
        name="xcp_trace",
        description="Trace XCP command/response transactions on a CAN interface.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
                "request_id": {
                    "type": "string",
                    "description": "Master request CAN id (decimal or 0x hex; default 0x3E0)",
                },
                "response_id": {
                    "type": "string",
                    "description": "Slave response CAN id (decimal or 0x hex; default 0x3E1)",
                },
            },
        },
    ),
    types.Tool(
        name="xcp_read",
        description="Read raw XCP DAQ measurement (DTO) values from a short CAN capture.",
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "description": "CAN interface name; omit to use configured default",
                },
                "response_id": {
                    "type": "string",
                    "description": "Slave response CAN id (decimal or 0x hex; default 0x3E1)",
                },
            },
        },
    ),
    types.Tool(
        name="xcp_commands",
        description="List the XCP command catalog with codes, names, and categories.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="j1587_decode",
        description=(
            "Decode a J1708 capture file into J1587 PID parameters. Use max_frames or "
            "seconds to limit processing on large captures."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to a J1708 capture file"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N messages from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N messages (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j1587_pids",
        description="List the bundled J1587 PID catalog with names, units, and scaling.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="j2497_decode",
        description=(
            "Decode a J2497 (PLC4TRUCKS trailer power-line) capture file into frames "
            "(MID, message data, checksum validity). Use max_frames or seconds to limit "
            "processing on large captures."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to a J2497 capture file"},
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames (useful for large captures)",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="j2497_mids",
        description="List the bundled J2497/J1587 MID catalog with ECU names.",
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
    types.Tool(
        name="doctor",
        description=(
            "Run local environment health checks (Python version, python-can, "
            "transport backend, python-can interface dependency, config file, "
            "cache directories, opendbc cache, "
            "MCP server, package/source version drift) and return the canonical "
            "envelope. No network or live bus access."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="datasets_provider_list",
        description="List registered dataset providers.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="datasets_search",
        description="Search public CAN dataset provider catalogs by name, protocol, or keyword.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query; omit or use empty string to list datasets",
                    "default": "",
                },
                "provider": {
                    "type": "string",
                    "description": "Restrict search to a specific provider",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 20,
                },
            },
        },
    ),
    types.Tool(
        name="datasets_inspect",
        description="Show full metadata for a dataset ref.",
        inputSchema={
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Dataset ref, e.g. catalog:candid"},
            },
            "required": ["ref"],
        },
    ),
    types.Tool(
        name="datasets_fetch",
        description="Record dataset provenance in the local cache without downloading large dataset payloads.",
        inputSchema={
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Dataset ref, e.g. catalog:road"},
            },
            "required": ["ref"],
        },
    ),
    types.Tool(
        name="datasets_cache_list",
        description="List cached dataset provider manifests and provenance records.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="datasets_cache_refresh",
        description="Refresh the dataset provider catalog manifest.",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider to refresh",
                    "default": "catalog",
                },
            },
        },
    ),
    types.Tool(
        name="datasets_convert",
        description="Convert a downloaded dataset file to candump or JSONL without streaming frame records through MCP.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to the downloaded dataset file"},
                "source_format": {
                    "type": "string",
                    "description": "Source file format",
                    "enum": ["hcrl-csv", "candump", "comma-rlog"],
                },
                "format": {
                    "type": "string",
                    "description": "Output format",
                    "enum": ["candump", "jsonl"],
                },
                "output": {
                    "type": "string",
                    "description": "Output file path (defaults to source path with new suffix)",
                },
            },
            "required": ["file", "source_format", "format"],
        },
    ),
    types.Tool(
        name="datasets_replay_plan",
        description="Resolve dataset replay metadata for a dataset ref or URL without opening the remote stream.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Dataset ref (e.g. catalog:candid) or remote candump URL",
                },
                "format": {
                    "type": "string",
                    "description": "Planned output format",
                    "enum": ["candump", "jsonl"],
                    "default": "candump",
                },
                "rate": {
                    "type": "number",
                    "description": "Playback rate multiplier for the planned replay",
                    "default": 1.0,
                },
                "file": {
                    "type": "string",
                    "description": "Replay file id or name from the dataset manifest",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform filter for dynamic manifests such as commaCarSegments",
                },
                "limit": {
                    "type": "integer",
                    "description": "Limit dynamic manifest entries while planning",
                },
                "max_frames": {"type": "integer", "description": "Planned frame limit"},
                "max_seconds": {
                    "type": "number",
                    "description": "Planned capture-time limit in seconds",
                },
            },
            "required": ["source"],
        },
    ),
    types.Tool(
        name="datasets_replay_files",
        description="List replayable files for a dataset ref without opening the remote stream.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Replayable dataset ref (e.g. catalog:candid)",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform filter for dynamic manifests such as commaCarSegments",
                },
                "limit": {
                    "type": "integer",
                    "description": "Limit dynamic manifest entries",
                },
            },
            "required": ["source"],
        },
    ),
    types.Tool(
        name="skills_provider_list",
        description="List registered skills providers.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="skills_search",
        description="Search skills across registered providers by name, tag, or keyword.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (name, tag, or keyword)"},
                "provider": {
                    "type": "string",
                    "description": "Restrict search to a specific provider",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="skills_fetch",
        description="Fetch and cache a skill by provider ref.",
        inputSchema={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Skill ref (e.g. github:j1939_compare_triage)",
                },
            },
            "required": ["ref"],
        },
    ),
    types.Tool(
        name="skills_cache_list",
        description="List cached skills providers and entries.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="skills_cache_refresh",
        description="Refresh a skills provider catalog from upstream.",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider to refresh",
                    "default": "github",
                },
            },
        },
    ),
    types.Tool(
        name="dbc_provider_list",
        description="List all registered DBC providers.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="dbc_search",
        description="Search for DBC files across registered providers by name, make, or keyword.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (name, make, or keyword)"},
                "provider": {
                    "type": "string",
                    "description": "Restrict search to a specific provider",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="dbc_fetch",
        description="Fetch and cache a DBC file by provider ref (e.g. opendbc:toyota_tnga_k_pt_generated).",
        inputSchema={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "DBC ref in the form provider:name (e.g. opendbc:toyota_tnga_k_pt_generated)",
                },
            },
            "required": ["ref"],
        },
    ),
    types.Tool(
        name="dbc_cache_list",
        description="List all locally cached DBC providers and their entries.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="dbc_cache_prune",
        description="Remove stale cached DBC commits.",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Restrict pruning to a specific provider",
                },
            },
        },
    ),
    types.Tool(
        name="dbc_cache_refresh",
        description="Refresh the DBC catalog from upstream for a provider.",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider to refresh",
                    "default": "opendbc",
                },
            },
        },
    ),
    types.Tool(
        name="re_signals",
        description="Analyze changing bit fields and infer signal candidates from a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="re_correlate",
        description="Correlate candidate bit fields in a capture against a reference time series to identify which fields encode a known physical quantity.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "reference": {
                    "type": "string",
                    "description": "Path to reference series file (.json or .jsonl) with timestamp and value fields",
                },
            },
            "required": ["file", "reference"],
        },
    ),
    types.Tool(
        name="re_anomalies",
        description=(
            "Flag inter-frame-timing outliers and unexpected/dropped arbitration IDs "
            "in a capture, optionally against a baseline capture."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "baseline": {
                    "type": "string",
                    "description": "Reference capture to learn expected timing and ID coverage from",
                },
                "dbc": {
                    "type": "string",
                    "description": "Database (DBC/ARXML/KCD/SYM or provider ref) whose cycle time and send type classify which messages are cyclic (authoritative over the CV guard)",
                },
                "z_threshold": {
                    "type": "number",
                    "description": "Minimum absolute z-score to flag a timing anomaly",
                    "default": 3.0,
                },
                "cv_max": {
                    "type": "number",
                    "description": "Max coefficient of variation for an ID to be treated as cyclic when no DBC is supplied",
                    "default": 0.5,
                },
                "min_samples": {
                    "type": "integer",
                    "description": (
                        "Minimum inter-frame gaps before an ID's timing is scored "
                        "(default: 3 with a baseline, 10 without; sparser IDs are "
                        "reported as low-rate instead of ranked)"
                    ),
                },
                "offset": {"type": "integer", "description": "Skip the first N frames"},
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first N seconds from capture start",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="re_counters",
        description="Detect likely counter fields in CAN frames from a capture file.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="re_entropy",
        description="Rank payload bytes by Shannon entropy to surface high-activity signal candidates.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="re_match_dbc",
        description="Rank candidate DBC files from a provider catalog by how well they match a capture.",
        inputSchema={
            "type": "object",
            "properties": {
                "capture": {"type": "string", "description": "Path to candump capture file"},
                "provider": {
                    "type": "string",
                    "description": "DBC provider catalog to search",
                    "default": "opendbc",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidates to return",
                    "default": 10,
                },
            },
            "required": ["capture"],
        },
    ),
    types.Tool(
        name="re_shortlist_dbc",
        description="Rank DBC candidates pre-filtered by vehicle make against a capture.",
        inputSchema={
            "type": "object",
            "properties": {
                "capture": {"type": "string", "description": "Path to candump capture file"},
                "make": {
                    "type": "string",
                    "description": "Vehicle make to pre-filter candidates (e.g. toyota)",
                },
                "provider": {
                    "type": "string",
                    "description": "DBC provider catalog to search",
                    "default": "opendbc",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidates to return",
                    "default": 10,
                },
            },
            "required": ["capture", "make"],
        },
    ),
    types.Tool(
        name="re_corpus",
        description="Cross-capture corpus analysis: per-ID coverage matrix, cycle-time drift, and signal stability across multiple candump/PCAP captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to candump or PCAP capture files",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from each capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames per capture",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of each capture",
                },
            },
            "required": ["files"],
        },
    ),
    types.Tool(
        name="re_suggest",
        description=(
            "Propose names for ranked signal candidates using offline heuristics "
            "(reference-DBC overlap, J1939 SPN/PGN catalog, range/scale, templates). "
            "The optional external-LLM enrichment is CLI-only and not available here."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump or PCAP capture file"},
                "reference_dbc": {
                    "type": "string",
                    "description": "DBC/ARXML/KCD/SYM file or provider ref to seed name suggestions",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum ranked candidates to name (default 25)",
                },
            },
            "required": ["file"],
        },
    ),
    types.Tool(
        name="fuzz_payload",
        description=(
            "Active-transmit payload fuzzing gated by docs/design/active-transmit-safety.md. "
            "Mandatory `ack_active=true`. `dry_run` defaults to true; set to false only after "
            "explicit human authorisation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "Target CAN interface"},
                "id": {"type": "string", "description": "Hex CAN ID (e.g. `0x123`)"},
                "strategy": {
                    "type": "string",
                    "enum": ["bitflip", "random", "boundary", "havoc", "splice", "interesting"],
                    "description": "Mutation strategy",
                },
                "data": {
                    "type": "string",
                    "description": "Baseline hex payload for bitflip / havoc (defaults to 8 zero bytes)",
                },
                "dlc": {
                    "type": "integer",
                    "description": "Payload length for random / boundary / interesting",
                    "default": 8,
                },
                "corpus": {
                    "type": "string",
                    "description": "Candump capture supplying the seed corpus for the splice strategy",
                },
                "max": {
                    "type": "integer",
                    "description": "Maximum frames to emit",
                    "default": 64,
                },
                "rate": {"type": "number", "description": "Frames per second", "default": 100.0},
                "seed": {"type": "integer", "description": "Seed for the mutator", "default": 0},
                "extended": {
                    "type": "boolean",
                    "description": "Treat the ID as 29-bit extended",
                    "default": False,
                },
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory explicit human acknowledgement of active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, emit JSONL plan without transmitting",
                    "default": True,
                },
                "run_id": {
                    "type": "string",
                    "description": "Explicit run UUID (random if omitted)",
                },
            },
            "required": ["id", "strategy", "ack_active"],
        },
    ),
    types.Tool(
        name="fuzz_replay",
        description=(
            "Active-transmit replay mutation gated by docs/design/active-transmit-safety.md. "
            "Mandatory `ack_active=true`. `dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump capture file"},
                "strategy": {
                    "type": "string",
                    "enum": ["timing", "payload-bitflip"],
                    "description": "Mutation strategy",
                },
                "interface": {
                    "type": "string",
                    "description": "Target CAN interface (required unless dry_run=true)",
                },
                "max": {
                    "type": "integer",
                    "description": "Maximum frames to emit",
                },
                "rate": {"type": "number", "description": "Frames per second", "default": 100.0},
                "seed": {"type": "integer", "description": "Seed for the mutator", "default": 0},
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory explicit human acknowledgement of active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, emit JSONL plan without transmitting",
                    "default": True,
                },
                "run_id": {
                    "type": "string",
                    "description": "Explicit run UUID (random if omitted)",
                },
            },
            "required": ["file", "strategy", "ack_active"],
        },
    ),
    types.Tool(
        name="fuzz_arbitration_id",
        description=(
            "Active-transmit arbitration-id walk gated by docs/design/active-transmit-safety.md. "
            "Mandatory `ack_active=true`. `dry_run` defaults to true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "Target CAN interface"},
                "range": {
                    "type": "string",
                    "description": "Inclusive `<start>:<end>` hex range, e.g. `0x100:0x110`",
                },
                "step": {"type": "integer", "description": "ID step", "default": 1},
                "data": {
                    "type": "string",
                    "description": "Hex payload to send with each ID (default: 8 zero bytes)",
                },
                "rate": {"type": "number", "description": "Frames per second", "default": 100.0},
                "extended": {
                    "type": "boolean",
                    "description": "Walk the 29-bit address space",
                    "default": False,
                },
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory explicit human acknowledgement of active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, emit JSONL plan without transmitting",
                    "default": True,
                },
                "run_id": {
                    "type": "string",
                    "description": "Explicit run UUID (random if omitted)",
                },
            },
            "required": ["range", "ack_active"],
        },
    ),
    types.Tool(
        name="fuzz_signal",
        description=(
            "Active-transmit DBC signal fuzzing gated by docs/design/active-transmit-safety.md. "
            "Mutates a single DBC signal within or beyond its declared bounds. "
            "Mandatory `ack_active=true`. `dry_run` defaults to true; set to false only after "
            "explicit human authorisation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "Target CAN interface"},
                "dbc": {
                    "type": "string",
                    "description": "DBC path or provider ref (e.g. `opendbc:...`)",
                },
                "message": {"type": "string", "description": "DBC message name"},
                "signal": {"type": "string", "description": "Signal name to mutate"},
                "mode": {
                    "type": "string",
                    "enum": ["in_bounds", "out_of_bounds", "boundary", "enum_gaps", "full_field"],
                    "description": (
                        "Mutation mode; full_field sweeps the entire signal field, "
                        "ignoring the declared DBC bounds"
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum mutated frames to emit",
                    "default": 64,
                },
                "rate": {"type": "number", "description": "Frames per second", "default": 100.0},
                "seed": {"type": "integer", "description": "Seed for the mutator", "default": 0},
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory explicit human acknowledgement of active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, emit JSONL plan without transmitting",
                    "default": True,
                },
                "run_id": {
                    "type": "string",
                    "description": "Explicit run UUID (random if omitted)",
                },
            },
            "required": ["dbc", "message", "signal", "mode", "ack_active"],
        },
    ),
    types.Tool(
        name="fuzz_spn",
        description=(
            "Active-transmit J1939 SPN fuzzing gated by docs/design/active-transmit-safety.md. "
            "Mutates a single SPN across its operational range and the J1939 not-available / "
            "error sentinels. Mandatory `ack_active=true`. `dry_run` defaults to true; set to "
            "false only after explicit human authorisation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "Target CAN interface"},
                "spn": {"type": "integer", "description": "J1939 SPN to mutate"},
                "pgn": {
                    "type": "integer",
                    "description": "Expected PGN (validated against the SPN's PGN; derived if omitted)",
                },
                "mode": {
                    "type": "string",
                    "enum": ["in_bounds", "not_available", "error", "out_of_bounds", "boundary"],
                    "description": "Mutation mode; not_available / error emit the J1939 sentinels",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum mutated frames to emit",
                    "default": 64,
                },
                "rate": {"type": "number", "description": "Frames per second", "default": 100.0},
                "seed": {"type": "integer", "description": "Seed for the mutator", "default": 0},
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory explicit human acknowledgement of active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, emit JSONL plan without transmitting",
                    "default": True,
                },
                "run_id": {
                    "type": "string",
                    "description": "Explicit run UUID (random if omitted)",
                },
            },
            "required": ["spn", "mode", "ack_active"],
        },
    ),
    types.Tool(
        name="fuzz_guided",
        description=(
            "Active-transmit response-feedback guided fuzzing gated by "
            "docs/design/active-transmit-safety.md. Mutates payloads on a CAN id and scores "
            "novelty from the target's responses (UDS NRCs, DM1 faults, timing, silence). "
            "Mandatory `ack_active=true`. `dry_run` defaults to true; set to false only after "
            "explicit human authorisation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface": {"type": "string", "description": "Target CAN interface"},
                "id": {
                    "type": "string",
                    "description": "Arbitration id to transmit on (decimal or 0x hex)",
                },
                "extended": {"type": "boolean", "description": "Send on a 29-bit extended id"},
                "signals": {
                    "type": "string",
                    "description": "Comma list of feedback signals (nrc,pos,dm1,timing,silence)",
                },
                "corpus": {
                    "type": "string",
                    "description": "Seed-corpus directory (persisted/reused)",
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Campaign iteration budget",
                    "default": 200,
                },
                "max_seconds": {"type": "number", "description": "Campaign wall-clock budget"},
                "rate": {
                    "type": "number",
                    "description": "Iterations per second",
                    "default": 100.0,
                },
                "seed": {"type": "integer", "description": "Deterministic RNG seed", "default": 0},
                "ack_active": {
                    "type": "boolean",
                    "const": True,
                    "description": "Mandatory explicit human acknowledgement of active transmission",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, plan the campaign without transmitting",
                    "default": True,
                },
            },
            "required": ["id", "ack_active"],
        },
    ),
    types.Tool(
        name="plugins_list",
        description="List discovered CANarchy processor, sink, and input plugins.",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="plugins_info",
        description="Show metadata and configured options for a discovered CANarchy plugin.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Registered plugin name"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="plot",
        description="Plot decoded signal time-series from a capture file. Requires canarchy[plot] (matplotlib/plotly). Returns the output file path and data-point counts.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Path to candump or PCAP capture file"},
                "dbc": {
                    "type": "string",
                    "description": "Database path or provider ref (e.g. opendbc:<name>) for signal decoding",
                },
                "signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Signal names to plot (e.g. ["EngineSpeed", "TorqueMode"])',
                },
                "out": {"type": "string", "description": "Output file path (e.g. /tmp/plot.png)"},
                "format": {
                    "type": "string",
                    "enum": ["png", "svg", "html"],
                    "description": "Output format (default: png)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip the first N frames from the capture file",
                },
                "max_frames": {
                    "type": "integer",
                    "description": "Limit analysis to the first N frames",
                },
                "seconds": {
                    "type": "number",
                    "description": "Limit analysis to the first T seconds of the capture",
                },
            },
            "required": ["file", "dbc", "signals", "out"],
        },
    ),
    types.Tool(
        name="cannelloni_decode",
        description="Decode a captured cannelloni CAN-over-UDP datagram payload file into CAN frame events.",
        inputSchema={
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Path to a raw cannelloni datagram payload file",
                },
            },
            "required": ["file"],
        },
    ),
]

_TOOL_NAMES: frozenset[str] = frozenset(tool.name for tool in _TOOLS)


def _build_argv(tool_name: str, arguments: dict[str, Any]) -> list[str]:
    """Convert an MCP tool name and arguments into a CLI argv list."""
    a = arguments
    match tool_name:
        case "capture":
            argv = ["capture"]
            if a.get("interface"):
                argv.append(a["interface"])
            return argv + ["--json"]
        case "send":
            argv = ["send"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += [a["frame_id"], a["data"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "generate":
            argv = ["generate"]
            if a.get("interface"):
                argv.append(a["interface"])
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
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "simulate":
            argv = ["simulate"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += ["--profile", a["profile"]]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if "duration" in a:
                argv += ["--duration", str(a["duration"])]
            if "seed" in a:
                argv += ["--seed", str(a["seed"])]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
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
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "replay":
            argv = ["replay"]
            if a.get("file"):
                argv += ["--file", a["file"]]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if a.get("interface"):
                argv += ["--interface", a["interface"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "sequence_replay":
            argv = ["sequence", "replay", "--file", a["file"]]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if a.get("interface"):
                argv += ["--interface", a["interface"]]
            if a.get("loop"):
                argv += ["--loop"]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "filter":
            argv = ["filter", a["expression"], "--file", a["file"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "stats":
            argv = ["stats", "--file", a["file"]]
            if a.get("top") is not None:
                argv += ["--top", str(a["top"])]
            if a.get("pgn") is not None:
                argv += ["--pgn", str(a["pgn"])]
            if a.get("sa"):
                argv += ["--sa", str(a["sa"])]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "capture_info":
            return ["capture-info", "--file", a["file"], "--json"]
        case "decode":
            argv = ["decode", "--file", a["file"], "--dbc", a["dbc"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "encode":
            argv = ["encode", "--dbc", a["dbc"], a["message"]]
            argv += a.get("signals", [])
            return argv + ["--json"]
        case "dbc_inspect":
            argv = ["dbc", "inspect", a["dbc"]]
            if a.get("message"):
                argv += ["--message", a["message"]]
            if a.get("signals_only"):
                argv.append("--signals-only")
            if a.get("search"):
                argv += ["--search", a["search"]]
            if a.get("layout"):
                argv.append("--layout")
            return argv + ["--json"]
        case "dbc_signals":
            argv = ["dbc", "signals", a["dbc"]]
            if a.get("message"):
                argv += ["--message", a["message"]]
            if a.get("search"):
                argv += ["--search", a["search"]]
            return argv + ["--json"]
        case "dbc_convert":
            argv = ["dbc", "convert", a["dbc"], "--to", a["to"]]
            if a.get("out"):
                argv += ["--out", a["out"]]
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
            argv = ["j1939", "decode", "--file", a["file"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_pgn":
            argv = ["j1939", "pgn", str(a["pgn"])]
            if a.get("file"):
                argv += ["--file", a["file"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_spn":
            argv = ["j1939", "spn", str(a["spn"])]
            if a.get("file"):
                argv += ["--file", a["file"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_tp":
            argv = ["j1939", "tp", "sessions", "--file", a["file"]]
            if a.get("pgn") is not None:
                argv += ["--pgn", str(a["pgn"])]
            if a.get("sa"):
                argv += ["--sa", a["sa"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_tp_compare":
            argv = ["j1939", "tp", "compare", "--file", a["file"], "--sa", a["sa"]]
            if a.get("pgn") is not None:
                argv += ["--pgn", str(a["pgn"])]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_dm1":
            argv = ["j1939", "dm1", "--file", a["file"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_faults":
            argv = ["j1939", "faults", "--file", a["file"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_summary":
            argv = ["j1939", "summary", "--file", a["file"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_inventory":
            argv = ["j1939", "inventory", "--file", a["file"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_compare":
            argv = ["j1939", "compare"] + [str(file) for file in a["files"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1939_map":
            argv = ["j1939", "map", "--file", a["file"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "uds_scan":
            argv = ["uds", "scan"]
            if a.get("interface"):
                argv.append(a["interface"])
            return argv + ["--json"]
        case "uds_trace":
            argv = ["uds", "trace"]
            if a.get("interface"):
                argv.append(a["interface"])
            return argv + ["--json"]
        case "uds_services":
            return ["uds", "services", "--json"]
        case "xcp_scan":
            argv = ["xcp", "scan"]
            if a.get("interface"):
                argv.append(a["interface"])
            if a.get("request_id"):
                argv += ["--request-id", str(a["request_id"])]
            if a.get("response_id"):
                argv += ["--response-id", str(a["response_id"])]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "xcp_trace":
            argv = ["xcp", "trace"]
            if a.get("interface"):
                argv.append(a["interface"])
            if a.get("request_id"):
                argv += ["--request-id", str(a["request_id"])]
            if a.get("response_id"):
                argv += ["--response-id", str(a["response_id"])]
            return argv + ["--json"]
        case "xcp_read":
            argv = ["xcp", "read"]
            if a.get("interface"):
                argv.append(a["interface"])
            if a.get("response_id"):
                argv += ["--response-id", str(a["response_id"])]
            return argv + ["--json"]
        case "xcp_commands":
            return ["xcp", "commands", "--json"]
        case "j1587_decode":
            argv = ["j1587", "decode", "--file", a["file"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j1587_pids":
            return ["j1587", "pids", "--json"]
        case "j2497_decode":
            argv = ["j2497", "decode", "--file", a["file"]]
            if a.get("offset") is not None and a["offset"] > 0:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "j2497_mids":
            return ["j2497", "mids", "--json"]
        case "config_show":
            return ["config", "show", "--json"]
        case "doctor":
            return ["doctor", "--json"]
        case "datasets_provider_list":
            return ["datasets", "provider", "list", "--json"]
        case "datasets_search":
            argv = ["datasets", "search"]
            if a.get("query"):
                argv.append(a["query"])
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            if "limit" in a:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "datasets_inspect":
            return ["datasets", "inspect", a["ref"], "--json"]
        case "datasets_fetch":
            return ["datasets", "fetch", a["ref"], "--json"]
        case "datasets_cache_list":
            return ["datasets", "cache", "list", "--json"]
        case "datasets_cache_refresh":
            argv = ["datasets", "cache", "refresh"]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            return argv + ["--json"]
        case "datasets_convert":
            argv = [
                "datasets",
                "convert",
                a["file"],
                "--source-format",
                a["source_format"],
                "--format",
                a["format"],
            ]
            if a.get("output"):
                argv += ["--output", a["output"]]
            return argv + ["--json"]
        case "datasets_replay_plan":
            argv = ["datasets", "replay", a["source"]]
            if a.get("format"):
                argv += ["--format", a["format"]]
            if a.get("file"):
                argv += ["--file", a["file"]]
            if a.get("platform"):
                argv += ["--platform", a["platform"]]
            if a.get("limit") is not None:
                argv += ["--limit", str(a["limit"])]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("max_seconds") is not None:
                argv += ["--max-seconds", str(a["max_seconds"])]
            return argv + ["--dry-run", "--json"]
        case "datasets_replay_files":
            argv = ["datasets", "replay", a["source"], "--list-files"]
            if a.get("platform"):
                argv += ["--platform", a["platform"]]
            if a.get("limit") is not None:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "skills_provider_list":
            return ["skills", "provider", "list", "--json"]
        case "skills_search":
            argv = ["skills", "search", a["query"]]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            if "limit" in a:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "skills_fetch":
            return ["skills", "fetch", a["ref"], "--json"]
        case "skills_cache_list":
            return ["skills", "cache", "list", "--json"]
        case "skills_cache_refresh":
            argv = ["skills", "cache", "refresh"]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            return argv + ["--json"]
        case "dbc_provider_list":
            return ["dbc", "provider", "list", "--json"]
        case "dbc_search":
            argv = ["dbc", "search", a["query"]]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            if "limit" in a:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "dbc_fetch":
            return ["dbc", "fetch", a["ref"], "--json"]
        case "dbc_cache_list":
            return ["dbc", "cache", "list", "--json"]
        case "dbc_cache_prune":
            argv = ["dbc", "cache", "prune"]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            return argv + ["--json"]
        case "dbc_cache_refresh":
            argv = ["dbc", "cache", "refresh"]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            return argv + ["--json"]
        case "re_signals":
            return ["re", "signals", a["file"], "--json"]
        case "re_correlate":
            return ["re", "correlate", a["file"], "--reference", a["reference"], "--json"]
        case "re_anomalies":
            argv = ["re", "anomalies", a["file"]]
            if a.get("baseline"):
                argv += ["--baseline", a["baseline"]]
            if a.get("dbc"):
                argv += ["--dbc", a["dbc"]]
            if "z_threshold" in a:
                argv += ["--z-threshold", str(a["z_threshold"])]
            if "cv_max" in a:
                argv += ["--cv-max", str(a["cv_max"])]
            if a.get("min_samples") is not None:
                argv += ["--min-samples", str(a["min_samples"])]
            if a.get("offset"):
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "re_counters":
            return ["re", "counters", a["file"], "--json"]
        case "re_entropy":
            return ["re", "entropy", a["file"], "--json"]
        case "re_match_dbc":
            argv = ["re", "match-dbc", a["capture"]]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            if "limit" in a:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "re_shortlist_dbc":
            argv = ["re", "shortlist-dbc", a["capture"], "--make", a["make"]]
            if a.get("provider"):
                argv += ["--provider", a["provider"]]
            if "limit" in a:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "re_corpus":
            argv = ["re", "corpus"] + a["files"]
            if a.get("offset") is not None:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            return argv + ["--json"]
        case "re_suggest":
            argv = ["re", "suggest", a["file"]]
            if a.get("reference_dbc"):
                argv += ["--reference-dbc", a["reference_dbc"]]
            if a.get("limit") is not None:
                argv += ["--limit", str(a["limit"])]
            return argv + ["--json"]
        case "fuzz_payload":
            argv = ["fuzz", "payload"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += ["--id", a["id"], "--strategy", a["strategy"]]
            if "data" in a:
                argv += ["--data", a["data"]]
            if "dlc" in a:
                argv += ["--dlc", str(a["dlc"])]
            if a.get("corpus"):
                argv += ["--corpus", a["corpus"]]
            if "max" in a:
                argv += ["--max", str(a["max"])]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if "seed" in a:
                argv += ["--seed", str(a["seed"])]
            if a.get("extended"):
                argv += ["--extended"]
            if "run_id" in a:
                argv += ["--run-id", a["run_id"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--jsonl"]
        case "fuzz_replay":
            argv = ["fuzz", "replay", "--file", a["file"], "--strategy", a["strategy"]]
            if "interface" in a:
                argv += ["--interface", a["interface"]]
            if "max" in a:
                argv += ["--max", str(a["max"])]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if "seed" in a:
                argv += ["--seed", str(a["seed"])]
            if "run_id" in a:
                argv += ["--run-id", a["run_id"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--jsonl"]
        case "fuzz_arbitration_id":
            argv = ["fuzz", "arbitration-id"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += ["--range", a["range"]]
            if "step" in a:
                argv += ["--step", str(a["step"])]
            if "data" in a:
                argv += ["--data", a["data"]]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if a.get("extended"):
                argv += ["--extended"]
            if "run_id" in a:
                argv += ["--run-id", a["run_id"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--jsonl"]
        case "fuzz_signal":
            argv = ["fuzz", "signal"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += [
                "--dbc",
                a["dbc"],
                "--message",
                a["message"],
                "--signal",
                a["signal"],
                "--mode",
                a["mode"],
            ]
            if "count" in a:
                argv += ["--count", str(a["count"])]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if "seed" in a:
                argv += ["--seed", str(a["seed"])]
            if "run_id" in a:
                argv += ["--run-id", a["run_id"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--jsonl"]
        case "fuzz_spn":
            argv = ["fuzz", "spn"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += ["--spn", str(a["spn"]), "--mode", a["mode"]]
            if a.get("pgn") is not None:
                argv += ["--pgn", str(a["pgn"])]
            if "count" in a:
                argv += ["--count", str(a["count"])]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if "seed" in a:
                argv += ["--seed", str(a["seed"])]
            if "run_id" in a:
                argv += ["--run-id", a["run_id"]]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--jsonl"]
        case "fuzz_guided":
            argv = ["fuzz", "guided"]
            if a.get("interface"):
                argv.append(a["interface"])
            argv += ["--id", str(a["id"])]
            if a.get("extended"):
                argv.append("--extended")
            if a.get("signals"):
                argv += ["--signals", str(a["signals"])]
            if a.get("corpus"):
                argv += ["--corpus", str(a["corpus"])]
            if a.get("max_iterations") is not None:
                argv += ["--max-iterations", str(a["max_iterations"])]
            if a.get("max_seconds") is not None:
                argv += ["--max-seconds", str(a["max_seconds"])]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if "seed" in a:
                argv += ["--seed", str(a["seed"])]
            if a.get("ack_active"):
                argv += ["--ack-active"]
            if a.get("dry_run", True):
                argv += ["--dry-run"]
            return argv + ["--json"]
        case "plugins_list":
            return ["plugins", "list", "--json"]
        case "plugins_info":
            return ["plugins", "info", a["name"], "--json"]
        case "cannelloni_decode":
            return ["cannelloni", "decode", "--file", a["file"], "--json"]
        case "plot":
            argv = ["plot", "--dbc", a["dbc"], "--out", a["out"]]
            for sig in a.get("signals", []):
                argv += ["--signal", sig]
            if a.get("format"):
                argv += ["--format", a["format"]]
            if a.get("offset") is not None:
                argv += ["--offset", str(a["offset"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("seconds") is not None:
                argv += ["--seconds", str(a["seconds"])]
            argv += ["--file", a["file"]]
            return argv + ["--json"]
        case _:
            raise ValueError(f"Unknown tool: {tool_name!r}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _TOOLS


_ACTIVE_TRANSMIT_TOOLS: frozenset[str] = frozenset(
    {
        "send",
        "generate",
        "simulate",
        "gateway",
        "fuzz_payload",
        "fuzz_replay",
        "fuzz_arbitration_id",
        "fuzz_signal",
        "fuzz_spn",
        "replay",
        "sequence_replay",
        "xcp_scan",
        "fuzz_guided",
    }
)


# --- Response bounding (#405) -----------------------------------------------
#
# The stdio transport (and the agent on the other end of it) cannot absorb an
# unbounded tool result: a single high-rate per-frame command can serialize to
# tens of megabytes and tear down the session. Every response is therefore
# bounded to `_response_byte_limit()` bytes; oversized list-shaped data is
# truncated with an explicit marker and total counts, and anything that still
# cannot fit is replaced by a stub envelope rather than crashing the server.

_DEFAULT_MAX_RESPONSE_BYTES = 512_000
# Reserve headroom for the truncation marker added after trimming.
_TRUNCATION_MARKER_RESERVE = 4_096
_TRUNCATION_HINT = (
    "The response exceeded the MCP output cap and was truncated. Re-run the "
    "equivalent canarchy CLI command for the full result, or bound the input "
    "with max_frames/seconds."
)


def _response_byte_limit() -> int:
    raw = os.environ.get("CANARCHY_MCP_MAX_RESPONSE_BYTES", "")
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_RESPONSE_BYTES
    return value if value > 0 else _DEFAULT_MAX_RESPONSE_BYTES


def _list_slots(node: Any, path: str, slots: list[tuple[Any, Any, str, int]]) -> None:
    """Collect (container, key, path, length) for every list reachable in node."""
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(value, list):
                slots.append((node, key, child_path, len(value)))
            _list_slots(value, child_path, slots)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _list_slots(value, f"{path}[{index}]", slots)


def _payload_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, sort_keys=True).encode("utf-8"))


def bound_payload(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Return ``payload`` reduced to fit in ``max_bytes`` of serialized JSON.

    Oversized payloads are trimmed by repeatedly halving the longest list in
    ``data``; each trimmed list is recorded with its original total so an
    agent can distinguish "truncated" from "zero matches". If no list can be
    trimmed further, ``data`` is replaced by a stub. The envelope itself
    (``ok`` / ``command`` / ``warnings`` / ``errors``) is always preserved.
    """
    if _payload_bytes(payload) <= max_bytes:
        return payload

    payload = copy.deepcopy(payload)
    budget = max(max_bytes - _TRUNCATION_MARKER_RESERVE, 1_024)
    truncated_lists: dict[str, dict[str, int]] = {}

    while _payload_bytes(payload) > budget:
        slots: list[tuple[Any, Any, str, int]] = []
        _list_slots(payload.get("data", {}), "data", slots)
        trimmable = [slot for slot in slots if slot[3] > 0]
        if not trimmable:
            # No list left to trim (e.g. one enormous string): keep the
            # envelope, drop the data block, and say so explicitly.
            payload["data"] = {
                "truncated": True,
                "truncation": {
                    "max_response_bytes": max_bytes,
                    "reason": "non-list data exceeded the output cap",
                    "hint": _TRUNCATION_HINT,
                },
            }
            break
        container, key, path, length = max(trimmable, key=lambda slot: slot[3])
        keep = length // 2
        truncated_lists.setdefault(path, {"total_items": length})
        truncated_lists[path]["returned_items"] = keep
        container[key] = container[key][:keep]

    if truncated_lists:
        data = payload.get("data")
        if isinstance(data, dict):
            data["truncated"] = True
            data["truncation"] = {
                "max_response_bytes": max_bytes,
                "hint": _TRUNCATION_HINT,
                "lists": [
                    {"path": path, **counts} for path, counts in sorted(truncated_lists.items())
                ],
            }
        warnings = payload.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(_TRUNCATION_HINT)

    return payload


def _tool_execution_error_payload(name: str, exc: BaseException) -> dict[str, Any]:
    """Canonical envelope for an unexpected in-tool failure (REQ: isolation)."""
    return {
        "ok": False,
        "command": name,
        "data": {},
        "warnings": [],
        "errors": [
            {
                "code": "TOOL_EXECUTION_ERROR",
                "message": f"{type(exc).__name__}: {exc}",
                "hint": (
                    "The canarchy MCP server caught this error; the session and the "
                    "other tools remain usable. Check the tool arguments or run the "
                    "equivalent CLI command for full diagnostics."
                ),
            }
        ],
    }


def _is_doip_interface(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("doip://")


def _doip_excluded_payload(name: str) -> dict[str, Any]:
    """Envelope refusing a DoIP target on the MCP `uds_scan` / `uds_trace` tools."""
    return {
        "ok": False,
        "command": name,
        "data": {},
        "warnings": [],
        "errors": [
            {
                "code": "DOIP_MCP_EXCLUDED",
                "message": (
                    "DoIP diagnostic workflows perform active TCP egress to an arbitrary "
                    "network host and are not exposed through the MCP server."
                ),
                "hint": (
                    "Run `canarchy uds scan|trace doip://<host>:<port>?logical_address=0x...` "
                    "from the CLI as an operator action."
                ),
            }
        ],
    }


def _missing_ack_active_payload(name: str) -> dict[str, Any]:
    """Canonical envelope for an MCP active-transmit call without `ack_active=true`."""
    return {
        "ok": False,
        "command": name,
        "data": {},
        "warnings": [],
        "errors": [
            {
                "code": "ACTIVE_TRANSMIT_REQUIRES_ACK",
                "message": (
                    "MCP active-transmit tools require an explicit `ack_active=true` argument."
                ),
                "hint": (
                    "Re-call the tool with `ack_active=true` (and `dry_run=true` unless an "
                    "operator has authorised live transmission)."
                ),
            }
        ],
    }


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    if name not in _TOOL_NAMES:
        raise ValueError(f"Unknown tool: {name!r}")
    args = arguments or {}
    if name in ("uds_scan", "uds_trace") and _is_doip_interface(args.get("interface")):
        # Active TCP egress to an arbitrary host is a CLI-only operator action,
        # consistent with the `cannelloni send` exclusion. See the "Excluded"
        # table in docs/design/mcp-server.md.
        payload = _doip_excluded_payload(name)
        return [types.TextContent(type="text", text=json.dumps(payload, sort_keys=True))]
    if name in _ACTIVE_TRANSMIT_TOOLS:
        # The CLI surface already enforces `--ack-active`; the MCP gate
        # is the *separate* opt-in token that prevents a confused agent
        # from invoking an active tool without an explicit YES from its
        # operator. See `docs/design/active-transmit-safety.md`
        # `REQ-ATS-11` / `REQ-ATS-12`.
        if args.get("ack_active") is not True:
            payload = _missing_ack_active_payload(name)
            return [types.TextContent(type="text", text=json.dumps(payload, sort_keys=True))]
        # Default dry_run=true for agent-initiated calls (REQ-ATS-13).
        # The argv builder respects an explicit `dry_run=false` and
        # otherwise emits --dry-run.
        args.setdefault("dry_run", True)
    # Isolate per-tool failures: an exception or oversized result from one
    # call must never tear down the stdio transport for the whole session
    # (#405). Anything raised here is converted into a structured error
    # envelope instead of propagating to the protocol layer.
    try:
        argv = _build_argv(name, args)
        _, result = await asyncio.to_thread(execute_command, argv)
        if result is None:
            payload = {
                "ok": False,
                "command": name,
                "data": {},
                "warnings": [],
                "errors": [{"code": "NO_RESULT", "message": "Command returned no result"}],
            }
        else:
            payload = result.to_payload()
        # A parse-level CLI failure (e.g. INVALID_ARGUMENTS) is reported by the
        # CLI under the generic command name "cli", since argparse failed before
        # a subcommand was resolved. Relabel it with the tool the agent actually
        # invoked so errors are attributable programmatically (#446).
        if isinstance(payload, dict) and payload.get("command") == "cli":
            payload["command"] = name
        payload = bound_payload(payload, _response_byte_limit())
    except Exception as exc:  # noqa: BLE001 - isolation boundary by design
        payload = _tool_execution_error_payload(name, exc)
    return [types.TextContent(type="text", text=json.dumps(payload, sort_keys=True))]


def run_server() -> None:
    # The MCP stdio server owns `sys.stdin` / `sys.stdout` as the
    # JSON-RPC protocol stream. Any CLI command we invoke from inside
    # `handle_call_tool` must NOT block on `sys.stdin.readline()` —
    # that would consume protocol bytes and destabilise the session.
    # Setting this flag tells `cli.enforce_active_transmit_safety` to
    # treat `--ack-active` itself as the operator acknowledgement
    # without prompting (REQ-ATS-03 / REQ-ATS-11 in
    # `docs/design/active-transmit-safety.md`). `setdefault` so external
    # operators can already have set it explicitly without us clobbering
    # their choice.
    os.environ.setdefault("CANARCHY_MCP_NONINTERACTIVE_ACK", "1")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop_event = asyncio.Event()

    async def run_with_shutdown() -> None:
        server_task: asyncio.Task | None = None

        def signal_handler() -> None:
            stop_event.set()
            if server_task and not server_task.done():
                server_task.cancel()
            # anyio's to_thread.run_sync wraps stdin readline() in a shielded
            # cancel scope — cleanup blocks until readline() returns, which on a
            # tty means waiting for the user to press Enter.  Use SIGALRM as an
            # OS-level escape hatch: it fires unconditionally after 2 s and
            # does not depend on the asyncio event loop processing callbacks.
            signal.signal(signal.SIGALRM, lambda _s, _f: os._exit(0))
            signal.alarm(2)
            try:
                os.close(0)
            except OSError:
                pass

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                server_task = asyncio.create_task(
                    server.run(
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
                )

                stop_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait(
                    [server_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if server_task in done:
                    stop_task.cancel()
                    return

                server_task.cancel()
                stop_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
        except BaseExceptionGroup:
            # mcp's stdin_reader catches parse errors and tries to forward them
            # into read_stream_writer; if server_task was already cancelled the
            # stream is closed, raising BrokenResourceError.  The mcp library
            # only guards against ClosedResourceError, so this leaks as a
            # BaseExceptionGroup.  Suppress it — we're shutting down anyway.
            pass

    try:
        loop.run_until_complete(run_with_shutdown())
    finally:
        loop.close()
