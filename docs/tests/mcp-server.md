# Test Spec: MCP Server

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/mcp-server.md` |
| Test file | `tests/test_mcp.py` (plus `tests/test_cli.py` for the CLI-side stdin-pipeline regressions, TEST-MCP-57/58) |

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
| REQ-MCP-20 | Tool responses are bounded by the output cap with explicit truncation markers and totals | TEST-MCP-39, TEST-MCP-40, TEST-MCP-41, TEST-MCP-42 |
| REQ-MCP-21 | An in-tool exception returns a `TOOL_EXECUTION_ERROR` envelope and leaves the session usable | TEST-MCP-43 |
| REQ-MCP-22 | Every flag an MCP tool forwards maps to a real CLI flag; `stats` exposes the same `top` knob on both surfaces | TEST-MCP-44, TEST-MCP-45, TEST-MCP-46 |
| REQ-MCP-23 | A parse-level CLI failure relayed over MCP carries the invoked tool name, not the generic `cli` | TEST-MCP-47 |
| REQ-MCP-24 | The `-` stdin sentinel is refused before argv construction on every stdin-capable parameter | TEST-MCP-48, TEST-MCP-49, TEST-MCP-50, TEST-MCP-51, TEST-MCP-52, TEST-MCP-53, TEST-MCP-56 |
| REQ-MCP-25 | The refusal carries the canonical envelope and sets the MCP `isError` flag; the session survives it | TEST-MCP-48, TEST-MCP-55 |
| REQ-MCP-26 | Guarded parameters document the restriction; CLI stdin pipelines are unchanged | TEST-MCP-54, TEST-MCP-57, TEST-MCP-58 |

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

When   called with `("dbc_inspect", {"dbc": "t.dbc", "message": "Msg", "signals_only": true, "layout": true})`
Then   the result shall contain `"dbc"`, `"inspect"`, `"t.dbc"`, `"--message"`, `"Msg"`, `"--signals-only"`, and `"--layout"`

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

### `TEST-MCP-39` — Small payloads pass through the output cap unchanged

```gherkin
Given  a payload that serializes below the output cap
When   `bound_payload(payload, cap)` is called
Then   the identical payload object shall be returned
And    no `truncated` marker shall be added
```

**Fixture:** none.

---

### `TEST-MCP-40` — Oversized list data is truncated with marker and totals

```gherkin
Given  a payload whose `data.events` list serializes far beyond the cap
When   `bound_payload(payload, cap)` is called
Then   the serialized result shall fit within the cap
And    `data.truncated` shall be `true`
And    `data.truncation.lists` shall record `total_items` and `returned_items` for the trimmed list
And    a truncation warning shall be appended to `warnings`
And    the original payload shall be left unmodified
```

**Fixture:** synthetic 2000-element event list.

---

### `TEST-MCP-41` — Non-list oversized data falls back to a stub envelope

```gherkin
Given  a payload whose `data` holds one giant scalar (no trimmable list)
When   `bound_payload(payload, cap)` is called
Then   the serialized result shall fit within the cap
And    the `ok` / `command` envelope fields shall be preserved
And    `data.truncated` shall be `true`
```

**Fixture:** 100 kB string in `data.content`.

---

### `TEST-MCP-42` — High-rate `j1939_pgn` returns a bounded, well-formed envelope

```gherkin
Given  a synthetic high-rate EEC1 (PGN 61444) capture of 4000 frames
And    `CANARCHY_MCP_MAX_RESPONSE_BYTES` is set to 65536
When   `handle_call_tool("j1939_pgn", {"pgn": 61444, "file": <capture>})` is called
Then   the response text shall not exceed 65536 bytes
And    it shall parse as JSON with `ok: true`
And    `data.truncated` shall be `true` with at least one trimmed list recording `total_items > returned_items`
```

**Fixture:** generated per-test high-rate candump file.

---

### `TEST-MCP-43` — In-tool exception is isolated; session stays usable

```gherkin
Given  `execute_command` is patched to raise `RuntimeError`
When   `handle_call_tool("uds_services", {})` is called
Then   the response shall be a canonical envelope with `ok: false` and error code `TOOL_EXECUTION_ERROR`
When   the patch is removed and the same tool is called again
Then   the call shall succeed with `ok: true`
```

**Fixture:** none.

---

### `TEST-MCP-44` — Every MCP tool flag maps to a real CLI flag

```gherkin
Given  the registered MCP tools and the CLI argument parser
When   `_build_argv` is invoked for each tool with a fully populated argument set
Then   every `--flag` it emits shall be an accepted option of the resolved CLI command
And    no tool shall forward a flag the CLI rejects with `unrecognized arguments`
```

**Test:** `test_mcp_tool_flags_map_to_real_cli_flags`. **Fixture:** none.

---

### `TEST-MCP-45` — `stats` schema exposes the `top` parameter

```gherkin
Given  the registered MCP tool schemas
When   the `stats` tool input schema is inspected
Then   its properties shall include `top`, matching the CLI `--top` flag
```

**Test:** `test_stats_schema_exposes_top_param`. **Fixture:** none.

---

### `TEST-MCP-46` — `stats` `top` limits the detailed-id list end-to-end

```gherkin
Given  a candump capture fixture
When   `handle_call_tool("stats", {"file": ..., "top": 1})` is called
Then   the envelope shall be `ok: true`
And    `data.top_ids_returned` shall equal `1`
```

**Test:** `test_call_tool_stats_top_limits_detailed_ids`. **Fixture:** `sample.candump`.

---

### `TEST-MCP-47` — Parse-level error envelope carries the invoked tool name

```gherkin
Given  a `stats` call whose `pgn` value fails the CLI argparse type converter
When   `handle_call_tool("stats", {"file": "x", "pgn": "notanint"})` is called
Then   the envelope shall be `ok: false` with error code `INVALID_ARGUMENTS`
And    `command` shall be `stats`, not the generic `cli`
```

**Test:** `test_parse_level_error_envelope_carries_tool_name`. **Fixture:** none.

---

### `TEST-MCP-48` — Stdin sentinel is refused with the canonical envelope and `isError`

```gherkin
Given  an initialised MCP server
When   `handle_call_tool("capture_info", {"file": "-"})` is called
Then   the result shall be a `CallToolResult` with `isError` set to true
And    its single text item shall be the canonical envelope with `ok: false`
And    `command` shall be `capture_info` with empty `data` and `warnings`
And    the error code shall be `STDIN_MCP_EXCLUDED`
And    the message shall name the offending parameter `file`
And    the hint shall point at a real file path
```

**Test:** `test_capture_info_rejects_stdin_sentinel`. **Fixture:** none.

---

### `TEST-MCP-49` — Refusal happens before any CLI reader or argv build

```gherkin
Given  `_build_argv` and `execute_command` are patched to raise if called
When   `handle_call_tool("stats", {"file": "-"})` is called
Then   neither patched function shall be invoked
And    the response shall carry error code `STDIN_MCP_EXCLUDED`
```

**Test:** `test_stdin_rejection_never_reaches_a_cli_reader`. **Fixture:** none.

---

### `TEST-MCP-50` — Refusal starts no worker thread, so none can leak

```gherkin
Given  `asyncio.to_thread` is patched to raise if called
When   `handle_call_tool("capture_info", {"file": "-"})` is called
Then   no worker thread shall be dispatched
And    the live thread count shall not increase
```

**Test:** `test_stdin_rejection_starts_no_worker_thread`. **Fixture:** none.

---

### `TEST-MCP-51` — Every stdin-capable parameter shape is refused

```gherkin
Given  the registered MCP tool surface
When   a tool is called with `-` in a scalar path parameter (`file`, `dbc`,
       `baseline`, `bundle`, `source`), in a path array (`files`,
       `artifacts`), in a dry-run replay input, or on an acknowledged
       active-transmit tool
Then   each call shall be refused with `STDIN_MCP_EXCLUDED`
And    the message shall name the offending parameter
```

**Test:** `test_stdin_sentinel_rejected_across_the_tool_surface`. **Fixture:** none.

---

### `TEST-MCP-52` — No path parameter drifts out of the stdin guard

```gherkin
Given  the registered MCP tool schemas and `_STDIN_CAPABLE_PARAMS`
When   every schema property whose name denotes a readable input path is inspected
Then   each shall be registered in the guard or listed as a documented exemption
```

**Test:** `test_every_path_parameter_is_stdin_guarded_or_documented`. **Fixture:** none.

---

### `TEST-MCP-53` — The stdin guard registry matches the tool schemas

```gherkin
Given  `_STDIN_CAPABLE_PARAMS`
When   each registered tool and parameter is looked up in the tool schemas
Then   every tool name shall exist
And    every registered parameter shall be a declared property of that tool
```

**Test:** `test_stdin_guard_registry_matches_the_tool_schemas`. **Fixture:** none.

---

### `TEST-MCP-54` — Guarded parameters document the restriction

```gherkin
Given  the tool list returned by `handle_list_tools()`
When   the description of each guarded parameter is inspected
Then   it shall mention the `-` sentinel and stdin
```

**Test:** `test_stdin_restricted_parameters_document_the_restriction`. **Fixture:** none.

---

### `TEST-MCP-55` — A rejected stdin call leaves the stdio session usable

```gherkin
Given  a real `canarchy mcp serve` process driven over stdio by `stdio_client`
When   `capture_info` is called with `file: "-"`
Then   the call shall return within the timeout with `isError` true and
       error code `STDIN_MCP_EXCLUDED`
When   `plugins_list` is called on the SAME session
Then   it shall return promptly with `ok: true`
And    the transport shall shut down cleanly afterwards
```

**Test:** `test_stdin_rejection_survives_a_real_stdio_session`. **Fixture:** none
(spawns `python -m canarchy.cli mcp serve` with an isolated `HOME`).

---

### `TEST-MCP-56` — Ordinary file paths are unaffected by the guard

```gherkin
Given  a candump capture fixture
When   `handle_call_tool("capture_info", {"file": <path>})` is called
Then   the result shall be the normal `TextContent` list, not a refusal
And    the envelope shall be `ok: true`
```

**Test:** `test_ordinary_file_paths_are_unaffected`. **Fixture:** `sample.candump`.

---

### `TEST-MCP-57` — CLI `capture-info --file -` pipeline is unchanged

```gherkin
Given  candump text piped on stdin
When   `canarchy capture-info --file - --json` is run
Then   it shall exit `0`
And    `data.implementation` shall be `stdin-metadata` with the piped frame count
```

**Test:** `test_capture_info_stdin_pipeline_still_supported` (`tests/test_cli.py`).
**Fixture:** none (inline candump text).

---

### `TEST-MCP-58` — CLI `filter --file -` pipeline is unchanged

```gherkin
Given  candump text piped on stdin
When   `canarchy filter id==0x123 --file - --json` is run
Then   it shall exit `0`
And    `data.input` shall be `stdin-candump` with only the matching frame
```

**Test:** `test_filter_stdin_candump_pipeline_still_supported` (`tests/test_cli.py`).
**Fixture:** none (inline candump text).
