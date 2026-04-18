# Design Spec: `gateway` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy gateway` |
| Primary area | CLI, transport |

## Goal

Bridge CAN frames between two interfaces so operators can forward traffic from a physical bus to a software loopback, between two network endpoints, or between any two `python-can` supported channels without dropping to `python-can` directly.

## User-Facing Motivation

Operators need a first-class CLI workflow for controlled bus-to-bus forwarding that remains scriptable, observable, and compatible with CANarchy output modes.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-GATEWAY-01` | The system shall provide a `canarchy gateway <src> <dst>` command for live CAN frame forwarding. |
| `REQ-GATEWAY-02` | The command shall support independent backend selection for source and destination buses. |
| `REQ-GATEWAY-03` | The command shall support optional bidirectional forwarding. |
| `REQ-GATEWAY-04` | The command shall support bounded forwarding through `--count`. |
| `REQ-GATEWAY-05` | The command shall emit structured frame events with direction encoded in the event `source` field. |
| `REQ-GATEWAY-06` | The command shall require the `python-can` backend and return structured transport errors when unavailable. |
| `REQ-GATEWAY-07` | Table and raw output shall present forwarded frames in candump-style form with direction labels. |

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

`--src-backend` and `--dst-backend` both default to `CANARCHY_PYTHON_CAN_INTERFACE` so operators only need explicit flags when the two buses use different backend types.

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

`gateway` is always a streaming command. It runs until interrupted with `Ctrl+C` or until `--count` frames have been forwarded.

### Unidirectional mode

A single read loop reads from `src`, sends each message to `dst`, and emits one forwarded frame event per iteration.

### Bidirectional mode

Two worker threads run concurrently:

* one reads from `src` and forwards to `dst`
* one reads from `dst` and forwards to `src`

Both workers write forwarded events to a shared queue. A shared stop condition ends processing when `--count` is reached or a transport error occurs.

## Backend Requirement

`gateway` requires the `python-can` backend. If `CANARCHY_TRANSPORT_BACKEND` is not `python-can`, the command returns a structured transport error with code `GATEWAY_LIVE_BACKEND_REQUIRED`.

## Data Model

Each forwarded frame is emitted as a serialized `FrameEvent`.

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

`--json` returns the standard CANarchy command envelope. `--jsonl` emits one forwarded frame event per line. Forwarded frame events use `source` values `gateway.src->dst` and `gateway.dst->src`.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `GATEWAY_LIVE_BACKEND_REQUIRED` | `CANARCHY_TRANSPORT_BACKEND` is not `python-can` | 2 |
| `TRANSPORT_UNAVAILABLE` | Source or destination bus cannot be opened or written | 2 |
| `INVALID_COUNT` | `--count` is less than `1` | 1 |

## Deferred Decisions

* per-direction count limits
* forwarding-time frame filtering
* destination pacing or bandwidth controls
