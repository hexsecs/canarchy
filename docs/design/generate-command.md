# Design Spec: `generate` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy generate` |
| Primary area | CLI, active transmit |

## Goal

Give operators a `cangen` style frame-generation workflow directly from the CANarchy CLI so they can produce repeatable test traffic without reaching for a separate tool.

## User-Facing Motivation

Operators need a quick active-traffic workflow for lab validation, replay support, and transport testing while preserving CANarchy's structured output and explicit active-transmit warnings.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-GENERATE-01` | The system shall provide a `canarchy generate` command for active frame generation. |
| `REQ-GENERATE-02` | The command shall support fixed, random, and incrementing generation modes for identifiers and payloads as defined by the flags. |
| `REQ-GENERATE-03` | The command shall support bounded generation through `--count` and timestamp spacing through `--gap`. |
| `REQ-GENERATE-04` | The command shall emit an active-transmit warning and serialized frame events. |
| `REQ-GENERATE-05` | The command shall return structured validation errors for invalid identifier, DLC, payload, count, and gap inputs. |

## Command Surface

```text
canarchy generate <interface> [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>]
                               [--count <n>] [--gap <ms>] [--extended]
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

### Incrementing payload mode

`--data I` fills each frame payload with bytes starting at `(frame_index * dlc + byte_index) % 256`. This yields a rolling pattern useful for spotting dropped or reordered frames.

## Responsibilities And Boundaries

In scope:

* deterministic frame generation from CLI arguments
* random and incrementing payload modes
* active-transmit warnings and event emission

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

### JSON and JSONL

Standard CANarchy envelope:

```json
{
  "ok": true,
  "command": "generate",
  "data": {
    "interface": "can0",
    "mode": "active",
    "frame_count": 3,
    "gap_ms": 200,
    "transport_backend": "scaffold",
    "events": []
  },
  "warnings": ["..."],
  "errors": []
}
```

### Table

```text
command: generate
interface: can0
frames: 3
(0.000000) can0 07A#C3F1
(0.200000) can0 3B2#00112233
(0.400000) can0 1FF#FF
warning: Frame generation is an active transmission workflow; use intentionally on a controlled bus.
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

## Deferred Decisions

* live-backend gap enforcement with real sleeps
* CAN FD frame-generation support
