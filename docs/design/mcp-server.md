# Design Spec: MCP Server

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy mcp serve` |
| Primary area | CLI, agent integration |

## Goal

Expose the CANarchy command surface as a native Model Context Protocol (MCP) server so agents can invoke CANarchy tools directly over the MCP wire protocol instead of spawning subprocesses and parsing stdout.

## User-Facing Motivation

Agents that already call tools via MCP (Claude, OpenCode, etc.) can integrate CANarchy without subprocess overhead or fragile stdout parsing. The MCP server turns CANarchy into a first-class tool-call surface: structured inputs, structured outputs, consistent error codes, and tool discovery built into the protocol.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-MCP-01` | Ubiquitous | The system shall provide a `canarchy mcp serve` subcommand that starts an MCP server over stdio. |
| `REQ-MCP-02` | Ubiquitous | Each command selected for the MCP surface shall surface as an MCP tool whose name is the command string with spaces replaced by underscores (e.g. `j1939 monitor` → `j1939_monitor`). |
| `REQ-MCP-03` | Ubiquitous | Each MCP tool's input schema shall be derived from the argparse parameter definitions of the corresponding CLI command. |
| `REQ-MCP-04` | Event-driven | When an MCP tool call is received, the system shall return the canonical command result envelope (`ok`, `command`, `data`, `warnings`, `errors`) serialised as JSON text content. |
| `REQ-MCP-05` | Event-driven | When an MCP tool call is received with invalid inputs, the system shall return the same structured error codes as the equivalent CLI invocation. |
| `REQ-MCP-06` | Event-driven | When a `list_tools` request is received, the system shall return all registered MCP tools with name, description, and input schema. |
| `REQ-MCP-07` | Ubiquitous | The MCP server shall use stdio transport only. |
| `REQ-MCP-08` | Unwanted behaviour | If a `call_tool` request names an unregistered tool, the system shall raise an error indicating the tool is unknown. |
| `REQ-MCP-09` | Ubiquitous | The `mcp` package shall be declared as a project dependency in `pyproject.toml`. |
| `REQ-MCP-10` | Ubiquitous | The server shall not expose `shell` or `tui` as MCP tools; those are interactive front-end commands with no RPC equivalent. |
| `REQ-MCP-11` | Event-driven | The `call_tool` handler shall execute `execute_command` in a thread pool via `asyncio.to_thread` so that the asyncio event loop is not blocked during file I/O or analysis, preventing MCP keepalive timeouts on large captures. |
| `REQ-MCP-12` | Ubiquitous | File-backed J1939 tools (`j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_dm1`, `j1939_summary`, `j1939_inventory`) shall expose optional `max_frames` (integer) and `seconds` (number) parameters that bound analysis to the first N frames or first T seconds of the capture, respectively. |

## Command Surface

```text
canarchy mcp serve
```

The `serve` subcommand accepts no positional arguments or output flags. The server runs until the stdio transport closes (client disconnect or EOF).

The current MCP tool surface is a curated non-interactive subset of the CLI. It intentionally excludes interactive commands and some newer command families that do not yet have MCP adapters. Skills are not exposed as MCP tools, resources, or prompts in phase 1; agents discover and fetch skills through the CLI provider workflow before optionally using MCP for individual referenced commands that are already exposed.

## Tool Naming Convention

| CLI command | MCP tool name |
|-------------|--------------|
| `capture` | `capture` |
| `send` | `send` |
| `generate` | `generate` |
| `gateway` | `gateway` |
| `replay` | `replay` |
| `filter` | `filter` |
| `stats` | `stats` |
| `capture-info` | `capture_info` |
| `decode` | `decode` |
| `encode` | `encode` |
| `dbc inspect` | `dbc_inspect` |
| `export` | `export` |
| `session save` | `session_save` |
| `session load` | `session_load` |
| `session show` | `session_show` |
| `j1939 monitor` | `j1939_monitor` |
| `j1939 decode` | `j1939_decode` |
| `j1939 pgn` | `j1939_pgn` |
| `j1939 spn` | `j1939_spn` |
| `j1939 tp sessions` | `j1939_tp` |
| `j1939 dm1` | `j1939_dm1` |
| `j1939 summary` | `j1939_summary` |
| `j1939 inventory` | `j1939_inventory` |
| `uds scan` | `uds_scan` |
| `uds trace` | `uds_trace` |
| `uds services` | `uds_services` |
| `config show` | `config_show` |

## Response Envelope

Every tool call returns a single `TextContent` item whose `text` field is a JSON object with the canonical command result shape:

```json
{
  "ok": true,
  "command": "<cli-command-string>",
  "data": { "events": [...], ... },
  "warnings": [],
  "errors": []
}
```

Error responses set `"ok": false` and populate `errors` with structured error objects (`code`, `message`, optional `hint`), matching CLI exit-code semantics exactly.

## Architecture

```
Agent / MCP client
       │  stdio (JSON-RPC 2.0)
       ▼
canarchy mcp serve
  └─ mcp_server.py
       ├─ list_tools()     → returns _TOOLS catalogue
       └─ call_tool(name, args)          [async]
            ├─ _build_argv(name, args) → CLI argv list
            └─ asyncio.to_thread(execute_command, argv)
                 └─ execute_command(argv)  → CommandResult   [thread pool]
                                               │ .to_payload()
                                               ▼
                                          TextContent(JSON)
```

The server delegates directly to `execute_command()` from `cli.py`, so all validation, error handling, and output formatting logic is shared with the CLI. No protocol logic is duplicated.

`execute_command` runs in a thread pool via `asyncio.to_thread` so the asyncio event loop remains live during file I/O. Without this, processing a large capture file would block the event loop, preventing MCP keepalive messages from being handled and causing client-side timeout errors (`-32001`/`-32000`).

## Responsibilities And Boundaries

In scope:

* stdio MCP transport only
* buffered (non-streaming) tool responses for all commands including live-capture variants (scaffold backend returns a fixed event batch)
* a curated non-interactive CLI subset covering transport, protocol, export, session, and configuration workflows

Out of scope:

* HTTP/SSE transport
* streaming tool responses / MCP notifications for live capture
* authentication or access control
* plugin or custom tool registration
* exposing every implemented CLI command automatically
* exposing CANarchy skills as MCP tools, resources, prompts, or a separate MCP discovery surface in phase 1
