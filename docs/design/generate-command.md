# Design Spec: `generate` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy generate` |
| Primary area | CLI, active transmit |

## Goal

Give operators a `cangen`-style frame-generation workflow directly from the CANarchy CLI so they can produce repeatable test traffic without reaching for a separate tool.

## User-Facing Motivation

Operators need a quick active-traffic workflow for lab validation, replay support, and transport testing while preserving CANarchy's structured output and explicit preflight active-transmit signaling.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-GENERATE-01` | Ubiquitous | The system shall provide a `canarchy generate <interface>` command for active CAN frame generation. |
| `REQ-GENERATE-02` | Event-driven | When `generate` is invoked, the system shall support fixed, random (`R`), and incrementing (`I`) generation modes for identifiers and payloads as specified by `--id`, `--dlc`, and `--data`. |
| `REQ-GENERATE-03` | Event-driven | When `generate` is invoked, the system shall bound output by `--count` and space events by `--gap` milliseconds. |
| `REQ-GENERATE-04` | Event-driven | When `generate` is invoked and validation succeeds, the system shall emit a preflight active-transmit warning to `stderr`, emit a leading active-transmit alert event, and serialise the generated frame events. |
| `REQ-GENERATE-10` | Optional feature | Where `--ack-active` is supplied for `generate`, the system shall require a confirmation response of `YES` before generated frames are transmitted. |
| `REQ-GENERATE-11` | Optional feature | Where active acknowledgement is required, the system shall require `--ack-active` before generated frames are transmitted. |
| `REQ-GENERATE-05` | Unwanted behaviour | If `--id` is not a valid hex value or `R`, the system shall return a structured error with code `INVALID_FRAME_ID` and exit code 1. |
| `REQ-GENERATE-06` | Unwanted behaviour | If `--dlc` is not an integer in 0–8 or `R`, the system shall return a structured error with code `INVALID_DLC` and exit code 1. |
| `REQ-GENERATE-07` | Unwanted behaviour | If `--data` is not valid hex, `R`, or `I`, the system shall return a structured error with code `INVALID_FRAME_DATA` and exit code 1. |
| `REQ-GENERATE-08` | Unwanted behaviour | If `--count` is less than 1, the system shall return a structured error with code `INVALID_COUNT` and exit code 1. |
| `REQ-GENERATE-09` | Unwanted behaviour | If `--gap` is negative, the system shall return a structured error with code `INVALID_GAP` and exit code 1. |

## Command Surface

```text
canarchy generate <interface> [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>]
                               [--count <n>] [--gap <ms>] [--extended] [--ack-active]
                               [--json] [--jsonl] [--table] [--raw]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `interface` | required | CAN interface to transmit on |
| `--id` | `R` | Arbitration ID as hex or `R` for random |
| `--dlc` | `R` | Data length `0-8` or `R` for random |
| `--data` | `R` | Payload as hex, `R` for random bytes, or `I` for incrementing |
| `--count` | `1` | Number of frames to generate |
| `--gap` | `200` | Inter-frame gap in milliseconds |
| `--extended` | off | Force 29-bit extended arbitration IDs |
| `--ack-active` | off | Request an interactive confirmation prompt before generated frames are transmitted |

### Incrementing payload mode

`--data I` fills each frame payload with bytes starting at `(frame_index * dlc + byte_index) % 256`. This yields a rolling pattern useful for spotting dropped or reordered frames.

## Responsibilities And Boundaries

In scope:

* deterministic frame generation from CLI arguments
* random and incrementing payload modes
* preflight active-transmit warnings and event emission

Out of scope:

* CAN FD generation flags
* real-time sleep enforcement on live backends

## Data Model

Generated frames are `CanFrame` instances with:

* `arbitration_id` resolved from `--id`
* `data` resolved from `--data` and `--dlc`
* `is_extended_id` derived from `--extended` or the resolved identifier width
* `interface` from the positional argument
* `timestamp` set from `frame_index * gap_ms / 1000.0`

## Event Model

Each generated frame produces a `FrameEvent` with `source="transport.generate"`. A leading `AlertEvent` with `code="ACTIVE_TRANSMIT"` communicates the active nature of the workflow.

## Output Contracts

### Preflight warning

After argument validation succeeds, `generate` emits a preflight warning to `stderr` before frame transmission begins.

### JSON and JSONL

`--json` returns the standard CANarchy envelope. `--jsonl` emits the generated event stream one event per line.

### Table

```text
command: generate
interface: can0
frames: 3
(0.000000) can0 07A#C3F1
(0.200000) can0 3B2#00112233
(0.400000) can0 1FF#FF
```

### Raw

Emits the command name on success or the first error message on failure.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_FRAME_ID` | `--id` is not hex and not `R` | 1 |
| `INVALID_DLC` | `--dlc` is not `0-8` and not `R` | 1 |
| `INVALID_FRAME_DATA` | `--data` is not valid hex, `R`, or `I` | 1 |
| `INVALID_COUNT` | `--count` is less than `1` | 1 |
| `INVALID_GAP` | `--gap` is less than `0` | 1 |
| `ACTIVE_ACK_REQUIRED` | active acknowledgement is required but `--ack-active` was omitted | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | `--ack-active` was supplied but the confirmation response was not `YES` | 1 |

## Deferred Decisions

* live-backend gap enforcement with real sleeps
* CAN FD frame-generation support
