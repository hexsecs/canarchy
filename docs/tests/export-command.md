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

### `TEST-EXPORT-01` Capture file to JSON

Setup: use a representative candump fixture.  
Action: run `canarchy export sample.candump artifact.json --json`.  
Assert: the destination file exists, contains a structured envelope, and includes serialized frame events.

### `TEST-EXPORT-02` Capture file to JSONL

Setup: use a representative candump fixture.  
Action: run `canarchy export sample.candump artifact.jsonl --json`.  
Assert: the destination file contains one serialized event per line.

### `TEST-EXPORT-03` Saved session to JSON

Setup: save a session first.  
Action: run `canarchy export session:lab-a artifact.json --json`.  
Assert: the destination file contains a structured envelope with a session payload.

### `TEST-EXPORT-04` Session to JSONL rejected

Setup: save a session first.  
Action: run `canarchy export session:lab-a artifact.jsonl --json`.  
Assert: exit code `1` and `errors[0].code == "EXPORT_EVENTS_UNAVAILABLE"`.

### `TEST-EXPORT-05` Unsupported source rejected

Setup: no matching capture file or session source.  
Action: run `canarchy export unknown-source artifact.json --json`.  
Assert: exit code `1` and `errors[0].code == "EXPORT_SOURCE_UNSUPPORTED"`.

### `TEST-EXPORT-06` Unsupported destination suffix rejected

Setup: valid exportable source.  
Action: run `canarchy export sample.candump artifact.txt --json`.  
Assert: exit code `1` and `errors[0].code == "EXPORT_FORMAT_UNSUPPORTED"`.

## Fixtures And Environment

* existing candump fixture files
* temporary directories for exported artifacts
* temporary session store content under `.canarchy/`

## Explicit Non-Coverage

* unwritable filesystem locations, which are environment-dependent
* future non-file sinks or archive formats

## Traceability

This spec maps to the export acceptance criteria around structured artifacts, schema consistency, and representative success and failure paths.
