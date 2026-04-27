# Command Spec

## Status

This document describes the current implemented CLI contract.

Implemented and verified in the current codebase:

* live and deterministic transport workflows for `capture`, `send`, and `generate`
* file-backed `filter` and `stats` over candump capture logs
* default `python-can` support for `capture` and `send`
* deterministic `replay`
* live `gateway` bridging between CAN interfaces via `python-can`
* structured `export` for capture files and saved sessions
* DBC-backed `decode`, `encode`, and `dbc inspect`
* DBC provider workflows for `dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list`, `dbc cache prune`, and `dbc cache refresh`
* J1939 `monitor`, `decode`, `pgn`, `spn`, `tp`, and `dm1`
* session `save`, `load`, and `show`
* shell one-shot command execution
* initial text-mode `tui` shell over the shared command layer
* UDS `scan`, `trace`, and `services`
* `config show` for effective transport configuration inspection
* `re counters` and `re entropy` for passive file-backed analysis
* `re match-dbc` and `re shortlist-dbc` for provider-backed DBC candidate ranking against captures
* structured JSON and JSONL output
* explicit error schema and exit codes

Some other commands are already present in the CLI tree but still return placeholder results until their implementation issues are completed.

Important current behavior:

* live transport-facing commands default to the `python-can` backend; set `backend = "scaffold"` in `~/.canarchy/config.toml` or export `CANARCHY_TRANSPORT_BACKEND=scaffold` for deterministic offline behavior
* `capture`, `send`, and `gateway` use the selected transport backend, but `gateway` specifically requires `python-can`
* the default `python-can` interface is `socketcan`; set `interface` in the config file or `CANARCHY_PYTHON_CAN_INTERFACE` to change it
* DBC-backed commands accept local paths and provider refs such as `opendbc:<name>` or `comma:<name>`
* `decode`, `encode`, and `dbc inspect` include `data.dbc_source` in structured output so callers can see the provider, logical DBC name, pinned version, and resolved local path
* placeholder-only commands still return `status: planned` and `implementation: command surface scaffold`
* some protocol-oriented commands currently use explicit sample/reference providers rather than true transport-backed execution paths
* specialized table formatting exists for J1939 monitor and decode style output; other `--table` output is generic key/value rendering
* file-backed analysis commands currently support standard timestamped candump log files with `.candump` and `.log` suffixes

---

## Command Structure

Commands follow one of these patterns:

```text
canarchy <domain> <action> [args]
```

or

```text
canarchy <action> <object>
```

Examples:

* `canarchy capture can0 --json`
* `canarchy replay tests/fixtures/sample.candump --rate 2.0 --json`
* `canarchy j1939 monitor --pgn 65262 --json`
* `canarchy decode tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json`

---

## Implemented Commands

### capture

Capture traffic from a local interface. Structured capture uses the selected transport backend. `--candump` is a live-only mode.

```bash
canarchy capture <interface> [--candump] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy capture can0 --json
canarchy capture vcan0 --candump
```

Notes:

* `--candump` is a live-only mode that requires the `python-can` backend (set in `~/.canarchy/config.toml` or via `CANARCHY_TRANSPORT_BACKEND=python-can`)
* `--candump` keeps running and printing frames until interrupted
* `--candump` changes the human-readable output path to a `candump`-style line format such as `(0.100000) vcan0 18F00431#AABBCCDD`
* `--candump --json` and `--candump --jsonl` keep structured output for automation, but still require a live backend
* default table output without `--candump` remains the generic key/value renderer

Supported file input today:

* file-backed commands consume standard timestamped candump logs in the form `(timestamp) interface frame#data`
* supported additional candump forms include classic RTR `id#R`, CAN FD `id##<flags><data>`, and error frames using a CAN error-flagged identifier
* supported CAN FD flags today are the BRS and ESI bits in the single-nibble candump flags field
* supported capture-file suffixes today are `.candump` and `.log`
* malformed log lines fail with structured transport errors rather than silently falling back to fixture data

### send

Prepare an active transmit frame.

```bash
canarchy send <interface> <frame-id> <hex-data> [--ack-active] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy send can0 0x123 11223344 --json
```

Notes:

* `--ack-active` requests an interactive `YES` confirmation before the frame is transmitted
* when active acknowledgement is required by configuration, omitting `--ack-active` returns a structured `ACTIVE_ACK_REQUIRED` error

### filter

Filter a capture source by a simple expression.

```bash
canarchy filter <expression> (--file <path> | --stdin) [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--compact|--table|--raw]
```

Supported expressions today:

* `all`
* `id==0x18FEEE31`
* `pgn==65262`

Notes:

* `--stdin` reads JSONL `frame` events from standard input instead of a positional capture file

### capture-info

Inspect a candump capture quickly before running deeper analysis.

```bash
canarchy capture-info --file <path> [--json|--jsonl|--table|--raw]
```

Returns capture metadata only:

* `frame_count`
* `first_timestamp`
* `last_timestamp`
* `duration_seconds`
* `unique_ids`
* `interfaces`
* `suggested_max_frames`
* `suggested_seconds`

### stats

Summarize a capture source.

```bash
canarchy stats --file <path> [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--table|--raw]
```

### generate

Generate CAN frames from explicit, random, or incrementing inputs.

```bash
canarchy generate <interface> [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>] [--count <n>] [--gap <ms>] [--extended] [--ack-active] [--json|--jsonl|--table|--raw]
```

Examples:

```bash
canarchy generate can0 --id 0x123 --dlc 4 --data 11223344 --count 2 --gap 100 --json
canarchy generate can0 --data I --count 4 --table
```

Notes:

* `--id`, `--dlc`, and `--data` accept `R` for random generation, and `--data I` enables a deterministic incrementing payload pattern
* `--ack-active` requests an interactive `YES` confirmation before generated frames are transmitted
* when active acknowledgement is required by configuration, omitting `--ack-active` returns a structured `ACTIVE_ACK_REQUIRED` error
* generated JSON output includes an active-transmit alert followed by generated frame events

### replay

Replay a capture source with deterministic timing derived from relative frame timestamps.

```bash
canarchy replay --file <path> [--rate <factor>] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy replay --file tests/fixtures/sample.candump --rate 2.0 --json
```

### gateway

Bridge frames from one live CAN interface to another through the `python-can` backend.

```bash
canarchy gateway <src> <dst> [--src-backend <type>] [--dst-backend <type>] [--bidirectional] [--count <n>] [--ack-active] [--json|--jsonl|--table|--raw]
```

Examples:

```bash
canarchy gateway can0 can1 --table
canarchy gateway can0 239.0.0.1 --dst-backend udp_multicast --count 10 --json
```

Notes:

* `gateway` requires the `python-can` backend (set in `~/.canarchy/config.toml` or via `CANARCHY_TRANSPORT_BACKEND=python-can`)
* `--src-backend` and `--dst-backend` default to the configured `interface` value
* `--ack-active` requests an interactive `YES` confirmation before forwarding begins
* default table and raw output use candump-style forwarded frame lines with direction labels such as `[src->dst]`
* `--json` returns a standard command envelope; `--jsonl` emits one forwarded event per line for `gateway`

### export

Export structured artifacts for later analysis.

```bash
canarchy export <source> <destination> [--json|--jsonl|--table|--raw]
```

Examples:

```bash
canarchy export tests/fixtures/sample.candump artifacts/sample.json --json
canarchy export tests/fixtures/sample.candump artifacts/sample.jsonl --json
canarchy export session:lab-a artifacts/session.json --json
```

Notes:

* capture file sources use `.candump` or `.log` paths
* saved sessions use the explicit `session:<name>` source form
* destination `.json` writes a full structured artifact envelope
* destination `.jsonl` writes one serialized event per line and is only supported for event-capable sources such as capture files

### decode

Decode frames from a capture source using a DBC file.

```bash
canarchy decode <file> --dbc <file> [--stdin] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy decode tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json
```

Notes:

* `--dbc` accepts a local file path or a provider ref such as `opendbc:<name>`
* `--stdin` reads JSONL `frame` events from standard input instead of a positional capture file
* structured output includes a `dbc_source` object describing the provider-backed or local DBC resolution that was used

### encode

Encode a DBC message into a frame payload.

```bash
canarchy encode --dbc <file> <message> <signal=value>... [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
```

Notes:

* `--dbc` accepts a local file path or a provider ref such as `opendbc:toyota_tnga_k_pt_generated`
* structured output includes a `dbc_source` object describing the provider-backed or local DBC resolution that was used

### dbc inspect

Inspect database, message, and signal metadata for a DBC file or provider ref.

```bash
canarchy dbc inspect <dbc> [--message <name>] [--signals-only] [--json|--jsonl|--table|--raw]
```

Examples:

```bash
canarchy dbc inspect tests/fixtures/sample.dbc --json
canarchy dbc inspect opendbc:toyota_tnga_k_pt_generated --message STEER_TORQUE_SENSOR --json
```

Notes:

* `<dbc>` accepts a local file path or a provider ref such as `opendbc:<name>` or `comma:<name>`
* structured output includes `dbc_source` provenance alongside the inspection payload

### dbc provider list

List registered DBC providers.

```bash
canarchy dbc provider list [--json|--jsonl|--table|--raw]
```

### dbc search

Search DBC catalogs across enabled providers.

```bash
canarchy dbc search <query> [--provider <name>] [--limit <n>] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy dbc search toyota --provider opendbc --limit 5 --json
```

### dbc fetch

Fetch and cache a DBC file from a provider.

```bash
canarchy dbc fetch <ref> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy dbc fetch opendbc:toyota_tnga_k_pt_generated --json
```

### dbc cache list

List cached provider manifests.

```bash
canarchy dbc cache list [--json|--jsonl|--table|--raw]
```

### dbc cache prune

Remove stale cached provider snapshots while keeping the pinned commit.

```bash
canarchy dbc cache prune [--provider <name>] [--json|--jsonl|--table|--raw]
```

### dbc cache refresh

Refresh a provider catalog from upstream.

```bash
canarchy dbc cache refresh [--provider <name>] [--json|--jsonl|--table|--raw]
```

Notes:

* the default provider is `opendbc`
* refreshing updates the cached catalog manifest; individual DBC files are fetched on demand or through `dbc fetch`
* provider-backed decode, encode, and inspect commands return `DBC_CACHE_MISS` by default when the provider cache is cold; enabling `[dbc.providers.opendbc].auto_refresh = true` allows first-use refresh on resolution

### skills provider list

List registered repository-backed skills providers.

```bash
canarchy skills provider list [--json|--jsonl|--table|--raw]
```

### skills search

Search repository-backed skills catalogs by name, tag, or keyword.

```bash
canarchy skills search <query> [--provider <name>] [--limit <n>] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy skills search j1939 --provider github --json
```

### skills fetch

Fetch and cache a repository-backed skill locally.

```bash
canarchy skills fetch <provider>:<skill> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy skills fetch github:j1939_compare_triage --json
```

### skills cache list

List cached skills provider manifests.

```bash
canarchy skills cache list [--json|--jsonl|--table|--raw]
```

### skills cache refresh

Refresh a skills provider catalog from upstream.

```bash
canarchy skills cache refresh [--provider <name>] [--json|--jsonl|--table|--raw]
```

Notes:

* the first provider implementation is GitHub-backed and consumes `.skill.yaml` manifests that follow the CANarchy skill manifest schema
* `skills fetch` returns both the cached manifest path and the cached skill entry path
* skills provider/cache commands are currently CLI-only and are not yet exposed as MCP tools

### session save

Save a named session with useful CLI context.

```bash
canarchy session save <name> [--interface <name>] [--dbc <file>] [--capture <file>] [--json|--jsonl|--table|--raw]
```

### session load

Load a previously saved session and mark it active.

```bash
canarchy session load <name> [--json|--jsonl|--table|--raw]
```

### session show

Show saved sessions and the active session.

```bash
canarchy session show [--json|--jsonl|--table|--raw]
```

### shell

Run a single shell command through the shared parser, or start a minimal interactive shell loop.

```bash
canarchy shell [--command "capture can0 --raw"] [--json|--jsonl|--table|--raw]
```

### j1939 monitor

Inspect J1939 traffic and emit PGN-oriented structured events.

```bash
canarchy j1939 monitor [<interface>] [--pgn <id>] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy j1939 monitor --pgn 65262 --json
canarchy j1939 monitor can0 --pgn 65262 --json
```

Notes:

* without an interface, this command uses an explicit sample/reference provider
* with an interface, this command captures from the selected transport backend and filters to J1939 extended-ID traffic
* `j1939 decode`, `j1939 spn`, `j1939 tp sessions`, `j1939 dm1`, `j1939 summary`, `j1939 inventory`, and `j1939 compare` remain file-backed

### j1939 decode

Decode a capture source into J1939 PGN observations.

```bash
canarchy j1939 decode <file> [--stdin] [--json|--jsonl|--table|--raw]
```

Notes:

* `--stdin` reads JSONL `frame` events from standard input instead of a positional capture file

### j1939 pgn

Inspect events for a specific PGN from a capture file.

```bash
canarchy j1939 pgn <pgn> --file <file> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy j1939 pgn 65262 --file tests/fixtures/sample.candump --json
```

```bash
canarchy j1939 pgn <id> [--json|--jsonl|--table|--raw]
```

### j1939 spn

Inspect a curated SPN decoder over recorded J1939 traffic.

```bash
canarchy j1939 spn <spn> --file <file> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy j1939 spn 110 --file tests/fixtures/sample.candump --json
```

Notes:

* the first implementation supports a curated SPN decoder set rather than a full J1939 database
* unsupported SPNs return a structured `J1939_SPN_UNSUPPORTED` error

### j1939 tp sessions

Summarize J1939 transport-protocol sessions from a capture file.

```bash
canarchy j1939 tp sessions --file <file> [--json|--jsonl|--table|--raw]
```

Notes:

* the first implementation focuses on BAM-style TP sessions and packet reassembly

### j1939 dm1

Inspect DM1 fault traffic from direct J1939 frames and TP-reassembled payloads.

```bash
canarchy j1939 dm1 --file <file> [--json|--jsonl|--table|--raw]
```

### j1939 inventory

Build a source-address inventory from a J1939 capture file, including top PGNs, component-identification strings, vehicle-identification strings, and DM1 presence.

```bash
canarchy j1939 inventory --file <file> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy j1939 inventory --file tests/fixtures/j1939_inventory.candump --json
```

Notes:

* inventory rows are grouped by source address
* printable TP payloads for component identification and vehicle identification are associated with the reporting source address when available
* DM1 presence is summarised per source address so initial triage does not require a second command

### j1939 compare

Compare two or more J1939 capture files and highlight common versus capture-unique PGNs, source-address changes, DM1 differences, and printable TP identification changes.

```bash
canarchy j1939 compare <file> <file> [<file> ...] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy j1939 compare tests/fixtures/j1939_inventory.candump tests/fixtures/j1939_compare_shifted.candump --json
```

Notes:

* this command requires at least two capture files
* `--max-frames`, `--seconds`, and `--offset` apply independently to each compared capture file
* DM1 differences are grouped by source address and surface active-fault or lamp-state changes when present
* printable TP component-identification and vehicle-identification payloads are compared by source address and payload label

### tui

Start the initial text-mode TUI shell.

```bash
canarchy tui [--command "<existing canarchy command>"]
```

Notes:

* the first implementation is a thin text-mode shell, not a full-screen terminal UI
* panes include bus status, live traffic, alerts, and command entry help
* command entry runs existing CANarchy commands through the shared parser and result path
* nested interactive front ends like `shell` or `tui` are rejected from TUI command entry

### uds scan

Inspect representative UDS responder discovery transactions.

```bash
canarchy uds scan <interface> [--ack-active] [--json|--jsonl|--table|--raw]
```

Notes:

* with the `python-can` backend, this command sends a single-frame functional DiagnosticSessionControl request and summarizes captured UDS responses after ISO-TP reassembly when needed
* with the `scaffold` backend, this command emits explicit sample/reference UDS transaction data
* `--ack-active` requests an interactive `YES` confirmation before the diagnostic request is sent
* if a segmented response is truncated or arrives out of order, the emitted `uds_transaction` event keeps the partial `response_data` and sets `complete` to `false`

### uds trace

Inspect representative UDS request and response transactions.

```bash
canarchy uds trace <interface> [--json|--jsonl|--table|--raw]
```

Notes:

* with the `python-can` backend, this command captures raw CAN frames and infers UDS request/response transactions from common diagnostic IDs, including ISO-TP multi-frame responses
* with the `scaffold` backend, this command emits explicit sample/reference UDS transaction data
* flow-control frames are used only for reassembly and are not emitted as transactions
* if a segmented response is truncated or arrives out of order, the emitted `uds_transaction` event keeps the partial `response_data` and sets `complete` to `false`

### uds services

Inspect the built-in UDS service catalog.

```bash
canarchy uds services [--json|--jsonl|--table|--raw]
```

Notes:

* this is a reference command and does not require an interface
* output includes service identifier, positive-response identifier, category, and subfunction expectations

### re counters

Rank likely counter fields from recorded CAN traffic.

```bash
canarchy re counters <file> [--json|--jsonl|--table|--raw]
```

Notes:

* this command is passive and file-backed
* the current implementation inspects nibble- and byte-sized candidate fields on recorded arbitration IDs
* candidates are ranked by monotonicity evidence and explicit rollover detection

### re signals

Rank likely signal fields from recorded CAN traffic.

```bash
canarchy re signals <file> [--json|--jsonl|--table|--raw]
```

Notes:

* this command is passive and file-backed
* the current implementation inspects nibble-aligned 4-bit fields, byte-aligned 8-bit fields, and word-aligned 16-bit fields
* candidates are ranked by change-rate preference, observed range, and value diversity
* arbitration IDs with fewer than 5 frames are omitted from the candidate list and reported in `low_sample_ids`

### re entropy

Rank arbitration IDs and byte positions by Shannon entropy over recorded CAN traffic.

```bash
canarchy re entropy <file> [--json|--jsonl|--table|--raw]
```

Notes:

* this command is passive and file-backed
* JSON output includes one candidate per arbitration ID plus a per-byte entropy breakdown inside each candidate
* IDs with fewer than 10 observed frames are retained and marked with `low_sample: true`

### re match-dbc

Rank candidate DBC files against a capture using provider-backed catalog metadata.

```bash
canarchy re match-dbc <capture> [--provider <name>] [--limit <n>] [--json|--jsonl|--table|--raw]
```

Notes:

* this command is passive and file-backed
* candidates are scored by frequency-weighted arbitration-ID coverage against the capture
* the default provider is `opendbc`

### re shortlist-dbc

Rank candidate DBC files against a capture after pre-filtering by vehicle make.

```bash
canarchy re shortlist-dbc <capture> --make <brand> [--provider <name>] [--limit <n>] [--json|--jsonl|--table|--raw]
```

Notes:

* this command is passive and file-backed
* `--make` narrows provider-catalog candidates before scoring them against the capture
* the default provider is `opendbc`

### config show

Inspect the effective transport configuration and the source of each setting.

```bash
canarchy config show [--json|--jsonl|--table|--raw]
```

### mcp serve

Start the MCP server over stdio.

```bash
canarchy mcp serve
```

Notes:

* this command does not accept output flags
* the current MCP tool surface is a curated non-interactive subset of the CLI, not every implemented command

---

## Output Modes

All commands support:

* `--json`
* `--jsonl`
* `--table`
* `--raw`

Current behavior:

* `--json` emits one structured JSON object
* `--jsonl` emits one JSON object per line
* event-producing commands emit each event as its own JSON line; command warnings that are not already events are emitted as `alert` event lines
* event-less successful commands emit a single result object line
* failed commands emit a single error result object line
* `--table` emits a human-readable summary view, with protocol-aware pretty-printing for J1939 monitor and decode workflows
* `--raw` emits the command name on success or the primary error message on failure

J1939 `--table` output includes:

* PGN
* source address
* destination address when present, otherwise broadcast
* priority
* CAN identifier
* payload bytes

### JSON Result Shape

Successful `--json` output uses this shape:

```json
{
  "ok": true,
  "command": "capture",
  "data": {},
  "warnings": [],
  "errors": []
}
```

Error `--json` output and event-less/error `--jsonl` output use this shape:

```json
{
  "ok": false,
  "command": "decode",
  "data": {},
  "warnings": [],
  "errors": [
    {
      "code": "DBC_LOAD_FAILED",
      "message": "Failed to parse DBC file.",
      "hint": "Validate the DBC syntax and line endings."
    }
  ]
}
```

### Event Types In Structured Output

Implemented commands currently emit these event types:

* `frame`
* `decoded_message`
* `signal`
* `j1939_pgn`
* `uds_transaction`
* `replay_event`
* `alert`

---

## Exit Codes

* `0` success
* `1` user, input, or usage error
* `2` backend or transport error
* `3` decode, schema, or DBC error
* `4` partial success

Representative failures:

* `INVALID_ARGUMENTS` => exit code `1`
* `INVALID_RATE` => exit code `1`
* `TRANSPORT_UNAVAILABLE` => exit code `2`
* `CAPTURE_SOURCE_UNAVAILABLE` => exit code `2`
* `DBC_LOAD_FAILED` => exit code `3`
* `DBC_SIGNAL_INVALID` => exit code `3`

---

## Examples

### Transport Capture

```bash
canarchy capture can0 --json
```

### Transport Stats

```bash
canarchy stats --file tests/fixtures/sample.candump --json
```

### Capture Metadata

```bash
canarchy capture-info --file tests/fixtures/sample.candump --json
```

### Deterministic Replay

```bash
canarchy replay --file tests/fixtures/sample.candump --rate 0.5 --json
```

### J1939 Monitor

```bash
canarchy j1939 monitor --json
```

### J1939 PGN Filter

```bash
canarchy j1939 monitor --pgn 65262 --json
```

### DBC Decode

```bash
canarchy decode --file tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json
```

### DBC Provider Search

```bash
canarchy dbc search toyota --provider opendbc --json
```

### DBC Provider Decode

```bash
canarchy decode tests/fixtures/sample.candump --dbc opendbc:toyota_tnga_k_pt_generated --json
```

### Reverse-Engineering DBC Match

```bash
canarchy re match-dbc tests/fixtures/sample.candump --provider opendbc --limit 5 --json
```

### DBC Encode

```bash
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
```

### UDS Scan

```bash
canarchy uds scan can0 --json
```

Notes:

* the result reports `protocol_decoder` as `built-in` by default
* when the optional Scapy extra is installed, UDS transaction payloads may include summary-level request/response enrichment without changing the command surface

### UDS Trace

```bash
canarchy uds trace can0 --json
```

Notes:

* the result reports `protocol_decoder` as `built-in` by default
* negative responses may include `negative_response_code` and `negative_response_name`

### Session Save

```bash
canarchy session save lab-a --interface can0 --dbc tests/fixtures/sample.dbc --capture tests/fixtures/sample.candump --json
```

### Shell One-Shot Command

```bash
canarchy shell --command "capture can0 --raw"
```

---

## Current Gaps

These commands are present in the CLI tree but not yet implemented end to end:

* `re signals` and `re correlate`
* `fuzz replay|mutate|id`

These deeper capabilities are also not implemented yet even where the command surface exists:

* deeper live transport integration beyond the current `python-can` transport path
* pretty-print output tailored for UDS commands
