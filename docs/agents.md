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
| `decode` | `canarchy decode` |
| `encode` | `canarchy encode` |
| `dbc_inspect` | `canarchy dbc inspect` |
| `export` | `canarchy export` |
| `session_save` | `canarchy session save` |
| `session_load` | `canarchy session load` |
| `session_show` | `canarchy session show` |
| `j1939_monitor` | `canarchy j1939 monitor` |
| `j1939_decode` | `canarchy j1939 decode` |
| `j1939_pgn` | `canarchy j1939 pgn` |
| `j1939_spn` | `canarchy j1939 spn` |
| `j1939_tp` | `canarchy j1939 tp` |
| `j1939_dm1` | `canarchy j1939 dm1` |
| `uds_scan` | `canarchy uds scan` |
| `uds_trace` | `canarchy uds trace` |
| `uds_services` | `canarchy uds services` |
| `config_show` | `canarchy config show` |

Current exclusions:

* DBC provider and cache commands such as `dbc search` and `dbc fetch`
* reverse-engineering helpers such as `re counters`, `re entropy`, `re match-dbc`, and `re shortlist-dbc`
* interactive or service commands such as `shell`, `tui`, and `mcp serve`

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

* Streaming is not supported in v1 — live-capture tools (`capture`, `gateway`) return a buffered batch from the active backend.
* `shell`, `tui`, and `mcp serve` are not exposed as MCP tools.
* Error codes are identical to the CLI, so existing JSON-parsing logic transfers without changes.
