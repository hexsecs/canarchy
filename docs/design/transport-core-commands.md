# Design Spec: Transport Core Commands

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy capture`, `send`, `filter`, `stats` |
| Primary area | CLI, transport |

## Goal

Provide the foundational transport-facing CAN workflows for passive observation, active transmit, file-backed filtering, and capture summary statistics.

## User-Facing Motivation

Operators need a stable base command set that supports passive live observation, intentional active transmit, and deterministic file-backed analysis without leaving the CLI.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-TRANSPORT-01` | Ubiquitous | The system shall provide `capture`, `send`, `filter`, and `stats` commands as the foundational transport command set. |
| `REQ-TRANSPORT-02` | Event-driven | When `capture <interface>` is invoked, the system shall stream frame events through the live capture path for all output formats. |
| `REQ-TRANSPORT-03` | Event-driven | When `send <interface> <frame-id> <data>` is invoked, the system shall transmit the specified frame and emit an active-transmit warning distinct from passive workflows. |
| `REQ-TRANSPORT-04` | Event-driven | When `filter <file> <expression>` is invoked, the system shall return only the frame events from the capture file that satisfy the expression. |
| `REQ-TRANSPORT-05` | Event-driven | When `stats <file>` is invoked, the system shall return a deterministic summary including total frame count and unique arbitration ID count. |
| `REQ-TRANSPORT-06` | Event-driven | When `capture` or `send` is invoked, the system shall expose the effective transport backend name and configuration metadata in the result. |
| `REQ-TRANSPORT-07` | Unwanted behaviour | If a transport interface is unavailable or a backend open fails, the system shall return a structured error with code `TRANSPORT_UNAVAILABLE` and exit code 2. |
| `REQ-TRANSPORT-08` | Unwanted behaviour | If a capture file cannot be parsed, the system shall return a structured error with code `CAPTURE_SOURCE_INVALID` and exit code 2. |
| `REQ-TRANSPORT-09` | Unwanted behaviour | If a capture file format is unsupported, the system shall return a structured error with code `CAPTURE_FORMAT_UNSUPPORTED` and exit code 2. |
| `REQ-TRANSPORT-10` | Unwanted behaviour | If `filter` receives an unsupported expression, the system shall return a structured error with code `FILTER_EXPRESSION_UNSUPPORTED` and exit code 2. |

## Command Surface

```text
canarchy capture <interface> [--candump] [--json] [--jsonl] [--table] [--raw]
canarchy send <interface> <frame-id> <hex-data> [--json] [--jsonl] [--table] [--raw]
canarchy filter <file> <expression> [--json] [--jsonl] [--table] [--raw]
canarchy stats <file> [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* passive capture through selected backend resolution
* intentional active transmit through `send`
* file-backed filtering by simple expressions
* file-backed capture summary statistics

Out of scope:

* deep live capture subscriptions beyond the current streaming backend path
* arbitrary expression language expansion beyond the supported filter syntax
* transport-specific vendor tooling or hardware setup guidance

## Data Model

Transport-facing commands return serialised frame events and transport metadata. File-backed analysis returns frame events or summary fields derived from parsed candump inputs.

Relevant shared fields include:

* `mode`
* `interface` or `file`
* `transport_backend`
* `python_can_interface` when applicable
* `status`
* `implementation`

Current backend note:

* the effective backend defaults to `python-can`
* the deterministic scaffold backend remains available for offline tests, CI, and demos

## Output Contracts

### JSON

Live `capture` emits one serialised event per line, matching JSONL semantics. Other transport commands return the standard CANarchy command envelope with events or summary fields under `data`.

### JSONL

Event-producing commands emit one event per line. Event-less success and error paths emit a single result object line.

### Table and raw

`capture` uses candump-style rendering for table, raw, and `--candump`. Other commands use the standard table or raw command-result paths.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `TRANSPORT_UNAVAILABLE` | interface or backend open/send fails | 2 |
| `FILTER_EXPRESSION_UNSUPPORTED` | `filter` receives an unsupported expression | 2 |
| `CAPTURE_SOURCE_INVALID` | capture file cannot be parsed | 2 |
| `CAPTURE_FORMAT_UNSUPPORTED` | file format is unsupported | 2 |

## Deferred Decisions

* broader live transport adapter coverage
* richer filter language support
* higher-order transport statistics and analysis helpers
