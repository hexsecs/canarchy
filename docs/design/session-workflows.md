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

| ID | Requirement |
|----|-------------|
| `REQ-SESSION-01` | The system shall provide `session save`, `session load`, and `session show` commands. |
| `REQ-SESSION-02` | `session save` shall persist a named session record with the current CLI context. |
| `REQ-SESSION-03` | `session load` shall restore a previously saved named session. |
| `REQ-SESSION-04` | `session show` shall present active-session and saved-session state. |
| `REQ-SESSION-05` | Loading a missing session shall return a structured user error. |

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

## Deferred Decisions

* session deletion and lifecycle management commands
* richer session metadata beyond the current context payload
