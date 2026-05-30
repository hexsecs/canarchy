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
* optional cantools layout rendering in text, JSON, and JSONL output
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
| `REQ-DBCI-09` | `TEST-DBCI-06`, `TEST-DBCI-07`, `TEST-DBCI-08`, `TEST-DBCI-10` |
| `REQ-DBCI-10` | `TEST-DBCI-06`, `TEST-DBCI-09` |
| `REQ-DBCI-11` | `TEST-DBCI-11` |

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

---

### `TEST-DBCI-06` — Text layout for a named message

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --message EngineStatus1 --layout --text`
Then   the system shall render the bit-layout diagram
And    the system shall render the signal tree
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-07` — JSON layout fields

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --message EngineStatus1 --layout --json`
Then   the first message payload shall include `layout`, `signal_tree`, and `signal_choices`
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-08` — JSONL layout fields

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --message EngineStatus1 --layout --jsonl`
Then   the `dbc_message` event payload shall include `layout` and `signal_tree`
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-09` — Layout combines with search

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/sample.dbc --search speed --layout --json`
Then   the response shall include only the matching message
And    that message shall include layout metadata
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBCI-10` — Choice table rendering

```gherkin
Given  the file `tests/fixtures/complex.dbc` is available
When   the operator runs `canarchy dbc inspect tests/fixtures/complex.dbc --message TransmissionGear --layout --text`
Then   the system shall render choice tables for choice-bearing signals
```

**Fixture:** `tests/fixtures/complex.dbc`.

---

### `TEST-DBCI-11` — MCP layout flag

```gherkin
Given  the MCP server exposes `dbc_inspect`
When   the tool schema is inspected
Then   the `layout` property shall be a boolean with default `false`
```

**Fixture:** none.

## Fixtures And Environment

The command can be tested with the existing `tests/fixtures/sample.dbc`, `tests/fixtures/complex.dbc`, and `tests/fixtures/invalid.dbc` files.

## Explicit Non-Coverage

* non-DBC source formats
* future `db convert` and `db compare` workflows
* live decode or encode behavior, which remain covered by separate DBC workflow tests
