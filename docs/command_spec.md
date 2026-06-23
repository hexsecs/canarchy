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
* XCP (measurement/calibration) `scan`, `trace`, `read`, and `commands` for XCP-on-CAN
* J1587/J1708 `decode` and `pids` for legacy heavy-vehicle diagnostic captures
* J2497 (PLC4TRUCKS) `decode` and `mids` for passive trailer power-line frame captures
* `config show` for effective transport configuration inspection
* `re signals`, `re counters`, `re entropy`, `re correlate`, and `re anomalies` for passive file-backed analysis
* `re match-dbc` and `re shortlist-dbc` for provider-backed DBC candidate ranking against captures
* `re suggest` for heuristic signal-name suggestions (with an optional, off-by-default external-LLM enrichment)
* `plugins list`, `plugins info`, `plugins enable`, and `plugins disable` for Python entry-point plugin inspection and toggles
* `web serve` for the read-only browser dashboard over the JSONL event envelope
* `cannelloni decode` and `cannelloni send` for cannelloni CAN-over-UDP wire-format interop
* structured JSON and JSONL output
* explicit error schema and exit codes

Important current behavior:

* live transport-facing commands default to the `python-can` backend; set `backend = "scaffold"` in `~/.canarchy/config.toml` or export `CANARCHY_TRANSPORT_BACKEND=scaffold` for deterministic offline behavior
* `capture`, `send`, and `gateway` use the selected transport backend, but `gateway` specifically requires `python-can`
* the default `python-can` interface is `socketcan`; set `interface` in the config file or `CANARCHY_PYTHON_CAN_INTERFACE` to change it
* the default CAN interface/channel is optional; set `default_interface` in the config file or `CANARCHY_DEFAULT_INTERFACE` to let single-interface commands such as `capture`, `send`, `generate`, `uds scan`, and live fuzz commands omit the interface argument
* DBC-backed commands accept local paths and provider refs such as `opendbc:<name>` or `comma:<name>`
* database-backed commands (`decode`, `encode`, `dbc inspect`, `dbc convert`, …) also accept ARXML (`.arxml`), KCD (`.kcd`), and SYM (`.sym`) files in addition to DBC (`.dbc`); the format is selected by filename suffix through the cantools runtime, and the user-facing flag remains `--dbc`
* `decode`, `encode`, and `dbc inspect` include `data.dbc_source` in structured output so callers can see the provider, logical DBC name, pinned version, resolved local path, and database `kind` (`dbc` / `arxml` / `kcd` / `sym`); `dbc inspect` additionally reports the same value as `data.database.format`
* some protocol-oriented commands currently use explicit sample/reference providers rather than true transport-backed execution paths
* specialized text formatting exists for J1939 monitor and decode style output; other `--text` output is generic key/value rendering
* file-backed analysis commands support standard timestamped candump log files (`.candump`, `.log`) and pcap/pcapng files (`.pcap`, `.pcapng`) with CAN SocketCAN (DLT 227) frames; selected commands also support `--file -` for candump text from stdin
* commands that historically took positional capture paths (the `re *` family and `j1939 compare`) also accept the `--file <path>` flag form (repeatable for multi-file commands); supplying both forms with different paths returns `CONFLICTING_FILE_ARGUMENTS`

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
* `canarchy capture --json` when `[transport].default_interface` is configured
* `canarchy replay --file tests/fixtures/sample.candump --rate 2.0 --json`
* `canarchy j1939 monitor --pgn 65262 --json`
* `canarchy decode --file tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json`

---

## Implemented Commands

### capture

Capture traffic from a local interface. Structured capture uses the selected transport backend. `--candump` is a live-only mode.

```bash
canarchy capture [interface] [--candump] [--json|--jsonl|--text]
```

Example:

```bash
canarchy capture can0 --json
canarchy capture vcan0 --candump
```

Notes:

* `--candump` is a live-only mode that requires the `python-can` backend (set in `~/.canarchy/config.toml` or via `CANARCHY_TRANSPORT_BACKEND=python-can`)
* if `interface` is omitted, `capture` uses `[transport].default_interface` or `CANARCHY_DEFAULT_INTERFACE`; without either, it returns `INTERFACE_REQUIRED`
* `--candump` keeps running and printing frames until interrupted
* `--candump` changes the human-readable output path to a `candump`-style line format such as `(0.100000) vcan0 18F00431#AABBCCDD`
* `--candump --json` and `--candump --jsonl` keep structured output for automation, but still require a live backend
* default text output without `--candump` remains the generic key/value renderer

Supported file input today:

* file-backed commands consume standard timestamped candump logs in the form `(timestamp) interface frame#data`
* supported additional candump forms include classic RTR `id#R`, CAN FD `id##<flags><data>`, and error frames using a CAN error-flagged identifier
* supported CAN FD flags today are the BRS and ESI bits in the single-nibble candump flags field
* supported capture-file suffixes today are `.candump`, `.log`, `.pcap`, and `.pcapng`; `--file -` reads candump text from stdin for commands that explicitly support it
* pcap/pcapng support requires the file to use the CAN SocketCAN linktype (DLT 227); files with other linktypes are rejected with a clear error
* pcap/pcapng files are always fully scanned (no fast-scan estimation); the binary format does not support text-based head/tail estimation
* malformed log lines are skipped during capture parsing rather than falling back to fixture data; commands that require capture metadata or explicitly validate stdin emptiness return structured errors when no valid frames are available

### send

Prepare an active transmit frame.

```bash
canarchy send [interface] <frame-id> <hex-data> [--dry-run] [--ack-active] [--json|--jsonl|--text]
```

Example:

```bash
canarchy send can0 0x123 11223344 --json
```

Notes:

* `--ack-active` requests an interactive `YES` confirmation before the frame is transmitted
* `--dry-run` returns the planned frame without opening a transport or requiring confirmation
* when active acknowledgement is required by configuration, omitting `--ack-active` returns a structured `ACTIVE_ACK_REQUIRED` error
* if `interface` is omitted, `send` uses `[transport].default_interface` or `CANARCHY_DEFAULT_INTERFACE`; explicit command-line interfaces take precedence over the configured default

### filter

Filter a capture source by a simple expression.

```bash
canarchy filter <expression> (--file <path> | --file - | --stdin) [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--text]
```
```

Notes:

* `--file -` reads candump text from standard input instead of a file and still honors `--offset`, `--max-frames`, and `--seconds`
* `--stdin` reads JSONL `frame` events from standard input regardless of output format
* For `filter --stdin`, each line must be a valid `frame` event JSON object
* expression operands for `id==` / `pgn==` accept decimal, `0x`-prefixed hex, or bare hex, and all operators tolerate surrounding whitespace (e.g. `pgn == 61444`)
* supported atoms: `all`, `id==<id>`, `pgn==<pgn>`, `dlc><n>`, `data~=<hex>`, `extended`, `standard`, combined with `&&` / `||`
* on an invalid expression the JSON error envelope carries no `frames` / `frame_count` block, so an error can never read as a successful zero-match

### capture-info

Inspect a candump capture quickly before running deeper analysis.

```bash
canarchy capture-info --file <path> [--json|--jsonl|--text]
canarchy capture-info --file - [--json|--jsonl|--text]
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

Summarize a capture source. The capture path may be given positionally or via `--file` (equivalent).

```bash
canarchy stats <path> [--top <n>] [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--text]
canarchy stats --file <path> [--top <n>] [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--text]
canarchy stats --file - [--top <n>] [--offset <n>] [--max-frames <n>] [--seconds <seconds>] [--json|--jsonl|--text]
```

The following passive analysis commands likewise accept a positional capture path as an alias for `--file`: `stats`, `j1939 summary`, `j1939 faults`, `j1939 dm1`, `j1939 inventory`, `j1939 map`, `j1939 tp sessions`, `j1939 tp compare`, `j1587 decode`, `j2497 decode`. Supplying both forms with different paths returns `CONFLICTING_FILE_ARGUMENTS`.

Notes:

* `--file -` reads candump text from standard input instead of a file
* beyond `total_frames` / `unique_arbitration_ids`, the payload reports `duration_seconds`, first/last timestamps, a `dlc_distribution`, and a `bus_load` block with total bits, bits/s, and load percentages at 250 k / 500 k / 1 M bit/s (frame overhead without stuff bits; a lower-bound estimate)
* `top_ids` details the highest-frequency arbitration ids (default 20, bounded by `--top`): `arbitration_id_hex`, `frame_count`, `share`, `rate_hz`, mean/min/max inter-frame gap, `gap_jitter_ms`, observed DLCs, and first/last seen

### compare

Diff two or more plain CAN captures per arbitration ID against a baseline, the generic-CAN analogue of `j1939 compare`.

```bash
canarchy compare (<file> <file> [<file> ...] | --file <file> --file <file> ...) [--baseline <path>] \
    [--top <n>] [--offset <n>] [--max-frames <n>] [--seconds <s>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed; it accepts two or more captures positionally or via repeatable `--file`, and requires at least two (`COMPARE_NEEDS_FILES` otherwise)
* the baseline is the first file unless `--baseline <path>` designates another; a `--baseline` outside the compared set is folded in as the reference
* each `comparison` entry reports, per arbitration ID, the per-file `frame_counts`, `rates_hz`, `mean_gap_ms`, and `mean_byte_entropy` arrays, the `frame_count_delta` / `rate_ratio` / `entropy_delta` versus the baseline, a `cycle_time_drift_ratio` (reusing the `re corpus` drift formulation), a combined `change_score`, and a `flags` list (`new-vs-baseline`, `dropped-vs-baseline`, `rate-drop`, `rate-spike`, `entropy-collapse`, `timing-drift`)
* entries are ranked by `change_score` and capped at `--top` (default 20; `0` for all); `id_count` reports the full total and `returned_count` the number returned
* the `summary` block lists the affected IDs by category (`new_ids`, `dropped_ids`, `rate_drop_ids`, `rate_spike_ids`, `entropy_collapse_ids`, `timing_drift_ids`); J1939 ids are annotated with `pgn`, `pgn_label`, and `source_address_name`
* `--offset`, `--max-frames`, and `--seconds` bound each capture independently

### generate

Generate CAN frames from explicit, random, or incrementing inputs.

```bash
canarchy generate [interface] [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>] [--count <n>] [--gap <ms>] [--extended] [--dry-run] [--ack-active] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy generate can0 --id 0x123 --dlc 4 --data 11223344 --count 2 --gap 100 --json
canarchy generate --id 0x123 --dlc 4 --data 11223344 --count 2 --dry-run --json
canarchy generate can0 --data I --count 4 --text
```

Notes:

* `--id`, `--dlc`, and `--data` accept `R` for random generation, and `--data I` enables a deterministic incrementing payload pattern
* `--dry-run` emits the planned generated frame events without requiring an interface or opening a transport
* `--ack-active` requests an interactive `YES` confirmation before generated frames are transmitted
* when active acknowledgement is required by configuration, omitting `--ack-active` returns a structured `ACTIVE_ACK_REQUIRED` error
* generated JSON output includes an active-transmit alert followed by generated frame events

### simulate

Emit a deterministic, profile-driven mix of classic CAN, J1939, and DM1 traffic without hardware or an external generator.

```bash
canarchy simulate [interface] --profile {heavy-truck,passenger-car} [--rate <hz>] \
    [--duration <seconds>] [--seed <n>] [--dry-run] [--ack-active] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy simulate --profile heavy-truck --duration 5 --dry-run --json
canarchy simulate vcan0 --profile passenger-car --rate 50 --seed 7 --ack-active --json
```

Notes:

* profiles are data-driven JSON resources (`canarchy/resources/simulate/profiles.json`); frame mix, weights, and DM1 bursts are defined there, so new archetypes need no code changes
* deterministic and seedable via `--seed`; timestamps are spaced at `1 / --rate`
* `--dry-run` plans the frame mix without transmitting; live transmission honors the active-transmit safety model (`--ack-active`, `YES` confirmation, `[safety].require_active_ack`)
* reuses the existing transport backends, including `socketcan` virtual interfaces, `udp_multicast`, and stdout candump piping
* structured errors: `SIMULATE_INVALID_RATE`, `SIMULATE_INVALID_DURATION`

### replay

Replay a capture source with deterministic timing derived from relative frame timestamps. By default this returns a replay plan (planning mode). When `--interface` is specified, frames are transmitted onto a live CAN bus with capture timing.

```bash
canarchy replay --file <path> [--interface <iface>] [--rate <factor>] [--dry-run] [--ack-active] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy replay --file tests/fixtures/sample.candump --rate 2.0 --json
canarchy replay --file tests/fixtures/sample.candump --interface vcan0 --rate 1.0 --ack-active --json
canarchy replay --file tests/fixtures/sample.candump --interface vcan0 --dry-run --json
```

### gateway

Bridge frames from one live CAN interface to another through the `python-can` backend.

```bash
canarchy gateway <src> <dst> [--src-backend <type>] [--dst-backend <type>] [--bidirectional] [--count <n>] [--dry-run] [--ack-active] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy gateway can0 can1 --text
canarchy gateway can0 can1 --dry-run --json
canarchy gateway can0 239.0.0.1 --dst-backend udp_multicast --count 10 --json
```

Notes:

* `gateway` requires the `python-can` backend (set in `~/.canarchy/config.toml` or via `CANARCHY_TRANSPORT_BACKEND=python-can`)
* `--src-backend` and `--dst-backend` default to the configured `interface` value
* `--dry-run` returns the forwarding plan without opening either transport
* `--ack-active` requests an interactive `YES` confirmation before forwarding begins
* default text output use candump-style forwarded frame lines with direction labels such as `[src->dst]`
* `--json` returns a standard command envelope; `--jsonl` emits one forwarded event per line for `gateway`

### export

Export structured artifacts for later analysis.

```bash
canarchy export <source> <destination> [--json|--jsonl|--text]
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
canarchy decode --file <file> --dbc <file> [--json|--jsonl|--text]
canarchy decode --stdin --dbc <file> [--json|--jsonl|--text]
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
canarchy encode --dbc <file> <message> <signal=value>...
                 [--crc-algorithm stellantis|sae-j1850|fca-giorgio]
                 [--json|--jsonl|--text]
```

Example:

```bash
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
```

Notes:

* `--dbc` accepts a local file path or a provider ref such as `opendbc:toyota_tnga_k_pt_generated`
* `--crc-algorithm` overrides checksum detection for DBC messages with an 8-bit `CHECKSUM` signal; when omitted, CANarchy attempts DBC-name detection and otherwise uses the default supported CRC behavior
* explicitly supplied `CHECKSUM=<value>` signal assignments are preserved
* structured output includes a `dbc_source` object describing the provider-backed or local DBC resolution that was used
* message names resolve by exact DBC name, case/spacing-insensitive match, or SAE PGN label/name (e.g. `EEC1` → the DBC message carrying PGN 61444); signal names resolve by exact DBC name, case/spacing-insensitive match, or the bundled SAE SPN name — so names displayed by `decode`/`j1939` re-encode directly (e.g. `encode EEC1 "Engine Speed=1200"`)
* when a PGN label matches several messages (same PGN, different source addresses), the supplied signal names break the tie; a remaining ambiguity returns `DBC_MESSAGE_NOT_FOUND` listing the candidates
* unsupplied signals default to the DBC initial value (else 0, clamped into range/choices) so single-signal encodes work; every default is reported under `data.resolution.filled_signals` and in a warning — review before transmitting (multiplexed messages are not auto-filled)
* all non-exact resolutions are recorded under `data.resolution` (`message.via`, `signal_aliases`) and warned about; misspelled names get closest-match suggestions in the error hint
* `send --dbc` applies the same resolution and defaulting, with a transmission-specific warning

### plot

Plot decoded signal time-series from a capture to PNG, SVG, or HTML.

```bash
canarchy plot --file <capture> --dbc <path|provider:ref> --signal <name> [--signal <name> ...] \
    --out <path> [--format {png,svg,html}] [--offset <n>] [--max-frames <n>] [--seconds <s>] [--json|--jsonl|--text]
```

Example:

```bash
canarchy plot --file drive.candump --dbc truck.dbc --signal EngineSpeed --signal VehicleSpeed --out rpm.png --json
```

Notes:

* requires the optional plotting extra: `pip install canarchy[plot]` (matplotlib for PNG/SVG, plotly for HTML); a missing dependency returns `PLOT_DEPENDENCY_MISSING` with the install hint
* `--dbc` accepts a local database path or a `provider:ref` (e.g. `opendbc:<name>`), resolved like `decode`/`encode`; the envelope includes `dbc_source` describing the resolution, and a bad ref returns the standard `DBC_*` error
* multiple `--signal` flags overlay signals; `--format` selects the renderer (default `png`)
* the envelope reports the output file path plus `signals_plotted` and `data_points`
* `--offset`, `--max-frames`, and `--seconds` bound the analysed window like the rest of the file-backed surface
* structured errors: `PLOT_DEPENDENCY_MISSING`, `PLOT_ERROR`, `UNSUPPORTED_OUTPUT_FORMAT`

### cannelloni decode

Decode a captured cannelloni CAN-over-UDP datagram payload into CAN frames.

```bash
canarchy cannelloni decode --file <payload> [--json|--jsonl|--text]
```

Notes:

* reads one or more concatenated cannelloni datagrams (wire version 2) from a raw payload file and emits canonical `frame` events
* passive and file-backed; supports classic CAN, extended, RTR, error, and CAN FD frames
* structured errors: `CANNELLONI_TRUNCATED`, `CANNELLONI_VERSION_UNSUPPORTED`, `CANNELLONI_INVALID_DLC`, `CANNELLONI_FILE_UNREADABLE`

### cannelloni send

Transmit a capture to a cannelloni endpoint as UDP datagrams.

```bash
canarchy cannelloni send <host:port> --file <capture> [--seq-no <n>] [--max-count <n>] \
    [--rate <hz>] [--ack-active] [--dry-run] [--offset <n>] [--max-frames <n>] [--seconds <s>] \
    [--json|--jsonl|--text]
```

Notes:

* active-transmit path gated by the [active-transmit safety design](design/active-transmit-safety.md) (`--ack-active`, `YES` confirmation, `[safety].require_active_ack`)
* `--dry-run` plans the datagrams (returned as hex in `data.datagrams`) without opening a socket
* `--max-count` bounds frames per datagram (default 64); `--mtu` bounds encoded bytes per datagram (default 1500, so a stock peer's MTU is not overrun by CAN FD frames; `--mtu 0` disables it); `--rate` paces datagrams per second; `--seq-no` sets the starting cannelloni sequence number
* CLI-only (not an MCP tool): active UDP egress to an arbitrary host
* structured errors: `CANNELLONI_INVALID_TARGET` (exit 1), `CANNELLONI_SEND_FAILED` (exit 2)

### web serve

Serve the read-only browser dashboard over HTTP + WebSocket.

```bash
canarchy web serve --file <capture> [--dbc <path|provider:ref>] [--bind <host:port>] \
    [--rate <multiplier>] [--loop] [--offset <n>] [--max-frames <n>] [--seconds <s>] \
    [--json|--jsonl|--text]
```

Example:

```bash
canarchy web serve --file tests/fixtures/j1939_heavy_vehicle.candump --dbc tests/fixtures/j1939_sample.dbc --json
```

Notes:

* streams the capture as canonical envelope events (`frame`, `j1939_pgn` with bundled PGN/source-address annotation, `decoded_message` when `--dbc` is supplied, `uds_transaction` reassembled from the capture) to the bundled single-file SPA
* the server is read-only: no active-transmit endpoints exist and non-GET requests return HTTP 405 with `WEB_READ_ONLY`
* default bind is `127.0.0.1:8474`; port `0` selects an ephemeral port and the startup envelope reports the resolved `url`
* `--rate` scales timestamp pacing (`0` disables it; gaps are capped at 1 s); `--loop` restarts the stream when the capture ends, otherwise a `STREAM_COMPLETE` alert closes it
* structured errors: `WEB_BIND_INVALID` / `WEB_BIND_FAILED` (exit 1) and the standard capture-file transport errors (exit 2)
* the command runs until interrupted and is not exposed as an MCP tool (long-running front end, like `shell`/`tui`)

### dbc inspect

Inspect database, message, and signal metadata for a DBC file or provider ref.

```bash
canarchy dbc inspect <dbc> [--message <name>] [--signals-only] [--search <pattern>] [--layout] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy dbc inspect tests/fixtures/sample.dbc --json
canarchy dbc inspect opendbc:toyota_tnga_k_pt_generated --message STEER_TORQUE_SENSOR --json
canarchy dbc inspect tests/fixtures/sample.dbc --message EngineStatus1 --layout --text
```

Notes:

* `<dbc>` accepts a local file path or a provider ref such as `opendbc:<name>` or `comma:<name>`
* the database file may be DBC (`.dbc`), ARXML (`.arxml`), KCD (`.kcd`), or SYM (`.sym`); the format is detected by suffix and `data.database.format` / `data.dbc_source.kind` report which loader was used
* structured output includes `dbc_source` provenance alongside the inspection payload
* `--layout` adds cantools-rendered per-message `layout`, `signal_tree`, and `signal_choices` strings; text output renders those diagrams directly, while JSON/JSONL keep them as fields on each message payload

### dbc convert

Convert a loaded database to another cantools-supported serialization
format (DBC, KCD, or SYM).

```bash
canarchy dbc convert <dbc> --to {dbc,kcd,sym} [--out <path>] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy dbc convert tests/fixtures/sample.dbc --to kcd --out sample.kcd
canarchy dbc convert opendbc:toyota_tnga_k_pt_generated --to sym --json
```

Notes:

* `<dbc>` accepts a local file path or a provider ref such as `opendbc:<name>`; the source may be any format the cantools runtime can load
* serialization uses the cantools `as_dbc_string` / `as_kcd_string` / `as_sym_string` emitters — no hand-rolled writers
* with `--out`, the converted database is written to the given path and the envelope reports `out`, `target_format`, `message_count`, and `signal_count`; without `--out`, the serialized `content` is returned in the envelope (and printed directly in `--text` mode)
* structured errors cover unwritable output directories (`DBC_CONVERT_WRITE_FAILED`) and serialization failures where the target format cannot express a source feature (`DBC_CONVERT_FAILED`)

### dbc generate-c

Generate C source and header files from a database using the cantools C
source generator with `pack`/`unpack` structs and helpers.

```bash
canarchy dbc generate-c <dbc> [--out-dir <dir>] [--database-name <name>]
    [--no-floating-point-numbers] [--bit-fields] [--use-float] [--node <name>]
    [--use-round] [--json|--jsonl|--text]
```

Examples:

```bash
canarchy dbc generate-c tests/fixtures/sample.dbc --out-dir ./out --json
canarchy dbc generate-c opendbc:toyota_tnga_k_pt_generated --out-dir ./c_code --bit-fields --json
```

Notes:

* `<dbc>` accepts a local file path or a provider ref such as `opendbc:<name>`; the source may be any format the cantools runtime can load
* `--out-dir` specifies the output directory (default: current directory); it must already exist
* `--database-name` sets the prefix used for all defines, data structures, and functions in the generated code (default: derived from the source filename stem)
* four files are generated per database: `.h` header, `.c` source, `_fuzzer.c` fuzzer source, and `_fuzzer.mk` fuzzer makefile
* the envelope returns `out_dir`, `database_name`, `files` (list of `{path, kind, size_bytes}`), and `file_count`
* structured errors cover missing output directories (`DBC_GENERATE_C_DIR_MISSING`), write failures (`DBC_GENERATE_C_WRITE_FAILED`), and generation failures (`DBC_GENERATE_C_FAILED`)
* MCP is not exposed — file generation is a developer action

### dbc provider list

List registered DBC providers.

```bash
canarchy dbc provider list [--json|--jsonl|--text]
```

### dbc search

Search DBC catalogs across enabled providers.

```bash
canarchy dbc search <query> [--provider <name>] [--limit <n>] [--json|--jsonl|--text]
```

Example:

```bash
canarchy dbc search toyota --provider opendbc --limit 5 --json
```

### dbc fetch

Fetch and cache a DBC file from a provider.

```bash
canarchy dbc fetch <ref> [--json|--jsonl|--text]
```

Example:

```bash
canarchy dbc fetch opendbc:toyota_tnga_k_pt_generated --json
```

### dbc cache list

List cached provider manifests.

```bash
canarchy dbc cache list [--json|--jsonl|--text]
```

### dbc cache prune

Remove stale cached provider snapshots while keeping the pinned commit.

```bash
canarchy dbc cache prune [--provider <name>] [--json|--jsonl|--text]
```

### dbc cache refresh

Refresh a provider catalog from upstream.

```bash
canarchy dbc cache refresh [--provider <name>] [--json|--jsonl|--text]
```

Notes:

* the default provider is `opendbc`
* refreshing updates the cached catalog manifest; individual DBC files are fetched on demand or through `dbc fetch`
* provider-backed decode, encode, and inspect commands return `DBC_CACHE_MISS` by default when the provider cache is cold; enabling `[dbc.providers.opendbc].auto_refresh = true` allows first-use refresh on resolution

### skills provider list

List registered repository-backed skills providers.

```bash
canarchy skills provider list [--json|--jsonl|--text]
```

### skills search

Search repository-backed skills catalogs by name, tag, or keyword.

```bash
canarchy skills search <query> [--provider <name>] [--limit <n>] [--json|--jsonl|--text]
```

Example:

```bash
canarchy skills search j1939 --provider github --json
```

### skills fetch

Fetch and cache a repository-backed skill locally.

```bash
canarchy skills fetch <provider>:<skill> [--json|--jsonl|--text]
```

Example:

```bash
canarchy skills fetch github:j1939_compare_triage --json
```

### skills cache list

List cached skills provider manifests.

```bash
canarchy skills cache list [--json|--jsonl|--text]
```

### skills cache refresh

Refresh a skills provider catalog from upstream.

```bash
canarchy skills cache refresh [--provider <name>] [--json|--jsonl|--text]
```

Notes:

* the first provider implementation is GitHub-backed and consumes `.skill.yaml` manifests that follow the CANarchy skill manifest schema
* `skills fetch` returns both the cached manifest path and the cached skill entry path
* skills provider/cache commands are mirrored by MCP tools for search/fetch/cache workflows, but skills themselves are workflow descriptors rather than MCP prompts or resources
* agents should use skills as workflow descriptors: search, fetch, inspect compatibility/provenance, then run referenced CANarchy commands explicitly

### plugins list

List registered Python entry-point plugins and built-in plugins.

```bash
canarchy plugins list [--json|--jsonl|--text]
```

Output includes each plugin's `name`, `kind` (`processor`, `sink`, or `input`), `api_version`, package `version`, `source_distribution`, `entry_point_group`, `enabled`, and `configured_options` fields.

### plugins info

Show metadata and configured options for a registered plugin name.

```bash
canarchy plugins info <name> [--json|--jsonl|--text]
```

If the same name is registered in more than one plugin namespace, `data.plugins` contains each matching entry and `data.match_count` reports the count.

### plugins enable / disable

Persist a plugin toggle in `~/.canarchy/config.toml` under `[plugins."<name>"].enabled`.

```bash
canarchy plugins enable <name> [--json|--jsonl|--text]
canarchy plugins disable <name> [--json|--jsonl|--text]
```

Notes:

* enable/disable requires the plugin to be discovered by the current environment; unknown names return `PLUGIN_NOT_FOUND`
* `plugins_list` and `plugins_info` are mirrored by MCP tools; enable/disable is intentionally CLI-only because it writes user config

### datasets provider list

List registered public CAN dataset providers.

```bash
canarchy datasets provider list [--json|--jsonl|--text]
```

### datasets search

Search public CAN dataset provider catalogs by name, protocol, or keyword.

```bash
canarchy datasets search [query] [--provider <name>] [--limit <n>] [--verbose] [--json|--jsonl|--text]
```

### datasets inspect

Show full metadata for a dataset ref.

```bash
canarchy datasets inspect <provider>:<dataset> [--json|--jsonl|--text]
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
canarchy datasets fetch <provider>:<dataset> [--json|--jsonl|--text]
```

Notes:

* `datasets fetch` records provenance **only** — it does not download data. Use `datasets download` to retrieve the actual file, or `datasets replay` to stream it.
* normal dataset entries return `download_instructions` plus a `next_steps` cross-link to `datasets download`/`datasets replay`
* curated index entries return `is_index=true` and `index_instructions`; there is no single dataset payload to download

### datasets download

Download a dataset's actual data file to disk (where the manifest exposes a direct URL). Reuses the same manifest resolution as `datasets replay`, but writes the native file verbatim rather than streaming decoded frames.

```bash
canarchy datasets download <provider>:<dataset> --out <path> [--file <name>] [--platform <p>] [--json|--jsonl|--text]
canarchy datasets download <https-url> --out <path> [--json|--jsonl|--text]
```

Notes:

* `--file` selects a specific file from a multi-file dataset manifest (id or name); `--platform` filters dynamic manifests
* reports `out_path`, `bytes_written`, `source_format`, and a `next_steps` hint for `stats`/`datasets convert`
* a download/network failure returns a structured `DATASET_DOWNLOAD_FAILED` error; a non-replayable index returns `DATASET_INDEX_NOT_REPLAYABLE`
* CLI-only operator action (writes bulk bytes to an arbitrary host path); not exposed as an MCP tool

### datasets cache list

List cached dataset provider manifests and provenance records.

```bash
canarchy datasets cache list [--json|--jsonl|--text]
```

### datasets cache refresh

Refresh the built-in dataset catalog manifest.

```bash
canarchy datasets cache refresh [--provider <name>] [--json|--jsonl|--text]
```

### datasets convert

Convert a downloaded dataset file to a CANarchy-compatible capture format.

```bash
canarchy datasets convert <file> --source-format hcrl-csv|candump|comma-rlog --format candump|jsonl [--output <path>] [--json|--jsonl|--text]
```

### datasets stream

Stream a downloaded dataset file to candump or JSONL without loading the full conversion into memory.

```bash
canarchy datasets stream <file> --source-format hcrl-csv|candump|comma-rlog --format candump|jsonl [--chunk-size <n>] [--max-frames <n>] [--provider-ref <ref>] [--output <path>] [--json]
```

Examples:

```bash
canarchy datasets stream sample.csv --source-format hcrl-csv --format jsonl --provider-ref catalog:hcrl-car-hacking
canarchy datasets stream sample.log --source-format candump --format jsonl --provider-ref catalog:candid
canarchy datasets stream rlog.zst --source-format comma-rlog --format jsonl --provider-ref catalog:comma-car-segments --max-frames 1000
canarchy datasets stream sample.csv --source-format hcrl-csv --format candump --output sample.candump
canarchy datasets stream sample.csv --source-format hcrl-csv --format jsonl --max-frames 1000
canarchy datasets stream sample.csv --source-format hcrl-csv --format jsonl --json
```

Notes:

* `datasets search` defaults to a compact human-readable table with a `TYPE` column (`INDEX` for curated indexes, `PLAY` for replayable datasets); use `--verbose` for detailed result blocks with type labels, descriptions, source URLs, replay defaults, index notes, and access notes
* without `--json`, stream records are written directly to stdout or `--output`
* `comma-rlog` parses openpilot/comma `rlog.zst` CAN events when optional openpilot LogReader support is installed (`uv pip install git+https://github.com/commaai/openpilot.git` on Python 3.12.x); missing support returns `COMMA_RLOG_SUPPORT_UNAVAILABLE`
* JSONL stream records include `payload.dataset.provider_ref`, `frame_offset`, `chunk_index`, and `chunk_position`
* `--chunk-size` controls JSONL provenance chunk metadata and does not bound emitted frames
* `--max-frames` stops local dataset streaming after at most N emitted frames for candump and JSONL output
* with `--json`, stdout contains the standard result envelope and reports `frame_count`, `chunks`, and `max_frames`
* live-bus replay from dataset streams is not part of this command; use explicit replay workflows after writing a capture file

### datasets replay

Stream a remote candump dataset file directly to stdout with replay timing. The source may be a direct candump download URL or a replayable dataset ref such as `catalog:candid`.

```bash
canarchy datasets replay <dataset-ref-or-url> [--file <id-or-name>] [--platform <name>] [--limit <n>] [--list-files] [--format candump|jsonl] [--rate <multiplier>] [--max-frames <n>] [--max-seconds <seconds>] [--dry-run] [--json]
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
canarchy datasets replay catalog:comma-car-segments --platform TESLA_MODEL_3 --list-files --limit 20 --json
canarchy datasets replay catalog:comma-car-segments --platform TESLA_MODEL_3 --file 0 --format jsonl --max-frames 1000
```

Notes:

* without `--json`, replayed frames are written directly to stdout as candump or JSONL records for piping
* JSONL replay frame events include `payload.dataset.provider_ref`, `source_url`, `replay_file`, `default_replay_file`, `frame_offset`, `source_format`, and `source_type`
* with `--json`, stdout contains a clean standard result envelope with replay metadata and no frame records
* `--list-files --json` returns replay file entries with stable `id`, `name`, `size_bytes`, `format`, and `source_url` fields
* `--file` accepts a replay file `id` or `name`; unknown files fail with `DATASET_REPLAY_FILE_NOT_FOUND`
* `catalog:comma-car-segments` builds a dynamic replay manifest from HuggingFace `database.json`; use `--platform` to filter platforms such as `TESLA_MODEL_3`, and `--limit` to bound listed entries
* commaCarSegments replay resolves HuggingFace LFS URLs only for active streaming; `--dry-run` and `--list-files` do not open rlog payload streams
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
canarchy session save <name> [--interface <name>] [--dbc <file>] [--capture <file>] [--json|--jsonl|--text]
```

### session load

Load a previously saved session and mark it active.

```bash
canarchy session load <name> [--json|--jsonl|--text]
```

### session show

Show saved sessions and the active session.

```bash
canarchy session show [--json|--jsonl|--text]
```

### shell

Run a single shell command through the shared parser, or start a minimal interactive shell loop.

```bash
canarchy shell [--command "capture can0 --text"] [--json|--jsonl|--text]
```

### j1939 monitor

Inspect J1939 traffic and emit PGN-oriented structured events.

```bash
canarchy j1939 monitor [<interface>] [--pgn <id>] [--json|--jsonl|--text]
```

Example:

```bash
canarchy j1939 monitor --pgn 65262 --json
canarchy j1939 monitor can0 --pgn 65262 --json
```

Notes:

* without an interface, this command uses an explicit sample/reference provider
* with an interface, this command captures from the selected transport backend and filters to J1939 extended-ID traffic
* `j1939 decode`, `j1939 tp sessions`, `j1939 dm1`, `j1939 summary`, `j1939 inventory`, `j1939 compare`, and `j1939 map` remain file-backed; `j1939 pgn` and `j1939 spn` accept an optional `--file` and otherwise perform a built-in reference lookup

### j1939 decode

Decode a capture source into J1939 PGN observations.

```bash
canarchy j1939 decode --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text]
canarchy j1939 decode --stdin [--dbc <path|provider-ref>] [--json|--jsonl|--text]
```

Notes:

* `--stdin` reads JSONL `frame` events from standard input instead of a `--file` capture source
* `--dbc` enriches J1939 results with DBC-backed decoded signal events when available

### j1939 pgn

Inspect a specific PGN. With `--file`, reports matching events from the capture; without `--file`, returns the built-in reference definition (name, label, description, and the catalogued SPNs the PGN carries).

```bash
canarchy j1939 pgn <pgn> [--file <file>] [--dbc <path|provider-ref>] [--json|--jsonl|--text]
```

Example:

```bash
canarchy j1939 pgn 61444 --json
canarchy j1939 pgn 65262 --file tests/fixtures/sample.candump --json
```

### j1939 spn

Inspect a specific SPN. With `--file`, runs the curated/DBC SPN decoder over recorded J1939 traffic; without `--file`, returns the built-in reference definition (name, owning PGN, units, resolution, offset, bit layout). An OEM SPN absent from the bundled catalog is resolved from a supplied/configured DBC.

```bash
canarchy j1939 spn <spn> [--file <file>] [--dbc <path|provider-ref>] [--json|--jsonl|--text]
```

Example:

```bash
canarchy j1939 spn 190 --json
canarchy j1939 spn 110 --file tests/fixtures/sample.candump --json
```

Notes:

* curated metadata is built in for common SPNs
* `--dbc` can expand coverage for SPNs exposed through DBC signal metadata
* unsupported SPNs return a structured `J1939_SPN_UNSUPPORTED` error

### j1939 tp sessions

Summarize J1939 transport-protocol sessions from a capture file. `sessions` is the default `tp` action, so `j1939 tp --file <file>` is equivalent to `j1939 tp sessions --file <file>`.

```bash
canarchy j1939 tp [sessions] <file> [--json|--jsonl|--text]
canarchy j1939 tp [sessions] --file <file> [--json|--jsonl|--text]
```

Notes:

* the implementation handles BAM and RTS/CTS transport sessions with packet reassembly
* `j1939 tp --file <file>` defaults to the `sessions` action; a bare positional path (`j1939 tp <file>`) must still be disambiguated via the explicit `sessions`/`compare` action or `--file`, since the next token is interpreted as the sub-action

### j1939 dm1

Inspect DM1 fault traffic from direct J1939 frames and TP-reassembled payloads.

```bash
canarchy j1939 dm1 --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text]
```

### j1939 faults

Summarize active DM1 faults by ECU/source address, including lamp state and suspicious DTC markers.

```bash
canarchy j1939 faults --file <file> [--dbc <path|provider-ref>] [--json|--jsonl|--text]
```

### j1939 inventory

Build a source-address inventory from a J1939 capture file, including top PGNs, component-identification strings, vehicle-identification strings, and DM1 presence.

```bash
canarchy j1939 inventory --file <file> [--json|--jsonl|--text]
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
canarchy j1939 compare (<file> <file> [<file> ...] | --file <file> --file <file> ...) [--json|--jsonl|--text]
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

### j1939 map

Build a passive network-topology map from a J1939 capture file: nodes (one per source address, carrying the SA name, decoded Address Claimed NAME fields when present, and component/vehicle identification strings) and edges (observed PGN flows from a source address to a destination, or to the broadcast/global address). The map is derived purely from captured frames — there is no active probing or address-claim solicitation.

```bash
canarchy j1939 map --file <file> [--json|--jsonl|--text]
```

Example:

```bash
canarchy j1939 map --file tests/fixtures/j1939_map.candump --json
```

Notes:

* nodes reuse the `j1939 inventory` machinery, so identification strings and source-address names match between the two commands
* the 64-bit NAME from an Address Claimed message (PGN 60928) is decoded into its constituent fields (manufacturer code, function, identity number, industry group, arbitrary-address-capable flag, and the instance fields) when address-claim traffic is present in the capture
* edges aggregate repeated frames into a single per-(source, destination, PGN) flow with a frame count; PDU1 traffic addressed to the global address (0xFF) is reported as a broadcast, the same as PDU2 traffic
* the structured `nodes`/`edges` output is suitable for graphing and diffing

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
canarchy uds scan <interface | doip://host:port?logical_address=0x0E80> [--ack-active] [--json|--jsonl|--text]
```

Notes:

* with the `python-can` backend, this command sends a single-frame functional DiagnosticSessionControl request and summarizes captured UDS responses after ISO-TP reassembly when needed
* with the `scaffold` backend, this command emits explicit sample/reference UDS transaction data
* a `doip://<host>:<port>?logical_address=0x0E80` target routes the scan over DoIP (Diagnostic over IP, ISO 13400-2): the command opens a TCP connection, performs routing activation, and probes the default / programming / extended diagnostic sessions, emitting the same `uds_transaction` events with `transport: doip` in the envelope. Optional query parameters: `source_address` (tester address, default `0x0E00`), `activation_type` (default `0x00`), `timeout` (seconds, default `2.0`); port defaults to `13400`
* DoIP targets are an active network egress and are gated by the active-transmit safety model; structured errors include `DOIP_INVALID_TARGET` (exit 1), `DOIP_CONNECTION_FAILED` / `DOIP_TIMEOUT` / `DOIP_ROUTING_ACTIVATION_DENIED` / `DOIP_DIAGNOSTIC_NACK` / `DOIP_PROTOCOL_ERROR` (exit 2)
* `--ack-active` requests an interactive `YES` confirmation before the diagnostic request is sent
* if a segmented response is truncated or arrives out of order, the emitted `uds_transaction` event keeps the partial `response_data` and sets `complete` to `false`

### uds trace

Inspect representative UDS request and response transactions.

```bash
canarchy uds trace <interface | doip://host:port?logical_address=0x0E80> [--ack-active] [--json|--jsonl|--text]
```

Notes:

* with the `python-can` backend, this command captures raw CAN frames and infers UDS request/response transactions from common diagnostic IDs, including ISO-TP multi-frame responses
* with the `scaffold` backend, this command emits explicit sample/reference UDS transaction data
* a `doip://` target routes the trace over DoIP: the command performs routing activation and a DiagnosticSessionControl + TesterPresent exchange, emitting the transactions with `transport: doip`. Because DoIP is connection-oriented, this is an active exchange (not a passive sniff) and is gated by the active-transmit safety model; the same DoIP query parameters and error codes as `uds scan` apply
* flow-control frames are used only for reassembly and are not emitted as transactions
* if a segmented response is truncated or arrives out of order, the emitted `uds_transaction` event keeps the partial `response_data` and sets `complete` to `false`

### uds services

Inspect the built-in UDS service catalog.

```bash
canarchy uds services [--json|--jsonl|--text]
```

Notes:

* this is a reference command and does not require an interface
* output includes service identifier, positive-response identifier, category, and subfunction expectations

### xcp scan

Discover XCP responders by transmitting an XCP CONNECT command.

```bash
canarchy xcp scan <interface> [--request-id 0x3E0] [--response-id 0x3E1] [--ack-active] [--dry-run] [--json|--jsonl|--text]
```

Notes:

* XCP-on-CAN: sends a single CONNECT (`FF 00`) on `--request-id` and reports each command-response object on `--response-id` as an `xcp_transaction` event; a CONNECT positive response is parsed into resources, max-CTO, max-DTO, and protocol/transport versions
* with the `scaffold` backend, this command emits sample/reference XCP transaction data
* this is an active command honouring the active-transmit safety model; `--ack-active` requests an interactive `YES` confirmation before the CONNECT is sent; `--dry-run` plans the CONNECT frame (reported as `planned_frame`, `mode: dry_run`) without opening the transport or transmitting
* `--request-id` / `--response-id` accept decimal or `0x` hex CAN ids (defaults 0x3E0 / 0x3E1; an extended 29-bit request id is transmitted as an extended frame); a malformed id returns `XCP_INVALID_ID`
* the `xcp_scan` MCP tool is gated like other active-transmit tools: mandatory `ack_active=true` with `dry_run` defaulting to true

### xcp trace

Pair XCP command and response transactions from bus traffic.

```bash
canarchy xcp trace <interface> [--request-id 0x3E0] [--response-id 0x3E1] [--json|--jsonl|--text]
```

Notes:

* passive: pairs each command CTO on `--request-id` with the following response CTO on `--response-id`, naming the command and surfacing positive/error status (error codes resolve to ASAM names)
* with the `scaffold` backend, this command emits sample/reference XCP transaction data

### xcp read

Surface raw DAQ measurement (DTO) payloads from a short capture.

```bash
canarchy xcp read <interface> [--response-id 0x3E1] [--json|--jsonl|--text]
```

Notes:

* passive: emits an `xcp_measurement` event (packet identifier plus raw bytes) for each DAQ DTO on `--response-id`; command-response objects (PID ≥ 0xFC) are skipped
* signal-level decoding of DAQ payloads requires the slave's A2L description and is out of scope; raw ODT bytes are reported

### xcp commands

Inspect the built-in XCP command catalog.

```bash
canarchy xcp commands [--json|--jsonl|--text]
```

Notes:

* this is a reference command and does not require an interface
* output includes the command code, name, and category (standard / calibration / daq / programming)

### j1587 decode

Decode a J1708 capture file into J1587 PID parameters.

```bash
canarchy j1587 decode --file <path> [--offset N] [--max-frames N] [--seconds N] [--json|--jsonl|--text]
```

```bash
canarchy j1587 decode --file tests/fixtures/j1708_sample.j1708 --json
```

Notes:

* each line of the capture file must read `(timestamp) j1708 <hex>`, where `<hex>` is the full raw message (source MID, PID-framed parameters, and a trailing checksum byte)
* emits one `j1587_parameter` event per parameter, with `mid`, `pid`, `raw`, `name`, `value`, `units`, `checksum_valid`, and `timestamp`; PIDs are resolved against the bundled `resources/j1587/pids.json` catalog (override via `CANARCHY_J1587_PID_OVERRIDES` or `~/.canarchy/j1587_pids.json`)
* an all-ones raw value (the J1587 "data not available" sentinel) resolves `value` to `null` while keeping `name`/`units`
* `data` reports `mode: "passive"`, `file`, `message_count`, `parameter_count`, and `checksum_failures`
* `--offset` / `--max-frames` / `--seconds` apply to the message stream the same way they do for `j1939 decode`
* a missing `--file` returns `J1587_SOURCE_UNAVAILABLE`; a line that does not match the expected format, has an odd number of hex digits, or fails J1708 framing returns `J1587_SOURCE_INVALID` (exit code 1)

### j1587 pids

Inspect the built-in J1587 PID catalog.

```bash
canarchy j1587 pids [--json|--jsonl|--text]
```

Notes:

* this is a reference command and does not require a capture file
* output includes each PID's name, data length, resolution, offset, units, and byte order

### j2497 decode

Decode a J2497 (PLC4TRUCKS trailer power-line) capture file into frames.

```bash
canarchy j2497 decode --file <path> [--offset N] [--max-frames N] [--seconds N] [--json|--jsonl|--text]
```

```bash
canarchy j2497 decode --file tests/fixtures/j2497_sample.j2497 --json
```

Notes:

* each line of the capture file must read `(timestamp) j2497 <hex>`, where `<hex>` is the full raw frame (source MID, message data, and a trailing checksum byte)
* emits one `j2497_message` event per frame, with `mid`, `name`, `data`, `checksum_valid`, and `timestamp`; MIDs are resolved against the bundled `resources/j2497/mids.json` catalog (override via `CANARCHY_J2497_MID_OVERRIDES` or `~/.canarchy/j2497_mids.json`)
* J2497 reuses the J1708/J1587 frame format; the `data` bytes follow the J1587 PID framing rules, so feed the same byte format to `j1587 decode` for PID-level resolution
* `data` reports `mode: "passive"`, `file`, `frame_count`, and `checksum_failures`
* `--offset` / `--max-frames` / `--seconds` apply to the frame stream the same way they do for `j1939 decode`
* live J2497 / power-line access requires a power-line carrier modem and external hardware and is not provided; this command is decode-only over captured frames
* a missing `--file` returns `J2497_SOURCE_UNAVAILABLE`; a line that does not match the expected format, has an odd number of hex digits, or is too short to be a frame returns `J2497_SOURCE_INVALID` (exit code 1)

### j2497 mids

Inspect the built-in J2497/J1587 MID catalog.

```bash
canarchy j2497 mids [--json|--jsonl|--text]
```

Notes:

* this is a reference command and does not require a capture file
* output includes each MID's ECU name (trailer ABS controllers and related units)

### re counters

Rank likely counter fields from recorded CAN traffic.

```bash
canarchy re counters (<file> | --file <file>) [--top <n>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed
* the current implementation inspects nibble- and byte-sized candidate fields on recorded arbitration IDs
* candidates are ranked by monotonicity evidence and explicit rollover detection
* J1939 transport-protocol IDs (TP.CM / TP.DT / ETP.CM / ETP.DT) are excluded — their sequence numbers are protocol plumbing, not application counters — and reported in metadata as `excluded_transport_ids`
* J1939 candidates carry `pgn`, `pgn_label`, `source_address`, and `source_address_name`; every candidate carries `arbitration_id_hex`
* `--top` caps the returned `candidates` array (default 20; `0` for all); `candidate_count` reports the full total and `returned_count` the number returned

### re signals

Rank likely signal fields from recorded CAN traffic.

```bash
canarchy re signals (<file> | --file <file>) [--top <n>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed
* the current implementation inspects nibble-aligned 4-bit fields, byte-aligned 8-bit fields, and word-aligned 16-bit fields
* candidates are ranked by change-rate preference, observed range, and value diversity
* J1939 transport-protocol IDs (TP.CM / TP.DT / ETP.CM / ETP.DT) are excluded from signal inference and reported under `excluded_transport_ids`
* J1939 candidates carry `pgn`, `pgn_label`, `source_address`, and `source_address_name`; every candidate carries `arbitration_id_hex`
* arbitration IDs with fewer than 5 frames are omitted from the candidate list and reported in `low_sample_ids`
* `--top` caps the returned `candidates` array (default 20; `0` for all); `candidate_count` reports the full total and `returned_count` the number returned

### re correlate

Correlate candidate bit fields against a timestamped reference series.

```bash
canarchy re correlate (<file> | --file <file>) --reference <ref.json|ref.jsonl> [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed
* reference files may be JSON arrays, named JSON objects with `name` and `samples`, or JSONL sample streams
* each reference sample must include numeric `timestamp` and `value` fields
* candidates report `pearson_r`, `spearman_r`, `sample_count`, and `lag_ms`, and are ranked by absolute Pearson correlation

### re anomalies

Flag inter-frame-timing outliers and unexpected/dropped arbitration IDs.

```bash
canarchy re anomalies (<file> | --file <file>) [--baseline <ref>] [--dbc <ref>] [--z-threshold <z>] \
    [--cv-max <cv>] [--min-samples <n>] [--entropy-drop <r>] [--rate-drop <r>] [--top <n>] \
    [--offset <n>] [--max-frames <n>] [--seconds <s>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed; it honors the standard `--offset`, `--max-frames`, and `--seconds` window flags
* with `--baseline`, per-ID timing statistics and the expected ID set are learned from the reference capture and the input is scored against them; without it, each ID is scored against its own statistics (self-consistency), ID-presence anomalies are not emitted, and a warning nudges the operator toward supplying a baseline
* anomalies carry `arbitration_id`, `kind` (`timing` / `unknown-id` / `dropped-id` / `rate-drop` / `rate-spike` / `entropy-collapse`), `score`, `z_score`, `z_score_capped`, `sample_count`, `timestamp`, and a `rationale`, ranked by score; J1939 candidates additionally carry `pgn`, `pgn_label`, `source_address`, and `source_address_name`
* against a `--baseline`, IDs present in both captures are additionally checked for two attack classes that pure timing analysis misses: a `rate-drop` / `rate-spike` when an ID's time-normalised frame rate falls to `--rate-drop` of (default 0.5; suppression) or rises to its reciprocal above (injection) the baseline rate, and an `entropy-collapse` when an ID's mean per-byte payload entropy falls to `--entropy-drop` of (default 0.5) a baseline that itself carried meaningful entropy (plateau / frozen-value attacks)
* **only IDs judged cyclic are timing-checked, so event-based and event-periodic messages are not falsely flagged.** Classification is authoritative from the database when `--dbc` is supplied (a message's `cycle_time` / send type decides cyclic vs event); otherwise a robust coefficient of variation (scaled median-absolute-deviation over the median inter-frame gap) is compared against `--cv-max` (default 0.5)
* timing statistics use the median and MAD rather than mean and standard deviation, so a minority of outlier gaps cannot inflate the spread and mask themselves
* a cyclic-looking ID needs at least `--min-samples` inter-frame gaps before its timing is scored (default 10 without a baseline, 3 with one); sparser IDs are listed under `low_rate_ids` with classification source `low-sample` instead of being ranked, and reported z-scores are capped at ±100σ
* `--top` caps the ranked `candidates` array (default 20; `0` for all) for agent-friendly output; `candidate_count` always reports the full total and `returned_count` the number returned
* the payload also reports `mode`, `timing_source` (`dbc` / `observed`), `min_samples`, `entropy_drop`, `rate_drop`, `cyclic_ids`, `event_ids` (timing skipped), `low_rate_ids`, and a per-ID `classifications` list

### re corpus

Cross-capture corpus analysis: per-ID coverage matrix, cycle-time drift, and signal stability across multiple captures.

```bash
canarchy re corpus (<file> ... | --file <file> ...) [--corpus-glob <pattern>] \
    [--offset <n>] [--max-frames <n>] [--seconds <s>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed; accepts two or more captures positionally, via repeatable `--file`, or expanded from `--corpus-glob`
* reports per-ID `coverage` (frame counts per capture, presence), `cycle_time_drift` (cross-capture mean-gap stddev and drift ratio), and `signal_stability` (per-byte coefficient of variation), plus a `summary` of unique/stable/drifting/new IDs
* J1939 ids are annotated with `pgn`, `pgn_label`, and `source_address_name`; every row carries `arbitration_id_hex`
* `--offset`, `--max-frames`, and `--seconds` bound each capture independently

### re entropy

Rank arbitration IDs and byte positions by Shannon entropy over recorded CAN traffic.

```bash
canarchy re entropy (<file> | --file <file>) [--top <n>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed
* JSON output includes one candidate per arbitration ID plus a per-byte entropy breakdown inside each candidate
* IDs with fewer than 10 observed frames are retained and marked with `low_sample: true`
* J1939 transport-protocol IDs are retained but labeled with `j1939_transport: true` and a rationale note, so TP framing is not mistaken for an application signal
* J1939 candidates carry `pgn`, `pgn_label`, `source_address`, and `source_address_name`; every candidate carries `arbitration_id_hex`
* `--top` caps the returned `candidates` array (default 20; `0` for all); `candidate_count` reports the full total and `returned_count` the number returned

### re match-dbc

Rank candidate DBC files against a capture using provider-backed catalog metadata.

```bash
canarchy re match-dbc (<capture> | --file <capture>) [--provider <name>] [--limit <n>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed
* candidates are scored by frequency-weighted arbitration-ID coverage against the capture
* the default provider is `opendbc`

### re shortlist-dbc

Rank candidate DBC files against a capture after pre-filtering by vehicle make.

```bash
canarchy re shortlist-dbc (<capture> | --file <capture>) --make <brand> [--provider <name>] [--limit <n>] [--json|--jsonl|--text]
```

Notes:

* this command is passive and file-backed
* `--make` narrows provider-catalog candidates before scoring them against the capture
* the default provider is `opendbc`

### re suggest

Propose names for ranked signal candidates.

```bash
canarchy re suggest (<file> | --file <file>) [--reference-dbc <ref>] [--limit <n>] \
    [--llm <provider> [--llm-model <model>] [--yes]] [--json|--jsonl|--text]
```

Notes:

* passive and file-backed: reuses `re signals` to rank candidates, then attaches `suggestions` (each with a `source` of `dbc` / `spn` / `pgn` / `heuristic` / `llm` and a `confidence`), reporting the top as `suggested_name` / `suggested_source`
* heuristics combine reference-DBC overlap (`--reference-dbc`, a path or provider ref), bit-range overlap with the bundled J1939 SPN catalog, the PGN name as a coarse fallback, and a plain-English template from the candidate's change behaviour — all fully offline
* `--llm <provider>` (off by default; only `anthropic` is supported) enriches names via an external LLM. It requires explicit confirmation (`--yes`, or a `YES` reply, or `CANARCHY_LLM_NONINTERACTIVE=1`), sends only candidate metadata — never payload bytes — and records `external_enrichment` plus an `EXTERNAL_SERVICE_CALLED` warning. Declining returns `LLM_CONFIRMATION_DECLINED`; an unknown provider returns `LLM_PROVIDER_UNSUPPORTED`; a missing key returns `LLM_PROVIDER_UNAVAILABLE`
* the `re_suggest` MCP tool exposes the heuristic path only; the `--llm` enrichment is CLI-only

### config show

Inspect the effective transport configuration and the source of each setting.

```bash
canarchy config show [--json|--jsonl|--text]
```

The payload includes both `interface` (the python-can backend type) and `default_interface` (the optional CAN channel fallback for commands that omit their interface argument).

### doctor

Run local environment health checks and return the canonical envelope.
Each check has a `name`, `status` (`ok`, `warn`, or `fail`), `detail`, and
an optional `hint` for non-ok results.

```bash
canarchy doctor [--json|--jsonl|--text]
```

Covered checks:

* `python_version` — Python is at least 3.12.
* `python_can` — `python-can` is importable in the active environment.
* `transport_backend` — the effective transport backend resolves to a known backend.
* `python_can_interface_dependency` — when the effective python-can interface is a known vendor backend such as `pcan`, `vector`, or `kvaser`, the corresponding python-can interface module is importable. This is an offline import check only; it does not open hardware.
* `config_file` — `~/.canarchy/config.toml` parses cleanly when present.
* `cache_dirs` — DBC, dataset, and skills caches are writable.
* `opendbc_cache` — opendbc DBC cache is populated; warns if it needs `dbc cache refresh`.
* `mcp_server` — the MCP stdio server is constructable.
* `version_consistency` — the installed package version matches `src/canarchy/__init__.py`.

The command also runs against the MCP server as the `doctor` tool. No
network or live bus access is required.

### completion

Emit a shell completion script for the given shell. The script is
written to stdout — not wrapped in the canonical envelope, because the
output is meant to be sourced.

```bash
canarchy completion {bash,zsh,fish}
```

Install snippets:

* bash — `eval "$(canarchy completion bash)"` in `~/.bashrc`, or copy the
  output into `~/.bash_completion.d/canarchy`.
* zsh — `eval "$(canarchy completion zsh)"` in `~/.zshrc`, or save the
  output to a directory on `$fpath` such as `~/.zsh/completions/_canarchy`
  and run `compinit`.
* fish — `canarchy completion fish | source` from
  `~/.config/fish/config.fish`, or save to
  `~/.config/fish/completions/canarchy.fish`.

Supplying an unsupported shell name returns the standard
`INVALID_ARGUMENTS` structured error.

### Global flags

The following flags are accepted before any subcommand (place them
between `canarchy` and the subcommand name):

* `--log-level {debug,info,warn,error}` — stderr log verbosity; defaults
  to `warn`. Log records never contaminate machine-readable stdout
  (`--json`, `--jsonl`, `--text`).
* `--quiet` — suppress every level below `ERROR`. Useful in pipelines
  where only structured errors should reach stderr.

### fuzz

Active-transmit fuzzing, gated by the controls in
[`docs/design/active-transmit-safety.md`](design/active-transmit-safety.md).
Three subcommands, all built on the pure-function mutation engine in
`src/canarchy/fuzzing.py`. Every emitted event carries a stable
`run_id` (UUID) so post-mortem analysis can match output to the
invocation that produced it.

`--dry-run` is the safe planning path: events are emitted as JSONL
with `payload.frame.dry_run = true`, no transport is opened, and the
`--ack-active` confirmation prompt is skipped. Without `--dry-run`,
the existing active-transmit safety gate (`--ack-active` plus optional
config-driven prompt) applies before any frame is transmitted via
`LocalTransport.send`.

```bash
canarchy fuzz payload <interface> --id <hex> --strategy {bitflip,random,boundary}
                                  [--data <hex>] [--dlc <n>] [--max <n>]
                                  [--rate <hz>] [--seed <int>] [--extended]
                                  [--repair-crc] [--crc-algorithm <name>] [--crc-address <id>]
                                  [--dry-run] [--run-id <uuid>] [--ack-active]
canarchy fuzz replay --file <capture> --strategy {timing,payload-bitflip}
                      [--interface <iface>] [--max <n>] [--rate <hz>] [--seed <int>]
                      [--repair-crc] [--crc-algorithm <name>] [--crc-address <id>]
                      [--dry-run] [--run-id <uuid>] [--ack-active]
canarchy fuzz arbitration-id <interface> --range <start>:<end> [--step <n>]
                               [--data <hex>] [--rate <hz>] [--extended]
                               [--repair-crc] [--crc-algorithm <name>] [--crc-address <id>]
                               [--dry-run] [--run-id <uuid>] [--ack-active]
```

`--repair-crc` recomputes the final payload byte after mutation. `--crc-algorithm`
accepts `stellantis`, `sae-j1850`, or `fca-giorgio`; if omitted, fuzz repair uses
`stellantis`. `--crc-address` supplies the arbitration ID used by algorithms that
include the message address; when omitted, each generated frame's arbitration ID is used.

Strategies and the engine they map to are documented in the
[active-transmit safety design](design/active-transmit-safety.md). The
following follow-up controls from that spec are tracked separately and
will land in subsequent PRs: configurable rate-cap ceiling
(`[safety.rate_cap]` in `~/.canarchy/config.toml`), TOML target
allowlist (`--targets`), explicit `KILL_SWITCH_TRIGGERED` alert on
SIGINT, MCP `ack_active=true` enforcement (#312).

### fuzz guided

Response-feedback coverage-guided fuzzing against an ECU target.

```bash
canarchy fuzz guided <interface> --id <arb-id> [--signals nrc,pos,dm1,timing,silence]
                     [--corpus <dir>] [--seed-data <hex>] [--max-iterations <n>]
                     [--max-seconds <s>] [--max-corpus <n>] [--rate <hz>] [--seed <int>]
                     [--extended] [--ack-active] [--dry-run] [--json|--jsonl|--text]
```

Notes:

* active-transmit: each iteration sends a mutated payload (via the `canarchy.fuzzing` havoc/splice mutators) on `--id` and observes the target's response. Novelty is scored from observed responses — UDS NRCs, UDS positive responses, DM1 fault emergence, response-timing buckets, and silence — selectable via `--signals` (default all)
* inputs that elicit new behaviour become corpus seeds whose lineage is prioritised for further mutation; `--corpus <dir>` persists the corpus (raw seed files plus a `lineage.json` manifest) and reloads it to resume campaigns; `--max-corpus` caps retained seeds (lowest-scoring pruned first)
* the campaign is bounded by `--max-iterations` and/or `--max-seconds`; the envelope reports `iterations`, `new_behaviour_count`, `corpus_size`, `unique_markers`, `stop_reason`, and a `findings` list
* honours the active-transmit safety model (`--ack-active`, `--rate` pacing); `--dry-run` plans the campaign (planned mutations, `mode: dry_run`) without opening the transport. Structured errors: `FUZZ_GUIDED_INVALID_SIGNALS`, `FUZZ_GUIDED_INVALID_ID` (exit 1), `FUZZ_GUIDED_TRANSPORT_FAILED` (exit 2)
* the `fuzz_guided` MCP tool is gated like other active tools (mandatory `ack_active=true`, `dry_run` defaulting to true)

### mcp serve

Start the MCP server over stdio.

```bash
canarchy mcp serve
```

Notes:

* this command does not accept output flags
* the current MCP tool surface is a curated non-interactive subset of the CLI, not every implemented command

---

### mcp install

Write the canarchy MCP server block into a client configuration file.

```bash
canarchy mcp install --client {claude-desktop,claude-code} [--config-path PATH] \
    [--command COMMAND] [--dry-run] [--ack] [--json|--jsonl|--text]
```

Flags:

* `--client {claude-desktop,claude-code}` — required; selects the target client. `claude-desktop` resolves the per-platform config path (macOS / Windows / Linux); `claude-code` writes a project-scoped `.mcp.json` in the current directory.
* `--config-path PATH` — override the auto-detected config path.
* `--command COMMAND` — the command the client runs for the server (default `canarchy`; use an absolute venv path when `canarchy` is not on `PATH`).
* `--dry-run` — print the would-write config without touching disk.
* `--ack` — skip the `YES` confirmation prompt and write immediately.

Behavior:

* merges the `mcpServers.canarchy` entry without disturbing other servers
* treats an identical existing entry as a no-op (`action: unchanged`)
* refuses to overwrite a *different* existing `canarchy` entry
* `action` in the envelope data is one of `create`, `update`, `unchanged`, or `planned` (dry-run)
* this command is CLI-only and is not exposed as an MCP tool (writing a client config is a user action)

Structured error codes: `MCP_INSTALL_CONFLICT`, `MCP_INSTALL_INVALID_CONFIG`, `MCP_INSTALL_DIR_MISSING`, `MCP_INSTALL_READ_FAILED`, `MCP_INSTALL_WRITE_FAILED`, `MCP_INSTALL_DECLINED`.

---

## Output Modes

All commands support:

* `--json`
* `--jsonl`
* `--text`

`--text` is the default when no output mode is specified. `--table` remains accepted as a compatibility alias for `--text`, but new examples and automation should use `--text`.

Current behavior:

* `--json` emits one structured JSON object
* `--jsonl` emits one JSON object per line
* event-producing commands emit each event as its own JSON line; command warnings that are not already events are emitted as `alert` event lines
* event-less successful commands emit a single result object line
* failed commands emit a single error result object line
* `--text` emits a human-readable summary view, with protocol-aware pretty-printing for J1939 monitor and decode workflows

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
* `j1587_parameter`
* `j2497_message`
* `uds_transaction`
* `xcp_transaction`
* `xcp_measurement`
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
canarchy shell --command "capture can0 --text"
```

---

## Current Gaps

Planned capabilities that are intentionally not exposed in the CLI yet:

* active fuzzing workflows for replay mutation, payload mutation, and arbitration-ID probing

These deeper capabilities are also not implemented yet even where the command surface exists:

* deeper live transport integration beyond the current `python-can` transport path
