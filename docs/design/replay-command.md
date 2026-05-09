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

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-REPLAY-01` | Ubiquitous | The system shall provide a `canarchy replay --file <file>` command for deterministic replay planning over capture files. |
| `REQ-REPLAY-02` | Event-driven | When `replay --file <file>` is invoked, the system shall produce a replay plan preserving the capture frame count and deriving duration from the capture timeline. |
| `REQ-REPLAY-03` | Event-driven | When `replay --file <file> --rate <factor>` is invoked, the system shall scale relative event timing by the specified rate factor. |
| `REQ-REPLAY-04` | Event-driven | When `replay` is invoked, the system shall return a replay plan that remains machine-readable without emitting duplicated active-transmit safety warnings in structured output. |
| `REQ-REPLAY-05` | Unwanted behaviour | If `--rate` is zero or negative, the system shall return a structured error with code `INVALID_RATE` and exit code 1. |
| `REQ-REPLAY-06` | Unwanted behaviour | If the capture source file is missing or unreadable, the system shall return a structured error with code `CAPTURE_SOURCE_UNAVAILABLE` and exit code 2. |

## Command Surface

```text
canarchy replay --file <file> [--rate <factor>] [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* deterministic replay planning from capture files
* relative timing scaling through `--rate`
* replay-event serialisation

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

`--json` returns the standard CANarchy result envelope. `--jsonl` emits replay events one per line.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_RATE` | replay rate is zero or negative | 1 |
| `CAPTURE_SOURCE_UNAVAILABLE` | replay source file cannot be opened | 2 |

## Deferred Decisions

* replay looping and more advanced scheduling controls
* live rate pacing enforcement against physical interfaces
