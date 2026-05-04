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

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-COMP-01` | Optional feature | Where `--stdin` is specified, `decode`, `filter`, and `j1939 decode` shall read JSONL frame events from stdin instead of a `--file` capture source. |
| `REQ-COMP-02` | Unwanted behaviour | If `--stdin` is specified alongside a `--file` capture source, the system shall return a structured error with code `STDIN_AND_FILE_SPECIFIED` and exit code 1. |
| `REQ-COMP-03` | Unwanted behaviour | If neither `--stdin` nor a capture file is provided for a command that requires one, the system shall return a structured error with code `MISSING_INPUT` and exit code 1. |
| `REQ-COMP-04` | Event-driven | When `--stdin` is in use, the system shall validate each non-empty line as a canonical frame event before command-specific processing begins. |
| `REQ-COMP-05` | Unwanted behaviour | If a stdin line is malformed JSON, is not a frame event, or does not decode into a valid frame, the system shall return a structured error with code `INVALID_STREAM_EVENT` and exit code 1. |
| `REQ-COMP-06` | Unwanted behaviour | If stdin contains no valid non-empty frame events, the system shall return a structured error with code `NO_STREAM_EVENTS` and exit code 1. |
| `REQ-COMP-07` | Ubiquitous | When `--stdin` is used, JSONL output shall preserve the existing event-stream contract of the consuming command. |

## Command Surface

```text
canarchy decode --dbc <file> --stdin [--json|--jsonl|--table|--raw]
canarchy filter <expression> --stdin [--json|--jsonl|--table|--raw]
canarchy j1939 decode --stdin [--json|--jsonl|--table|--raw]
```

Representative usage:

```bash
canarchy capture can0 --jsonl | canarchy filter 'id==0x18FEEE31' --stdin --jsonl
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
| `STDIN_AND_FILE_SPECIFIED` | `--stdin` is used with a `--file` capture source | 1 |
| `MISSING_INPUT` | neither `--stdin` nor a capture file is provided | 1 |
| `INVALID_STREAM_EVENT` | stdin line is malformed JSON, not a frame event, or does not decode into a valid frame | 1 |
| `NO_STREAM_EVENTS` | stdin contains no valid non-empty frame events | 1 |

## Notes

This is additive. File-backed workflows remain unchanged, and stdin support is limited to commands that naturally consume frame-event streams.
