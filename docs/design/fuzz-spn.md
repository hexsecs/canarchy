# Design Spec: `canarchy fuzz spn` — J1939 SPN-aware mutation

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy fuzz spn` |
| Primary area | CLI, fuzzing engine, MCP, protocol:j1939 |
| Related specs | `docs/design/active-transmit-safety.md`, `docs/design/fuzz-signal.md` |

## Goal

Add SPN-aware fuzzing for J1939. Where `fuzz signal` is generic DBC-driven
mutation, `fuzz spn` bakes in J1939-specific conventions: PGN routing, the
documented not-available / error sentinel patterns, and the operational raw
range that reserves the top of the field. It reuses the same SPN metadata the
`j1939` decode commands already rely on (`canarchy.j1939_metadata`).

## User-Facing Motivation

J1939 parameters have well-defined sentinels — `0xFF…` ("not available") and
`0xFE…` ("error") — and a reserved band at the top of each field. Exercising an
ECU against those sentinels and the operational edges is a routine robustness
check that raw byte fuzzing expresses clumsily. `fuzz spn` lets an analyst say
"drive SPN 110 to its error sentinel" or "sweep its operational boundary" with
the protocol semantics handled correctly.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-FZP-01` | Ubiquitous | The system shall provide a `canarchy fuzz spn` command that mutates a single J1939 SPN across a chosen mode. |
| `REQ-FZP-02` | Event-driven | When `fuzz spn --mode in_bounds` is invoked, the system shall emit `--count` payloads whose SPN raw value is within the operational range `[0, op_max]`. |
| `REQ-FZP-03` | Event-driven | When `fuzz spn --mode not_available` is invoked, the system shall emit the all-ones not-available sentinel for the SPN width (`0xFF` / `0xFFFF` / `0xFFFFFFFF`). |
| `REQ-FZP-04` | Event-driven | When `fuzz spn --mode error` is invoked, the system shall emit the J1939 error sentinel (`0xFE` / `0xFEFF` / `0xFEFFFFFF`). |
| `REQ-FZP-05` | Event-driven | When `fuzz spn --mode boundary` is invoked, the system shall emit `0`, `op_max`, and the representable `± 1 lsb` neighbours. |
| `REQ-FZP-06` | Event-driven | When `fuzz spn --mode out_of_bounds` is invoked, the system shall emit one lsb past the operational maximum (one lsb past the minimum is raw `-1`, which is not representable and is skipped). |
| `REQ-FZP-07` | Ubiquitous | The system shall encode the SPN bytes little-endian at the SPN's byte offset and fill the rest of the PGN payload with the `0xFF` not-available baseline. |
| `REQ-FZP-08` | State-driven | While generating payloads, the system shall be deterministic for a fixed `(spn, mode, seed, count)`. |
| `REQ-FZP-09` | Unwanted behaviour | If the SPN has no built-in J1939 metadata, the system shall return `INVALID_FUZZ_SPN`. |
| `REQ-FZP-10` | Unwanted behaviour | If `--pgn` is supplied and does not match the SPN's PGN, the system shall return `INVALID_FUZZ_SPN`. |
| `REQ-FZP-11` | Unwanted behaviour | If `--rate` is not greater than zero, the system shall return `INVALID_RATE`. |
| `REQ-FZP-12` | State-driven | While not in `--dry-run`, the system shall honour the active-transmit safety controls documented in `docs/design/active-transmit-safety.md`. |
| `REQ-FZP-13` | Optional feature | Where `--dry-run` is specified, the system shall emit the planned frame schedule without opening a transport and shall not require an interface. |
| `REQ-FZP-14` | Optional feature | Where the MCP `fuzz_spn` tool is invoked, the system shall require `ack_active=true` and default `dry_run=true`. |

## Command Surface

```text
canarchy fuzz spn [<interface>] --spn <id> [--pgn <id>] \
    --mode {in_bounds,not_available,error,out_of_bounds,boundary} \
    [--count <n>] [--rate <hz>] [--seed <n>] [--dry-run] [--ack-active] \
    [--run-id <uuid>] [--json|--jsonl|--text]
```

The arbitration id is composed from the SPN's PGN as a broadcast frame
(priority 6, source address `0x00`) via `canarchy.j1939.compose_arbitration_id`.

## Data Model

`canarchy.fuzzing.spn_payload` resolves the SPN's byte `start`, byte `length`
(1 / 2 / 4), byte order, resolution, and offset from `canarchy.j1939_metadata`.
The J1939 reserved band defines the operational raw maximum:

| Width | `op_max` | `error` | `not_available` |
|-------|----------|---------|-----------------|
| 1 byte | `0xFA` | `0xFE` | `0xFF` |
| 2 byte | `0xFAFF` | `0xFEFF` | `0xFFFF` |
| 4 byte | `0xFAFFFFFF` | `0xFEFFFFFF` | `0xFFFFFFFF` |

| Mode | Raw candidates |
|------|----------------|
| `in_bounds` | `count` seeded uniform samples in `[0, op_max]` |
| `not_available` | the all-ones sentinel |
| `error` | the error sentinel |
| `boundary` | `0`, `op_max`, `1`, `op_max−1`, `op_max+1` (min−1 lsb omitted, not representable) |
| `out_of_bounds` | `op_max+1` |

Each raw value is packed little-endian into a `pgn_length`-byte (default 8)
payload pre-filled with `0xFF`.

## Output Contracts

`--json` / `--jsonl` / `--text` mirror the other fuzz subcommands. The envelope
`data` adds `spn_mode`, `spn`, and `pgn`.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_FUZZ_SPN` | unknown SPN, `--pgn` mismatch, negative `--count`, or SPN field that does not fit the payload | 1 |
| `INVALID_RATE` | `--rate <= 0` | 1 |
| `ACTIVE_ACK_REQUIRED` | live mode without `--ack-active` when config demands it | 2 |

## Deferred Decisions

* DBC-sourced SPN metadata (a `decoder` argument) — the engine currently uses
  the built-in `canarchy.j1939_metadata`. A DBC-backed override is a natural
  follow-up.
* `--source-address` / `--priority` overrides for the composed arbitration id
  (currently fixed at SA `0x00`, priority 6).
* Multi-packet (BAM/TP) SPNs larger than a single 8-byte PGN payload.
