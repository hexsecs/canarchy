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

### `TEST-SESSION-01` — Session round trip

```gherkin
Given  a temporary working directory with an isolated `.canarchy/` store
And    the files `tests/fixtures/sample.candump` and `tests/fixtures/sample.dbc` are available
When   the operator saves a named session with interface, DBC, and capture context
And    then loads the saved session
And    then runs `canarchy session show --json`
Then   the saved context shall be preserved
And    `session show` shall report both the active and saved session entries
```

**Fixture:** `tests/fixtures/sample.candump`, `tests/fixtures/sample.dbc`, temporary session directory.

---

### `TEST-SESSION-02` — Missing session error

```gherkin
Given  no session named `missing` exists in the session store
When   the operator runs `canarchy session load missing --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"SESSION_NOT_FOUND"`
```

**Fixture:** temporary session directory (empty).

---

## Fixtures And Environment

* temporary working directories for isolated `.canarchy/` session storage
* `tests/fixtures/sample.candump`
* `tests/fixtures/sample.dbc`

## Explicit Non-Coverage

* concurrent session access
* session deletion lifecycle

## Traceability

This spec maps to the implemented session persistence behavior currently covered in `test_cli.py`.
