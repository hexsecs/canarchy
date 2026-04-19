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

| ID | Requirement |
|----|-------------|
| `REQ-MCP-01` | The system shall provide a `canarchy mcp serve` subcommand that starts an MCP server over stdio. |
| `REQ-MCP-02` | Each implemented CLI command shall surface as an MCP tool whose name is the command string with spaces replaced by underscores (e.g. `j1939 monitor` → `j1939_monitor`). |
| `REQ-MCP-03` | Each tool's input schema shall be derived from the argparse parameter definitions for the corresponding CLI command. |
| `REQ-MCP-04` | Tool responses shall return the canonical command result envelope (`ok`, `command`, `data`, `warnings`, `errors`) serialised as JSON text content. |
| `REQ-MCP-05` | Invalid tool inputs that would produce CLI user errors shall return the same structured error codes as the CLI (e.g. `INVALID_FRAME_ID`, `INVALID_RATE`). |
| `REQ-MCP-06` | Tool discovery (`list_tools`) shall return all implemented tools with name, description, and input schema. |
| `REQ-MCP-07` | The MCP server shall use stdio transport only (v1 scope). |
| `REQ-MCP-08` | Calling an unregistered tool name shall raise an error indicating the tool is unknown. |
| `REQ-MCP-09` | The `mcp` package shall be declared as a project dependency in `pyproject.toml`. |
| `REQ-MCP-10` | The server shall not expose `shell` or `tui` commands as MCP tools; those are interactive front-end commands with no RPC equivalent. |

## Command Surface

```text
canarchy mcp serve
```

The `serve` subcommand accepts no positional arguments or output flags. The server runs until the stdio transport closes (client disconnect or EOF).

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
| `decode` | `decode` |
| `encode` | `encode` |
| `export` | `export` |
| `session save` | `session_save` |
| `session load` | `session_load` |
| `session show` | `session_show` |
| `j1939 monitor` | `j1939_monitor` |
| `j1939 decode` | `j1939_decode` |
| `j1939 pgn` | `j1939_pgn` |
| `j1939 spn` | `j1939_spn` |
| `j1939 tp` | `j1939_tp` |
| `j1939 dm1` | `j1939_dm1` |
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
       └─ call_tool(name, args)
            ├─ _build_argv(name, args) → CLI argv list
            └─ execute_command(argv)  → CommandResult
                                          │ .to_payload()
                                          ▼
                                     TextContent(JSON)
```

The server delegates directly to `execute_command()` from `cli.py`, so all validation, error handling, and output formatting logic is shared with the CLI. No protocol logic is duplicated.

## Responsibilities And Boundaries

In scope:

* stdio MCP transport only
* buffered (non-streaming) tool responses for all commands including live-capture variants (scaffold backend returns a fixed event batch)
* full implemented command surface excluding interactive front ends (`shell`, `tui`)

Out of scope:

* HTTP/SSE transport
* streaming tool responses / MCP notifications for live capture
* authentication or access control
* plugin or custom tool registration
