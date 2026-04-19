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

### `TEST-REPLAY-01` — Replay plan preserves frame count

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   a replay plan is built from the capture at rate `1.0`
Then   the plan frame count, event count, and duration shall match the input capture
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-02` — Replay rate scales timing

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   a replay plan is built from the capture at rate `0.5`
Then   event timestamps shall be scaled relative to the slower replay rate
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-03` — Replay CLI returns structured output

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy replay sample.candump --rate 2.0 --json`
Then   the result shall include active mode, frame count, duration, and replay events
And    the result shall keep `warnings` empty for the replay plan output
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-04` — Invalid rate returns structured error

```gherkin
Given  a valid capture file is available
When   the operator runs `canarchy replay sample.candump --rate 0 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_RATE"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-05` — Missing source returns transport error

```gherkin
Given  the file `missing.candump` does not exist
When   the operator runs `canarchy replay missing.candump --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"CAPTURE_SOURCE_UNAVAILABLE"`
```

**Fixture:** none (missing file path).

---

## Fixtures And Environment

* `tests/fixtures/sample.candump`

## Explicit Non-Coverage

* live replay scheduling against hardware
* replay looping or advanced pacing controls

## Traceability

This spec maps to the implemented replay-plan and replay CLI behaviors covered in `test_replay.py` and `test_cli.py`.
