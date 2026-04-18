# Test Spec: Transport Core Commands

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/transport-core-commands.md` |
| Primary test area | CLI, transport |

## Test Objectives

Validate the shipped passive, active, and file-backed transport workflows, including scaffold/live backend behavior and structured error handling.

## Coverage Requirements

* capture JSON structure on scaffold backend
* send active mode and warning behavior
* candump live-backend requirement and live JSON/candump paths
* filter matching behavior
* stats summary behavior
* structured transport/file errors

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-TRANSPORT-01` | `TEST-TRANSPORT-01`, `TEST-TRANSPORT-03`, `TEST-TRANSPORT-04` |
| `REQ-TRANSPORT-02` | `TEST-TRANSPORT-02` |
| `REQ-TRANSPORT-03` | `TEST-TRANSPORT-05`, `TEST-TRANSPORT-06` |
| `REQ-TRANSPORT-04` | `TEST-TRANSPORT-01`, `TEST-TRANSPORT-04` |
| `REQ-TRANSPORT-05` | `TEST-TRANSPORT-03`, `TEST-TRANSPORT-08`, `TEST-TRANSPORT-09` |
| `REQ-TRANSPORT-06` | `TEST-TRANSPORT-02` |
| `REQ-TRANSPORT-07` | `TEST-TRANSPORT-05` |
| `REQ-TRANSPORT-08` | `TEST-TRANSPORT-06` |
| `REQ-TRANSPORT-09` | `TEST-TRANSPORT-03`, `TEST-TRANSPORT-07`, `TEST-TRANSPORT-10`, `TEST-TRANSPORT-11`, `TEST-TRANSPORT-12` |

## Representative Test Cases

### `TEST-TRANSPORT-01` Capture scaffold JSON output

Action: run `canarchy capture can0 --json`.  
Assert: output includes passive mode, scaffold backend metadata, and serialized frame events.

### `TEST-TRANSPORT-02` Send active JSON output

Action: run `canarchy send can0 0x123 11223344 --json`.  
Assert: output includes active mode, scaffold metadata, serialized events, and the active-transmit warning.

### `TEST-TRANSPORT-03` Candump requires live backend

Action: run `canarchy capture can0 --candump --json` without enabling `python-can`.  
Assert: exit code `2` and `errors[0].code == "CANDUMP_LIVE_BACKEND_REQUIRED"`.

### `TEST-TRANSPORT-04` Capture uses live backend when requested

Setup: patch the `python-can` open path.  
Action: run `capture` against the live backend.  
Assert: output reflects `python-can` metadata and emitted frame events.

### `TEST-TRANSPORT-05` Filter returns matching frames

Action: run `canarchy filter sample.candump id==0x18FEEE31 --json`.  
Assert: one matching frame event is returned.

### `TEST-TRANSPORT-06` Stats returns summary

Action: run `canarchy stats sample.candump --json`.  
Assert: output includes deterministic summary fields including frame and arbitration-ID counts.

### `TEST-TRANSPORT-07` Transport unavailable error

Action: run `capture` against an unavailable interface.  
Assert: exit code `2` and `errors[0].code == "TRANSPORT_UNAVAILABLE"`.

### `TEST-TRANSPORT-08` Candump live text rendering

Setup: patch a live backend bus with sample frames.  
Action: run `capture --candump`.  
Assert: output uses candump-style text lines.

### `TEST-TRANSPORT-09` Candump FD/RTR/error formatting

Setup: patch a live backend bus with FD, RTR, and error frames.  
Action: run `capture --candump`.  
Assert: output renders the special frame forms correctly.

### `TEST-TRANSPORT-10` Filter expression error

Action: run `filter` with an unsupported expression.  
Assert: exit code `2` and `errors[0].code == "FILTER_EXPRESSION_UNSUPPORTED"`.

### `TEST-TRANSPORT-11` Invalid capture file error

Action: run `stats` against an invalid candump fixture.  
Assert: exit code `2` and `errors[0].code == "CAPTURE_SOURCE_INVALID"`.

### `TEST-TRANSPORT-12` Unsupported capture format error

Action: run `stats` against an unsupported file type.  
Assert: exit code `2` and `errors[0].code == "CAPTURE_FORMAT_UNSUPPORTED"`.

## Fixtures And Environment

* `tests/fixtures/sample.candump`
* `tests/fixtures/invalid.candump`
* mocked `python-can` buses for live-path coverage

## Explicit Non-Coverage

* physical adapter integration
* advanced filter expression features beyond the shipped expression subset

## Traceability

This spec maps to the implemented transport command behaviors currently exercised through CLI and transport tests.
