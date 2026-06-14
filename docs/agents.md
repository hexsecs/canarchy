# Agent Guide

--8<-- "AGENTS.md"

---

## MCP Server Integration

CANarchy ships a native Model Context Protocol (MCP) server. Agents that support MCP tool calls can connect directly instead of spawning subprocesses and parsing stdout.

For security workflow examples that combine CLI/MCP calls into complete analyst tasks, see [Security Use Cases With Coding Agents](security-use-cases.md).

### Starting the Server

```bash
canarchy mcp serve
```

The server communicates over stdio using JSON-RPC 2.0 and runs until the client disconnects.

### Claude Desktop Configuration

The fastest way to wire CANarchy into a client is the `canarchy mcp install`
helper, which merges the `mcpServers.canarchy` block for you (see
[Install the CANarchy MCP server](mcp_install.md)):

```bash
canarchy mcp install --client claude-desktop --dry-run   # preview
canarchy mcp install --client claude-desktop             # write (prompts; --ack to skip)
canarchy mcp install --client claude-code --ack
```

It is CLI-only (writing a client config is a user action, so it is not an
MCP tool) and refuses to overwrite a different existing `canarchy` entry.
To wire it up by hand instead, add the block directly:

```json
{
  "mcpServers": {
    "canarchy": {
      "command": "canarchy",
      "args": ["mcp", "serve"]
    }
  }
}
```

With `uv` in a project environment:

```json
{
  "mcpServers": {
    "canarchy": {
      "command": "uv",
      "args": ["run", "canarchy", "mcp", "serve"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### Available Tools

The current MCP surface exposes a curated non-interactive subset of the CLI. Spaces in command names become underscores:

For MCP tools that accept a single CAN interface, omit the `interface` argument only when `[transport].default_interface` or `CANARCHY_DEFAULT_INTERFACE` is configured. Explicit MCP `interface` arguments take precedence over the configured default. `[transport].interface` is the python-can backend type (`socketcan`, `udp_multicast`, `pcan`, `vector`, `kvaser`, etc.) and is not the CAN channel fallback. `doctor` can report offline configured-backend dependency hints, but it does not open hardware.

Active-transmit MCP tools (`send`, `generate`, `simulate`, `gateway`, `replay`, `sequence_replay`, and `fuzz_*`) require `ack_active=true`. Their `dry_run` argument defaults to `true`, so agent calls plan without transmitting unless an operator explicitly authorizes live transmission with `dry_run=false`.

For DBC reconnaissance, `dbc_inspect` accepts `layout=true` to include cantools-rendered message bit diagrams, signal trees, and choice tables as structured strings on each message payload.

| MCP tool | CLI equivalent |
|----------|---------------|
| `capture` | `canarchy capture` |
| `send` | `canarchy send` |
| `generate` | `canarchy generate` |
| `gateway` | `canarchy gateway` |
| `replay` | `canarchy replay` |
| `sequence_replay` | `canarchy sequence replay` |
| `simulate` | `canarchy simulate` |
| `filter` | `canarchy filter` |
| `stats` | `canarchy stats` |
| `capture_info` | `canarchy capture-info` |
| `decode` | `canarchy decode` |
| `encode` | `canarchy encode` |
| `dbc_inspect` | `canarchy dbc inspect` |
| `dbc_signals` | `canarchy dbc signals` |
| `dbc_convert` | `canarchy dbc convert` |
| `dbc_provider_list` | `canarchy dbc provider list` |
| `dbc_search` | `canarchy dbc search` |
| `dbc_fetch` | `canarchy dbc fetch` |
| `dbc_cache_list` | `canarchy dbc cache list` |
| `dbc_cache_prune` | `canarchy dbc cache prune` |
| `dbc_cache_refresh` | `canarchy dbc cache refresh` |
| `datasets_provider_list` | `canarchy datasets provider list` |
| `datasets_search` | `canarchy datasets search` |
| `datasets_inspect` | `canarchy datasets inspect` |
| `datasets_fetch` | `canarchy datasets fetch` |
| `datasets_cache_list` | `canarchy datasets cache list` |
| `datasets_cache_refresh` | `canarchy datasets cache refresh` |
| `datasets_replay_plan` | `canarchy datasets replay --dry-run` |
| `export` | `canarchy export` |
| `session_save` | `canarchy session save` |
| `session_load` | `canarchy session load` |
| `session_show` | `canarchy session show` |
| `j1939_monitor` | `canarchy j1939 monitor` |
| `j1939_decode` | `canarchy j1939 decode` |
| `j1939_pgn` | `canarchy j1939 pgn` |
| `j1939_spn` | `canarchy j1939 spn` |
| `j1939_tp` | `canarchy j1939 tp sessions` |
| `j1939_dm1` | `canarchy j1939 dm1` |
| `j1939_summary` | `canarchy j1939 summary` |
| `j1939_inventory` | `canarchy j1939 inventory` |
| `uds_scan` | `canarchy uds scan` |
| `uds_trace` | `canarchy uds trace` |
| `uds_services` | `canarchy uds services` |
| `xcp_scan` | `canarchy xcp scan` |
| `xcp_trace` | `canarchy xcp trace` |
| `xcp_read` | `canarchy xcp read` |
| `xcp_commands` | `canarchy xcp commands` |
| `config_show` | `canarchy config show` |
| `doctor` | `canarchy doctor` |
| `re_anomalies` | `canarchy re anomalies` |
| `re_correlate` | `canarchy re correlate` |
| `re_counters` | `canarchy re counters` |
| `re_entropy` | `canarchy re entropy` |
| `re_match_dbc` | `canarchy re match-dbc` |
| `re_shortlist_dbc` | `canarchy re shortlist-dbc` |
| `j1939_tp_compare` | `canarchy j1939 tp compare` |
| `j1939_faults` | `canarchy j1939 faults` |
| `j1939_compare` | `canarchy j1939 compare` |
| `re_signals` | `canarchy re signals` |
| `re_corpus` | `canarchy re corpus` |
| `re_suggest` | `canarchy re suggest` (heuristic path only) |
| `plot` | `canarchy plot` |
| `cannelloni_decode` | `canarchy cannelloni decode` |
| `datasets_convert` | `canarchy datasets convert` |
| `datasets_replay_files` | `canarchy datasets replay --list-files` |
| `skills_provider_list` | `canarchy skills provider list` |
| `skills_search` | `canarchy skills search` |
| `skills_fetch` | `canarchy skills fetch` |
| `skills_cache_list` | `canarchy skills cache list` |
| `skills_cache_refresh` | `canarchy skills cache refresh` |
| `plugins_list` | `canarchy plugins list` |
| `plugins_info` | `canarchy plugins info` |

| `fuzz_payload` | `canarchy fuzz payload` |
| `fuzz_replay` | `canarchy fuzz replay` |
| `fuzz_arbitration_id` | `canarchy fuzz arbitration-id` |
| `fuzz_signal` | `canarchy fuzz signal` |
| `fuzz_spn` | `canarchy fuzz spn` |

Current exclusions:

* dataset streaming commands that emit frame records, such as `datasets stream` and non-dry-run `datasets replay`
* interactive or service commands such as `shell`, `tui`, `web serve`, `mcp serve`, and `mcp install`
* `cannelloni send` — active UDP egress to an arbitrary host:port; CLI-only operator action (`cannelloni decode` is exposed)
* `doip://` targets on `uds_scan` / `uds_trace` — DoIP routes UDS over active TCP egress to an arbitrary host; the tools stay CAN-interface-only and refuse a `doip://` interface with `DOIP_MCP_EXCLUDED`. Run DoIP scans/traces from the CLI as an operator action
* `completion`, which emits a raw shell script rather than a JSON envelope
* `dbc generate-c`, which generates C source/header files to disk and is a developer action
* `plugins enable` and `plugins disable`, which write user plugin configuration

The authoritative CLI-to-MCP coverage matrix (exposed / excluded / deferred, with rationale) lives in [`docs/design/mcp-server.md`](design/mcp-server.md#mcp-coverage-decisions); a test guard (`test_every_cli_command_is_exposed_or_documented`) fails the build if a new command drifts out of coverage.

For dataset workflows, agents should prefer MCP dataset tools when available. `datasets_search` and `datasets_inspect` include stable machine fields: `ref`, `is_replayable`, `is_index`, `default_replay_file`, `download_url_available`, and `source_type`. `datasets_fetch` distinguishes curated indexes from normal dataset entries with `is_index`, `index_instructions`, and `download_instructions`. Use `datasets_replay_plan` for safe replay preflight; use CLI `datasets replay --list-files --json` to choose a replay file and `--file <id-or-name>` to select it. Use `max_frames` or `max_seconds` to bound replay. For `catalog:comma-car-segments`, pass `--platform <name>` and `--limit <n>` when listing files so dynamic HuggingFace manifests remain bounded. Use CLI `datasets stream --max-frames <n>` to bound local downloaded dataset-file streaming. `--chunk-size` controls JSONL provenance chunk metadata only; it is not a frame limit. `comma-rlog` streaming requires optional openpilot LogReader support (`uv pip install git+https://github.com/commaai/openpilot.git` on Python 3.12.x) and returns `COMMA_RLOG_SUPPORT_UNAVAILABLE` when unavailable. Actual frame streaming remains CLI-only. Curated index entries that cannot be replayed return `DATASET_INDEX_NOT_REPLAYABLE`.

### Skills Workflow

CANarchy skills are phase-1 workflow descriptors, not MCP tools. Agents should discover and fetch skills through the CLI provider workflow, inspect the cached manifest and entry file, then run the referenced CANarchy commands explicitly through either the CLI or the MCP tools that already exist.

Recommended flow:

1. Run `canarchy skills search <domain-or-task> --json`.
2. Select a provider-qualified reference such as `github:j1939_compare_triage`.
3. Run `canarchy skills fetch <provider>:<skill> --json`.
4. Read `local_manifest_path` and `local_entry_path` from the fetch result.
5. Check `compatibility`, `required_tools`, `inputs`, `outputs`, `skill.tags`, and `skill.domains` before applying the workflow.
6. Run required CANarchy commands explicitly and record the selected skill reference plus provenance in the final analysis.

Example:

```bash
canarchy skills search j1939 --provider github --json
canarchy skills fetch github:j1939_compare_triage --json
canarchy j1939 summary --file baseline.candump --json
canarchy j1939 compare --file baseline.candump --file after-start.candump --json
```

If MCP is available, agents may use MCP for commands that are already exposed as tools, such as `j1939_summary`. The skill itself is still selected and fetched through the CLI in phase 1, and `compatibility.mcp=false` means the agent should not assume MCP invocation is supported for the skill workflow.

### Response Format

Every tool returns a single JSON text block with the canonical result envelope:

```json
{
  "ok": true,
  "command": "<command>",
  "data": { "events": [...] },
  "warnings": [],
  "errors": []
}
```

Failures set `"ok": false` and populate `errors` with structured objects (`code`, `message`, `hint`), using the same error codes as the CLI JSON output.

For UDS workflows, `uds_transaction` events may include `payload.complete=false` when a multi-frame ISO-TP response was only partially captured or arrived out of order. In that case `payload.response_data` still contains the partial bytes that were reassembled.

When the optional Scapy extra is installed, UDS results may also report `data.protocol_decoder="scapy"` and include summary-level `request_summary` / `response_summary` enrichment on `uds_transaction` payloads while preserving the same result envelope and event type.

### Example Interactions

```
tool: uds_services {}
→ {"ok": true, "command": "uds services", "data": {"service_count": 26, ...}}

tool: j1939_spn {"spn": 190, "file": "trace.candump"}
→ {"ok": true, "command": "j1939 spn", "data": {"observations": [...]}}

tool: send {"interface": "vcan0", "frame_id": "0x7DF", "data": "0201F1", "ack_active": true}
→ {"ok": true, "command": "send", "data": {"frame": {...}, "mode": "dry_run"}}
```

### Notes

* MCP streaming is not supported in v1 — live-capture tools (`capture`, live `gateway` with `dry_run=false`) return a buffered batch from the active backend. Use CLI `datasets stream --max-frames <n>` for bounded local dataset-file JSONL or candump pipelines, and `datasets replay --max-frames <n>` or `--max-seconds <s>` for bounded remote dataset-ref or URL playback to stdout.
* `shell`, `tui`, `mcp serve`, and `mcp install` are not exposed as MCP tools.
* Error codes are identical to the CLI, so existing JSON-parsing logic transfers without changes.
* Every MCP response is bounded (default 512 kB, configurable via `CANARCHY_MCP_MAX_RESPONSE_BYTES`). Oversized list data is trimmed and marked with `data.truncated: true` plus a `data.truncation` block recording each trimmed list's `total_items` vs `returned_items` — check that marker before treating a short list as a complete result, and re-run via the CLI (or bound the input with `max_frames`/`seconds`) when you need the full output. An unexpected in-tool failure returns a `TOOL_EXECUTION_ERROR` envelope; the session and the other tools stay usable.
* `encode` (and `send --dbc`) resolve message names by exact DBC name, case/spacing-insensitive match, or SAE PGN label (`EEC1`), and signal names by exact name, case/spacing-insensitive match, or SAE SPN name (`Engine Speed`) — so names displayed by decode tools re-encode directly. Unsupplied signals are defaulted and reported under `data.resolution.filled_signals` with a warning; review them before transmitting.
* CLI capture paths: the `re *` family and `j1939 compare` accept both positional paths and `--file <path>` flags, so agents shelling out do not need to remember which convention a command uses. Filter expressions accept decimal, `0x`-prefixed hex, or bare hex IDs/PGNs with whitespace tolerated around operators.
* RE tool results (`re_signals`, `re_counters`, `re_entropy`, `re_anomalies`, `re_corpus`) annotate J1939 frames with `pgn`, `pgn_label`, `source_address`, and `source_address_name`, and label or exclude J1939 transport-protocol framing (`j1939_transport`, `excluded_transport_ids`). `re_anomalies` without a `baseline` reports sparse ids under `low_rate_ids` instead of ranking them and caps z-scores at ±100σ — prefer supplying a known-good `baseline` capture.
* `re_suggest` proposes signal names for ranked candidates using offline heuristics only (reference-DBC overlap, the J1939 SPN/PGN catalog, and behaviour templates); each suggestion carries a `source` and `confidence`. The optional external-LLM enrichment (`re suggest --llm <provider>`) is **CLI-only** — it is not reachable through the MCP tool — because it sends candidate metadata to an external service and requires explicit operator confirmation. Even on the CLI it sends only candidate metadata (ids, bit ranges, observed ranges, heuristic names), never raw payload bytes, and records an `external_enrichment` note plus an `EXTERNAL_SERVICE_CALLED` warning.
* Stdin pipelines: `capture-info`, `stats`, and `filter --file -` read candump text from stdin. `filter --stdin`, `decode --stdin`, and `j1939 decode --stdin` read JSONL FrameEvents from stdin regardless of output format. This enables piping `datasets replay` candump output directly into analysis commands without temporary files.
