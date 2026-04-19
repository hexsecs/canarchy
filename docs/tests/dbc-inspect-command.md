# Test Spec: `dbc inspect` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/dbc-inspect-command.md` |
| Primary test area | CLI, DBC |

## Test Objectives

Validate that `dbc inspect` returns stable structured metadata for database, message, and signal inspection workflows.

## Coverage Requirements

* database summary inspection
* message-filtered inspection
* signal metadata output including units and ranges
* structured error handling for invalid DBC files and unknown messages

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-DBCI-01` | `TEST-DBCI-01`, `TEST-DBCI-02` |
| `REQ-DBCI-02` | `TEST-DBCI-01` |
| `REQ-DBCI-03` | `TEST-DBCI-01`, `TEST-DBCI-02` |
| `REQ-DBCI-04` | `TEST-DBCI-01`, `TEST-DBCI-03` |
| `REQ-DBCI-05` | `TEST-DBCI-02` |
| `REQ-DBCI-06` | `TEST-DBCI-03` |
| `REQ-DBCI-07` | `TEST-DBCI-04` |
| `REQ-DBCI-08` | `TEST-DBCI-05` |

## Representative Test Cases

### `TEST-DBCI-01` — Inspect full database summary

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --json`
Then   the system shall return a database summary with message, signal, and node counts
And    the response shall include message metadata for each message in the fixture
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-02` — Inspect a named message

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --message EngineStatus1 --json`
Then   the system shall return only the `EngineStatus1` message metadata
And    the response shall include its signal definitions
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-03` — Signals-only output

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --signals-only --json`
Then   the system shall emit signal-centric metadata without duplicating the full database structure
And    each signal record shall include units and scaling context where available
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-04` — Invalid DBC file

```gherkin
Given  the file `tests/fixtures/invalid.dbc` contains malformed DBC content
When   the operator runs `canarchy dbc inspect tests/fixtures/invalid.dbc --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_LOAD_FAILED"`
```

**Fixture:** `tests/fixtures/invalid.dbc`.

---

### `TEST-DBCI-05` — Unknown message filter

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --message DoesNotExist --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_MESSAGE_NOT_FOUND"`
```

**Fixture:** `tests/fixtures/sample.dbc`.

## Fixtures And Environment

The command can be tested with the existing `tests/fixtures/sample.dbc` and `tests/fixtures/invalid.dbc` files. Additional multiplexed and choice-heavy fixtures should be added before implementation begins.

## Explicit Non-Coverage

* non-DBC source formats
* future `db convert` and `db compare` workflows
* live decode or encode behavior, which remain covered by separate DBC workflow tests
