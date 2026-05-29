# Design Spec: `canarchy fuzz signal` — DBC-aware signal mutation

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy fuzz signal` |
| Primary area | CLI, fuzzing engine, MCP |
| Related specs | `docs/design/active-transmit-safety.md`, `docs/design/send-dbc-command.md`, `docs/design/sequence-replay.md` |

## Goal

Add DBC-aware, signal-level fuzzing on top of the raw-payload fuzzing engine
(`canarchy.fuzzing`). Where `fuzz payload` flips bits in opaque bytes, `fuzz
signal` targets a single signal inside a DBC message and exercises it within and
beyond its declared bounds — respecting bit layout, length, byte order, scale,
offset, minimum / maximum, and the choice set. This finds bugs that raw
bitflipping misses: out-of-range values, unit boundary conditions, enum gaps, and
byte-order pitfalls.

## User-Facing Motivation

An analyst or agent reverse-engineering or stress-testing an ECU usually thinks in
*signals*, not raw bytes. "Drive `EngineSpeed` one lsb past its declared maximum"
or "send every undefined value of a 3-bit mode enum" are natural fuzz intents that
raw byte mutation cannot express precisely. `fuzz signal` keeps CANarchy's
"protocol semantics over raw frames" philosophy and reuses the cantools-backed
runtime so the same DBC the operator already uses for `decode` / `encode` drives
the fuzz campaign.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-FZS-01` | Ubiquitous | The system shall provide a `canarchy fuzz signal` command that mutates a single DBC signal across a chosen mode. |
| `REQ-FZS-02` | Event-driven | When `fuzz signal --mode in_bounds` is invoked, the system shall emit `--count` payloads whose target signal decodes to a value within the declared `[minimum, maximum]` range. |
| `REQ-FZS-03` | Event-driven | When `fuzz signal --mode out_of_bounds` is invoked, the system shall emit payloads whose target signal decodes strictly outside the declared range, including the representable type extrema. |
| `REQ-FZS-04` | Event-driven | When `fuzz signal --mode boundary` is invoked, the system shall emit the declared minimum, maximum, and the min / max ± 1 lsb values that are representable in the signal field. |
| `REQ-FZS-05` | Optional feature | Where `--mode enum_gaps` is selected, the system shall emit every representable raw value that is not a defined choice. |
| `REQ-FZS-15` | Optional feature | Where `--mode full_field` is selected, the system shall sweep the entire representable raw field, ignoring the declared bounds, emitting evenly spaced samples (including both extrema) when the field is wider than `--count`. |
| `REQ-FZS-06` | Ubiquitous | The system shall hold all non-target signals at a baseline (raw zero by default) while mutating the target signal. |
| `REQ-FZS-07` | State-driven | While generating payloads, the system shall be deterministic for a fixed `(message, signal, mode, seed, count)`. |
| `REQ-FZS-08` | Unwanted behaviour | If the target signal is not defined on the message, the system shall return a structured error and exit non-zero. |
| `REQ-FZS-09` | Unwanted behaviour | If `--mode enum_gaps` is selected for a signal without a choice set, the system shall return `INVALID_FUZZ_SIGNAL`. |
| `REQ-FZS-10` | Unwanted behaviour | If the DBC message is not found, the system shall return `DBC_MESSAGE_NOT_FOUND`. |
| `REQ-FZS-11` | Unwanted behaviour | If `--rate` is not greater than zero, the system shall return `INVALID_RATE`. |
| `REQ-FZS-12` | State-driven | While not in `--dry-run`, the system shall honour the active-transmit safety controls (rate cap, kill-switch, ack requirement, `run_id` provenance) documented in `docs/design/active-transmit-safety.md`. |
| `REQ-FZS-13` | Optional feature | Where `--dry-run` is specified, the system shall emit the planned frame schedule without opening a transport, and shall not require an interface. |
| `REQ-FZS-14` | Optional feature | Where the MCP `fuzz_signal` tool is invoked, the system shall require `ack_active=true` and default `dry_run=true`. |

## Command Surface

```text
canarchy fuzz signal [<interface>] --dbc <path|ref> --message <name> --signal <name> \
    --mode {in_bounds,out_of_bounds,boundary,enum_gaps,full_field} \
    [--count <n>] [--rate <hz>] [--seed <n>] [--dry-run] [--ack-active] \
    [--run-id <uuid>] [--json|--jsonl|--text]
```

## Responsibilities And Boundaries

In scope:

* Signal-aware raw-value generation for the four modes.
* Full-message payload encoding via the cantools runtime
  (`scaling=False, strict=False`) so out-of-range raw values can be emitted.
* CLI surface, MCP mirror, and active-transmit safety integration.

Out of scope:

* J1939 SPN-aware mutation (`fuzz spn`, filed as #347).
* Multiplexed-message selector handling beyond what cantools encodes from a
  flat signal dict (deferred).
* CRC repair (not meaningful for deliberate signal mutation; raw `fuzz payload`
  carries `--repair-crc`).

## Data Model

The engine (`canarchy.fuzzing.signal_payload`) works in **raw signal space**:

* `raw_lo`, `raw_hi` — representable bounds from bit length and signedness.
* `dmin_raw`, `dmax_raw` — declared `[minimum, maximum]` converted to raw via
  `round((physical - offset) / scale)`, clamped to `[raw_lo, raw_hi]`.
* `1 lsb` == one raw unit (== `scale` in physical units).

Per mode, the raw candidate set is:

| Mode | Raw candidates |
|------|----------------|
| `in_bounds` | `count` seeded uniform samples in `[dmin_raw, dmax_raw]` |
| `boundary` | `dmin_raw`, `dmax_raw`, `dmin_raw±1`, `dmax_raw±1` (representable only) |
| `out_of_bounds` | `dmin_raw-1`, `dmax_raw+1`, `raw_lo`, `raw_hi` (representable and strictly outside the declared range) |
| `enum_gaps` | every raw in `[raw_lo, raw_hi]` not in the choice set |
| `full_field` | the whole `[raw_lo, raw_hi]` field; evenly spaced (extrema included) when wider than `count` |

Each candidate is packed into a full-message payload with other signals at the
baseline (raw zero unless a baseline mapping is supplied).

`full_field` is the escape hatch for signals whose declared range already spans
the full bit width (e.g. an 8-bit `[0, 255]` signal), where `out_of_bounds`
correctly yields nothing — it sweeps every representable value regardless of the
DBC bounds.

## Output Contracts

* `--json` — a single envelope with `data.signal_mode`, `data.message`,
  `data.signal`, `data.mode` (`dry_run`/`active`), `data.frame_count`,
  `data.run_id`, plus the canonical `events` list.
* `--jsonl` — an `alert` event (ACTIVE_TRANSMIT / dry-run notice) followed by one
  `frame` event per planned payload, each carrying `run_id` and `dry_run`.
* `--text` — human-readable summary consistent with the other fuzz subcommands.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DBC_MESSAGE_NOT_FOUND` | `--message` not in the DBC | 1 |
| `INVALID_FUZZ_SIGNAL` | unknown `--signal`, negative `--count`, or `enum_gaps` on a choiceless signal | 1 |
| `DBC_LOAD_FAILED` | DBC path/ref cannot be parsed | 1 |
| `INVALID_RATE` | `--rate <= 0` | 1 |
| `ACTIVE_ACK_REQUIRED` | live mode without `--ack-active` when config demands it | 2 |

## Deferred Decisions

* Multiplexed-message mutation (selecting the multiplexer before mutating a
  multiplexed signal).
* A `--baseline` flag to seed non-target signals from a decoded frame rather than
  raw zero (engine already accepts a `baseline` argument).
* Negative-scale signals are handled by swapping the derived raw bounds, but are
  not exhaustively tested.
