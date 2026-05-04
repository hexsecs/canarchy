# Agent Guide

--8<-- "AGENTS.md"

---

## MCP Server Integration

CANarchy ships a native Model Context Protocol (MCP) server. Agents that support MCP tool calls can connect directly instead of spawning subprocesses and parsing stdout.

### Starting the Server

```bash
canarchy mcp serve
```

The server communicates over stdio using JSON-RPC 2.0 and runs until the client disconnects.

### Claude Desktop Configuration

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

| MCP tool | CLI equivalent |
|----------|---------------|
| `capture` | `canarchy capture` |
| `send` | `canarchy send` |
| `generate` | `canarchy generate` |
| `gateway` | `canarchy gateway` |
| `replay` | `canarchy replay` |
| `filter` | `canarchy filter` |
| `stats` | `canarchy stats` |
| `capture_info` | `canarchy capture-info` |
| `decode` | `canarchy decode` |
| `encode` | `canarchy encode` |
| `dbc_inspect` | `canarchy dbc inspect` |
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
| `config_show` | `canarchy config show` |
| `re_correlate` | `canarchy re correlate` |
| `re_counters` | `canarchy re counters` |
| `re_entropy` | `canarchy re entropy` |
| `re_match_dbc` | `canarchy re match-dbc` |
| `re_shortlist_dbc` | `canarchy re shortlist-dbc` |

Current exclusions:

* skills provider and cache commands such as `skills search` and `skills fetch`
* dataset streaming commands that emit frame records, such as `datasets stream` and non-dry-run `datasets replay`
* CLI-only workflows such as `j1939 compare` that are not yet exposed as MCP tools
* CLI-only workflows such as `j1939 faults` and `re signals` that are not yet exposed as MCP tools
* interactive or service commands such as `shell`, `tui`, and `mcp serve`

For dataset workflows, agents should prefer MCP dataset tools when available. `datasets_search` and `datasets_inspect` include stable machine fields: `ref`, `is_replayable`, `is_index`, `default_replay_file`, `download_url_available`, and `source_type`. Use `datasets_replay_plan` for safe replay preflight; use `max_frames` or `max_seconds` to bound replay. Actual frame streaming remains CLI-only. Curated index entries that cannot be replayed return `DATASET_INDEX_NOT_REPLAYABLE`.

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

tool: send {"interface": "vcan0", "frame_id": "0x7DF", "data": "0201F1"}
→ {"ok": true, "command": "send", "data": {"frame": {...}, "mode": "active"}}
```

### Notes

* MCP streaming is not supported in v1 — live-capture tools (`capture`, `gateway`) return a buffered batch from the active backend. Use CLI `datasets stream` for local dataset-file JSONL or candump pipelines, and `datasets replay` for remote dataset-ref or URL playback to stdout.
* `shell`, `tui`, and `mcp serve` are not exposed as MCP tools.
* Error codes are identical to the CLI, so existing JSON-parsing logic transfers without changes.
