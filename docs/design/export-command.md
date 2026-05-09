# Design Spec: `export` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy export` |
| Primary area | CLI, artifacts |

## Goal

Preserve structured CANarchy artifacts on disk so operators and coding agents can save event streams and session state for later analysis without scraping text output.

## User-Facing Motivation

Operators need a deterministic way to persist machine-readable results from current workflows while keeping exports aligned with the existing command and event schemas.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-EXPORT-01` | Ubiquitous | The system shall provide a `canarchy export <source> <destination>` command for structured artifact persistence. |
| `REQ-EXPORT-02` | Event-driven | When `export` is invoked with a capture file source, the system shall write a structured event-stream artifact to the destination path. |
| `REQ-EXPORT-03` | Event-driven | When `export` is invoked with a `session:<name>` source, the system shall write a structured session record artifact to the destination path. |
| `REQ-EXPORT-04` | Event-driven | When the destination path ends in `.json`, the system shall write a full command-result envelope preserving event and session structure. |
| `REQ-EXPORT-05` | Event-driven | When the destination path ends in `.jsonl` and the source produces events, the system shall write one serialised event per line with no outer envelope. |
| `REQ-EXPORT-06` | Ubiquitous | The command result shall describe the artifact written using stable metadata fields including `source`, `destination`, `artifact_type`, and `export_format`. |
| `REQ-EXPORT-07` | Unwanted behaviour | If the source is neither a readable capture file nor a valid `session:<name>` reference, the system shall return a structured error with code `EXPORT_SOURCE_UNSUPPORTED` and exit code 1. |
| `REQ-EXPORT-08` | Unwanted behaviour | If the destination suffix is not `.json` or `.jsonl`, the system shall return a structured error with code `EXPORT_FORMAT_UNSUPPORTED` and exit code 1. |
| `REQ-EXPORT-09` | Unwanted behaviour | If `.jsonl` output is requested for a source that produces no events, the system shall return a structured error with code `EXPORT_EVENTS_UNAVAILABLE` and exit code 1. |

## Command Surface

```text
canarchy export <source> <destination> [--json] [--jsonl] [--text]
```

### Supported source forms

| Source form | Meaning |
|-------------|---------|
| `tests/fixtures/sample.candump` | export a structured event-stream artifact from a capture file |
| `session:lab-a` | export a saved session record |

### Supported destination formats

| Suffix | Shape |
|--------|-------|
| `.json` | full structured artifact envelope |
| `.jsonl` | one serialised event per line |

`.jsonl` is only supported for sources that produce `events`.

## Responsibilities And Boundaries

In scope:

* export of capture-file event streams
* export of saved session records
* envelope-preserving `.json` output
* event-only `.jsonl` output for event-capable sources

Out of scope:

* direct export of arbitrary command invocations
* archive formats such as SQLite or msgpack
* multi-artifact bundle generation

## Artifact Model

### Capture file to `.json`

Writes a full command-style envelope:

```json
{
  "ok": true,
  "command": "export",
  "data": {
    "artifact_type": "event_stream",
    "source": {
      "kind": "capture_file",
      "value": "tests/fixtures/sample.candump"
    },
    "events": []
  },
  "warnings": [],
  "errors": []
}
```

### Capture file to `.jsonl`

Writes each serialised event as one JSON line. No outer envelope is written.

### Session to `.json`

Writes a full command-style envelope with a `session` payload and no `events` list.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `EXPORT_SOURCE_UNSUPPORTED` | source is not a capture file or `session:<name>` | 1 |
| `EXPORT_FORMAT_UNSUPPORTED` | destination does not end in `.json` or `.jsonl` | 1 |
| `EXPORT_EVENTS_UNAVAILABLE` | `.jsonl` requested for a source without events | 1 |
| `EXPORT_WRITE_FAILED` | destination file cannot be written | 1 |

## Deferred Decisions

* exporting direct command invocations beyond capture files and saved sessions
* additional artifact formats
* multi-artifact bundle output
