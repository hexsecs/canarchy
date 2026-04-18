# Test Spec: DBC Command Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/dbc-command-workflows.md` |
| Primary test area | CLI, DBC |

## Test Objectives

Validate the shipped DBC-backed decode and encode workflows, including both library-level and CLI-level behavior.

## Coverage Requirements

* loading a valid DBC fixture
* decode events from captured frames
* encode frame creation from named message/signals
* CLI decode and encode JSON behavior
* invalid DBC handling

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-DBC-01` | `TEST-DBC-02`, `TEST-DBC-04` |
| `REQ-DBC-02` | `TEST-DBC-03`, `TEST-DBC-05` |
| `REQ-DBC-03` | `TEST-DBC-02`, `TEST-DBC-04` |
| `REQ-DBC-04` | `TEST-DBC-03`, `TEST-DBC-05` |
| `REQ-DBC-05` | `TEST-DBC-06` |

## Representative Test Cases

### `TEST-DBC-01` Load valid DBC fixture

Action: load the sample DBC fixture directly.  
Assert: a known frame name resolves correctly.

### `TEST-DBC-02` Decode frames returns semantic events

Action: decode sample capture frames with the sample DBC.  
Assert: decoded-message events are returned for known messages.

### `TEST-DBC-03` Encode message returns frame

Action: encode a named message with signal assignments.  
Assert: a frame and frame events are returned.

### `TEST-DBC-04` Decode CLI returns structured output

Action: run `canarchy decode sample.candump --dbc sample.dbc --json`.  
Assert: output includes matched message count and decoded-message events.

### `TEST-DBC-05` Encode CLI returns structured frame

Action: run `canarchy encode --dbc sample.dbc EngineStatus1 ... --json`.  
Assert: output includes the encoded frame and frame events.

### `TEST-DBC-06` Invalid DBC returns decode error

Action: run `decode` against an invalid DBC file.  
Assert: exit code `3` and `errors[0].code == "DBC_LOAD_FAILED"`.

## Fixtures And Environment

* `tests/fixtures/sample.dbc`
* `tests/fixtures/invalid.dbc`
* `tests/fixtures/sample.candump`

## Explicit Non-Coverage

* advanced DBC merge workflows
* live transmit of encoded frames

## Traceability

This spec maps to the implemented DBC library and CLI behaviors currently covered in `test_dbc.py`.
