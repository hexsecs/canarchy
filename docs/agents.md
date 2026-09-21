---
description: "How coding agents should drive CANarchy: command selection, structured output, safety gates on active commands, and MCP tool usage."
---

# Agent Guide

--8<-- "AGENTS.md"

---

For `compare`, identify each message by `(arbitration_id, is_extended_id)`. Standard and extended frames with the same numeric ID have separate rows. `id_count` and `summary.unique_ids` count these pairs. Use summary `*_identifiers` arrays (objects with `arbitration_id` and `is_extended_id`) for unambiguous category membership; legacy `*_ids` arrays remain sorted, deduplicated numeric views. Summaries include all findings even when `--top` limits rows.

## MCP Server Integration

Active `fuzz guided` runs archive each finding before the next transmission under `--findings-dir`, `<corpus>/findings`, or `~/.canarchy/findings` (in that order). Use the returned `archive_path` and `campaign_id` to inspect `campaign.json` and `finding-*.json` offline. Findings retain payload/response evidence and lineage after corpus pruning; storage failures stop transmission. Dry-run creates no archive. MCP accepts `findings_dir` and retains its acknowledgement gate and dry-run default.

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
| `session_verify` | `canarchy session verify` |
| `session_annotate` | `canarchy session annotate` |
| `session_attach` | `canarchy session attach` |
| `session_bundle` | `canarchy session bundle` |
| `session_import` | `canarchy session import` |
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
| `j1587_decode` | `canarchy j1587 decode` |
| `j1587_pids` | `canarchy j1587 pids` |
| `j2497_decode` | `canarchy j2497 decode` |
| `j2497_mids` | `canarchy j2497 mids` |
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
| `j1939_map` | `canarchy j1939 map` |
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
| `fuzz_guided` | `canarchy fuzz guided` |
| `compare` | `canarchy compare` |

Current exclusions:

* dataset streaming commands that emit frame records, such as `datasets stream` and non-dry-run `datasets replay`
* interactive or service commands such as `shell`, `tui`, `web serve`, `mcp serve`, and `mcp install`
* `cannelloni send` — active UDP egress to an arbitrary host:port; CLI-only operator action (`cannelloni decode` is exposed)
* `doip://` targets on `uds_scan` / `uds_trace` — DoIP routes UDS over active TCP egress to an arbitrary host; the tools stay CAN-interface-only and refuse a `doip://` interface with `DOIP_MCP_EXCLUDED`. Run DoIP scans/traces from the CLI as an operator action
* the dedicated `doip` command group (`doip discovery`, `doip services`, `doip ecu-reset`, `doip tester-present`, `doip security-seed`, `doip dump-dids`) — active network egress (UDP vehicle-identification discovery + TCP diagnostic sessions), CLI-only operator actions behind the active-transmit gate
* `completion`, which emits a raw shell script rather than a JSON envelope
* `dbc generate-c`, which generates C source/header files to disk and is a developer action
* `plugins enable` and `plugins disable`, which write user plugin configuration
* the active UDS workflows `uds subservices`, `uds ecu-reset`, `uds tester-present`, `uds security-seed`, `uds dump-dids`, `uds read-memory`, and `uds auto` — they transmit invasive diagnostic requests (ECU reset, seed collection, DID/memory extraction, ranged enumeration, multi-id recon) and stay CLI-only operator actions behind the active-transmit gate. The reference `uds services` catalog stays exposed; its active-probe mode only activates when a CLI caller supplies an interface on the command line. A configured `[transport].default_interface` or `CANARCHY_DEFAULT_INTERFACE` never promotes it to probing, so MCP `uds_services` is reference-only on any machine regardless of local configuration (#530)
* the active `xcp info` and `xcp dump` workflows — they connect to an XCP slave and read its capabilities / a bounded memory range, so they stay CLI-only operator actions behind the active-transmit gate (the broadcast `xcp scan` stays exposed)
* `fuzz identify`, a stateful multi-round human-in-the-loop replay/narrowing workflow (one bisected window replayed per invocation); CLI-only operator action

The authoritative CLI-to-MCP coverage matrix (exposed / excluded / deferred, with rationale) lives in [`docs/design/mcp-server.md`](design/mcp-server.md#mcp-coverage-decisions); a test guard (`test_every_cli_command_is_exposed_or_documented`) fails the build if a new command drifts out of coverage.

For dataset workflows, agents should prefer MCP dataset tools when available. `datasets_search` and `datasets_inspect` include stable machine fields: `ref`, `is_replayable`, `is_index`, `default_replay_file`, `download_url_available`, and `source_type`. `datasets_fetch` distinguishes curated indexes from normal dataset entries with `is_index`, `index_instructions`, and `download_instructions`, and reports `data_is_local: true` when the fetch materialised real bytes into the cache rather than recording provenance for a remote file. When `data_is_local` is true, `next_steps` names the local-file commands to run against `cache_path` — `datasets download` and `datasets replay` do not apply and will fail with `DATASET_REPLAY_UNAVAILABLE`. Use `datasets_replay_plan` for safe replay preflight; use CLI `datasets replay --list-files --json` to choose a replay file and `--file <id-or-name>` to select it. Use `max_frames` or `max_seconds` to bound replay. For `catalog:comma-car-segments`, pass `--platform <name>` and `--limit <n>` when listing files so dynamic HuggingFace manifests remain bounded. Use CLI `datasets stream --max-frames <n>` to bound local downloaded dataset-file streaming. `--chunk-size` controls JSONL provenance chunk metadata only; it is not a frame limit. `comma-rlog` streaming requires optional openpilot LogReader support (`uv pip install git+https://github.com/commaai/openpilot.git` on Python 3.12.x) and returns `COMMA_RLOG_SUPPORT_UNAVAILABLE` when unavailable. Actual frame streaming remains CLI-only. Curated index entries that cannot be replayed return `DATASET_INDEX_NOT_REPLAYABLE`.

Every dataset in the `catalog` provider downloads from a host (zenodo.org, figshare.com, huggingface.co, ocslab.hksecurity.net) that a typical sandboxed agent environment blocks, so `datasets fetch` followed by a replay fails there with a transport error. When there is no egress, use the `offline` provider instead: `datasets search --provider offline --json` lists synthetic datasets that generate locally and need no network. `datasets fetch offline:<name>` writes real data into the cache and returns its path in `cache_path`, after which the local-file commands (`datasets convert`, `datasets stream`, `capture-info`, `stats`, `j1939 summary`, `replay --file`) work normally. Offline datasets carry `synthetic: true` in the machine fields, a licence string identifying them as synthetic, and a `SYNTHETIC:` description prefix. The data has real protocol structure but is not vehicle behaviour: use it to exercise tooling, never report analysis of it as a research finding. Current offline datasets are `can-basic` (candump, with a discoverable counter), `j1939-basic` (candump, with BAM/TP and a DM1 active fault), `can-intrusion` (hcrl-csv, attack-labelled), and `signal-decoded` (decoded-signal-csv).

A bare dataset ref (no `provider:` prefix) resolves against providers in order, and `datasets_provider_list` / `datasets provider list --json` reports that effective order as `search_order` plus a per-provider `order` index. The default is `catalog` before `offline`, so a bare ref prefers a real dataset over synthetic data of the same name; an operator can reorder it with `[datasets].search_order` in `~/.canarchy/config.toml`. Prefer a prefixed ref (`catalog:road`, `offline:can-basic`) when the provider matters. A provider name in that config that does not exist fails every `datasets` command with `DATASET_PROVIDER_NOT_FOUND` (exit 1); a malformed value fails with `DATASET_SEARCH_ORDER_INVALID`.

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

### Research Record Workflow

A session is the durable record of an analysis: what it consumed, what it produced, and whether that still holds. Agents that report a finding should record it so a human can check the finding later against the exact bytes it came from.

Recommended flow:

1. `session_save` with the capture and DBC under analysis. The record stores a SHA-256 hash, size, and modification time per input, the effective configuration, and the CANarchy version.
2. Run the analysis tools as usual, writing the result to a file.
3. `session_attach` that file with `command` set to the exact command that produced it and `derived_from` set to the input ids from step 1, so the artifact points at the inputs it came from. Pass `embed: true` to keep the result inside the record.
4. `session_annotate` with the interpretation, targeting the input or artifact it refers to.
5. `session_verify` before relying on an earlier record. It re-hashes everything offline and returns `verification.status`, per-entry `unchanged` / `changed` / `missing` / `unverifiable`, a `reproduce_command` per recorded invocation, and `required_actions`. A degraded verification returns `ok: false` with code `SESSION_VERIFICATION_FAILED` — the recorded conclusion no longer follows from the files on disk, so re-run the analysis rather than repeating the old finding.
6. `session_bundle` to hand the whole record — manifest plus copies of its files — to another machine, and `session_import` to open it there.

`session_verify` and `session_load` only read files: they never re-run a recorded command or touch the bus. A record saved before provenance existed reports `provenance_available: false` with a `SESSION_PROVENANCE_UNAVAILABLE` warning; re-run `session_save` with its inputs to upgrade it. Credentials are never recorded — omitted configuration keys are listed in `effective_config.redacted_keys`.

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
→ {"ok": true, "command": "j1939 spn", "data": {"mode": "passive", "observations": [...]}}

tool: j1939_spn {"spn": 190}   # no file → built-in reference lookup
→ {"ok": true, "command": "j1939 spn", "data": {"mode": "reference", "name": "Engine Speed", "pgn": 61444, "units": "rpm", ...}}

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
* Reference-DBC matching in `re suggest` uses exact physical-bit overlap for Intel and Motorola signals; sharing a byte alone is insufficient. Confidence remains heuristic, and corrected overlap can change suggestion inclusion and ranking without changing output fields.
* `re_suggest` proposes signal names for ranked candidates using offline heuristics only (reference-DBC overlap, the J1939 SPN/PGN catalog, and behaviour templates); each suggestion carries a `source` and `confidence`. The optional external-LLM enrichment (`re suggest --llm <provider>`) is **CLI-only** — it is not reachable through the MCP tool — because it sends candidate metadata to an external service and requires explicit operator confirmation. Even on the CLI it sends only candidate metadata (ids, bit ranges, observed ranges, heuristic names), never raw payload bytes, and records an `external_enrichment` note plus an `EXTERNAL_SERVICE_CALLED` warning.
* Stdin pipelines: `capture-info`, `stats`, and `filter --file -` read candump text from stdin. `filter --stdin`, `decode --stdin`, and `j1939 decode --stdin` read JSONL FrameEvents from stdin regardless of output format. This enables piping `datasets replay` candump output directly into analysis commands without temporary files.
* Stdin pipelines are **CLI-only**. Over MCP, stdin carries the JSON-RPC transport, so passing `-` to any file or source parameter (`file`, `files`, `dbc`, `capture`, `baseline`, `reference`, `reference_dbc`, `source`, `artifact`, `artifacts`, `bundle`, `corpus`) is refused before the command runs, with error code `STDIN_MCP_EXCLUDED` and the MCP failure flag set. Pass a real file path instead: if the data is coming from a pipeline, write it to a file first (for example `canarchy datasets replay offline:can-basic > /tmp/run.candump`) and call the tool with that path. The parameter descriptions returned by `list_tools` state the restriction.
