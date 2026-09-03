# Full-Screen TUI Design Specification

## Document Control

| Field | Value |
|---|---|
| Status | Implemented |
| Command surface | `canarchy tui` |
| Related architecture | `docs/architecture.md` |
| Related test spec | `docs/tests/tui-shell.md` |

## Goal

Provide a full-screen Textual dashboard that reuses the canonical command engine while safely presenting live CAN traffic. Live capture must remain responsive during idle buses, preserve every buffered event until it is consumed or explicitly reported as dropped, and expose enough telemetry for operators to assess capture health.

## Scope

This specification covers TUI launch, shared command execution, live capture lifecycle, pause behavior, queue telemetry, and error presentation. Protocol enrichment and pane-specific decoding are separate follow-up work.

## Requirements

| ID | Type | Requirement |
|---|---|---|
| REQ-TUI-01 | State-driven | While standard input or output is not attached to a TTY, the system shall reject `canarchy tui` with the structured `TUI_REQUIRES_TTY` error. |
| REQ-TUI-02 | Ubiquitous | The system shall present status, traffic, decoded, J1939, UDS, alerts, and command-input surfaces in the full-screen TUI. |
| REQ-TUI-03 | Event-driven | When an operator submits a command, the system shall execute it through the same command engine used by the CLI. |
| REQ-TUI-04 | Unwanted behaviour | If an operator submits a nested `shell` or `tui` command, the system shall reject it without starting another interactive front end. |
| REQ-TUI-05 | Event-driven | When an operator starts live capture, the system shall run transport ingestion outside the Textual event loop and continue accepting UI input. |
| REQ-TUI-06 | Event-driven | When a capture stop is requested, the system shall signal the transport receive loop, poll an idle `python-can` bus at intervals no greater than 100 ms, close the bus, and report whether the worker stopped within the 250 ms join budget. |
| REQ-TUI-07 | Unwanted behaviour | If a capture worker does not stop within the join budget, the system shall retain the session, emit `CAPTURE_STOP_TIMEOUT`, and prevent a replacement worker from starting. |
| REQ-TUI-08 | Event-driven | When a capture source ends naturally or after a requested stop, the system shall retain the session until all buffered events and worker errors have been consumed. |
| REQ-TUI-09 | State-driven | While presentation is paused, the system shall continue capture ingestion and retain buffered events after producer completion until presentation resumes. |
| REQ-TUI-10 | Ubiquitous | The system shall expose immutable capture snapshots containing received, drained, dropped, current queue-depth, and high-water-mark counts. |
| REQ-TUI-11 | Event-driven | When the bounded capture queue overflows, the system shall evict the oldest buffered event, increment the dropped count, and surface the loss in both alerts and status telemetry. |
| REQ-TUI-12 | Event-driven | When buffered events are drained, the system shall update shared TUI state and render the applicable traffic and protocol panes without bypassing the command or protocol layers. |

## Command Surface

```text
canarchy tui
```

Inside the TUI, `/capture [interface]`, `/stop`, `/clear`, `/filter`, and `/help` control presentation and capture; the spacebar pauses or resumes presentation. Other commands are delegated to the canonical command executor.

## Data Model

`CaptureSession` owns one daemon worker, a bounded event queue, an error queue, and stop/finished events. Its `CaptureStats` snapshot contains:

```text
received: int
drained: int
dropped: int
queue_depth: int
high_water_mark: int
```

The producer never blocks on a full queue. It discards the oldest event and records that loss before adding the newest event. The Textual timer drains bounded batches but does not release a completed session until the queue is empty.

## Output

Capture health is rendered in the status pane using stable operator-facing labels:

```text
capture: received=1000 drained=1000 queued=0 dropped=0 high-water=1000
```

Dropped-event alerts include the newly observed loss and cumulative count. TUI output remains presentation-only and does not alter CLI JSON schemas.

## Errors

| Code | Condition | Operator action |
|---|---|---|
| `TUI_REQUIRES_TTY` | TUI launched without an interactive terminal | Run from an interactive terminal. |
| `CAPTURE_STOP_TIMEOUT` | Capture worker remains alive after the stop join budget | Wait for backend shutdown and inspect the configured adapter before retrying. |
| `CAPTURE_FAILED` | Unexpected capture worker failure | Check transport configuration and retry. |
| Transport error code | Backend raises a structured transport error | Follow the backend-provided hint. |

## Deferred Work

* Live DBC signal decoding and explicit decode-database selection.
* Protocol-aware J1939 and UDS transaction routing from live frames.
* Capture-rate visualizations beyond bounded queue counters.
