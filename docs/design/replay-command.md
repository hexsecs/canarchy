# Design Spec: `replay` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy replay` |
| Primary area | CLI, replay |

## Goal

Provide deterministic replay planning over capture files so operators can inspect or execute relative transmit schedules from recorded traffic.

## User-Facing Motivation

Replay is a core lab workflow for reproducing traffic patterns, validating tooling, and preparing controlled active transmission schedules.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-REPLAY-01` | The system shall provide a `canarchy replay <file>` command. |
| `REQ-REPLAY-02` | Replay planning shall preserve frame count and derive a duration from the capture timeline. |
| `REQ-REPLAY-03` | Replay planning shall scale relative timing based on `--rate`. |
| `REQ-REPLAY-04` | The command shall communicate its active nature through a warning. |
| `REQ-REPLAY-05` | Invalid rates and missing capture sources shall return structured errors. |

## Command Surface

```text
canarchy replay <file> [--rate <factor>] [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* deterministic replay planning from capture files
* relative timing scaling through `--rate`
* replay-event serialization

Out of scope:

* direct live transmit execution timing controls beyond the current plan representation
* indefinite streaming or looping replay

## Data Model

Replay returns:

* `frame_count`
* `duration`
* `rate`
* replay events derived from the capture timeline

## Output Contracts

`--json` returns the standard CANarchy result envelope. `--jsonl` emits replay events one per line plus synthetic warning alerts when needed.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_RATE` | replay rate is less than or equal to zero | 1 |
| `CAPTURE_SOURCE_UNAVAILABLE` | replay source file cannot be opened | 2 |

## Deferred Decisions

* replay looping and more advanced scheduling controls
* live rate pacing enforcement against physical interfaces
