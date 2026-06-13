# Design Spec: `canarchy send --dbc` — DBC-Aware Signal Transmit

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy send` |
| Primary area | CLI, DBC, active-transmit safety |
| Issue | #360 |

## Goal

Extend the existing `send` command with DBC-aware signal encoding so operators can transmit a named DBC message by signal values without writing a throwaway Python script.

## User-Facing Motivation

Every DBC-aware transmit research session currently requires importing cantools, loading the DBC, encoding the message, and sending — roughly five lines every time. The `send --dbc` surface eliminates that pattern for single-frame and periodic-repeat use cases.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SEND-DBC-01` | Ubiquitous | The system shall accept `--dbc <ref>`, `--message <name>`, and `--signals KEY=VAL…` flags on the `send` command. |
| `REQ-SEND-DBC-02` | Event-driven | When `send [interface] --dbc <ref> --message <name> --signals KEY=VAL…` is invoked without `--dry-run`, the system shall encode the message via the DBC runtime and transmit the resulting frame. |
| `REQ-SEND-DBC-03` | Event-driven | When `--dry-run` is supplied, the system shall encode the message and return the planned frame in the envelope without opening a transport. |
| `REQ-SEND-DBC-04` | Event-driven | When `--count N` is supplied (N > 1), the system shall send the encoded frame N times. |
| `REQ-SEND-DBC-05` | Event-driven | When `--rate HZ` is supplied together with `--count N > 1`, the system shall sleep `1/HZ` seconds between successive sends. |
| `REQ-SEND-DBC-06` | State-driven | While transmitting (non-dry-run), the system shall enforce active-transmit safety controls per `docs/design/active-transmit-safety.md`. |
| `REQ-SEND-DBC-07` | Optional feature | Where `--dry-run` is set, the system shall not require an interface argument and shall not open transport. |
| `REQ-SEND-DBC-08` | Unwanted behaviour | If `--dbc` is present but `--message` is absent, the system shall return a structured error with code `MISSING_MESSAGE` and exit code 3. |
| `REQ-SEND-DBC-09` | Unwanted behaviour | If a signal assignment does not contain `=`, the system shall return a structured error with code `INVALID_SIGNAL_ASSIGNMENT` and exit code 3. |
| `REQ-SEND-DBC-10` | Unwanted behaviour | If `--rate` is zero or negative, the system shall return a structured error with code `INVALID_RATE` and exit code 3. |
| `REQ-SEND-DBC-11` | Unwanted behaviour | If `--count` is less than 1, the system shall return a structured error with code `INVALID_COUNT` and exit code 3. |
| `REQ-SEND-DBC-12` | Unwanted behaviour | If the DBC cannot be resolved or loaded, the system shall propagate the existing `DBC_LOAD_FAILED` error. |
| `REQ-SEND-DBC-13` | Unwanted behaviour | If a signal name or value fails DBC validation, the system shall propagate the existing `DBC_SIGNAL_INVALID` error. |
| `REQ-SEND-DBC-14` | Ubiquitous | The raw `send <interface> <frame_id> <data>` surface shall remain fully backwards-compatible. |
| `REQ-SEND-DBC-15` | Ubiquitous | `send --dbc` shall apply the same encode name resolution and unsupplied-signal defaulting as `encode` (REQ-DBC-08/09), reporting defaults under `data.resolution.filled_signals` and warning the operator to review them before live transmission. |

## Command Surface

```text
canarchy send [<interface>] --dbc <file|opendbc:name> --message <name>
             [--signals KEY=VAL ...] [--crc-algorithm {stellantis,sae-j1850,fca-giorgio}]
             [--rate HZ] [--count N] [--dry-run]
             [--ack-active] [--json] [--jsonl] [--text]
```

`<interface>` is optional when `--dry-run` is set or a default interface is configured.

## Responsibilities And Boundaries

In scope:

* DBC-backed encoding of a named message from signal assignments
* Single-frame and counted-repeat transmit
* Dry-run planning mode (encode without transport)
* CRC auto-detection and algorithm override inherited from the DBC encode runtime
* Active-transmit safety guard (same as raw `send`)

Out of scope:

* Indefinite looping until SIGINT (users set `--count` explicitly)
* Signal padding / default-filling for unspecified signals (the DBC encode runtime decides this)
* Multi-message coordinated transmit (see issue #362 `sequence replay`)

## Data Model

The envelope `data` object for a DBC-mode send includes:

| Field | Description |
|-------|-------------|
| `mode` | `"active"` or `"dry_run"` |
| `dbc` | The `--dbc` argument as given |
| `dbc_source` | Provider metadata (provider, name, version, path) |
| `message` | The `--message` argument |
| `signals` | Parsed signal assignments dict |
| `frame` | Encoded frame payload (arbitration_id, data hex, etc.) |
| `count` | Requested send count |
| `rate` | Requested rate in Hz or null |
| `interface` | Target interface or null for dry-run |

## Output Contracts

Returns the standard CANarchy JSON envelope. Events list contains one `alert` event (ACTIVE_TRANSMIT) plus one `frame` event per send in active mode. Dry-run returns an empty events list.

## Active-Transmit Safety

`send` is in `ACTIVE_TRANSMIT_COMMANDS`. `enforce_active_transmit_safety()` is called before the first transmit when not in dry-run mode, emitting the preflight warning and enforcing `--ack-active` when `require_active_ack` is configured.
