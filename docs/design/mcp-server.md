# Design Spec: MCP Server

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy mcp serve` |
| Primary area | CLI, agent integration |
| Coverage audit | #323 (matrix in *MCP Coverage Decisions* below) |

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
| `REQ-MCP-12` | Ubiquitous | File-backed J1939 tools (`j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_tp_compare`, `j1939_dm1`, `j1939_faults`, `j1939_summary`, `j1939_inventory`, `j1939_compare`, `j1939_map`) shall expose optional `max_frames` (integer) and `seconds` (number) parameters that bound analysis to the first N frames or first T seconds of the capture, respectively. |
| `REQ-MCP-13` | Ubiquitous | Dataset provider workflows selected for MCP shall expose provider list, search, inspect, fetch, cache list, cache refresh, conversion, replay file listing, and safe replay planning tools while excluding streaming dataset frame output. |
| `REQ-MCP-14` | Ubiquitous | Skills provider workflows selected for MCP shall expose provider list, search, fetch, cache list, and cache refresh tools while preserving the same CLI result envelope. |
| `REQ-MCP-15` | Ubiquitous | Reverse-engineering helpers selected for MCP shall include `re signals`, `re counters`, `re entropy`, `re correlate`, `re match-dbc`, `re shortlist-dbc`, and `re suggest` (heuristic path only; the external `--llm` enrichment is CLI-only). |
| `REQ-MCP-16` | Ubiquitous | Every implemented CLI command shall be either exposed as an MCP tool or listed in the documented exclusion set (`shell`, `tui`, `mcp serve`, `mcp install`, `completion`, `datasets stream`, `datasets download`, `dbc generate-c`); a test shall enforce this invariant so new commands cannot silently drift out of coverage. |
| `REQ-MCP-20` | Ubiquitous | No tool response shall exceed the configured output cap (`CANARCHY_MCP_MAX_RESPONSE_BYTES`, default 512000 bytes). Oversized list-shaped data shall be truncated with `data.truncated: true` and a `data.truncation` block recording, per trimmed list, the original `total_items` and `returned_items`, plus a hint pointing at the CLI for the full result; data that cannot be reduced by list truncation shall be replaced by a stub that preserves the envelope. |
| `REQ-MCP-21` | Unwanted behaviour | If a tool call raises an unexpected exception, the server shall return a canonical envelope with error code `TOOL_EXECUTION_ERROR` instead of propagating the exception to the stdio transport, so one failing or oversized call never makes the remaining tools unavailable for the session. |
| `REQ-MCP-22` | Ubiquitous | A tool's parameter surface shall match the underlying CLI command's flags: every flag `_build_argv` forwards shall be a real option of the target command (enforced by a contract test over all tools), and the `stats` tool shall expose the same `top`/`sa`/`pgn` knobs the CLI offers. |
| `REQ-MCP-23` | Unwanted behaviour | When a relayed CLI result reports the generic command name `cli` (a parse-level failure that occurs before a subcommand resolves), the server shall relabel the envelope's `command` field with the invoked tool name so errors remain programmatically attributable. |

## Command Surface

```text
canarchy mcp serve
```

The `serve` subcommand accepts no positional arguments or output flags. The server runs until the stdio transport closes (client disconnect or EOF).

The current MCP tool surface is a curated non-interactive subset of the CLI. It intentionally excludes interactive commands and streaming workflows that do not fit MCP's buffered tool-response model.

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
| `compare` | `compare` |
| `capture-info` | `capture_info` |
| `decode` | `decode` |
| `encode` | `encode` |
| `dbc inspect` | `dbc_inspect` |
| `dbc signals` | `dbc_signals` |
| `dbc convert` | `dbc_convert` |
| `dbc provider list` | `dbc_provider_list` |
| `dbc search` | `dbc_search` |
| `dbc fetch` | `dbc_fetch` |
| `dbc cache list` | `dbc_cache_list` |
| `dbc cache prune` | `dbc_cache_prune` |
| `dbc cache refresh` | `dbc_cache_refresh` |
| `export` | `export` |
| `session save` | `session_save` |
| `session load` | `session_load` |
| `session show` | `session_show` |
| `j1939 monitor` | `j1939_monitor` |
| `j1939 decode` | `j1939_decode` |
| `j1939 pgn` | `j1939_pgn` |
| `j1939 spn` | `j1939_spn` |
| `j1939 tp sessions` | `j1939_tp` |
| `j1939 tp compare` | `j1939_tp_compare` |
| `j1939 dm1` | `j1939_dm1` |
| `j1939 faults` | `j1939_faults` |
| `j1939 summary` | `j1939_summary` |
| `j1939 inventory` | `j1939_inventory` |
| `j1939 compare` | `j1939_compare` |
| `j1939 map` | `j1939_map` |
| `j1587 decode` | `j1587_decode` |
| `j1587 pids` | `j1587_pids` |
| `j2497 decode` | `j2497_decode` |
| `j2497 mids` | `j2497_mids` |
| `uds scan` | `uds_scan` |
| `uds trace` | `uds_trace` |
| `uds services` | `uds_services` |
| `config show` | `config_show` |
| `datasets provider list` | `datasets_provider_list` |
| `datasets search` | `datasets_search` |
| `datasets inspect` | `datasets_inspect` |
| `datasets fetch` | `datasets_fetch` |
| `datasets cache list` | `datasets_cache_list` |
| `datasets cache refresh` | `datasets_cache_refresh` |
| `datasets convert` | `datasets_convert` |
| `datasets replay --dry-run` | `datasets_replay_plan` |
| `datasets replay --list-files` | `datasets_replay_files` |
| `skills provider list` | `skills_provider_list` |
| `skills search` | `skills_search` |
| `skills fetch` | `skills_fetch` |
| `skills cache list` | `skills_cache_list` |
| `skills cache refresh` | `skills_cache_refresh` |
| `re signals` | `re_signals` |
| `re correlate` | `re_correlate` |
| `re counters` | `re_counters` |
| `re entropy` | `re_entropy` |
| `re match-dbc` | `re_match_dbc` |
| `re shortlist-dbc` | `re_shortlist_dbc` |
| `re suggest` | `re_suggest` (heuristic path only) |
| `dbc signals` | `dbc_signals` |
| `doctor` | `doctor` |
| `sequence replay` | `sequence_replay` |
| `fuzz payload` | `fuzz_payload` |
| `fuzz replay` | `fuzz_replay` |
| `fuzz arbitration-id` | `fuzz_arbitration_id` |
| `fuzz signal` | `fuzz_signal` |
| `fuzz spn` | `fuzz_spn` |

## MCP Coverage Decisions

This matrix is the authoritative CLI-to-MCP coverage audit. Every
implemented CLI command (the `IMPLEMENTED_COMMANDS` set in `canarchy.cli`)
is accounted for as **Exposed**, **Excluded** (with rationale), or
**Deferred** (the command does not exist yet). The
`test_every_cli_command_is_exposed_or_documented` guard in
`tests/test_mcp.py` fails the build if a future command is added without
landing here.

### Exposed

| CLI surface | Rationale |
|-------------|-----------|
| Transport reads (`capture`, `filter`, `stats`, `capture-info`, `decode`, `encode`) | Non-interactive commands with bounded JSON envelopes. |
| `compare` | File-backed, multi-capture frame-rate/entropy/cycle-time diff against a baseline; same safety profile as `stats`/`re anomalies`, no transmit. |
| MCP-gated active transmit (`send`, `generate`, `gateway`, `replay`, `sequence replay`, `xcp scan`) | In `_ACTIVE_TRANSMIT_TOOLS`: schemas require `ack_active=true` and default `dry_run=true`. `xcp scan` transmits an XCP CONNECT, so its MCP tool is gated and `--dry-run` plans the frame without sending. |
| Fuzzing (`fuzz payload`, `fuzz replay`, `fuzz arbitration-id`, `fuzz signal`, `fuzz spn`, `fuzz guided`) | In `_ACTIVE_TRANSMIT_TOOLS`: mandatory `ack_active=true`, default `dry_run=true`. `fuzz guided` is response-feedback guided fuzzing — active transmit, gated the same way. |
| DBC + DBC provider (`dbc inspect`, `dbc signals`, `dbc convert`, `dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list/prune/refresh`) | Bounded inspection, conversion, and provider/cache workflows. `dbc_inspect.layout=true` exposes cantools-rendered bit layouts without ANSI parsing; `dbc_convert` returns the serialized database (or writes it to `out`) — file generation is a developer action, so no active-transmit gate applies. |
| Datasets provider/cache/fetch/search/inspect/convert | Metadata and local conversion workflows return bounded JSON envelopes. |
| `datasets replay --dry-run` (`datasets_replay_plan`) and `--list-files` (`datasets_replay_files`) | Safe planning and manifest inspection do not open or stream remote frame data. |
| Skills provider/cache/search/fetch | Non-interactive provider workflows with canonical JSON envelopes. |
| Plugin inspection (`plugins list`, `plugins info`) | Read-only discovery and metadata inspection with bounded JSON envelopes. |
| J1939 analysis (`j1939 decode/pgn/spn/tp sessions/tp compare/dm1/faults/summary/inventory/compare/map/monitor`) | File-backed analysis commands are safe, bounded, and deterministic; `j1939_map` returns passive nodes/edges topology data derived only from the capture. |
| J1587/J1708 (`j1587 decode`, `j1587 pids`) | File-backed legacy heavy-vehicle decoding and a static PID catalog; safe, bounded, and deterministic. |
| J2497/PLC4TRUCKS (`j2497 decode`, `j2497 mids`) | File-backed trailer power-line frame decoding and a static MID catalog; safe, bounded, and deterministic. Live PLC access requires external hardware and is not exposed. |
| Reverse-engineering helpers (`re signals/counters/entropy/correlate/anomalies/match-dbc/shortlist-dbc`, and `re suggest` heuristic path) | File-backed analysis commands are safe and deterministic. `re_suggest` exposes the offline heuristic path only; the external `--llm` enrichment is a CLI-only operator action behind explicit confirmation. |
| Session (`session save/load/show`), `export`, `config show`, `doctor`, UDS (`uds scan/trace/services`), XCP (`xcp trace/read/commands`) | Bounded, non-interactive envelopes. |

### Excluded

| CLI surface | Rationale |
|-------------|-----------|
| `shell`, `tui` | Interactive front ends with no one-shot RPC equivalent. |
| `web serve` | Long-running HTTP/WebSocket front end, like `shell`/`tui`; read-only by design (`docs/design/web-serve.md`). |
| `cannelloni send` | Transmits UDP datagrams to an arbitrary host:port — a CLI-only operator action, not a CAN-interface tool. `cannelloni decode` (passive) is exposed. |
| `mcp serve` | The server itself; not a tool it would expose. |
| `mcp install` | Writes a client config file — a user action, like `plugins enable/disable`, kept off the agent surface. |
| `plugins enable`, `plugins disable` | Write user plugin configuration under `~/.canarchy/config.toml`; kept CLI-only. |
| `dbc generate-c` | Generates C source/header files to disk — a developer action, not an agent tool call. |
| `completion` | Emits a raw shell script, not a JSON envelope. |
| `datasets stream`, non-dry-run `datasets replay` | Emit frame records to stdout and need streaming semantics outside MCP's current buffered response model. |
| `datasets download` | Writes bulk dataset bytes to an arbitrary host path — a CLI-only operator action. `datasets fetch` (provenance) and `datasets replay --dry-run`/`--list-files` (metadata) are exposed. |
| `doip discovery`, `doip services`, `doip ecu-reset`, `doip tester-present`, `doip security-seed`, `doip dump-dids` | The dedicated DoIP command group is active network egress to an arbitrary host (UDP vehicle-identification discovery + TCP diagnostic sessions), like the `doip://` target exclusion below. Kept CLI-only operator actions behind the active-transmit gate (`docs/design/doip-diagnostic-workflows.md`). |

The `uds_scan` / `uds_trace` tools are exposed for CAN interfaces, but a
`doip://` target is a **target-level exclusion**: DoIP routes the workflow over
active TCP egress to an arbitrary network host, which (like `cannelloni send`) is
a CLI-only operator action. The tools refuse a `doip://` interface with code
`DOIP_MCP_EXCLUDED` rather than connecting.

### Deferred (not yet implemented)

There are no deferred implemented CLI commands in the current MCP matrix.

As of this audit, every implemented command that should have MCP coverage
does; plugin toggles and `dbc generate-c` are intentionally excluded because
they write user/developer files. There are no missing mirrors, orphan tools,
or ungated active-transmit MCP tools.

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
* dataset provider metadata workflows and dry-run replay planning for dataset refs or direct URLs

Out of scope:

* HTTP/SSE transport
* streaming tool responses / MCP notifications for live capture
* authentication or access control
* plugin or custom tool registration
* exposing every implemented CLI command automatically
* exposing CANarchy skills as MCP tools, resources, prompts, or a separate MCP discovery surface in phase 1
* streaming dataset frame output through MCP; agents should use `datasets_replay_plan` for preflight metadata and the CLI for actual stdout streaming
