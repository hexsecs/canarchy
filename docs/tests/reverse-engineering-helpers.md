# Test Spec: Reverse-Engineering Helpers

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Related design spec | `docs/design/reverse-engineering-helpers.md` |
| Primary test area | CLI, analysis |

## Test Objectives

Define the expected coverage for the reverse-engineering helper family so shipped and future implementation work remains traceable to the command contracts and heuristic-output expectations.

## Coverage Requirements

* command-level success coverage for `re signals`, `re counters`, `re entropy`, and `re correlate`
* passive file-backed analysis behavior
* structured candidate output with rationale and confidence or score fields
* representative edge cases for sparse captures, low-sample captures, and mixed arbitration IDs
* structured error handling for missing captures and unsupported correlation references
* human-readable ranked table output for each command

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-RE-01` | `TEST-RE-01`, `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04` |
| `REQ-RE-02` | `TEST-RE-01`, `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04` |
| `REQ-RE-03` | `TEST-RE-01` |
| `REQ-RE-04` | `TEST-RE-02` |
| `REQ-RE-05` | `TEST-RE-03` |
| `REQ-RE-06` | `TEST-RE-04`, `TEST-RE-08` |
| `REQ-RE-07` | `TEST-RE-01`, `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04` |
| `REQ-RE-08` | `TEST-RE-05`, `TEST-RE-06` |
| `REQ-RE-09` | `TEST-RE-04`, `TEST-RE-08` |
| `REQ-RE-10` | `TEST-RE-07`, `TEST-RE-08`, `TEST-RE-09` |

## Representative Test Cases

### `TEST-RE-01` — Signal candidate analysis

```gherkin
Given  a capture fixture with varying byte fields is available
When   the operator runs `canarchy re signals <fixture> --json`
Then   the result shall indicate passive mode
And    the result shall include ranked signal candidates
And    each candidate shall include a confidence or score field and a rationale
```

**Fixture:** capture file with signal-like byte variation.

---

### `TEST-RE-02` — Counter candidate analysis

```gherkin
Given  a capture fixture containing monotonically incrementing nibble or byte fields is available
When   the operator runs `canarchy re counters <fixture> --json`
Then   the result shall include candidate fields
And    each candidate shall include monotonicity evidence and rollover detection metadata
```

**Fixture:** capture file with nibble and byte counter fields.

---

### `TEST-RE-03` — Entropy ranking analysis

```gherkin
Given  a capture fixture with mixed-entropy arbitration IDs and fields is available
When   the operator runs `canarchy re entropy <fixture> --json`
Then   the result shall rank arbitration IDs or fields by entropy-related values
And    each entry shall include a sample count
```

**Fixture:** capture file with mixed-entropy fields.

---

### `TEST-RE-04` — Correlation analysis

```gherkin
Given  a capture fixture and a reference series file are available
And    the reference file conforms to the documented schema with timestamp and value fields
When   the operator runs `canarchy re correlate <fixture> --reference <reference> --json`
Then   the result shall include ranked correlation candidates
And    each candidate shall include a correlation strength value and rationale
```

**Fixture:** capture file, `.json` or `.jsonl` reference series file.

---

### `TEST-RE-05` — Table output summaries

```gherkin
Given  a valid capture fixture is available
When   the operator runs any `re` command with `--table`
Then   the output shall present a compact ranked summary
And    score or confidence data shall be visible in the table
```

**Fixture:** capture file appropriate to the command.

---

### `TEST-RE-06` — JSONL behavior

```gherkin
Given  a valid capture fixture is available
When   the operator runs any `re` command with `--jsonl`
Then   the output shall match the documented JSONL contract selected by the implementation
```

**Fixture:** capture file appropriate to the command.

---

### `TEST-RE-07` — Missing capture error

```gherkin
Given  the specified capture file does not exist
When   the operator runs any `re` command against the missing file
Then   the command shall exit with code `2`
And    the error shall be a structured capture-source error
```

**Fixture:** none (missing file path).

---

### `TEST-RE-08` — Missing or unsupported reference input

```gherkin
Given  no `--reference` argument is provided
When   the operator runs `canarchy re correlate <fixture>`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"RE_REFERENCE_REQUIRED"`

Given  a reference file exists but does not contain timestamped numeric samples
When   the operator runs `re correlate` with that reference file
Then   `errors[0].code` shall equal `"RE_REFERENCE_INVALID"`
```

**Fixture:** none for missing-reference case; malformed reference file for schema-invalid case.

---

### `TEST-RE-09` — Low-sample or sparse capture behavior

```gherkin
Given  a capture fixture with very few frames or low field variance is available
When   the operator runs any `re` command against the sparse capture
Then   the command shall not exit with an error
And    the result shall return empty or low-confidence candidates
And    no candidates shall be presented as authoritative facts
```

**Fixture:** small or low-variance candump fixture.

---

## Fixture Requirements

Planned fixtures should include:

* captures with stable counters
* captures with mixed-entropy fields
* captures with likely analog-like signals
* captures plus `.json` and `.jsonl` reference-series fixtures for correlation
* malformed and low-sample fixtures

Current implementation note:

* `re counters` is covered with fixtures for nibble counters, rollover counters, non-counter noise, and low-sample captures

## Explicit Non-Coverage

* OEM-specific semantics
* active probing/fuzzing during reverse-engineering analysis
* live backend reverse-engineering workflows in the first version

## Traceability

This spec defines the coverage target for the planned reverse-engineering helper implementation and should be refined as concrete candidate schemas and fixtures are chosen.
