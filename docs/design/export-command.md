# Design Spec: `export` Command

## Goal

Preserve structured CANarchy artifacts on disk so operators and coding agents can save event streams and session state for later analysis without scraping table output.

## First supported sources

The initial implementation supports two explicit source kinds:

* capture files using `.candump` or `.log` paths
* saved sessions using the `session:<name>` source form

This keeps the first export shape narrow and deterministic while covering the current file-backed workflows and session persistence model.

## Command surface

```text
canarchy export <source> <destination>
                 [--json] [--jsonl] [--table] [--raw]
```

### Source forms

| Source form | Meaning |
|-------------|---------|
| `tests/fixtures/sample.candump` | export a structured event stream artifact from a capture file |
| `session:lab-a` | export a saved session record |

### Destination formats

| Suffix | Shape |
|--------|-------|
| `.json` | full structured artifact envelope |
| `.jsonl` | one serialized event per line |

`.jsonl` is only supported for sources that produce `events`.

## Artifact shapes

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

The `events` array uses the same serialized event schema already emitted by CLI JSON output.

### Capture file to `.jsonl`

Writes each serialized event as one JSON line. No outer envelope is written.

### Session to `.json`

Writes a full command-style envelope with a `session` payload and no `events` list.

## CLI result shape

The `export` command itself returns a normal CANarchy command result describing what was written:

* `source`
* `destination`
* `source_kind`
* `artifact_type`
* `export_format`
* `exported_events`

## Error cases

| Code | Trigger | Exit code |
|------|---------|-----------|
| `EXPORT_SOURCE_UNSUPPORTED` | source is not a capture file or `session:<name>` | 1 |
| `EXPORT_FORMAT_UNSUPPORTED` | destination does not end in `.json` or `.jsonl` | 1 |
| `EXPORT_EVENTS_UNAVAILABLE` | `.jsonl` requested for a source without events | 1 |
| `EXPORT_WRITE_FAILED` | destination file cannot be written | 1 |

## Deferred

* exporting direct command invocations beyond capture-file and session sources
* archive formats such as SQLite or msgpack
* multi-artifact bundle output
