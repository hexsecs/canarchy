# Design Spec: Session Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy session save`, `load`, `show` |
| Primary area | CLI, session |

## Goal

Provide lightweight stateful session persistence so operators can save, restore, and inspect working context across CLI workflows.

## User-Facing Motivation

Operators often reuse the same interface, DBC, and capture context across commands. Session workflows reduce repetition while keeping the effective state explicit and inspectable.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SESSION-01` | Ubiquitous | The system shall provide `session save`, `session load`, and `session show` commands for named session persistence. |
| `REQ-SESSION-02` | Event-driven | When `session save <name>` is invoked, the system shall persist a named session record with the supplied interface, DBC, and capture context. |
| `REQ-SESSION-03` | Event-driven | When `session load <name>` is invoked, the system shall restore the named session and update the active session state. |
| `REQ-SESSION-04` | Event-driven | When `session show` is invoked, the system shall return the current active session and the list of all saved sessions. |
| `REQ-SESSION-05` | Unwanted behaviour | If `session load` is invoked with a name that does not exist, the system shall return a structured error with code `SESSION_NOT_FOUND` and exit code 1. |
| `REQ-SESSION-06` | Unwanted behaviour | If a session name contains a path separator or is `.` or `..`, the system shall return a structured error with code `INVALID_SESSION_NAME` and exit code 1. |

## Command Surface

```text
canarchy session save <name> [--interface <name>] [--dbc <file>] [--capture <file>] [--json] [--jsonl] [--table] [--raw]
canarchy session load <name> [--json] [--jsonl] [--table] [--raw]
canarchy session show [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* named session record persistence
* explicit restore/show behavior through the CLI

Out of scope:

* multi-user session coordination
* hidden session mutation outside the explicit command surface

## Data Model

Session commands return stateful payloads with a `session`, `sessions`, or `active_session` structure derived from the session store.

## Output Contracts

`--json` returns the standard CANarchy result envelope. Because current session commands do not emit event streams, `--jsonl` also returns a single result object line.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `SESSION_NOT_FOUND` | requested session does not exist | 1 |
| `INVALID_SESSION_NAME` | session name contains path separators or is `.` / `..` | 1 |

## Deferred Decisions

* session deletion and lifecycle management commands
* richer session metadata beyond the current context payload
