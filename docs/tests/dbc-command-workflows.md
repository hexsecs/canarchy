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

### `TEST-DBC-01` — Load valid DBC fixture

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the DBC loader reads the fixture directly
Then   a known frame name shall resolve correctly from the loaded schema
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBC-02` — Decode frames returns semantic events

```gherkin
Given  the files `tests/fixtures/sample.candump` and `tests/fixtures/sample.dbc` are available
When   the decode library processes the capture frames with the DBC schema
Then   decoded-message events shall be returned for all known messages in the capture
```

**Fixture:** `tests/fixtures/sample.candump`, `tests/fixtures/sample.dbc`.

---

### `TEST-DBC-03` — Encode message returns frame

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the encode library encodes a named message with signal assignments
Then   the result shall include a frame and associated frame events
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBC-04` — Decode CLI returns structured output

```gherkin
Given  the files `tests/fixtures/sample.candump` and `tests/fixtures/sample.dbc` are available
When   the operator runs `canarchy decode sample.candump --dbc sample.dbc --json`
Then   the result shall include a matched message count
And    the result shall include decoded-message events for known messages
```

**Fixture:** `tests/fixtures/sample.candump`, `tests/fixtures/sample.dbc`.

---

### `TEST-DBC-05` — Encode CLI returns structured frame

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy encode --dbc sample.dbc EngineStatus1 ... --json`
Then   the result shall include the encoded frame
And    the result shall include associated frame events
```

**Fixture:** `tests/fixtures/sample.dbc`.

---

### `TEST-DBC-06` — Invalid DBC returns decode error

```gherkin
Given  the file `tests/fixtures/invalid.dbc` contains malformed DBC content
When   the operator runs `canarchy decode sample.candump --dbc invalid.dbc --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_LOAD_FAILED"`
```

**Fixture:** `tests/fixtures/invalid.dbc`, `tests/fixtures/sample.candump`.

---

## Fixtures And Environment

* `tests/fixtures/sample.dbc`
* `tests/fixtures/invalid.dbc`
* `tests/fixtures/sample.candump`

## Explicit Non-Coverage

* advanced DBC merge workflows
* live transmit of encoded frames

## Traceability

This spec maps to the implemented DBC library and CLI behaviors currently covered in `test_dbc.py`.
