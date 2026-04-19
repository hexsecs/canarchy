# Test Spec: MCP Server

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/mcp-server.md` |
| Test file | `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description | TEST IDs |
|--------|-------------|----------|
| REQ-MCP-01 | `mcp serve` subcommand starts MCP server | TEST-MCP-01 |
| REQ-MCP-02 | Each CLI command surfaces as an MCP tool | TEST-MCP-02, TEST-MCP-03 |
| REQ-MCP-03 | Input schemas derived from argparse definitions | TEST-MCP-04 |
| REQ-MCP-04 | Tool responses use canonical event envelope | TEST-MCP-05, TEST-MCP-06 |
| REQ-MCP-05 | Invalid inputs return same error codes as CLI | TEST-MCP-07, TEST-MCP-08 |
| REQ-MCP-06 | Tool discovery returns all tools with metadata | TEST-MCP-02, TEST-MCP-03 |
| REQ-MCP-07 | stdio transport only | TEST-MCP-01 |
| REQ-MCP-08 | Unknown tool name raises error | TEST-MCP-09 |
| REQ-MCP-09 | `mcp` declared in pyproject.toml | TEST-MCP-10 |
| REQ-MCP-10 | `shell` and `tui` not exposed as MCP tools | TEST-MCP-11 |

## Representative Test Cases

### `TEST-MCP-01` — Server entry point is callable

```gherkin
Given  the `canarchy.mcp_server` module is importable
When   `run_server` is retrieved from the module
Then   it shall be callable
And    `canarchy mcp serve --help` shall exit with code `0`
```

**Fixture:** none.

---

### `TEST-MCP-02` — Tool discovery returns expected tool names

```gherkin
Given  the MCP server is initialised
When   `handle_list_tools()` is called
Then   the returned set shall contain at minimum: `capture`, `send`, `filter`, `stats`, `decode`, `encode`, `dbc_inspect`, `j1939_monitor`, `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_dm1`, `uds_scan`, `uds_trace`, `uds_services`, `config_show`, `replay`, `gateway`, `generate`, `export`, `session_save`, `session_load`, `session_show`
```

**Fixture:** none.

---

### `TEST-MCP-03` — Tool count matches implemented command surface

```gherkin
Given  the MCP server is initialised
When   `handle_list_tools()` is called
Then   at least 24 tools shall be returned — one per implemented non-interactive command
```

**Fixture:** none.

---

### `TEST-MCP-04` — Each tool has a non-empty description and a valid inputSchema

```gherkin
Given  the MCP server is initialised
When   `handle_list_tools()` is called
Then   every tool shall have a non-empty string `description`
And    every tool `inputSchema` shall be a dict containing a `"type"` key
```

**Fixture:** none.

---

### `TEST-MCP-05` — `config_show` returns structured result

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("config_show", {})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"config show"`
And    `data` shall contain a `"backend"` key
```

**Fixture:** none (config show requires no files).

---

### `TEST-MCP-06` — `uds_services` returns service catalogue

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("uds_services", {})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `data.service_count` shall be greater than `0`
```

**Fixture:** none.

---

### `TEST-MCP-07` — `send` with invalid frame_id returns structured error

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("send", {"interface": "can0", "frame_id": "not_hex", "data": "1122"})` is called
Then   the response shall parse as JSON with `ok` equal to `false`
And    at least one error shall have `code` equal to `"INVALID_FRAME_ID"`
```

**Fixture:** none.

---

### `TEST-MCP-08` — `replay` with zero rate returns structured error

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("replay", {"file": "any.candump", "rate": 0.0})` is called
Then   the response shall parse as JSON with `ok` equal to `false`
And    `errors[0].code` shall equal `"INVALID_RATE"`
```

**Fixture:** any candump file path.

---

### `TEST-MCP-09` — Unknown tool name raises ValueError

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("nonexistent_tool", {})` is called
Then   a `ValueError` shall be raised
And    the error message shall reference the unknown tool name
```

**Fixture:** none.

---

### `TEST-MCP-10` — `mcp` dependency declared in pyproject.toml

```gherkin
Given  `pyproject.toml` is available in the repository root
When   the `[project.dependencies]` list is read
Then   an entry matching `mcp>=...` shall be present
```

**Fixture:** `pyproject.toml`.

---

### `TEST-MCP-11` — `shell` and `tui` are not MCP tools

```gherkin
Given  the MCP server is initialised
When   `handle_list_tools()` is called
Then   `"shell"` shall not appear in the set of tool names
And    `"tui"` shall not appear in the set of tool names
```

**Fixture:** none.

---

### `TEST-MCP-12` — `_build_argv` produces correct argv for representative tools

```gherkin
Given  the `_build_argv` helper is available
When   called with `("capture", {"interface": "can0"})`
Then   the result shall equal `["capture", "can0", "--json"]`

When   called with `("j1939_monitor", {"interface": "can0", "pgn": 60160})`
Then   the result shall contain `["j1939", "monitor", "can0", "--pgn", "60160"]` in order

When   called with `("encode", {"dbc": "t.dbc", "message": "Msg", "signals": ["RPM=1000"]})`
Then   the result shall contain `"--dbc"`, `"t.dbc"`, `"Msg"`, and `"RPM=1000"`

When   called with `("dbc_inspect", {"dbc": "t.dbc", "message": "Msg", "signals_only": true})`
Then   the result shall contain `"dbc"`, `"inspect"`, `"t.dbc"`, `"--message"`, `"Msg"`, and `"--signals-only"`

When   called with `("j1939_pgn", {"pgn": 61444, "file": "trace.candump"})`
Then   the result shall contain `["j1939", "pgn", "61444", "--file", "trace.candump"]` in order
And    `"--json"` shall be the final element in each case
```

**Fixture:** none.

---

### `TEST-MCP-13` — `_build_argv` raises for unknown tool

```gherkin
Given  the `_build_argv` helper is available
When   called with `("bad_tool", {})`
Then   a `ValueError` shall be raised
```

**Fixture:** none.
