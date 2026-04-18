# Test Spec: Session Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/session-workflows.md` |
| Primary test area | CLI, session |

## Test Objectives

Validate session round-trip persistence and structured missing-session error handling.

## Coverage Requirements

* save/load/show round trip with representative context
* missing-session error handling

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-SESSION-01` | `TEST-SESSION-01`, `TEST-SESSION-02` |
| `REQ-SESSION-02` | `TEST-SESSION-01` |
| `REQ-SESSION-03` | `TEST-SESSION-01` |
| `REQ-SESSION-04` | `TEST-SESSION-01` |
| `REQ-SESSION-05` | `TEST-SESSION-02` |

## Representative Test Cases

### `TEST-SESSION-01` Session round trip

Action: save a named session with interface, DBC, and capture context, then load it and show session state.  
Assert: saved context is preserved and `session show` reports the active and saved session entries.

### `TEST-SESSION-02` Missing session error

Action: run `session load missing --json`.  
Assert: exit code `1` and `errors[0].code == "SESSION_NOT_FOUND"`.

## Fixtures And Environment

* temporary working directories for isolated `.canarchy/` session storage
* `tests/fixtures/sample.candump`
* `tests/fixtures/sample.dbc`

## Explicit Non-Coverage

* concurrent session access
* session deletion lifecycle

## Traceability

This spec maps to the implemented session persistence behavior currently covered in `test_cli.py`.
