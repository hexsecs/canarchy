# Design Spec: `gateway` Command

## Goal

Bridge CAN frames between two interfaces so operators can forward traffic from a physical bus to a software loopback, between two network endpoints, or between any two python-can-supported channels — without dropping to python-can directly.

## Command surface

```
canarchy gateway <src> <dst>
                 [--src-backend TYPE] [--dst-backend TYPE]
                 [--bidirectional]
                 [--count N]
                 [--json] [--jsonl] [--table] [--raw]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `src` | required | Source channel (e.g. `can0`, `239.0.0.1`, `/dev/tty.usbmodem1`) |
| `dst` | required | Destination channel |
| `--src-backend` | `CANARCHY_PYTHON_CAN_INTERFACE` | python-can interface type for the source bus |
| `--dst-backend` | `CANARCHY_PYTHON_CAN_INTERFACE` | python-can interface type for the destination bus |
| `--bidirectional` | off | Also forward frames from dst back to src |
| `--count` | unlimited | Stop after N forwarded frames total |

`--src-backend` and `--dst-backend` both default to the value of `CANARCHY_PYTHON_CAN_INTERFACE` (default `virtual`), so when both buses use the same backend type only the env var needs to be set.

## Streaming behaviour

`gateway` is always a streaming command. It runs until interrupted with `Ctrl+C` or until `--count` frames have been forwarded. There is no batch/snapshot mode.

### Unidirectional (default)

A single read loop reads from the source bus and sends each message to the destination bus synchronously, yielding one `CanFrame` per iteration.

### Bidirectional (`--bidirectional`)

Two threads run concurrently:
- Thread A reads from src, sends to dst.
- Thread B reads from dst, sends to src.

Both threads put forwarded frames on a shared queue that the main generator drains. A shared stop event coordinates shutdown when `--count` is reached or an error occurs.

## Backend requirement

`gateway` requires the `python-can` backend. If `CANARCHY_TRANSPORT_BACKEND` is not set to `python-can`, the command raises a structured `TransportError` with code `GATEWAY_LIVE_BACKEND_REQUIRED`.

## Data model

Each forwarded frame yields a `CanFrame` tagged with the source channel as `interface`. The direction (`src->dst` or `dst->src`) is recorded in the `source` field of the corresponding `FrameEvent`.

## Output format

### Table / raw (default streaming output)

```
gateway: src=can0 dst=239.0.0.1
(1713369600.000000) can0 18FEEE31#11223344  [src->dst]
(1713369600.050000) can0 18F00431#AABBCCDD  [src->dst]
```

### JSON / JSONL

Standard envelope with `events` list. Each event is a `FrameEvent` with `source` set to `"gateway.src->dst"` or `"gateway.dst->src"`.

## Error cases

| Code | Trigger | Exit code |
|------|---------|-----------|
| `GATEWAY_LIVE_BACKEND_REQUIRED` | `CANARCHY_TRANSPORT_BACKEND` is not `python-can` | 2 |
| `TRANSPORT_UNAVAILABLE` | Source or destination bus cannot be opened | 2 |
| `INVALID_COUNT` | `--count` < 1 | 1 |

## Open questions / deferred

- Per-direction count limits (e.g. stop after N frames in each direction) are deferred.
- Frame filtering (forward only frames matching an expression) is deferred to a follow-up.
- Rate limiting / frame pacing on the destination bus is deferred.
