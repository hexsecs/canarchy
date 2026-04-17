# Command Spec

## Status

This document describes the current implemented CLI contract.

Implemented and verified in the current codebase:

* transport scaffolds for `capture`, `send`, `filter`, and `stats`
* deterministic `replay`
* DBC-backed `decode` and `encode`
* J1939 `monitor`, `decode`, and `pgn`
* structured JSON and JSONL output
* explicit error schema and exit codes

Some other commands are already present in the CLI tree but still return placeholder results until their implementation issues are completed.

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
* `canarchy replay capture.log --rate 2.0 --json`
* `canarchy j1939 monitor --pgn 65262 --json`
* `canarchy decode capture.log --dbc tests/fixtures/sample.dbc --json`

---

## Implemented Commands

### capture

Capture traffic from a local interface through the transport scaffold.

```bash
canarchy capture <interface> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy capture can0 --json
```

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
canarchy replay capture.log --rate 2.0 --json
```

### decode

Decode frames from a capture source using a DBC file.

```bash
canarchy decode <file> --dbc <file> [--json|--jsonl|--table|--raw]
```

Example:

```bash
canarchy decode capture.log --dbc tests/fixtures/sample.dbc --json
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

Inspect events for a specific PGN from the current scaffolded capture source.

```bash
canarchy j1939 pgn <id> [--json|--jsonl|--table|--raw]
```

---

## Output Modes

All commands support:

* `--json`
* `--jsonl`
* `--table`
* `--raw`

Current behavior:

* `--json` emits one structured JSON object
* `--jsonl` emits one structured JSON object per line
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

Successful JSON and JSONL output uses this shape:

```json
{
  "ok": true,
  "command": "capture",
  "data": {},
  "warnings": [],
  "errors": []
}
```

Error JSON and JSONL output uses this shape:

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
canarchy stats capture.log --json
```

### Deterministic Replay

```bash
canarchy replay capture.log --rate 0.5 --json
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
canarchy decode capture.log --dbc tests/fixtures/sample.dbc --json
```

### DBC Encode

```bash
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
```

---

## Current Gaps

These commands are present in the CLI tree but still scaffolded or not yet implemented end to end:

* `export`
* `session save|load|show`
* `j1939 spn|tp|dm1`
* `uds scan|trace|services`
* `re signals|counters|entropy|correlate`
* `fuzz replay|mutate|id`
* `shell`
* `tui`
