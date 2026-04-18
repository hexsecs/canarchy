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

| ID | Requirement |
|----|-------------|
| `REQ-TRANSPORT-01` | The system shall provide a `capture` command for passive transport observation. |
| `REQ-TRANSPORT-02` | The system shall provide a `send` command for intentional active transmit. |
| `REQ-TRANSPORT-03` | The system shall provide `filter` and `stats` commands for file-backed capture analysis. |
| `REQ-TRANSPORT-04` | `capture` and `send` shall use the deterministic scaffold backend by default and expose live backend metadata when `python-can` is selected. |
| `REQ-TRANSPORT-05` | `capture` shall stream frames through the live capture path for every output format. |
| `REQ-TRANSPORT-06` | `send` shall emit an active-transmit warning distinct from passive workflows. |
| `REQ-TRANSPORT-07` | `filter` shall emit matching frame events from file-backed captures. |
| `REQ-TRANSPORT-08` | `stats` shall return deterministic file-backed summary fields such as total frame count and unique arbitration ID count. |
| `REQ-TRANSPORT-09` | Transport and file-parse failures shall return structured transport errors. |

## Command Surface

```text
canarchy capture <interface> [--candump] [--json] [--jsonl] [--table] [--raw]
canarchy send <interface> <frame-id> <hex-data> [--json] [--jsonl] [--table] [--raw]
canarchy filter <file> <expression> [--json] [--jsonl] [--table] [--raw]
canarchy stats <file> [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* passive capture through scaffold or live backend selection
* intentional active transmit through `send`
* file-backed filtering by simple expressions
* file-backed capture summary statistics

Out of scope:

* deep live capture subscriptions beyond the current streaming backend path
* arbitrary expression language expansion beyond the supported filter syntax
* transport-specific vendor tooling or hardware setup guidance

## Data Model

Transport-facing commands return serialized frame events and transport metadata. File-backed analysis returns frame events or summary fields derived from parsed candump inputs.

Relevant shared fields include:

* `mode`
* `interface` or `file`
* `transport_backend`
* `python_can_interface` when applicable
* `status`
* `implementation`

## Output Contracts

### JSON

Live `capture` emits one serialized event per line, matching JSONL semantics. Other transport commands return the standard CANarchy command envelope with events or summary fields under `data`.

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
