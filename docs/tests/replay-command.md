# Test Spec: `replay` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented with live transmit |
| Related design spec | `docs/design/replay-command.md` |
| Primary test area | CLI, replay |

## Test Objectives

Validate deterministic replay-plan behavior, CLI result structure, live frame transmission, active-transmit safety gating, and structured validation/transport errors.

## Coverage Requirements

* replay plan preserves frame count and duration
* replay rate scales relative timing
* replay CLI returns structured JSON output
* invalid rate and missing source errors are surfaced
* live transmit to interface sends frames and returns interface metadata
* live transmit requires `--ack-active` when safety config demands it
* dry-run with interface returns plan and warning without sending frames
* planning mode (no interface) unchanged from prior behavior

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-REPLAY-01` | `TEST-REPLAY-03` |
| `REQ-REPLAY-02` | `TEST-REPLAY-01`, `TEST-REPLAY-03` |
| `REQ-REPLAY-03` | `TEST-REPLAY-02` |
| `REQ-REPLAY-04` | `TEST-REPLAY-03` |
| `REQ-REPLAY-05` | `TEST-REPLAY-04`, `TEST-REPLAY-05` |
| `REQ-REPLAY-07` | `TEST-REPLAY-06`, `TEST-REPLAY-07` |
| `REQ-REPLAY-08` | `TEST-REPLAY-08` |
| `REQ-REPLAY-09` | `TEST-REPLAY-06` |
| `REQ-REPLAY-10` | `TEST-REPLAY-07` |

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
When   the operator runs `canarchy replay --file sample.candump --rate 2.0 --json`
Then   the result shall include active mode, frame count, duration, and replay events
And    the result shall keep `warnings` empty for the replay plan output
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-04` — Invalid rate returns structured error

```gherkin
Given  a valid capture file is available
When   the operator runs `canarchy replay --file sample.candump --rate 0 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_RATE"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-05` — Missing source returns transport error

```gherkin
Given  the file `missing.candump` does not exist
When   the operator runs `canarchy replay --file missing.candump --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"CAPTURE_SOURCE_UNAVAILABLE"`
```

**Fixture:** none (missing file path).

---

### `TEST-REPLAY-06` — Live transmit requires `--ack-active` when config demands it

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
And    `[safety].require_active_ack` is `true`
When   the operator runs `canarchy replay --file sample.candump --interface vcan0 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"ACTIVE_ACK_REQUIRED"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-07` — Live transmit sends frames and returns metadata

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy replay --file sample.candump --interface vcan0 --ack-active --json`
And    answers the confirmation prompt with `YES`
Then   the result shall include `mode = "active"`, `interface = "vcan0"`, and `frame_count = 3`
And    the events shall be replay events
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-08` — Dry-run with interface returns plan and warning

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy replay --file sample.candump --interface vcan0 --dry-run --json`
Then   the result shall include `mode = "dry_run"` and `interface = "vcan0"`
And    `warnings` shall contain `"ACTIVE_TRANSMIT_DRY_RUN"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-REPLAY-09` — Planning mode without interface is unchanged

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy replay --file sample.candump --json`
Then   the result shall include `mode = "active"` and `frame_count = 3`
And    `interface` shall not be in the result data
```

**Fixture:** `tests/fixtures/sample.candump`.

---

## Fixtures And Environment

* `tests/fixtures/sample.candump`

## Explicit Non-Coverage

* replay looping or advanced pacing controls

## Traceability

This spec maps to the implemented replay-plan and replay CLI behaviors covered in `test_replay.py` and `test_cli.py`.
