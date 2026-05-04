# Test Spec: Composition

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/composition.md` |
| Primary test area | CLI, event stream composition |

## Test Objectives

Validate that commands supporting `--stdin` correctly compose in pipelines, reject conflicting input specifications, and enforce the canonical frame-event stream contract.

## Coverage Requirements

* `decode`, `filter`, and `j1939 decode` read JSONL frame events from stdin when `--stdin` is specified
* `--stdin` combined with a positional file returns a structured error
* missing input source returns a structured error
* malformed stdin lines return a structured error
* empty stdin (no valid frame events) returns a structured error
* output contract is preserved in `--stdin` mode

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-COMP-01` | `TEST-COMP-01`, `TEST-COMP-02`, `TEST-COMP-03` |
| `REQ-COMP-02` | `TEST-COMP-04` |
| `REQ-COMP-03` | `TEST-COMP-05` |
| `REQ-COMP-04` | `TEST-COMP-01`, `TEST-COMP-06` |
| `REQ-COMP-05` | `TEST-COMP-06` |
| `REQ-COMP-06` | `TEST-COMP-07` |
| `REQ-COMP-07` | `TEST-COMP-01`, `TEST-COMP-02`, `TEST-COMP-03` |

## Representative Test Cases

### `TEST-COMP-01` — Filter via stdin returns matching frame

```gherkin
Given  a canonical JSONL frame event line is provided on stdin
And    the frame has arbitration ID `0x18FEEE31`
When   the operator runs `canarchy filter --stdin id==0x18FEEE31 --json`
Then   the result shall contain exactly one frame event
And    the event arbitration ID shall equal `0x18FEEE31`
```

**Fixture:** single-frame JSONL string injected as stdin.

---

### `TEST-COMP-02` — Decode via stdin returns decoded message events

```gherkin
Given  one or more canonical JSONL frame event lines are provided on stdin
And    the DBC file `tests/fixtures/sample.dbc` is available
When   the operator runs `canarchy decode --stdin --dbc sample.dbc --json`
Then   the result shall include decoded-message events for known messages in the stream
```

**Fixture:** JSONL frame events from sample capture on stdin, `tests/fixtures/sample.dbc`.

---

### `TEST-COMP-03` — J1939 decode via stdin returns PGN events

```gherkin
Given  canonical JSONL frame events containing J1939 frames are provided on stdin
When   the operator runs `canarchy j1939 decode --stdin --json`
Then   the result shall include J1939 decoded-message events with PGN and source address fields
```

**Fixture:** JSONL J1939 frame events on stdin.

---

### `TEST-COMP-04` — `--stdin` combined with a capture file returns an error

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy filter --stdin id==0x123 --file tests/fixtures/sample.candump --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"STDIN_AND_FILE_SPECIFIED"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-COMP-05` — Missing input returns an error

```gherkin
Given  neither `--stdin` nor a capture file is provided
When   the operator runs `canarchy filter id==0x123 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"MISSING_INPUT"`
```

**Fixture:** none required.

---

### `TEST-COMP-06` — Malformed stdin line returns an error

```gherkin
Given  a non-JSON or non-frame-event line is provided on stdin
When   the operator runs `canarchy filter --stdin id==0x123 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_STREAM_EVENT"`
```

**Fixture:** malformed JSON string or alert-type event injected as stdin.

---

### `TEST-COMP-07` — Empty stdin returns an error

```gherkin
Given  stdin contains only blank lines or is empty
When   the operator runs `canarchy filter --stdin id==0x123 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"NO_STREAM_EVENTS"`
```

**Fixture:** empty or whitespace-only stdin.

---

## Fixtures And Environment

* `tests/fixtures/sample.candump` for conflict-detection tests
* `tests/fixtures/sample.dbc` for decode pipeline tests
* synthetic JSONL frame event strings injected as stdin for positive-path tests

## Explicit Non-Coverage

* multi-process pipe performance
* stdin usage for commands that do not support `--stdin` (send, capture, gateway, etc.)

## Traceability

This spec maps to the composition requirements around pipeline-friendly `--stdin` behavior for frame-consuming commands.
