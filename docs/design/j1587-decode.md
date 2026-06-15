# Design Spec: J1587/J1708 Legacy Heavy-Vehicle Decoding

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j1587 decode`, `j1587 pids` |
| Primary area | Protocol, CLI |
| Related specs | `docs/design/j1939-first-class-decoder.md` |

## Goal

Bring J1587/J1708 coverage — the data-link and parameter layers underlying
legacy heavy-vehicle diagnostic buses — to the same structured-output surface
used for J1939. J1708 is an asynchronous serial bus (RS-485, 9600 baud)
carrying variable-length `MID <parameters...> checksum` messages; J1587
defines the Parameter IDs (PIDs) carried in those messages and how to scale
their raw bytes into engineering values. `canarchy j1587 decode` parses a
J1708 capture file into messages and parameters and resolves common PIDs
against a bundled catalog, mirroring the `canarchy.j1939` /
`canarchy.j1939_metadata` split.

## User-Facing Motivation

Some fleets still run J1708/J1587 alongside or instead of J1939. Analysts
working those buses previously had no CANarchy-native way to decode a
captured J1708 trace; this brings that traffic into the same canonical
JSON/JSONL event contract used elsewhere, including checksum validation and
PID-to-name/units/value resolution.

This is a clean-room implementation against the public SAE J1587 PID framing
rules and a small hand-built PID catalog; it does not reuse code or data from
bundled third-party tools (e.g. `pretty-j1939`), which carry their own
licenses.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1587-01` | Ubiquitous | The system shall provide a pure parser that decodes a raw J1708 message (`MID <parameters...> checksum`) into a source MID, a sequence of PID/data parameters, and a checksum-valid flag. |
| `REQ-J1587-02` | Ubiquitous | The parser shall determine each parameter's data length from its PID per SAE J1587: PIDs 0-127 take one data byte, 128-191 take two data bytes, 192-253 are followed by an explicit length byte and that many data bytes, and 254 is an extended-PID marker whose following byte is added to 256 to form a 16-bit PID, followed by a length byte and that many data bytes. |
| `REQ-J1587-03` | Unwanted behaviour | If a message is shorter than two bytes, or a parameter's extended PID, length byte, or data is truncated, the parser shall raise a `ValueError` describing the truncation. |
| `REQ-J1587-04` | Ubiquitous | The system shall provide a bundled J1587 PID catalog (`resources/j1587/pids.json`) mapping PIDs to name, data length, resolution, offset, units, and byte order, mirroring the `resources/j1939/` pattern, with override support via `CANARCHY_J1587_PID_OVERRIDES` (falling back to `~/.canarchy/j1587_pids.json`). |
| `REQ-J1587-05` | Event-driven | When a parameter's PID is in the bundled catalog, the system shall resolve `(name, value, units)` by interpreting the raw bytes with the catalog's byte order, scaling by `resolution`, and adding `offset`; an all-ones raw value (the J1587 "data not available" sentinel) shall resolve to `value: null` with `name`/`units` still populated. |
| `REQ-J1587-06` | Unwanted behaviour | If a parameter's PID has no catalog entry, the system shall resolve `(None, None, None)` for that parameter without error. |
| `REQ-J1587-07` | Event-driven | When `j1587 decode --file <path>` is invoked, the system shall parse each `(timestamp) j1708 <hex>` line of the capture file into a J1708 message and emit one `j1587_parameter` event per parameter, reporting `mid`, `pid`, `raw`, `name`, `value`, `units`, `checksum_valid`, and `timestamp`. |
| `REQ-J1587-08` | Optional feature | Where `--offset` / `--max-frames` / `--seconds` are supplied, the system shall apply them to the J1708 message stream the same way `j1939 decode` applies them to CAN frames. |
| `REQ-J1587-09` | Unwanted behaviour | If the capture file is missing, the system shall return a structured error with code `J1587_SOURCE_UNAVAILABLE` and exit code 1. If a line does not match the `(timestamp) j1708 <hex>` format, has an odd number of hex digits, or fails to parse as a J1708 message, the system shall return a structured error with code `J1587_SOURCE_INVALID` and exit code 1. |
| `REQ-J1587-10` | Event-driven | When `j1587 pids` is invoked, the system shall return the bundled PID catalog as a reference-mode payload (`mode: "reference"`, `pid_count`, `pids`). |

## Command Surface

```text
canarchy j1587 decode --file <path> [--offset N] [--max-frames N] [--seconds N] [--json|--jsonl|--text]
canarchy j1587 pids [--json|--jsonl|--text]
```

## Wire Model (J1708 / J1587)

Each line of a capture file reads `(timestamp) j1708 <hex>`, where `<hex>` is
the full raw message: a source MID byte, zero or more PID-framed parameters,
and a trailing checksum byte chosen so the byte sum of the whole message is
congruent to 0 mod 256.

## Responsibilities And Boundaries

In scope: the J1708 framing parser, PID-based value decoding against the
bundled catalog, and the `j1587 decode` / `j1587 pids` file-backed workflows.

Out of scope (v1): live J1708/RS-485 transports (file-backed captures only);
a MID-to-ECU-name catalog (`mid` is reported as a raw integer); a `j1587
monitor` live-stream command.

## Data Model

`j1587 decode` emits `j1587_parameter` events (`mid`, `pid`, `raw` hex,
`name`, `value`, `units`, `checksum_valid`, `timestamp`). Envelope `data`
reports `mode: "passive"`, `file`, `message_count`, `parameter_count`, and
`checksum_failures`. `j1587 pids` returns `mode: "reference"`, `pid_count`,
and `pids` (the bundled catalog, each entry annotated with its `pid`).

## Output Contracts

`--json` returns the envelope with the `data` block and an `events` array;
`--jsonl` streams the `j1587_parameter` events; `--text` renders a table of
parsed parameters (`j1587 decode`) or the PID catalog (`j1587 pids`),
shape-consistent with the `j1939` output.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `J1587_SOURCE_UNAVAILABLE` | `--file` does not exist | 1 |
| `J1587_SOURCE_INVALID` | a capture line is malformed (bad format, odd hex digits, or framing error) | 1 |

## Deferred Decisions

* A live J1708/RS-485 transport and `j1587 monitor` command.
* A bundled MID-to-ECU-name catalog.
