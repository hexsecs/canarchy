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
| `REQ-MCP-24` | Unwanted behaviour | If an MCP tool call supplies the stdin sentinel `-` for any parameter that the CLI resolves to a readable input path, the server shall refuse the call with error code `STDIN_MCP_EXCLUDED` before building the CLI argv, so no reader and no `asyncio.to_thread` worker is started against the JSON-RPC transport stream. |
| `REQ-MCP-25` | Event-driven | When the server refuses a stdin sentinel, the response shall carry the canonical envelope (`ok: false` with the `STDIN_MCP_EXCLUDED` error object) **and** set the MCP `isError` flag, so the failure is visible both structurally and at the protocol level. |
| `REQ-MCP-26` | Ubiquitous | Every tool parameter covered by `REQ-MCP-24` shall document the restriction in its input-schema description; the CLI stdin pipelines (`capture-info --file -`, `stats --file -`, `filter --file -`, and the `--stdin` JSONL variants) shall remain unchanged. |
| `REQ-MCP-27` | Ubiquitous | The appended restriction note shall describe only the unavailability of the `-` value and shall make no claim about the form a parameter's value must otherwise take, since the covered parameters include dataset refs, remote URLs, manifest file ids and session names as well as filesystem paths. |

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
| `session verify` | `session_verify` |
| `session annotate` | `session_annotate` |
| `session attach` | `session_attach` |
| `session bundle` | `session_bundle` |
| `session import` | `session_import` |
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
| `uds services` | `uds_services` (reference-only; see `REQ-UDS-ACT-17`) |
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
| Session (`session save/load/show/verify/annotate/attach/bundle/import`), `export`, `config show`, `doctor`, UDS (`uds scan/trace/services`), XCP (`xcp trace/read/commands`) | Bounded, non-interactive envelopes. |

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
| `uds subservices`, `uds ecu-reset`, `uds tester-present`, `uds security-seed`, `uds dump-dids`, `uds read-memory`, `uds auto` | Active UDS workflows that transmit invasive diagnostic requests (ECU reset, SecurityAccess seed collection, DID/memory extraction, ranged service/subfunction enumeration, and a multi-id reconnaissance chain). More intrusive than the single-broadcast `uds scan`; kept CLI-only operator actions behind the active-transmit safety gate (`docs/design/uds-active-workflows.md`). The reference `uds services` catalog stays exposed; its active-probe mode only activates when a CLI caller supplies an interface. |
| `xcp info`, `xcp dump` | Active XCP workflows that connect to a slave and read its capabilities / a bounded memory range. More intrusive than the single-broadcast `xcp scan`; kept CLI-only operator actions behind the active-transmit gate (`docs/design/xcp-workflows.md`). The broadcast `xcp scan` and the passive `xcp trace`/`xcp read`/`xcp commands` stay exposed. |
| `doip discovery`, `doip services`, `doip ecu-reset`, `doip tester-present`, `doip security-seed`, `doip dump-dids` | The dedicated DoIP command group is active network egress to an arbitrary host (UDP vehicle-identification discovery + TCP diagnostic sessions), like the `doip://` target exclusion below. Kept CLI-only operator actions behind the active-transmit gate (`docs/design/doip-diagnostic-workflows.md`). |
| `fuzz identify` | Stateful, multi-round human-in-the-loop replay/narrowing workflow: each invocation replays a bisected window and the operator records an effect/no-effect observation before re-invoking. Does not map to a single buffered tool call; kept CLI-only behind the active-transmit gate (`docs/design/fuzz-identify.md`). |

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

## Stdin Sentinel Exclusion

Each covered parameter's schema description gains this sentence at import time:

> The `-` stdin sentinel is not accepted here: it is a CLI-only pipeline feature, and over MCP stdin carries the JSON-RPC transport. Supply an explicit value instead.

The wording is deliberately silent on what the value must otherwise be. An earlier version opened with "Must be a real filesystem path", which contradicted the parameters that accept a dataset ref, a remote URL, a manifest file id or a session name — `datasets_replay_plan.source` read "Dataset ref (e.g. catalog:candid) or remote candump URL. Must be a real filesystem path" and would have steered an agent away from the supported value (issue #544). One sentence appended to every covered parameter can only say what is true of all of them.

`-` is a documented CLI sentinel meaning "read the capture from stdin"
(`canarchy stats --file -`, `canarchy capture-info --file -`,
`canarchy filter --file -`, plus the `--stdin` JSONL variants). Those
pipelines are unchanged and remain fully supported on the CLI.

Over MCP the same sentinel is fatal. The server owns `sys.stdin` as its
JSON-RPC transport, so a reader opened for `-` consumes protocol bytes
instead of capture text: the call never returns, and every later call in the
session is starved behind the stolen stream (#516). This is a
**parameter-level exclusion**, analogous to the `doip://` target-level
exclusion above.

The server therefore refuses `-` at the tool boundary, *before*
`_build_argv` and therefore before any CLI reader — and before the
`asyncio.to_thread` worker that would host one — is created. Because no
worker is ever started, there is nothing to leak on cancellation or
shutdown.

`_STDIN_CAPABLE_PARAMS` in `canarchy/mcp_server.py` is the authoritative
registry of guarded parameters. It covers every parameter that the CLI
resolves to a readable input path, i.e. every value that can reach the
shared capture reader (`LocalTransport._capture_file_path` maps `-` to
`None`, which `iter_candump_file` reads from `sys.stdin`) or the
`capture-info` stdin branch:

| Parameter | Tools |
|-----------|-------|
| `file` | `replay`, `sequence_replay`, `filter`, `stats`, `capture_info`, `decode`, `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_tp_compare`, `j1939_dm1`, `j1939_faults`, `j1939_summary`, `j1939_inventory`, `j1939_map`, `j1587_decode`, `j2497_decode`, `datasets_convert`, `datasets_replay_plan`, `re_signals`, `re_correlate`, `re_anomalies`, `re_counters`, `re_entropy`, `re_suggest`, `fuzz_replay`, `plot`, `cannelloni_decode` |
| `files` (array) | `j1939_compare`, `re_corpus`, `compare` |
| `dbc` | `decode`, `encode`, `dbc_inspect`, `dbc_signals`, `dbc_convert`, `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_dm1`, `j1939_faults`, `session_save`, `re_anomalies`, `fuzz_signal`, `plot` |
| `capture` | `session_save`, `re_match_dbc`, `re_shortlist_dbc` |
| `baseline` | `re_anomalies`, `compare` |
| `reference` / `reference_dbc` | `re_correlate` / `re_suggest` |
| `source` | `export`, `datasets_replay_plan`, `datasets_replay_files` |
| `artifact` / `artifacts` (array) | `session_attach` / `session_save` |
| `bundle` | `session_import` |
| `corpus` | `fuzz_payload` (seed-capture file) |

Directory-valued parameters (`fuzz_guided.corpus`, `fuzz_guided.findings_dir`,
`session_verify.root`) and output paths (`out`, `output`, `destination`) are
deliberately **not** guarded: neither can resolve to stdin. A contract test
(`test_every_path_parameter_is_stdin_guarded_or_documented`) enforces that a
future path parameter is either registered or explicitly exempted.

Each guarded parameter's input-schema description carries the restriction, so
an agent reading `list_tools` learns the rule without having to trigger it.

A refusal returns the canonical envelope **and** sets the MCP `isError` flag:

```json
{
  "ok": false,
  "command": "capture_info",
  "data": {},
  "warnings": [],
  "errors": [
    {
      "code": "STDIN_MCP_EXCLUDED",
      "message": "`file` was the stdin sentinel '-', which this tool cannot read: the MCP server owns stdin as its JSON-RPC transport stream.",
      "hint": "Pass a real file path for `file`, for example `/path/to/capture.candump`. Reading from `-` is a CLI-only pipeline feature (`canarchy stats --file -`); over MCP, write the upstream stream to a file first and call the tool with that path."
    }
  ]
}
```

This is the one response path that sets `isError`, because refusing the
sentinel is a genuine tool failure rather than a domain result: the tool did
not run at all. Relayed CLI domain failures keep their existing reporting.

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
            ├─ _stdin_sentinel_param(name, args) → refuse `-` (REQ-MCP-24)
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
* reading tool inputs from stdin (the `-` sentinel and the `--stdin` JSONL variants); stdin is the JSON-RPC transport, so those pipelines stay CLI-only (see *Stdin Sentinel Exclusion*). An inline-data parameter for small captures is a possible future addition, deliberately deferred.
