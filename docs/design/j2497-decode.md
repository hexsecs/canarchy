# Design Spec: J2497 (PLC4TRUCKS) Trailer Power-Line Decoding

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j2497 decode`, `j2497 mids` |
| Primary area | Protocol, CLI |
| Related specs | `docs/design/j1587-decode.md` |

## Goal

Bring passive J2497 ("PLC4TRUCKS") coverage to the same structured-output
surface used for J1939 and J1587. J2497 (SAE J2497, "Power Line Carrier
Communications for Commercial Vehicles") is the trailer power-line network
that carries diagnostic messages — most visibly trailer ABS status — between
a tractor and its trailer(s) over the power line rather than a dedicated data
bus. At the message layer it reuses the J1708/J1587 frame format:
`MID <message-data...> checksum`. `canarchy j2497 decode` parses a captured
J2497 trace into one structured message per frame (source MID, raw
message-data bytes, and checksum validity), resolving common MIDs against a
bundled trailer-oriented catalog.

## User-Facing Motivation

CAN-centric tooling generally ignores the trailer power-line network, leaving
analysts working trailer ABS / PLC traffic with no CANarchy-native way to
read a captured J2497 trace. This brings that traffic into the same canonical
JSON/JSONL event contract used elsewhere, including byte-sum checksum
validation and MID-to-ECU-name resolution.

This is a clean-room implementation against the public J2497 / J1708 framing
semantics and a small hand-built MID catalog. It reuses no code or data from
hardware-oriented PLC tooling (e.g. PLC4TRUCKSduck), which is write-oriented
and carries its own license.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J2497-01` | Ubiquitous | The system shall provide a pure parser that decodes a raw J2497 frame (`MID <message-data...> checksum`) into a source MID, the raw message-data bytes (everything between the MID and the trailing checksum), and a checksum-valid flag. |
| `REQ-J2497-02` | Ubiquitous | The parser shall compute checksum validity as whether the byte sum of the whole frame is congruent to 0 mod 256, mirroring J1708. |
| `REQ-J2497-03` | Unwanted behaviour | If a frame is shorter than two bytes (a MID and a checksum), the parser shall raise a `ValueError` describing the truncation. The message-data bytes are treated opaquely; a frame is not rejected for imperfect J1587 PID framing. |
| `REQ-J2497-04` | Ubiquitous | The system shall provide a bundled J2497/J1587 MID catalog (`resources/j2497/mids.json`) mapping common source MIDs (trailer ABS controllers and related ECUs) to names, with override support via `CANARCHY_J2497_MID_OVERRIDES` (falling back to `~/.canarchy/j2497_mids.json`). |
| `REQ-J2497-05` | Event-driven | When a frame's MID is in the bundled catalog, the system shall resolve its `name`; an unknown MID shall resolve `name: null` without error. |
| `REQ-J2497-06` | Event-driven | When `j2497 decode --file <path>` is invoked, the system shall parse each `(timestamp) j2497 <hex>` line of the capture file into a J2497 frame and emit one `j2497_message` event per frame, reporting `mid`, `name`, `data`, `checksum_valid`, and `timestamp`. |
| `REQ-J2497-07` | Optional feature | Where `--offset` / `--max-frames` / `--seconds` are supplied, the system shall apply them to the J2497 frame stream the same way `j1939 decode` applies them to CAN frames. |
| `REQ-J2497-08` | Unwanted behaviour | If the capture file is missing, the system shall return a structured error with code `J2497_SOURCE_UNAVAILABLE` and exit code 1. If a line does not match the `(timestamp) j2497 <hex>` format, has an odd number of hex digits, or is too short to be a frame, the system shall return a structured error with code `J2497_SOURCE_INVALID` and exit code 1. |
| `REQ-J2497-09` | Event-driven | When `j2497 mids` is invoked, the system shall return the bundled MID catalog as a reference-mode payload (`mode: "reference"`, `mid_count`, `mids`). |

## Command Surface

```text
canarchy j2497 decode --file <path> [--offset N] [--max-frames N] [--seconds N] [--json|--jsonl|--text]
canarchy j2497 mids [--json|--jsonl|--text]
```

## Wire Model (J2497 / J1708)

Each line of a capture file reads `(timestamp) j2497 <hex>`, where `<hex>` is
the full raw frame: a source MID byte, zero or more message-data bytes, and a
trailing checksum byte chosen so the byte sum of the whole frame is congruent
to 0 mod 256. The message-data bytes follow the J1587 PID framing rules; for
PID-level resolution of that content, feed the same byte format to
`canarchy j1587 decode`.

## Responsibilities And Boundaries

In scope: the J2497 framing parser, MID-name resolution against the bundled
catalog, and the `j2497 decode` / `j2497 mids` file-backed workflows.

Out of scope (v1): live J2497 / power-line-carrier transports — live PLC
access requires a power-line carrier modem and external hardware and is not
provided; PID-level decoding of the message-data bytes (delegated to
`j1587 decode`); a `j2497 monitor` live-stream command.

## Data Model

`j2497 decode` emits `j2497_message` events (`mid`, `name`, `data` hex,
`checksum_valid`, `timestamp`). Envelope `data` reports `mode: "passive"`,
`file`, `frame_count`, and `checksum_failures`. `j2497 mids` returns
`mode: "reference"`, `mid_count`, and `mids` (the bundled catalog, each entry
annotated with its `mid`).

## Output Contracts

`--json` returns the envelope with the `data` block and an `events` array;
`--jsonl` streams the `j2497_message` events; `--text` renders a table of
parsed frames (`j2497 decode`) or the MID catalog (`j2497 mids`),
shape-consistent with the `j1587` output.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `J2497_SOURCE_UNAVAILABLE` | `--file` does not exist | 1 |
| `J2497_SOURCE_INVALID` | a capture line is malformed (bad format, odd hex digits, or too short to be a frame) | 1 |

## Deferred Decisions

* A live J2497 / power-line-carrier transport and `j2497 monitor` command.
* PID-level decoding of the message-data bytes within `j2497 decode` (today
  delegated to `j1587 decode`, which understands the same byte format).
