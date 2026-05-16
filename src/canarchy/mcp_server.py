"""MCP server — exposes CANarchy CLI commands as Model Context Protocol tools over stdio."""

from __future__ import annotations

import asyncio
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
                "frame_id": {
                    "type": "string",
                    "description": "Frame ID as hex (e.g. 0x123 or 291)",
                },
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
                "rate": {
                    "type": "number",
                    "description": "Playback rate multiplier",
                    "default": 1.0,
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
            },
            "required": ["dbc"],
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
        description="Inspect a specific J1939 PGN within a capture file. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "pgn": {"type": "integer", "description": "J1939 PGN value (0–262143)"},
                "file": {"type": "string", "description": "Path to candump capture file"},
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
            "required": ["pgn", "file"],
        },
    ),
    types.Tool(
        name="j1939_spn",
        description="Inspect a specific J1939 SPN within a capture file. Use max_frames or seconds to limit processing on large captures.",
        inputSchema={
            "type": "object",
            "properties": {
                "spn": {"type": "integer", "description": "J1939 SPN value (non-negative integer)"},
                "file": {"type": "string", "description": "Path to candump capture file"},
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
            "required": ["spn", "file"],
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
                    "enum": ["hcrl-csv"],
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
            argv = ["replay"]
            if a.get("file"):
                argv += ["--file", a["file"]]
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
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
            argv = ["j1939", "pgn", str(a["pgn"]), "--file", a["file"]]
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
            argv = ["j1939", "spn", str(a["spn"]), "--file", a["file"]]
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
        case "uds_scan":
            return ["uds", "scan", a["interface"], "--json"]
        case "uds_trace":
            return ["uds", "trace", a["interface"], "--json"]
        case "uds_services":
            return ["uds", "services", "--json"]
        case "config_show":
            return ["config", "show", "--json"]
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
            if "rate" in a:
                argv += ["--rate", str(a["rate"])]
            if a.get("max_frames") is not None:
                argv += ["--max-frames", str(a["max_frames"])]
            if a.get("max_seconds") is not None:
                argv += ["--max-seconds", str(a["max_seconds"])]
            return argv + ["--dry-run", "--json"]
        case "datasets_replay_files":
            return ["datasets", "replay", a["source"], "--list-files", "--json"]
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
        case _:
            raise ValueError(f"Unknown tool: {tool_name!r}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    if name not in _TOOL_NAMES:
        raise ValueError(f"Unknown tool: {name!r}")
    argv = _build_argv(name, arguments or {})
    _, result = await asyncio.to_thread(execute_command, argv)
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
