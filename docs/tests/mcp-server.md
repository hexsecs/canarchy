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
| REQ-MCP-02 | Each selected CLI command surfaces as an MCP tool | TEST-MCP-02, TEST-MCP-03 |
| REQ-MCP-03 | Input schemas derived from argparse definitions | TEST-MCP-04 |
| REQ-MCP-04 | Tool responses use canonical event envelope | TEST-MCP-05, TEST-MCP-06, TEST-MCP-19, TEST-MCP-20, TEST-MCP-21 |
| REQ-MCP-05 | Invalid inputs return same error codes as CLI | TEST-MCP-07, TEST-MCP-08 |
| REQ-MCP-06 | Tool discovery returns all registered MCP tools with metadata | TEST-MCP-02, TEST-MCP-03 |
| REQ-MCP-07 | stdio transport only | TEST-MCP-01 |
| REQ-MCP-08 | Unknown tool name raises error | TEST-MCP-09 |
| REQ-MCP-09 | `mcp` declared in pyproject.toml | TEST-MCP-10 |
| REQ-MCP-10 | `shell` and `tui` not exposed as MCP tools | TEST-MCP-11 |
| REQ-MCP-11 | `call_tool` handler runs `execute_command` in a thread pool | TEST-MCP-15 |
| REQ-MCP-12 | File-backed J1939 tools expose `max_frames` and `seconds` parameters | TEST-MCP-16, TEST-MCP-17 |
| REQ-MCP-13 | Dataset MCP tools expose provider workflows, safe replay planning, conversion, and replay file listing | TEST-MCP-22, TEST-MCP-23, TEST-MCP-24, TEST-MCP-25, TEST-MCP-37, TEST-MCP-38 |
| REQ-MCP-14 | Dataset fetch returns index_instructions for curated indexes | TEST-MCP-26 |
| REQ-MCP-15 | Dataset fetch returns download_instructions for normal datasets | TEST-MCP-27 |
| REQ-MCP-16 | Skills provider workflows shall be exposed as MCP tools | TEST-MCP-28, TEST-MCP-29, TEST-MCP-30, TEST-MCP-31, TEST-MCP-32 |
| REQ-MCP-17 | J1939 tools `j1939_compare`, `j1939_faults`, `j1939_tp_compare` shall be exposed as MCP tools | TEST-MCP-33, TEST-MCP-34, TEST-MCP-35 |
| REQ-MCP-18 | `re signals` shall be exposed as MCP tool `re_signals` | TEST-MCP-36 |
| REQ-MCP-19 | `datasets convert` and `datasets replay --list-files` shall be exposed as MCP tools | TEST-MCP-37, TEST-MCP-38 |

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
Then   the returned set shall contain at minimum: `capture`, `send`, `filter`, `stats`, `capture_info`, `decode`, `encode`, `dbc_inspect`, `dbc_provider_list`, `dbc_search`, `dbc_fetch`, `dbc_cache_list`, `dbc_cache_prune`, `dbc_cache_refresh`, `datasets_provider_list`, `datasets_search`, `datasets_inspect`, `datasets_fetch`, `datasets_cache_list`, `datasets_cache_refresh`, `datasets_replay_plan`, `j1939_monitor`, `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_dm1`, `j1939_summary`, `j1939_inventory`, `uds_scan`, `uds_trace`, `uds_services`, `config_show`, `replay`, `gateway`, `generate`, `export`, `session_save`, `session_load`, `session_show`, `re_correlate`, `re_counters`, `re_entropy`, `re_match_dbc`, `re_shortlist_dbc`
```

**Fixture:** none.

---

### `TEST-MCP-03` — Tool count matches the registered MCP surface

```gherkin
Given  the MCP server is initialised
When   `handle_list_tools()` is called
Then   at least 45 tools shall be returned — one per registered MCP tool in the current curated surface
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

### `TEST-MCP-19` — `capture_info` returns capture metadata

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("capture_info", {"file": "tests/fixtures/sample.candump"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"capture-info"`
And    `data.frame_count` and `data.unique_ids` shall both be greater than `0`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-MCP-20` — `stats` maps file input to current CLI grammar

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("stats", {"file": "tests/fixtures/sample.candump"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"stats"`
And    the result shall report the expected frame and arbitration-ID counts
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-MCP-21` — `filter` maps expression and file input to current CLI grammar

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("filter", {"file": "tests/fixtures/sample.candump", "expression": "id==0x18FEEE31"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"filter"`
And    the result shall contain one matching frame
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-MCP-22` — Dataset search returns machine fields

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_search", {"query": "candid"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"datasets search"`
And    the result shall include stable machine fields such as `ref`, `is_replayable`, and `default_replay_file`
```

**Fixture:** embedded dataset catalog.

---

### `TEST-MCP-23` — Dataset inspect returns index metadata

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_inspect", {"ref": "catalog:pivot-auto-datasets"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    the result shall report `is_index=true` and `is_replayable=false`
```

**Fixture:** embedded dataset catalog.

---

### `TEST-MCP-24` — Dataset replay plan does not stream

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_replay_plan", {"source": "catalog:candid", "max_seconds": 2.5})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"datasets replay"`
And    the result shall report `dry_run=true` and `streamed=false`
And    the result shall preserve the requested `max_seconds` value
```

**Fixture:** embedded dataset catalog.

---

### `TEST-MCP-25` — Dataset replay plan preserves index errors

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_replay_plan", {"source": "catalog:pivot-auto-datasets"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `false`
And    `errors[0].code` shall equal `"DATASET_INDEX_NOT_REPLAYABLE"`
```

**Fixture:** embedded dataset catalog.

---

### `TEST-MCP-26` — Dataset fetch returns index_instructions for curated indexes

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_fetch", {"ref": "catalog:pivot-auto-datasets"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `data.is_index` shall equal `true`
And    `data.index_instructions` shall be a non-empty string
And    `data.index_instructions` shall contain `"Visit the index page"`
```

**Fixture:** embedded dataset catalog.

---

### `TEST-MCP-27` — Dataset fetch returns download_instructions for normal datasets

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_fetch", {"ref": "catalog:road"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `data.is_index` shall equal `false`
And    `data.index_instructions` shall be `null`
And    `data.download_instructions` shall be a non-empty string
And    `data.download_instructions` shall contain `"Download the data manually"`
```

**Fixture:** embedded dataset catalog.

---

### `TEST-MCP-13` — `_build_argv` produces correct argv for representative tools

```gherkin
Given  the `_build_argv` helper is available
When   called with `("capture", {"interface": "can0"})`
Then   the result shall equal `["capture", "can0", "--json"]`

When   called with `("capture_info", {"file": "trace.candump"})`
Then   the result shall equal `["capture-info", "--file", "trace.candump", "--json"]`

When   called with `("j1939_monitor", {"interface": "can0", "pgn": 60160})`
Then   the result shall contain `["j1939", "monitor", "can0", "--pgn", "60160"]` in order

When   called with `("encode", {"dbc": "t.dbc", "message": "Msg", "signals": ["RPM=1000"]})`
Then   the result shall contain `"--dbc"`, `"t.dbc"`, `"Msg"`, and `"RPM=1000"`

When   called with `("dbc_inspect", {"dbc": "t.dbc", "message": "Msg", "signals_only": true})`
Then   the result shall contain `"dbc"`, `"inspect"`, `"t.dbc"`, `"--message"`, `"Msg"`, and `"--signals-only"`

When   called with `("j1939_pgn", {"pgn": 61444, "file": "trace.candump"})`
Then   the result shall contain `["j1939", "pgn", "61444", "--file", "trace.candump"]` in order

When   called with `("j1939_inventory", {"file": "trace.candump", "max_frames": 5000})`
Then   the result shall contain `["j1939", "inventory", "--file", "trace.candump", "--max-frames", "5000"]` in order
And    `"--json"` shall be the final element in each case
```

**Fixture:** none.

---

### `TEST-MCP-14` — `_build_argv` raises for unknown tool

```gherkin
Given  the `_build_argv` helper is available
When   called with `("bad_tool", {})`
Then   a `ValueError` shall be raised
```

**Fixture:** none.

---

### `TEST-MCP-15` — `handle_call_tool` does not block the event loop

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool` is awaited for any tool that delegates to `execute_command`
Then   the asyncio event loop shall remain live during execution
And    a concurrently scheduled coroutine shall be able to run while the tool executes
```

**Fixture:** none (uses `config_show` which requires no files).

---

### `TEST-MCP-16` — `_build_argv` threads `max_frames` and `seconds` through for J1939 file tools

```gherkin
Given  the `_build_argv` helper is available
When   called with a J1939 file tool and `max_frames` set to N
Then   the returned argv shall contain `["--max-frames", str(N)]`

When   called with a J1939 file tool and `seconds` set to T
Then   the returned argv shall contain `["--seconds", str(T)]`

When   called with a J1939 file tool and neither limit is supplied
Then   neither `"--max-frames"` nor `"--seconds"` shall appear in the returned argv
```

Applies to: `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_dm1`, `j1939_summary`, `j1939_inventory`.

**Fixture:** none.

---

### `TEST-MCP-17` — File-backed J1939 tool schemas expose `max_frames` and `seconds`

```gherkin
Given  the MCP server is initialised
When   `handle_list_tools()` is called
Then   for each of `j1939_decode`, `j1939_pgn`, `j1939_spn`, `j1939_tp`, `j1939_dm1`, `j1939_summary`, `j1939_inventory`
       the tool's `inputSchema.properties` shall contain `"max_frames"` of type `"integer"`
        and `"seconds"` of type `"number"`
```

---

### `TEST-MCP-28` — Skills provider list exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("skills_provider_list", {})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"skills provider list"`
And    `data.providers` shall be a list
```

**Fixture:** embedded skills catalog.

---

### `TEST-MCP-29` — Skills search exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("skills_search", {"query": "j1939"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"skills search"`
And    `data.results` shall be a list
```

**Fixture:** embedded skills catalog.

---

### `TEST-MCP-30` — Skills fetch exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("skills_fetch", {"ref": "github:j1939_compare_triage"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"skills fetch"`
And    the result shall include `local_manifest_path` and `local_entry_path`
```

**Fixture:** embedded skills catalog.

---

### `TEST-MCP-31` — Skills cache list exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("skills_cache_list", {})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"skills cache list"`
```

**Fixture:** none.

---

### `TEST-MCP-32` — Skills cache refresh exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("skills_cache_refresh", {"provider": "github"})` is called
Then   the response `text` shall parse as JSON with `ok` equal to `true`
And    `command` shall equal `"skills cache refresh"`
```

**Fixture:** none.

---

### `TEST-MCP-33` — `j1939_compare` exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("j1939_compare", {"files": ["a.candump", "b.candump"]})` is called
Then   `command` shall equal `"j1939 compare"`
And    the argv shall contain both file names and `--json`
```

**Fixture:** none.

---

### `TEST-MCP-34` — `j1939_faults` exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("j1939_faults", {"file": "trace.candump"})` is called
Then   `command` shall equal `"j1939 faults"`
And    the argv shall contain `"--file", "trace.candump", "--json"`
```

**Fixture:** none.

---

### `TEST-MCP-35` — `j1939_tp_compare` exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("j1939_tp_compare", {"file": "trace.candump", "sa": "0x80,0x81"})` is called
Then   `command` shall equal `"j1939 tp compare"`
And    the argv shall contain `"--sa", "0x80,0x81", "--json"`
```

**Fixture:** none.

---

### `TEST-MCP-36` — `re_signals` exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("re_signals", {"file": "trace.candump"})` is called
Then   `command` shall equal `"re signals"`
And    the argv shall equal `["re", "signals", "trace.candump", "--json"]`
```

**Fixture:** none.

---

### `TEST-MCP-37` — `datasets_convert` exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_convert", {"file": "sample.csv", "source_format": "hcrl-csv", "format": "jsonl"})` is called
Then   `command` shall equal `"datasets convert"`
And    the argv shall contain `"--source-format", "hcrl-csv", "--format", "jsonl"`
```

**Fixture:** none.

---

### `TEST-MCP-38` — `datasets_replay_files` exposed as MCP tool

```gherkin
Given  the MCP server is initialised
When   `handle_call_tool("datasets_replay_files", {"source": "catalog:candid"})` is called
Then   `command` shall equal `"datasets replay"`
And    the argv shall contain `"--list-files", "--json"`
And    the result shall include `data.count` and `data.files`
```

**Fixture:** embedded dataset catalog.

**Fixture:** none.
