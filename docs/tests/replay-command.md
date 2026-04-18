# Test Spec: `replay` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/replay-command.md` |
| Primary test area | CLI, replay |

## Test Objectives

Validate deterministic replay-plan behavior, CLI result structure, and structured validation/transport errors.

## Coverage Requirements

* replay plan preserves frame count and duration
* replay rate scales relative timing
* replay CLI returns structured JSON output
* invalid rate and missing source errors are surfaced

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-REPLAY-01` | `TEST-REPLAY-03` |
| `REQ-REPLAY-02` | `TEST-REPLAY-01`, `TEST-REPLAY-03` |
| `REQ-REPLAY-03` | `TEST-REPLAY-02` |
| `REQ-REPLAY-04` | `TEST-REPLAY-03` |
| `REQ-REPLAY-05` | `TEST-REPLAY-04`, `TEST-REPLAY-05` |

## Representative Test Cases

### `TEST-REPLAY-01` Replay plan preserves frame count

Action: build a replay plan from the sample capture at rate `1.0`.  
Assert: frame count, event count, and duration match the input capture.

### `TEST-REPLAY-02` Replay rate scales timing

Action: build a replay plan from the sample capture at rate `0.5`.  
Assert: event timestamps scale relative to the slower replay rate.

### `TEST-REPLAY-03` Replay CLI returns structured output

Action: run `canarchy replay sample.candump --rate 2.0 --json`.  
Assert: output includes active mode, frame count, duration, replay events, and the active warning.

### `TEST-REPLAY-04` Invalid rate returns structured error

Action: run `replay` with `--rate 0`.  
Assert: exit code `1` and `errors[0].code == "INVALID_RATE"`.

### `TEST-REPLAY-05` Missing source returns transport error

Action: run `replay` against a missing file.  
Assert: exit code `2` and `errors[0].code == "CAPTURE_SOURCE_UNAVAILABLE"`.

## Fixtures And Environment

* `tests/fixtures/sample.candump`

## Explicit Non-Coverage

* live replay scheduling against hardware
* replay looping or advanced pacing controls

## Traceability

This spec maps to the implemented replay-plan and replay CLI behaviors covered in `test_replay.py` and `test_cli.py`.
