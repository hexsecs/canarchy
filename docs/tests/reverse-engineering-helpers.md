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

* command-level success coverage for shipped helpers: `re counters`, `re entropy`, `re match-dbc`, and `re shortlist-dbc`
* passive file-backed analysis behavior
* structured candidate output with rationale and confidence or score fields
* representative edge cases for sparse captures, low-sample captures, and mixed arbitration IDs
* warning and limit behavior for provider-backed DBC matching workflows
* structured error handling for missing captures and, when correlation is implemented, unsupported reference inputs
* human-readable ranked table output for each shipped helper

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-RE-01` | `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04`, `TEST-RE-05` |
| `REQ-RE-02` | `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04`, `TEST-RE-05` |
| `REQ-RE-03` | Deferred |
| `REQ-RE-04` | `TEST-RE-02` |
| `REQ-RE-05` | `TEST-RE-03` |
| `REQ-RE-06` | Deferred |
| `REQ-RE-07` | `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04`, `TEST-RE-05` |
| `REQ-RE-08` | `TEST-RE-06`, `TEST-RE-07` |
| `REQ-RE-09` | Deferred |
| `REQ-RE-10` | Deferred |
| `REQ-RE-11` | `TEST-RE-04`, `TEST-RE-05`, `TEST-RE-08`, `TEST-RE-09` |
| `REQ-RE-12` | `TEST-RE-05` |

## Representative Test Cases

### `TEST-RE-01` — Deferred signal candidate analysis

```gherkin
Given  `re signals` remains unimplemented
When   the operator reviews the current shipped reverse-engineering helper coverage
Then   signal candidate analysis shall be tracked as deferred work rather than represented as implemented coverage
```

**Fixture:** none.

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

### `TEST-RE-04` — DBC match analysis

```gherkin
Given  a capture fixture and a provider-backed DBC catalog are available
When   the operator runs `canarchy re match-dbc <fixture> --json`
Then   the result shall include ranked DBC candidates
And    each candidate shall include `name`, `source_ref`, `score`, `matched_ids`, and `total_capture_ids`
```

**Fixture:** capture file and mocked or cached provider catalog.

---

### `TEST-RE-05` — DBC shortlist analysis

```gherkin
Given  a valid capture fixture and provider catalog are available
When   the operator runs `canarchy re shortlist-dbc <fixture> --make <brand> --json`
Then   the result shall include shortlist candidates filtered by make
And    the response data shall record the selected `make`
```

**Fixture:** capture file and mocked or cached provider catalog.

---

### `TEST-RE-06` — Table output summaries for shipped helpers

```gherkin
Given  a valid capture fixture is available
When   the operator runs a shipped `re` helper with `--table`
Then   the output shall present a compact ranked summary
And    score or confidence data shall be visible in the table
```

**Fixture:** capture file appropriate to the shipped helper.

---

### `TEST-RE-07` — JSONL behavior for shipped helpers

```gherkin
Given  a valid capture fixture is available
When   the operator runs a shipped `re` helper with `--jsonl`
Then   the output shall match the documented JSONL contract selected by the implementation
```

**Fixture:** capture file appropriate to the shipped helper.

---

### `TEST-RE-08` — Missing capture error

```gherkin
Given  the specified capture file does not exist
When   the operator runs any `re` command against the missing file
Then   the command shall exit with code `2`
And    the error shall be a structured capture-source error
```

**Fixture:** none (missing file path).

---

### `TEST-RE-09` — Empty-catalog warning behavior for DBC matching

```gherkin
Given  no provider-catalog candidates are available for DBC matching
When   the operator runs `canarchy re match-dbc <fixture> --json`
Then   the command shall still succeed
And    the result shall contain a warning explaining that no candidates were available
```

**Fixture:** capture file and an empty mocked catalog.

---

### `TEST-RE-10` — Match limit behavior

```gherkin
Given  more candidate DBCs are available than the requested limit
When   the operator runs `canarchy re match-dbc <fixture> --limit <n> --json`
Then   no more than `<n>` candidates shall be returned
```

**Fixture:** capture file and mocked catalog larger than the requested limit.

---

### `TEST-RE-11` — Low-sample or sparse capture behavior

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

Fixtures should include:

* captures with stable counters
* captures with mixed-entropy fields
* captures sufficient for DBC-candidate ranking against mocked or cached provider catalogs
* malformed and low-sample fixtures

Current implementation note:

* `re counters` is covered with fixtures for nibble counters, rollover counters, non-counter noise, and low-sample captures
* `re entropy` is covered with fixtures for constant, alternating, high-entropy, and low-sample arbitration IDs
* `re match-dbc` and `re shortlist-dbc` are covered with mocked provider catalogs for output shape, warnings, and limit handling

## Explicit Non-Coverage

* OEM-specific semantics
* active probing/fuzzing during reverse-engineering analysis
* live backend reverse-engineering workflows in the first version

## Traceability

This spec defines the coverage target for the current shipped reverse-engineering helpers and the deferred helpers that remain to be implemented.
