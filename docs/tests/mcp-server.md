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

## Test Cases

### TEST-MCP-01 — Server entry point is callable

**Fixture:** none  
**Steps:**
1. Import `run_server` from `canarchy.mcp_server`.
2. Assert it is callable.
3. Assert `canarchy mcp serve --help` exits cleanly (exit code 0).

**Expected:** No import errors; help text exits 0.

---

### TEST-MCP-02 — Tool discovery returns expected tool names

**Fixture:** none  
**Steps:**
1. Call `asyncio.run(handle_list_tools())`.
2. Collect `{tool.name for tool in result}`.

**Expected:** Set contains at minimum: `capture`, `send`, `filter`, `stats`, `decode`, `encode`, `j1939_monitor`, `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_dm1`, `uds_scan`, `uds_trace`, `uds_services`, `config_show`, `replay`, `gateway`, `generate`, `export`, `session_save`, `session_load`, `session_show`.

---

### TEST-MCP-03 — Tool count matches implemented command surface

**Fixture:** none  
**Steps:**
1. Call `handle_list_tools()`.
2. Count returned tools.

**Expected:** At least 23 tools returned (one per implemented non-interactive command).

---

### TEST-MCP-04 — Each tool has a non-empty description and a valid inputSchema

**Fixture:** none  
**Steps:**
1. Call `handle_list_tools()`.
2. For each tool, assert `tool.description` is a non-empty string.
3. Assert `tool.inputSchema` is a dict with a `"type"` key.

**Expected:** All tools pass both assertions.

---

### TEST-MCP-05 — `config_show` returns structured result

**Fixture:** none (config show requires no files)  
**Steps:**
1. Call `asyncio.run(handle_call_tool("config_show", {}))`.
2. Parse `results[0].text` as JSON.

**Expected:** `payload["ok"] == True`, `payload["command"] == "config show"`, `"backend"` key present in `payload["data"]`.

---

### TEST-MCP-06 — `uds_services` returns service catalogue

**Fixture:** none  
**Steps:**
1. Call `asyncio.run(handle_call_tool("uds_services", {}))`.
2. Parse the response JSON.

**Expected:** `payload["ok"] == True`, `payload["data"]["service_count"] > 0`.

---

### TEST-MCP-07 — `send` with invalid frame_id returns structured error

**Fixture:** none  
**Steps:**
1. Call `handle_call_tool("send", {"interface": "can0", "frame_id": "not_hex", "data": "1122"})`.
2. Parse response.

**Expected:** `payload["ok"] == False`, at least one error with `code == "INVALID_FRAME_ID"`.

---

### TEST-MCP-08 — `replay` with zero rate returns structured error

**Fixture:** any candump file path  
**Steps:**
1. Call `handle_call_tool("replay", {"file": "any.candump", "rate": 0.0})`.
2. Parse response.

**Expected:** `payload["ok"] == False`, error code `"INVALID_RATE"`.

---

### TEST-MCP-09 — Unknown tool name raises ValueError

**Fixture:** none  
**Steps:**
1. Call `handle_call_tool("nonexistent_tool", {})`.

**Expected:** `ValueError` raised with message referencing the unknown tool name.

---

### TEST-MCP-10 — `mcp` dependency declared in pyproject.toml

**Fixture:** `pyproject.toml`  
**Steps:**
1. Read `pyproject.toml`.
2. Check `[project.dependencies]` list.

**Expected:** An entry matching `mcp>=...` is present.

---

### TEST-MCP-11 — `shell` and `tui` are not MCP tools

**Fixture:** none  
**Steps:**
1. Call `handle_list_tools()`.
2. Collect tool names.

**Expected:** `"shell"` and `"tui"` are not in the set.

---

### TEST-MCP-12 — `_build_argv` produces correct argv for representative tools

**Fixture:** none  
**Steps:**
1. `_build_argv("capture", {"interface": "can0"})` → `["capture", "can0", "--json"]`
2. `_build_argv("j1939_monitor", {"interface": "can0", "pgn": 60160})` → contains `["j1939", "monitor", "can0", "--pgn", "60160"]` elements in order.
3. `_build_argv("encode", {"dbc": "t.dbc", "message": "Msg", "signals": ["RPM=1000"]})` → contains `"--dbc"`, `"t.dbc"`, `"Msg"`, `"RPM=1000"`.
4. `_build_argv("j1939_pgn", {"pgn": 61444, "file": "trace.candump"})` → contains `["j1939", "pgn", "61444", "--file", "trace.candump"]`.

**Expected:** Each assertion passes; `--json` is always the final element.

---

### TEST-MCP-13 — `_build_argv` raises for unknown tool

**Fixture:** none  
**Steps:**
1. Call `_build_argv("bad_tool", {})`.

**Expected:** `ValueError` raised.
