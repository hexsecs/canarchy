# Design Spec: Composition

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy decode`, `filter`, `j1939 decode` |
| Primary area | CLI, event stream composition |

## Goal

Allow commands that consume frame events to read the canonical JSONL event stream from stdin so CANarchy commands compose cleanly in pipelines.

## User-Facing Motivation

Operators and coding agents should be able to connect commands with pipes instead of writing intermediate capture files for every transform.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-COMP-01` | `decode`, `filter`, and `j1939 decode` shall accept `--stdin` to read JSONL events from stdin. |
| `REQ-COMP-02` | When `--stdin` is used, the command shall reject a positional capture file. |
| `REQ-COMP-03` | When `--stdin` is not used, the command shall continue to use the existing file-backed path. |
| `REQ-COMP-04` | Stdin lines shall be validated as canonical frame events before command-specific processing begins. |
| `REQ-COMP-05` | Invalid JSON, invalid event shape, or non-frame events on stdin shall return `INVALID_STREAM_EVENT`. |
| `REQ-COMP-06` | Empty stdin shall return `NO_STREAM_EVENTS`. |
| `REQ-COMP-07` | JSONL output shall preserve the existing event-stream contract of the consuming command. |

## Command Surface

```text
canarchy decode --dbc <file> --stdin [--json|--jsonl|--table|--raw]
canarchy filter --stdin <expression> [--json|--jsonl|--table|--raw]
canarchy j1939 decode --stdin [--json|--jsonl|--table|--raw]
```

Representative usage:

```bash
canarchy capture can0 --jsonl | canarchy filter --stdin 'id==0x18FEEE31' --jsonl
canarchy capture can0 --jsonl | canarchy decode --stdin --dbc truck.dbc --jsonl
canarchy capture can0 --jsonl | canarchy j1939 decode --stdin --jsonl
```

## Pipe Contract

Each non-empty stdin line must be a JSON object whose top-level `event_type` is `"frame"` and whose payload contains `payload.frame` matching the canonical frame envelope.

Representative input line:

```json
{
  "event_type": "frame",
  "payload": {
    "frame": {
      "arbitration_id": 419360305,
      "data": "11223344",
      "frame_format": "can",
      "interface": "can0",
      "is_extended_id": true,
      "is_remote_frame": false,
      "is_error_frame": false,
      "bitrate_switch": false,
      "error_state_indicator": false,
      "timestamp": 0.0
    }
  },
  "source": "transport.capture",
  "timestamp": 0.0
}
```

Ignored input:

* blank lines

Rejected input:

* malformed JSON
* non-frame events such as `alert` or `signal`
* frame payloads missing required fields or containing invalid CAN frame data

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `STDIN_AND_FILE_SPECIFIED` | `--stdin` is used with a positional capture file | 1 |
| `MISSING_INPUT` | neither `--stdin` nor a capture file is provided | 1 |
| `INVALID_STREAM_EVENT` | stdin line is malformed JSON, not a frame event, or does not decode into a valid frame | 1 |
| `NO_STREAM_EVENTS` | stdin contains no valid non-empty frame events | 1 |

## Notes

This is additive. File-backed workflows remain unchanged, and stdin support is limited to commands that naturally consume frame-event streams.
