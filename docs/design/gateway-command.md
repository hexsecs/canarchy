# Design Spec: `gateway` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy gateway` |
| Primary area | CLI, transport |

## Goal

Bridge CAN frames between two interfaces so operators can forward traffic from a physical bus to a software loopback, between two network endpoints, or between any two `python-can`-supported channels without dropping to `python-can` directly.

## User-Facing Motivation

Operators need a first-class CLI workflow for controlled bus-to-bus forwarding that remains scriptable, observable, and compatible with CANarchy output modes.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-GATEWAY-01` | Ubiquitous | The system shall provide a `canarchy gateway <src> <dst>` command for live CAN frame forwarding between two interfaces. |
| `REQ-GATEWAY-02` | Event-driven | When `gateway <src> <dst>` is invoked, the system shall forward frames from the source interface to the destination interface and emit a structured frame event per forwarded frame. |
| `REQ-GATEWAY-03` | Optional feature | Where `--bidirectional` is specified, the system shall also forward frames from the destination interface back to the source. |
| `REQ-GATEWAY-04` | Optional feature | Where `--count <n>` is specified, the system shall stop forwarding after `n` total frames and return the result. |
| `REQ-GATEWAY-05` | Ubiquitous | Each forwarded frame event shall encode the direction in the event `source` field as `gateway.src->dst` or `gateway.dst->src`. |
| `REQ-GATEWAY-06` | State-driven | While the scaffold backend is active, the system shall refuse to start the gateway and return a structured error with code `GATEWAY_LIVE_BACKEND_REQUIRED` and exit code 2. |
| `REQ-GATEWAY-07` | Unwanted behaviour | If the source or destination interface is unavailable, the system shall return a structured error with code `TRANSPORT_UNAVAILABLE` and exit code 2. |
| `REQ-GATEWAY-08` | Unwanted behaviour | If `--count` is less than 1, the system shall return a structured error with code `INVALID_COUNT` and exit code 1. |

## Command Surface

```text
canarchy gateway <src> <dst>
                 [--src-backend TYPE] [--dst-backend TYPE]
                 [--bidirectional]
                 [--count N]
                 [--json] [--jsonl] [--table] [--raw]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `src` | required | Source channel such as `can0`, `239.0.0.1`, or `/dev/tty.usbmodem1` |
| `dst` | required | Destination channel |
| `--src-backend` | `CANARCHY_PYTHON_CAN_INTERFACE` | `python-can` interface type for the source bus |
| `--dst-backend` | `CANARCHY_PYTHON_CAN_INTERFACE` | `python-can` interface type for the destination bus |
| `--bidirectional` | off | Also forward frames from dst back to src |
| `--count` | unlimited | Stop after `N` forwarded frames total |

## Responsibilities And Boundaries

In scope:

* live forwarding between two interfaces
* optional bidirectional forwarding
* bounded forwarding for scripted use via `--count`
* structured output consistent with existing event envelopes

Out of scope:

* frame filtering during forwarding
* rate limiting or pacing on the destination bus
* per-direction count limits

## Behavioral Model

`gateway` is always a streaming command. It runs until interrupted with Ctrl+C or until `--count` frames have been forwarded.

### Unidirectional mode

A single read loop reads from `src`, sends each message to `dst`, and emits one forwarded frame event per iteration.

### Bidirectional mode

Two worker threads run concurrently:

* one reads from `src` and forwards to `dst`
* one reads from `dst` and forwards to `src`

Both workers write forwarded events to a shared queue. A shared stop condition ends processing when `--count` is reached or a transport error occurs.

## Backend Requirement

`gateway` requires the `python-can` backend. While the scaffold backend is active, the command returns a structured error with code `GATEWAY_LIVE_BACKEND_REQUIRED`.

## Data Model

Each forwarded frame is emitted as a serialised `FrameEvent`.

Relevant event fields:

* `event_type`: `frame`
* `payload.frame.interface`: original source channel
* `source`: `gateway.src->dst` or `gateway.dst->src`

## Output Contracts

### Table and raw

Default streaming output is candump-style with a gateway header and direction labels.

```text
gateway: src=can0 dst=239.0.0.1
(1713369600.000000) can0 18FEEE31#11223344  [src->dst]
(1713369600.050000) can0 18F00431#AABBCCDD  [src->dst]
```

### JSON and JSONL

`--json` returns the standard CANarchy command envelope. `--jsonl` emits one forwarded frame event per line.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `GATEWAY_LIVE_BACKEND_REQUIRED` | scaffold backend is active | 2 |
| `TRANSPORT_UNAVAILABLE` | source or destination bus cannot be opened or written | 2 |
| `INVALID_COUNT` | `--count` is less than `1` | 1 |

## Deferred Decisions

* per-direction count limits
* forwarding-time frame filtering
* destination pacing or bandwidth controls
