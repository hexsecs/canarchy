# Command Spec

## Status

This document describes the current implemented CLI contract.

Implemented and verified in the current codebase:

* scaffolded transport workflows for `capture` and `send`
* file-backed `filter` and `stats` over candump capture logs
* opt-in live `python-can` support for `capture` and `send`
* deterministic `replay`
* live `gateway` bridging between CAN interfaces via `python-can`
* structured `export` for capture files and saved sessions
* DBC-backed `decode` and `encode`
* J1939 `monitor`, `decode`, `pgn`, `spn`, `tp`, and `dm1`
* session `save`, `load`, and `show`
* shell one-shot command execution
* initial text-mode `tui` shell over the shared command layer
* UDS `scan`, `trace`, and `services`
* structured JSON and JSONL output
* explicit error schema and exit codes

Some other commands are already present in the CLI tree but still return placeholder results until their implementation issues are completed.

Important current behavior:

* live transport-facing commands default to the deterministic `LocalTransport` scaffold for `capture` and `send`
* `capture`, `send`, and `gateway` require the `python-can` backend for live transport; set `backend = "python-can"` in `~/.canarchy/config.toml` or export `CANARCHY_TRANSPORT_BACKEND=python-can`
* the default `python-can` interface is `virtual`; set `interface` in the config file or `CANARCHY_PYTHON_CAN_INTERFACE` to change it
* placeholder-only commands still return `status: planned` and `implementation: command surface scaffold`
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

Capture traffic from a local interface. Structured capture works with the default scaffold backend or the opt-in `python-can` live backend. `--candump` is a live-only mode.

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
canarchy send <interface> <frame-id> <hex-data> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy send can0 0x123 11223344 --json
```

### filter

Filter a capture source by a simple expression.

```bash
canarchy filter <file> <expression> [--json|--jsonl|--table|--raw]
```

Supported expressions today:

* `all`
* `id==0x18FEEE31`
* `pgn==65262`

### stats

Summarize a capture source.

```bash
canarchy stats <file> [--json|--jsonl|--table|--raw]
```

### replay

Replay a capture source with deterministic timing derived from relative frame timestamps.

```bash
canarchy replay <file> [--rate <factor>] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy replay tests/fixtures/sample.candump --rate 2.0 --json
```

### gateway

Bridge frames from one live CAN interface to another through the `python-can` backend.

```bash
canarchy gateway <src> <dst> [--src-backend <type>] [--dst-backend <type>] [--bidirectional] [--count <n>] [--json|--jsonl|--table|--raw]
```

Examples:

```bash
canarchy gateway can0 can1 --table
canarchy gateway can0 239.0.0.1 --dst-backend udp_multicast --count 10 --json
```

Notes:

* `gateway` requires the `python-can` backend (set in `~/.canarchy/config.toml` or via `CANARCHY_TRANSPORT_BACKEND=python-can`)
* `--src-backend` and `--dst-backend` default to the configured `interface` value
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
canarchy decode <file> --dbc <file> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy decode tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json
```

### encode

Encode a DBC message into a frame payload.

```bash
canarchy encode --dbc <file> <message> <signal=value>... [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
```

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

Monitor J1939 traffic and emit PGN-oriented structured events.

```bash
canarchy j1939 monitor [--pgn <id>] [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy j1939 monitor --pgn 65262 --json
```

### j1939 decode

Decode a capture source into J1939 PGN observations.

```bash
canarchy j1939 decode <file> [--json|--jsonl|--table|--raw]
```

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

### j1939 tp

Summarize J1939 transport-protocol sessions from a capture file.

```bash
canarchy j1939 tp <file> [--json|--jsonl|--table|--raw]
```

Notes:

* the first implementation focuses on BAM-style TP sessions and packet reassembly

### j1939 dm1

Inspect DM1 fault traffic from direct J1939 frames and TP-reassembled payloads.

```bash
canarchy j1939 dm1 <file> [--json|--jsonl|--table|--raw]
```

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

Scan for UDS responders through the transport scaffold.

```bash
canarchy uds scan <interface> [--json|--jsonl|--table|--raw]
```

### uds trace

Emit structured request and response transactions for a UDS session trace.

```bash
canarchy uds trace <interface> [--json|--jsonl|--table|--raw]
```

### uds services

Inspect the built-in UDS service catalog.

```bash
canarchy uds services [--json|--jsonl|--table|--raw]
```

Notes:

* this is a reference command and does not require an interface
* output includes service identifier, positive-response identifier, category, and subfunction expectations

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
* `DBC_ENCODE_FAILED` => exit code `3`

---

## Examples

### Transport Capture

```bash
canarchy capture can0 --json
```

### Transport Stats

```bash
canarchy stats tests/fixtures/sample.candump --json
```

### Deterministic Replay

```bash
canarchy replay tests/fixtures/sample.candump --rate 0.5 --json
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
canarchy decode tests/fixtures/sample.candump --dbc tests/fixtures/sample.dbc --json
```

### DBC Encode

```bash
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
```

### UDS Scan

```bash
canarchy uds scan can0 --json
```

### UDS Trace

```bash
canarchy uds trace can0 --json
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

These commands are present in the CLI tree but still scaffolded or not yet implemented end to end:

* `re signals|counters|entropy|correlate`
* `fuzz replay|mutate|id`

These deeper capabilities are also not implemented yet even where the command surface exists:

* live transport integration beyond the initial `python-can` `virtual` backend path
* pretty-print output tailored for UDS commands
