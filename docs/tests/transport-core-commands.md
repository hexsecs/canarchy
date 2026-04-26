# Test Spec: Transport Core Commands

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Related design spec | `docs/design/transport-core-commands.md` |
| Primary test area | CLI, transport |

## Test Objectives

Validate the shipped passive, active, and file-backed transport workflows, including default `python-can` and deterministic scaffold behavior plus structured error handling.

## Coverage Requirements

* capture streaming output across JSON, JSONL, and candump-style formats
* send active mode, preflight warning, and acknowledgement behavior
* default `python-can` and scaffold capture streaming paths
* filter matching behavior
* stats summary behavior
* capture metadata reconnaissance behavior
* structured transport/file errors

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-TRANSPORT-01` | `TEST-TRANSPORT-01`, `TEST-TRANSPORT-02`, `TEST-TRANSPORT-05`, `TEST-TRANSPORT-06`, `TEST-TRANSPORT-13` |
| `REQ-TRANSPORT-02` | `TEST-TRANSPORT-01`, `TEST-TRANSPORT-03`, `TEST-TRANSPORT-04`, `TEST-TRANSPORT-08`, `TEST-TRANSPORT-09` |
| `REQ-TRANSPORT-03` | `TEST-TRANSPORT-02` |
| `REQ-TRANSPORT-04` | `TEST-TRANSPORT-05` |
| `REQ-TRANSPORT-05` | `TEST-TRANSPORT-06` |
| `REQ-TRANSPORT-06` | Deferred |
| `REQ-TRANSPORT-07` | `TEST-TRANSPORT-07` |
| `REQ-TRANSPORT-08` | `TEST-TRANSPORT-11` |
| `REQ-TRANSPORT-09` | `TEST-TRANSPORT-12` |
| `REQ-TRANSPORT-10` | `TEST-TRANSPORT-10` |
| `REQ-TRANSPORT-11` | `TEST-TRANSPORT-13`, `TEST-TRANSPORT-14` |
| `REQ-TRANSPORT-12` | `TEST-TRANSPORT-15`, `TEST-TRANSPORT-16` |

## Representative Test Cases

### `TEST-TRANSPORT-01` — Capture scaffold JSON streaming output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy capture can0 --json`
Then   the system shall emit at least one JSON-parseable line
And    each emitted object shall have `event_type` equal to `"frame"`
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-TRANSPORT-02` — Send active JSON output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy send can0 0x123 11223344 --json`
Then   the result envelope shall indicate active mode
And    the envelope shall include serialized frame events
And    the preflight warning shall be emitted on `stderr`
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-TRANSPORT-03` — Candump-style scaffold streaming

```gherkin
Given  the scaffold transport backend is active and `python-can` is not enabled
When   the operator runs `canarchy capture can0 --candump`
Then   the system shall emit fixture frames as candump-style text lines
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-TRANSPORT-04` — Capture JSONL uses live backend when requested

```gherkin
Given  the `python-can` open path is patched with a mock bus
When   the operator runs `canarchy capture can0 --jsonl` against the live backend
Then   the system shall emit one serialized frame event per output line
```

**Fixture:** mocked `python-can` bus.

---

### `TEST-TRANSPORT-05` — Filter returns matching frames

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy filter id==0x18FEEE31 --file tests/fixtures/sample.candump --json`
Then   the result shall contain exactly one frame event matching arbitration ID `0x18FEEE31`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-TRANSPORT-06` — Stats returns summary

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy stats --file tests/fixtures/sample.candump --json`
Then   the result shall include deterministic summary fields
And    the summary shall include a total frame count and an arbitration-ID count
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-TRANSPORT-07` — Transport unavailable error

```gherkin
Given  the interface `offline0` is not available
When   the operator runs `canarchy capture offline0 --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"TRANSPORT_UNAVAILABLE"`
```

**Fixture:** none (unavailable interface name).

---

### `TEST-TRANSPORT-08` — Candump live text rendering

```gherkin
Given  the `python-can` bus is patched with sample frames
When   the operator runs `canarchy capture can0 --candump`
Then   the system shall emit candump-style text lines for each frame
```

**Fixture:** mocked `python-can` bus with sample frames.

---

### `TEST-TRANSPORT-09` — Candump FD/RTR/error formatting

```gherkin
Given  the `python-can` bus is patched with FD, RTR, and error frame types
When   the operator runs `canarchy capture can0 --candump`
Then   the system shall render each special frame type correctly in candump format
```

**Fixture:** mocked `python-can` bus with FD, RTR, and error frames.

---

### `TEST-TRANSPORT-10` — Filter expression error

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy filter unsupported_expr --file tests/fixtures/sample.candump --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"INVALID_FILTER_EXPRESSION"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-TRANSPORT-11` — Invalid capture file error

```gherkin
Given  the file `tests/fixtures/invalid.candump` contains unparseable content
When   the operator runs `canarchy stats --file tests/fixtures/invalid.candump --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"CAPTURE_SOURCE_INVALID"`
```

**Fixture:** `tests/fixtures/invalid.candump`.

---

### `TEST-TRANSPORT-12` — Unsupported capture format error

```gherkin
Given  a file with an unsupported extension is present
When   the operator runs `canarchy stats --file file.xyz --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"CAPTURE_FORMAT_UNSUPPORTED"`
```

**Fixture:** file with an unsupported format suffix.

---

### `TEST-TRANSPORT-13` — Capture-info returns fast capture metadata

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy capture-info --file tests/fixtures/sample.candump --json`
Then   the result shall include `frame_count`, `first_timestamp`, `last_timestamp`, `duration_seconds`, `unique_ids`, and `interfaces`
And    the result shall include suggested `max_frames` and `seconds` bounds for follow-on analysis
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-TRANSPORT-14` — Capture-info reports invalid capture files consistently

```gherkin
Given  the file `tests/fixtures/invalid.candump` contains no valid candump frames
When   the operator runs `canarchy capture-info --file tests/fixtures/invalid.candump --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"CAPTURE_SOURCE_INVALID"`
```

**Fixture:** `tests/fixtures/invalid.candump`.

---

### `TEST-TRANSPORT-15` — Capture-info uses full scan for small files and sets scan_mode=full

```gherkin
Given  a small capture file (under 50 MB)
When   the operator runs `canarchy capture-info --file <small-file> --json`
Then   `data.scan_mode` shall equal `"full"`
And    `data.frame_count` shall be the exact frame count
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-TRANSPORT-16` — Capture-info uses estimated scan for large files and sets scan_mode=estimated

```gherkin
Given  a capture file larger than 50 MB (or threshold patched to 1 byte in test)
When   the operator runs `canarchy capture-info --file <large-file> --json`
Then   `data.scan_mode` shall equal `"estimated"`
And    `data.first_timestamp` and `data.last_timestamp` shall be parseable from head/tail bytes
```

**Fixture:** `tests/fixtures/sample.candump` with threshold patched.

---

## Fixtures And Environment

* `tests/fixtures/sample.candump`
* `tests/fixtures/invalid.candump`
* mocked `python-can` buses for live-path coverage
* scaffold backend fixture frames for deterministic transport coverage

## Explicit Non-Coverage

* physical adapter integration
* advanced filter expression features beyond the shipped expression subset

## Traceability

This spec maps to the implemented transport command behaviors currently exercised through CLI and transport tests.
