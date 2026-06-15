# Test Spec: AFL-style mutators — `havoc` / `splice` / `interesting`

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/fuzz-afl-mutators.md` |
| Test file | `tests/test_fuzz.py`, `tests/test_fuzz_cli.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-AFL-02` | determinism for a fixed seed | `TEST-AFL-01`, `TEST-AFL-05`, `TEST-AFL-08` |
| `REQ-AFL-03` | havoc stacks operators and mutates input | `TEST-AFL-02` |
| `REQ-AFL-04` | splice joins corpus prefix/suffix | `TEST-AFL-04` |
| `REQ-AFL-05` | empty corpus raises | `TEST-AFL-06` |
| `REQ-AFL-06` | interesting enumerates known values, deduped | `TEST-AFL-07` |
| `REQ-AFL-07` | payloads clamped to 64 bytes | `TEST-AFL-03`, `TEST-AFL-09` |
| `REQ-AFL-08` | CLI strategies emit frames | `TEST-AFL-10`, `TEST-AFL-11`, `TEST-AFL-13` |
| `REQ-AFL-09` | splice without corpus errors | `TEST-AFL-12` |
| `REQ-AFL-10` | 29-bit id inferred extended; out-of-range id errors | `TEST-AFL-14`, `TEST-AFL-15` |

## Test Cases

### TEST-AFL-02 — havoc stacks operators and mutates the input

```gherkin
Given  a 4-byte baseline payload
When   havoc_payload runs with count 32
Then   the variants shall not all be identical
And    nearly every variant shall differ from the baseline
```

**Fixture:** none.

### TEST-AFL-04 — splice joins corpus prefix and suffix

```gherkin
Given  a corpus of an all-0xAA payload and an all-0xBB payload
When   splice_payload runs with count 10
Then   every emitted byte shall be either 0xAA or 0xBB
```

**Fixture:** none.

### TEST-AFL-06 — empty corpus raises

```gherkin
Given  an empty corpus
When   splice_payload is iterated
Then   the system shall raise ValueError
```

**Fixture:** none.

### TEST-AFL-07 — interesting enumerates known values and dedupes

```gherkin
Given  dlc 4
When   interesting_values_payload is enumerated
Then   the output shall include 0xFF / 0x7F / 0x80 / 0x00 at byte 0 and 256 (LE) at word 0
And    contain no duplicate payloads
```

**Fixture:** none.

### TEST-AFL-12 — CLI splice without corpus errors

```gherkin
Given  no --corpus argument
When   the operator runs `canarchy fuzz payload --strategy splice --dry-run`
Then   the system shall return an error with code "MISSING_INPUT"
```

**Fixture:** none.

### TEST-AFL-13 — CLI splice with a candump corpus emits frames

```gherkin
Given  tests/fixtures/complex.candump as the corpus
When   the operator runs `canarchy fuzz payload --strategy splice --corpus … --max 6 --dry-run`
Then   the system shall emit 6 frame events
```

**Fixture:** `tests/fixtures/complex.candump`.

---

### TEST-AFL-14 — 29-bit `--id` without `--extended` is inferred extended

```gherkin
Given  `fuzz payload --id 0x18DAF110` without `--extended`
When   the operator runs the command with `--dry-run`
Then   the system shall emit frames with `is_extended_id` true and the given arbitration id
```

**Fixture:** none.

---

### TEST-AFL-15 — `--id` outside the 29-bit range returns a structured error

```gherkin
Given  `fuzz payload --id 0xFFFFFFFF`
When   the operator runs the command with `--dry-run`
Then   the system shall exit non-zero with error code `INVALID_FRAME_ID`
```

**Fixture:** none.

## Fixtures And Environment

Engine tests are fixture-free; the CLI splice test uses
`tests/fixtures/complex.candump`. No live bus.

## Explicit Non-Coverage

* Big-endian interesting-value / arithmetic writes.
* Live transmission against real hardware.
