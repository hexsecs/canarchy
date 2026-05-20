# Design Spec: `replay` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented with live transmit |
| Command surface | `canarchy replay` |
| Primary area | CLI, replay |
| Related specs | [`active-transmit-safety.md`](active-transmit-safety.md) |

## Goal

Provide deterministic replay planning and live transmission over capture files so operators can inspect, plan, and execute controlled replay of recorded traffic onto a CAN bus.

## User-Facing Motivation

Replay is a core lab workflow for reproducing traffic patterns, validating tooling, and preparing controlled active transmission schedules. Operators need both planning-only mode for preflight inspection and live mode for actually transmitting frames onto a bus.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-REPLAY-01` | Ubiquitous | The system shall provide a `canarchy replay --file <file>` command for deterministic replay planning over capture files. |
| `REQ-REPLAY-02` | Event-driven | When `replay --file <file>` is invoked, the system shall produce a replay plan preserving the capture frame count and deriving duration from the capture timeline. |
| `REQ-REPLAY-03` | Event-driven | When `replay --file <file> --rate <factor>` is invoked, the system shall scale relative event timing by the specified rate factor. |
| `REQ-REPLAY-04` | Event-driven | When `replay` is invoked, the system shall return a replay plan that remains machine-readable without emitting duplicated active-transmit safety warnings in structured output. |
| `REQ-REPLAY-05` | Unwanted behaviour | If `--rate` is zero or negative, the system shall return a structured error with code `INVALID_RATE` and exit code 1. |
| `REQ-REPLAY-06` | Unwanted behaviour | If the capture source file is missing or unreadable, the system shall return a structured error with code `CAPTURE_SOURCE_UNAVAILABLE` and exit code 2. |
| `REQ-REPLAY-07` | Event-driven | When `replay --file <file> --interface <iface>` is invoked, the system shall transmit frames onto the specified CAN interface with timing derived from the original capture and scaled by `--rate`. |
| `REQ-REPLAY-08` | Optional feature | Where `--interface` is supplied with `--dry-run`, the system shall plan the live transmission and emit JSONL events without opening a transport, carrying the warning `ACTIVE_TRANSMIT_DRY_RUN`. |
| `REQ-REPLAY-09` | Event-driven | When live transmission is requested (`--interface` without `--dry-run`), the system shall enforce active-transmit safety controls including `--ack-active` per the active-transmit safety model. |
| `REQ-REPLAY-10` | State-driven | While live replay is transmitting, the system shall pace frames according to the original capture inter-frame timing scaled by `--rate`, capping each sleep at 1 second for responsive interrupt handling. |

## Command Surface

```text
canarchy replay --file <file> [--interface <iface>] [--rate <factor>] [--dry-run] [--ack-active] [--json] [--jsonl] [--text]
```

## Responsibilities And Boundaries

In scope:

* deterministic replay planning from capture files (planning mode)
* relative timing scaling through `--rate`
* replay-event serialisation
* live frame transmission onto a real or virtual CAN interface
* active-transmit safety gating (--ack-active) for live mode
* dry-run planning mode for preflight inspection with interface target

Out of scope:

* indefinite streaming or looping replay
* dataset-backed replay (handled by `datasets replay` — see dataset-provider-workflow design spec)
* target allowlists and rate caps (handled by the active-transmit safety model)

## Data Model

### Planning mode (no --interface)

Replay returns:

* `frame_count`
* `duration`
* `rate`
* `mode`: `"active"`
* replay events derived from the capture timeline

### Live transmit mode (--interface, no --dry-run)

Replay returns:

* `frame_count`
* `duration`
* `rate`
* `mode`: `"active"`
* `interface`: target CAN interface
* replay events derived from the capture timeline

### Dry-run mode (--interface + --dry-run)

Replay returns:

* `frame_count`
* `duration`
* `rate`
* `mode`: `"dry_run"`
* `interface`: target CAN interface
* replay events derived from the capture timeline
* warning `ACTIVE_TRANSMIT_DRY_RUN` in warnings array

## Output Contracts

`--json` returns the standard CANarchy result envelope. `--jsonl` emits replay events one per line.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_RATE` | replay rate is zero or negative | 1 |
| `CAPTURE_SOURCE_UNAVAILABLE` | replay source file cannot be opened | 2 |
| `ACTIVE_ACK_REQUIRED` | live transmit requested without `--ack-active` and `[safety].require_active_ack` is on | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | user declined the active transmit confirmation prompt | 1 |

Active-transmit safety errors follow the codes defined in `active-transmit-safety.md`.

## Deferred Decisions

* replay looping and more advanced scheduling controls
* rate cap enforcement and target allowlists for live replay (tracked in active-transmit safety model)
* streaming live replay output in candump/text mode to stderr or a separate display
