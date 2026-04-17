# Design Spec: `generate` Command

## Goal

Give operators a `cangen`-style frame generation workflow directly from the CANarchy CLI, producing test traffic without a separate tool.

## Command surface

```
canarchy generate <interface> [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>]
                              [--count <n>] [--gap <ms>] [--extended]
                              [--json] [--jsonl] [--table] [--raw]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `interface` | required | CAN interface to transmit on (e.g. `can0`) |
| `--id` | `R` | Arbitration ID as hex (`0x123`) or `R` for random |
| `--dlc` | `R` | Data length 0–8 or `R` for random |
| `--data` | `R` | Payload as hex, `R` for random bytes, or `I` for incrementing |
| `--count` | `1` | Number of frames to generate (must be ≥ 1) |
| `--gap` | `200` | Inter-frame gap in milliseconds (must be ≥ 0) |
| `--extended` | off | Force 29-bit extended arbitration IDs |

### `--data I` semantics

Incrementing mode fills each frame's payload with bytes starting at `(frame_index * dlc + byte_index) % 256`. This produces a rolling pattern across frames that is useful for identifying out-of-order or dropped frames.

## Data model

Generated frames are `CanFrame` instances with:

- `arbitration_id`: resolved from `--id`
- `data`: resolved from `--data` and `--dlc`
- `is_extended_id`: `True` if `--extended` or if `arbitration_id > 0x7FF`
- `interface`: from the `interface` argument
- `timestamp`: `frame_index * gap_ms / 1000.0`

## Events

Each generated frame produces a `FrameEvent` with `source="transport.generate"`. A single `AlertEvent` with `code="ACTIVE_TRANSMIT"` is prepended to the event list.

## Output format

### JSON / JSONL

Standard envelope:

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
    "events": [...]
  },
  "warnings": ["..."],
  "errors": []
}
```

### Table

```
command: generate
interface: can0
frames: 3
(0.000000) can0 07A#C3F1
(0.200000) can0 3B2#00112233
(0.400000) can0 1FF#FF
warning: Frame generation is an active transmission workflow; use intentionally on a controlled bus.
```

### Raw

Emits the command name on success, or the first error message on failure.

## Error cases

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_FRAME_ID` | `--id` is not hex and not `R` | 1 |
| `INVALID_DLC` | `--dlc` is not 0–8 and not `R` | 1 |
| `INVALID_FRAME_DATA` | `--data` is not valid hex, `R`, or `I` | 1 |
| `INVALID_COUNT` | `--count` < 1 | 1 |
| `INVALID_GAP` | `--gap` < 0 | 1 |

## Open questions / deferred

- Live backend gap enforcement (actual `time.sleep` between sends) is deferred until the live backend path is exercised end-to-end.
- CAN FD frame generation (`--fd` flag) is deferred to a follow-up issue.
