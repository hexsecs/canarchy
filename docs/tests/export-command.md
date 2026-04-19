# Test Spec: `export` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/export-command.md` |
| Primary test area | CLI, artifacts |

## Test Objectives

Validate that `export` writes the supported artifact shapes, preserves event and session structures, and returns deterministic structured errors for unsupported inputs.

## Coverage Requirements

* capture file export to `.json`
* capture file export to `.jsonl`
* saved session export to `.json`
* `.jsonl` rejection for sources without events
* unsupported source error
* unsupported destination format error

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-EXPORT-01` | `TEST-EXPORT-01`, `TEST-EXPORT-02`, `TEST-EXPORT-03` |
| `REQ-EXPORT-02` | `TEST-EXPORT-01`, `TEST-EXPORT-03` |
| `REQ-EXPORT-03` | `TEST-EXPORT-01`, `TEST-EXPORT-03` |
| `REQ-EXPORT-04` | `TEST-EXPORT-02` |
| `REQ-EXPORT-05` | `TEST-EXPORT-04`, `TEST-EXPORT-05`, `TEST-EXPORT-06` |
| `REQ-EXPORT-06` | `TEST-EXPORT-01`, `TEST-EXPORT-03` |

## Representative Test Cases

### `TEST-EXPORT-01` — Capture file to JSON

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy export sample.candump artifact.json --json`
Then   the destination file shall exist
And    it shall contain a structured result envelope
And    the envelope shall include serialized frame events
```

**Fixture:** `tests/fixtures/sample.candump`, temporary output directory.

---

### `TEST-EXPORT-02` — Capture file to JSONL

```gherkin
Given  the file `tests/fixtures/sample.candump` is available
When   the operator runs `canarchy export sample.candump artifact.jsonl --json`
Then   the destination file shall contain one serialized event per line
```

**Fixture:** `tests/fixtures/sample.candump`, temporary output directory.

---

### `TEST-EXPORT-03` — Saved session to JSON

```gherkin
Given  a session named `lab-a` has been saved to the session store
When   the operator runs `canarchy export session:lab-a artifact.json --json`
Then   the destination file shall contain a structured envelope with a session payload
```

**Fixture:** temporary session store under `.canarchy/`, temporary output directory.

---

### `TEST-EXPORT-04` — Session to JSONL rejected

```gherkin
Given  a session named `lab-a` has been saved to the session store
When   the operator runs `canarchy export session:lab-a artifact.jsonl --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"EXPORT_EVENTS_UNAVAILABLE"`
```

**Fixture:** temporary session store under `.canarchy/`.

---

### `TEST-EXPORT-05` — Unsupported source rejected

```gherkin
Given  no capture file or session named `unknown-source` exists
When   the operator runs `canarchy export unknown-source artifact.json --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"EXPORT_SOURCE_UNSUPPORTED"`
```

**Fixture:** none required.

---

### `TEST-EXPORT-06` — Unsupported destination suffix rejected

```gherkin
Given  a valid exportable source is available
When   the operator runs `canarchy export sample.candump artifact.txt --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"EXPORT_FORMAT_UNSUPPORTED"`
```

**Fixture:** `tests/fixtures/sample.candump`.

---

## Fixtures And Environment

* existing candump fixture files
* temporary directories for exported artifacts
* temporary session store content under `.canarchy/`

## Explicit Non-Coverage

* unwritable filesystem locations, which are environment-dependent
* future non-file sinks or archive formats

## Traceability

This spec maps to the export acceptance criteria around structured artifacts, schema consistency, and representative success and failure paths.
