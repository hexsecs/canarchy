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
| `REQ-DBC-07` | `TEST-DBC-07` |
| `REQ-DBC-08` | `TEST-DBC-08`, `TEST-DBC-09`, `TEST-DBC-11` |
| `REQ-DBC-09` | `TEST-DBC-10` |
| `REQ-DBC-10` | `TEST-DBC-11` |

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
When   the operator runs `canarchy decode --file sample.candump --dbc sample.dbc --json`
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
When   the operator runs `canarchy decode --file sample.candump --dbc invalid.dbc --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_LOAD_FAILED"`
```

**Fixture:** `tests/fixtures/invalid.dbc`, `tests/fixtures/sample.candump`.

---

### `TEST-DBC-07` — Invalid signal assignment returns structured encode error

```gherkin
Given  the file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy encode --dbc sample.dbc EngineStatus1 NotASignal=1 --json`
Then   the command shall exit with code `3`
And    `errors[0].code` shall equal `"DBC_SIGNAL_INVALID"`
```

**Fixture:** `tests/fixtures/sample.dbc`.

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

---

### `TEST-DBC-08` — Encode resolves SAE PGN labels and displayed signal names

```gherkin
Given  a J1939 DBC whose message EngineSpeed1 carries PGN 61444 and signal EngineSpeed (SPN 190)
When   `canarchy encode --dbc <dbc> EEC1 "Engine Speed=1200" --json` is invoked
Then   the frame shall encode against EngineSpeed1 with EngineSpeed = 1200
And    `data.resolution.message.via` shall be `pgn_label` and the signal alias recorded
And    warnings shall state both resolutions
```

**Fixture:** `tests/fixtures/j1939_sample.dbc`.

---

### `TEST-DBC-09` — Decode → encode round-trip by displayed names

```gherkin
Given  a frame encoded from EngineSpeed1 with explicit signal values
When   the frame is decoded and the decoded name/value pairs are re-encoded via the PGN label
Then   the re-encoded frame bytes shall equal the original frame bytes
```

**Fixture:** `tests/fixtures/j1939_sample.dbc`.

---

### `TEST-DBC-10` — Encode defaults unsupplied signals and reports them

```gherkin
Given  a message with three signals
When   `encode` is invoked supplying only one signal
Then   the remaining signals shall be defaulted and listed under `data.resolution.filled_signals`
And    a warning shall direct the operator to review the defaults before transmitting
```

**Fixture:** `tests/fixtures/j1939_sample.dbc`.

---

### `TEST-DBC-11` — Name misses suggest close matches; PGN ambiguity is structured

```gherkin
Given  a misspelled message or signal name
When   `encode` is invoked
Then   the `DBC_MESSAGE_NOT_FOUND` / `DBC_SIGNAL_INVALID` hint shall suggest the closest valid names
When   a PGN label matches two messages and the supplied signals cannot break the tie
Then   `DBC_MESSAGE_NOT_FOUND` shall list both candidate DBC message names
```

**Fixture:** `tests/fixtures/j1939_sample.dbc`.
