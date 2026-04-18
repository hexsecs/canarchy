# Design Spec: `export` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy export` |
| Primary area | CLI, artifacts |

## Goal

Preserve structured CANarchy artifacts on disk so operators and coding agents can save event streams and session state for later analysis without scraping table output.

## User-Facing Motivation

Operators need a deterministic way to persist machine-readable results from current workflows while keeping exports aligned with the existing command and event schemas.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-EXPORT-01` | The system shall provide a `canarchy export <source> <destination>` command. |
| `REQ-EXPORT-02` | The command shall support capture-file sources and saved-session sources. |
| `REQ-EXPORT-03` | The command shall support `.json` artifact output that preserves the command-style envelope. |
| `REQ-EXPORT-04` | The command shall support `.jsonl` output for event-capable sources. |
| `REQ-EXPORT-05` | The command shall return structured errors for unsupported sources, unsupported destination formats, and unsupported `.jsonl` requests. |
| `REQ-EXPORT-06` | The command result shall describe the artifact written using stable metadata fields. |

## Command Surface

```text
canarchy export <source> <destination>
                 [--json] [--jsonl] [--table] [--raw]
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
| `.jsonl` | one serialized event per line |

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

Writes each serialized event as one JSON line. No outer envelope is written.

### Session to `.json`

Writes a full command-style envelope with a `session` payload and no `events` list.

## Command Result Contract

The `export` command itself returns a standard CANarchy result describing the write operation.

Returned fields include:

* `source`
* `destination`
* `source_kind`
* `artifact_type`
* `export_format`
* `exported_events`

## Output Contracts

### JSON and JSONL

The command result uses the existing CANarchy envelope shape. The written artifact depends on the destination suffix.

### Table and raw

Table and raw remain command-result views and do not change the artifact shape written to disk.

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
