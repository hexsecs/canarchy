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
* dataset provider workflows for `datasets provider list`, `datasets search`, `datasets inspect`, `datasets fetch`, `datasets cache list`, `datasets cache refresh`, `datasets convert`, `datasets stream`, and `datasets replay`
* J1939 `monitor`, `decode`, `pgn`, `spn`, `tp`, `dm1`, `faults`, `summary`, `inventory`, and `compare`
* session `save`, `load`, and `show`
* shell one-shot command execution
* initial text-mode `tui` shell over the shared command layer
* UDS `scan`, `trace`, and `services`
* `config show` for effective transport configuration inspection
* `re signals`, `re counters`, `re entropy`, and `re correlate` for passive file-backed analysis
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
* placeholder-only commands, currently limited to the `fuzz` family, still return `status: planned` and `implementation: command surface scaffold`
* some protocol-oriented commands currently use explicit sample/reference providers rather than true transport-backed execution paths
* specialized text formatting exists for J1939 monitor and decode style output; other `--text` output is generic key/value rendering
* file-backed analysis commands support standard timestamped candump log files with `.candump` and `.log` suffixes; selected commands also support `--file -` for candump text from stdin

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
* `canarchy replay --file tests/fixtures/sample.candump --rate 2.0 --json`
* `canarchy j1939 monitor --pgn 65262 --json`
* `canarchy decode --file tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json`

---

## Implemented Commands

### capture

Capture traffic from a local interface. Structured capture uses the selected transport backend. `--candump` is a live-only mode.

```bash
canarchy capture <interface> [--candump] [--json|--jsonl|--text|--raw]
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
* default text output without `--candump` remains the generic key/value renderer

Supported file input today:

* file-backed commands consume standard timestamped candump logs in the form `(timestamp) interface frame#data`
* supported additional candump forms include classic RTR `id#R`, CAN FD `id##<flags><data>`, and error frames using a CAN error-flagged identifier
* supported CAN FD flags today are the BRS and ESI bits in the single-nibble candump flags field
* supported capture-file suffixes today are `.candump` and `.log`; `--file -` reads candump text from stdin for commands that explicitly support it
* malformed log lines are skipped during capture parsing rather than falling back to fixture data; commands that require capture metadata or explicitly validate stdin emptiness return structured errors when no valid frames are available

### send

Prepare an active transmit frame.

```bash
canarchy send <interface> <frame-id> <hex-data> [--ack-active] [--json|--jsonl|--text|--raw]
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
canarchy filter <expression> (--file <path> | --file - | --stdin) [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--compact|--text|--raw]
```
```

Notes:

* `--file -` reads candump text from standard input instead of a file and still honors `--offset`, `--max-frames`, and `--seconds`
* `--stdin` reads JSONL `frame` events from standard input regardless of output format
* For `filter --stdin`, each line must be a valid `frame` event JSON object

### capture-info

Inspect a candump capture quickly before running deeper analysis.

```bash
canarchy capture-info --file <path> [--json|--jsonl|--text|--raw]
canarchy capture-info --file - [--json|--jsonl|--text|--raw]
```

Notes:

* `--file -` reads candump text from standard input instead of a file
* Returns capture metadata only:

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
canarchy stats --file <path> [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--text|--raw]
canarchy stats --file - [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--text|--raw]
```

Notes:

* `--file -` reads candump text from standard input instead of a file

### generate

Generate CAN frames from explicit, random, or incrementing inputs.

```bash
canarchy generate <interface> [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>] [--count <n>] [--gap <ms>] [--extended] [--ack-active] [--json|--jsonl|--text|--raw]
```

Examples:

```bash
canarchy generate can0 --id 0x123 --dlc 4 --data 11223344 --count 2 --gap 100 --json
canarchy generate can0 --data I --count 4 --text
```

Notes:

* `--id`, `--dlc`, and `--data` accept `R` for random generation, and `--data I` enables a deterministic incrementing payload pattern
* `--ack-active` requests an interactive `YES` confirmation before generated frames are transmitted
* when active acknowledgement is required by configuration, omitting `--ack-active` returns a structured `ACTIVE_ACK_REQUIRED` error
* generated JSON output includes an active-transmit alert followed by generated frame events

### replay

Replay a capture source with deterministic timing derived from relative frame timestamps.

```bash
canarchy replay --file <path> [--rate <factor>] [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy replay --file tests/fixtures/sample.candump --rate 2.0 --json
```

### gateway

Bridge frames from one live CAN interface to another through the `python-can` backend.

```bash
canarchy gateway <src> <dst> [--src-backend <type>] [--dst-backend <type>] [--bidirectional] [--count <n>] [--ack-active] [--json|--jsonl|--text|--raw]
```

Examples:

```bash
canarchy gateway can0 can1 --text
canarchy gateway can0 239.0.0.1 --dst-backend udp_multicast --count 10 --json
```

Notes:

* `gateway` requires the `python-can` backend (set in `~/.canarchy/config.toml` or via `CANARCHY_TRANSPORT_BACKEND=python-can`)
* `--src-backend` and `--dst-backend` default to the configured `interface` value
* `--ack-active` requests an interactive `YES` confirmation before forwarding begins
* default text and raw output use candump-style forwarded frame lines with direction labels such as `[src->dst]`
* `--json` returns a standard command envelope; `--jsonl` emits one forwarded event per line for `gateway`

### export

Export structured artifacts for later analysis.

```bash
canarchy export <source> <destination> [--json|--jsonl|--text|--raw]
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
canarchy decode --file <file> --dbc <file> [--json|--jsonl|--text|--raw]
canarchy decode --stdin --dbc <file> [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy decode --file tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json
```

Notes:

* `--dbc` accepts a local file path or a provider ref such as `opendbc:<name>`
* `--stdin` reads JSONL `frame` events from standard input instead of a `--file` capture source
* structured output includes a `dbc_source` object describing the provider-backed or local DBC resolution that was used

### encode

Encode a DBC message into a frame payload.

```bash
canarchy encode --dbc <file> <message> <signal=value>... [--json|--jsonl|--text|--raw]
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
canarchy dbc inspect <dbc> [--message <name>] [--signals-only] [--json|--jsonl|--text|--raw]
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
canarchy dbc provider list [--json|--jsonl|--text|--raw]
```

### dbc search

Search DBC catalogs across enabled providers.

```bash
canarchy dbc search <query> [--provider <name>] [--limit <n>] [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy dbc search toyota --provider opendbc --limit 5 --json
```

### dbc fetch

Fetch and cache a DBC file from a provider.

```bash
canarchy dbc fetch <ref> [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy dbc fetch opendbc:toyota_tnga_k_pt_generated --json
```

### dbc cache list

List cached provider manifests.

```bash
canarchy dbc cache list [--json|--jsonl|--text|--raw]
```

### dbc cache prune

Remove stale cached provider snapshots while keeping the pinned commit.

```bash
canarchy dbc cache prune [--provider <name>] [--json|--jsonl|--text|--raw]
```

### dbc cache refresh

Refresh a provider catalog from upstream.

```bash
canarchy dbc cache refresh [--provider <name>] [--json|--jsonl|--text|--raw]
```

Notes:

* the default provider is `opendbc`
* refreshing updates the cached catalog manifest; individual DBC files are fetched on demand or through `dbc fetch`
* provider-backed decode, encode, and inspect commands return `DBC_CACHE_MISS` by default when the provider cache is cold; enabling `[dbc.providers.opendbc].auto_refresh = true` allows first-use refresh on resolution

### skills provider list

List registered repository-backed skills providers.

```bash
canarchy skills provider list [--json|--jsonl|--text|--raw]
```

### skills search

Search repository-backed skills catalogs by name, tag, or keyword.

```bash
canarchy skills search <query> [--provider <name>] [--limit <n>] [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy skills search j1939 --provider github --json
```

### skills fetch

Fetch and cache a repository-backed skill locally.

```bash
canarchy skills fetch <provider>:<skill> [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy skills fetch github:j1939_compare_triage --json
```

### skills cache list

List cached skills provider manifests.

```bash
canarchy skills cache list [--json|--jsonl|--text|--raw]
```

### skills cache refresh

Refresh a skills provider catalog from upstream.

```bash
canarchy skills cache refresh [--provider <name>] [--json|--jsonl|--text|--raw]
```

Notes:

* the first provider implementation is GitHub-backed and consumes `.skill.yaml` manifests that follow the CANarchy skill manifest schema
* `skills fetch` returns both the cached manifest path and the cached skill entry path
* skills provider/cache commands are currently CLI-only and are not exposed as MCP tools, resources, or prompts in phase 1
* agents should use skills as workflow descriptors: search, fetch, inspect compatibility/provenance, then run referenced CANarchy commands explicitly

### datasets provider list

List registered public CAN dataset providers.

```bash
canarchy datasets provider list [--json|--jsonl|--text|--raw]
```

### datasets search

Search public CAN dataset provider catalogs by name, protocol, or keyword.

```bash
canarchy datasets search [query] [--provider <name>] [--limit <n>] [--verbose] [--json|--jsonl|--text|--raw]
```

### datasets inspect

Show full metadata for a dataset ref.

```bash
canarchy datasets inspect <provider>:<dataset> [--json|--jsonl|--text|--raw]
```

Examples:

```bash
canarchy datasets search pivot
canarchy datasets inspect catalog:pivot-auto-datasets --json
```

Notes:

* JSON `datasets search` and `datasets inspect` results include stable machine fields: `ref`, `is_replayable`, `is_index`, `default_replay_file`, `download_url_available`, and `source_type`
* `catalog:pivot-auto-datasets` is a curated external source index, not a directly downloadable or replayable dataset
* inspect linked source pages for per-dataset access terms, file formats, and conversion/replay suitability

### datasets fetch

Record dataset provenance in the local cache. This does not download large dataset payloads.

```bash
canarchy datasets fetch <provider>:<dataset> [--json|--jsonl|--text|--raw]
```

Notes:

* normal dataset entries return `download_instructions` that point operators to the source URL for manual download
* curated index entries return `is_index=true` and `index_instructions`; there is no single dataset payload to download

### datasets cache list

List cached dataset provider manifests and provenance records.

```bash
canarchy datasets cache list [--json|--jsonl|--text|--raw]
```

### datasets cache refresh

Refresh the built-in dataset catalog manifest.

```bash
canarchy datasets cache refresh [--provider <name>] [--json|--jsonl|--text|--raw]
```

### datasets convert

Convert a downloaded dataset file to a CANarchy-compatible capture format.

```bash
canarchy datasets convert <file> --source-format hcrl-csv --format candump|jsonl [--output <path>] [--json|--jsonl|--text|--raw]
```

### datasets stream

Stream a downloaded dataset file to candump or JSONL without loading the full conversion into memory.

```bash
canarchy datasets stream <file> --source-format hcrl-csv|candump --format candump|jsonl [--chunk-size <n>] [--max-frames <n>] [--provider-ref <ref>] [--output <path>] [--json]
```

Examples:

```bash
canarchy datasets stream sample.csv --source-format hcrl-csv --format jsonl --provider-ref catalog:hcrl-car-hacking
canarchy datasets stream sample.log --source-format candump --format jsonl --provider-ref catalog:candid
canarchy datasets stream sample.csv --source-format hcrl-csv --format candump --output sample.candump
canarchy datasets stream sample.csv --source-format hcrl-csv --format jsonl --max-frames 1000
canarchy datasets stream sample.csv --source-format hcrl-csv --format jsonl --json
```

Notes:

* `datasets search` defaults to a compact human-readable table with a `TYPE` column (`INDEX` for curated indexes, `PLAY` for replayable datasets); use `--verbose` for detailed result blocks with type labels, descriptions, source URLs, replay defaults, index notes, and access notes
* without `--json`, stream records are written directly to stdout or `--output`
* JSONL stream records include `payload.dataset.provider_ref`, `frame_offset`, `chunk_index`, and `chunk_position`
* `--chunk-size` controls JSONL provenance chunk metadata and does not bound emitted frames
* `--max-frames` stops local dataset streaming after at most N emitted frames for candump and JSONL output
* with `--json`, stdout contains the standard result envelope and reports `frame_count`, `chunks`, and `max_frames`
* live-bus replay from dataset streams is not part of this command; use explicit replay workflows after writing a capture file

### datasets replay

Stream a remote candump dataset file directly to stdout with replay timing. The source may be a direct candump download URL or a replayable dataset ref such as `catalog:candid`.

```bash
canarchy datasets replay <dataset-ref-or-url> [--file <id-or-name>] [--list-files] [--format candump|jsonl] [--rate <multiplier>] [--max-frames <n>] [--max-seconds <seconds>] [--dry-run] [--json]
```

Examples:

```bash
canarchy datasets replay catalog:candid --rate 1.0
canarchy datasets replay catalog:candid --format jsonl --rate 10 --max-frames 1000
canarchy datasets replay catalog:candid --format jsonl --rate 10 --max-seconds 30
canarchy datasets replay catalog:candid --list-files --json
canarchy datasets replay catalog:candid --file 2_indicator_CAN.log --rate 1000 --max-frames 10 --json
canarchy datasets replay https://ndownloader.figshare.com/files/54551156 --rate 1000 --max-frames 10
canarchy datasets replay catalog:candid --rate 1000 --max-frames 10 --json
canarchy datasets replay catalog:candid --dry-run --json
```

Notes:

* without `--json`, replayed frames are written directly to stdout as candump or JSONL records for piping
* JSONL replay frame events include `payload.dataset.provider_ref`, `source_url`, `replay_file`, `default_replay_file`, `frame_offset`, `source_format`, and `source_type`
* with `--json`, stdout contains a clean standard result envelope with replay metadata and no frame records
* `--list-files --json` returns replay file entries with stable `id`, `name`, `size_bytes`, `format`, and `source_url` fields
* `--file` accepts a replay file `id` or `name`; unknown files fail with `DATASET_REPLAY_FILE_NOT_FOUND`
* Curated indexes that cannot be replayed return `DATASET_INDEX_NOT_REPLAYABLE`
* Stdin pipeline: pipe `datasets replay` output into `stats --file -`, `capture-info --file -`, or `filter --file -` for analysis without temporary files
* JSON summary output reports `stop_reason`, including `eof`, `max_frames`, `max_seconds`, `broken_pipe`, or `interrupted`
* replay downloads incrementally from the remote HTTP response and does not require a complete local dataset file
* `--dry-run` resolves replay source metadata without opening the remote stream
* replaying a curated index entry fails with `DATASET_INDEX_NOT_REPLAYABLE`; other non-replayable datasets fail with `DATASET_REPLAY_UNAVAILABLE`
* `catalog:candid` currently resolves to the CANdid `2_brakes_CAN.log` Figshare file as its default replay source

### session save

Save a named session with useful CLI context.

```bash
canarchy session save <name> [--interface <name>] [--dbc <file>] [--capture <file>] [--json|--jsonl|--text|--raw]
```

### session load

Load a previously saved session and mark it active.

```bash
canarchy session load <name> [--json|--jsonl|--text|--raw]
```

### session show

Show saved sessions and the active session.

```bash
canarchy session show [--json|--jsonl|--text|--raw]
```

### shell

Run a single shell command through the shared parser, or start a minimal interactive shell loop.

```bash
canarchy shell [--command "capture can0 --raw"] [--json|--jsonl|--text|--raw]
```

### j1939 monitor

Inspect J1939 traffic and emit PGN-oriented structured events.

```bash
canarchy j1939 monitor [<interface>] [--pgn <id>] [--json|--jsonl|--text|--raw]
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
canarchy j1939 decode --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text|--raw]
canarchy j1939 decode --stdin [--dbc <path|provider-ref>] [--json|--jsonl|--text|--raw]
```

Notes:

* `--stdin` reads JSONL `frame` events from standard input instead of a `--file` capture source
* `--dbc` enriches J1939 results with DBC-backed decoded signal events when available

### j1939 pgn

Inspect events for a specific PGN from a capture file.

```bash
canarchy j1939 pgn <pgn> --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy j1939 pgn 65262 --file tests/fixtures/sample.candump --json
```

### j1939 spn

Inspect a curated SPN decoder over recorded J1939 traffic.

```bash
canarchy j1939 spn <spn> --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text|--raw]
```

Example:

```bash
canarchy j1939 spn 110 --file tests/fixtures/sample.candump --json
```

Notes:

* curated metadata is built in for common SPNs
* `--dbc` can expand coverage for SPNs exposed through DBC signal metadata
* unsupported SPNs return a structured `J1939_SPN_UNSUPPORTED` error

### j1939 tp sessions

Summarize J1939 transport-protocol sessions from a capture file.

```bash
canarchy j1939 tp sessions --file <file> [--json|--jsonl|--text|--raw]
```

Notes:

* the implementation handles BAM and RTS/CTS transport sessions with packet reassembly

### j1939 dm1

Inspect DM1 fault traffic from direct J1939 frames and TP-reassembled payloads.

```bash
canarchy j1939 dm1 --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text|--raw]
```

### j1939 faults

Summarize active DM1 faults by ECU/source address, including lamp state and suspicious DTC markers.

```bash
canarchy j1939 faults --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text|--raw]
```

### j1939 inventory

Build a source-address inventory from a J1939 capture file, including top PGNs, component-identification strings, vehicle-identification strings, and DM1 presence.

```bash
canarchy j1939 inventory --file <file> [--json|--jsonl|--text|--raw]
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
canarchy j1939 compare <file> <file> [<file> ...] [--json|--jsonl|--text|--raw]
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
canarchy uds scan <interface> [--ack-active] [--json|--jsonl|--text|--raw]
```

Notes:

* with the `python-can` backend, this command sends a single-frame functional DiagnosticSessionControl request and summarizes captured UDS responses after ISO-TP reassembly when needed
* with the `scaffold` backend, this command emits explicit sample/reference UDS transaction data
* `--ack-active` requests an interactive `YES` confirmation before the diagnostic request is sent
* if a segmented response is truncated or arrives out of order, the emitted `uds_transaction` event keeps the partial `response_data` and sets `complete` to `false`

### uds trace

Inspect representative UDS request and response transactions.

```bash
canarchy uds trace <interface> [--json|--jsonl|--text|--raw]
```

Notes:

* with the `python-can` backend, this command captures raw CAN frames and infers UDS request/response transactions from common diagnostic IDs, including ISO-TP multi-frame responses
* with the `scaffold` backend, this command emits explicit sample/reference UDS transaction data
* flow-control frames are used only for reassembly and are not emitted as transactions
* if a segmented response is truncated or arrives out of order, the emitted `uds_transaction` event keeps the partial `response_data` and sets `complete` to `false`

### uds services

Inspect the built-in UDS service catalog.

```bash
canarchy uds services [--json|--jsonl|--text|--raw]
```

Notes:

* this is a reference command and does not require an interface
* output includes service identifier, positive-response identifier, category, and subfunction expectations

### re counters

Rank likely counter fields from recorded CAN traffic.

```bash
canarchy re counters <file> [--json|--jsonl|--text|--raw]
```

Notes:

* this command is passive and file-backed
* the current implementation inspects nibble- and byte-sized candidate fields on recorded arbitration IDs
* candidates are ranked by monotonicity evidence and explicit rollover detection

### re signals

Rank likely signal fields from recorded CAN traffic.

```bash
canarchy re signals <file> [--json|--jsonl|--text|--raw]
```

Notes:

* this command is passive and file-backed
* the current implementation inspects nibble-aligned 4-bit fields, byte-aligned 8-bit fields, and word-aligned 16-bit fields
* candidates are ranked by change-rate preference, observed range, and value diversity
* arbitration IDs with fewer than 5 frames are omitted from the candidate list and reported in `low_sample_ids`

### re correlate

Correlate candidate bit fields against a timestamped reference series.

```bash
canarchy re correlate <file> --reference <ref.json|ref.jsonl> [--json|--jsonl|--text|--raw]
```

Notes:

* this command is passive and file-backed
* reference files may be JSON arrays, named JSON objects with `name` and `samples`, or JSONL sample streams
* each reference sample must include numeric `timestamp` and `value` fields
* candidates report `pearson_r`, `spearman_r`, `sample_count`, and `lag_ms`, and are ranked by absolute Pearson correlation

### re entropy

Rank arbitration IDs and byte positions by Shannon entropy over recorded CAN traffic.

```bash
canarchy re entropy <file> [--json|--jsonl|--text|--raw]
```

Notes:

* this command is passive and file-backed
* JSON output includes one candidate per arbitration ID plus a per-byte entropy breakdown inside each candidate
* IDs with fewer than 10 observed frames are retained and marked with `low_sample: true`

### re match-dbc

Rank candidate DBC files against a capture using provider-backed catalog metadata.

```bash
canarchy re match-dbc <capture> [--provider <name>] [--limit <n>] [--json|--jsonl|--text|--raw]
```

Notes:

* this command is passive and file-backed
* candidates are scored by frequency-weighted arbitration-ID coverage against the capture
* the default provider is `opendbc`

### re shortlist-dbc

Rank candidate DBC files against a capture after pre-filtering by vehicle make.

```bash
canarchy re shortlist-dbc <capture> --make <brand> [--provider <name>] [--limit <n>] [--json|--jsonl|--text|--raw]
```

Notes:

* this command is passive and file-backed
* `--make` narrows provider-catalog candidates before scoring them against the capture
* the default provider is `opendbc`

### config show

Inspect the effective transport configuration and the source of each setting.

```bash
canarchy config show [--json|--jsonl|--text|--raw]
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
* `--text`
* `--raw`

`--text` is the default when no output mode is specified. `--table` remains accepted as a compatibility alias for `--text`, but new examples and automation should use `--text`.

Current behavior:

* `--json` emits one structured JSON object
* `--jsonl` emits one JSON object per line
* event-producing commands emit each event as its own JSON line; command warnings that are not already events are emitted as `alert` event lines
* event-less successful commands emit a single result object line
* failed commands emit a single error result object line
* `--text` emits a human-readable summary view, with protocol-aware pretty-printing for J1939 monitor and decode workflows
* `--raw` emits the command name on success or the primary error message on failure

J1939 `--text` output includes:

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
canarchy decode --file tests/fixtures/sample.candump --dbc opendbc:toyota_tnga_k_pt_generated --json
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

### Dataset Analysis (CANdid)

The CANdid dataset (VehicleSec 2025) provides candump-format CAN logs ready for direct analysis:

```bash
# Summarize a CANdid capture
canarchy stats --file 2_driving_CAN.log --json
canarchy capture-info --file 2_driving_CAN.log --json

# Filter for specific IDs
canarchy filter 'id==0x123' --file 2_steering_CAN.log --json

# Reverse-engineering helpers
canarchy re entropy --file 2_driving_CAN.log
canarchy re counters --file 2_driving_CAN.log

# Inspect the catalog entry
canarchy datasets inspect catalog:candid --json
```

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

* `fuzz replay|mutate|id`

These deeper capabilities are also not implemented yet even where the command surface exists:

* deeper live transport integration beyond the current `python-can` transport path
* pretty-print output tailored for UDS commands
