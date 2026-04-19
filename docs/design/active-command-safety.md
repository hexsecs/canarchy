# Design Spec: Active Command Safety

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy send`, `generate`, `gateway`, `uds scan` |
| Primary area | CLI, safety |
| Related specs | `docs/design/transport-core-commands.md`, `docs/design/generate-command.md`, `docs/design/uds-transaction-workflows.md` |

## Goal

Provide a shared safety layer for active transmit commands so operators receive a visible preflight warning before frames are sent and can optionally require both an explicit flag and a positive confirmation before transmission begins.

## User-Facing Motivation

Operators and automation need active workflows to remain scriptable, but active transmission should still be clearly distinguished from passive workflows before any bus traffic is emitted.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-ACTIVE-SAFE-01` | Ubiquitous | The system shall treat `send`, `generate`, `gateway`, and `uds scan` as active transmit commands for preflight safety checks. |
| `REQ-ACTIVE-SAFE-02` | Event-driven | When an active transmit command is invoked and validation succeeds, the system shall emit a preflight warning to `stderr` before transport transmission begins. |
| `REQ-ACTIVE-SAFE-03` | Optional feature | Where `--ack-active` is supplied, the system shall require a confirmation response of `YES` before an active transmit command proceeds. |
| `REQ-ACTIVE-SAFE-04` | Optional feature | Where `[safety].require_active_ack` or `CANARCHY_REQUIRE_ACTIVE_ACK` is enabled, the system shall require `--ack-active` before an active transmit command proceeds. |
| `REQ-ACTIVE-SAFE-05` | Unwanted behaviour | If active acknowledgement is required but `--ack-active` is not supplied, the system shall return a structured error with code `ACTIVE_ACK_REQUIRED` and exit code `1` before transport transmission begins. |
| `REQ-ACTIVE-SAFE-06` | Unwanted behaviour | If `--ack-active` is supplied but the confirmation response is not `YES`, the system shall return a structured error with code `ACTIVE_CONFIRMATION_DECLINED` and exit code `1` before transport transmission begins. |
| `REQ-ACTIVE-SAFE-07` | Ubiquitous | The system shall keep machine-readable `stdout` output free of duplicated safety warnings when the preflight warning has already been emitted on `stderr`. |
| `REQ-ACTIVE-SAFE-08` | Optional feature | Where `config show` is invoked, the system shall report the effective `require_active_ack` value and its configuration source. |

## Command Surface

```text
canarchy send <interface> <frame-id> <hex-data> [--ack-active] [--json] [--jsonl] [--table] [--raw]
canarchy generate <interface> [--id <hex|R>] [--dlc <0-8|R>] [--data <hex|R|I>]
                           [--count <n>] [--gap <ms>] [--extended] [--ack-active]
                           [--json] [--jsonl] [--table] [--raw]
canarchy gateway <src> <dst> [--src-backend <name>] [--dst-backend <name>]
                            [--bidirectional] [--count <n>] [--ack-active]
                            [--json] [--jsonl] [--table] [--raw]
canarchy uds scan <interface> [--ack-active] [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* preflight `stderr` safety warnings for active transmit commands
* config-backed acknowledgement enforcement
* explicit per-invocation confirmation via `--ack-active`
* structured early failure before any transport send occurs

Out of scope:

* passive workflows such as `capture` or `uds trace`
* commands that prepare frames without transmitting them, such as `encode`

## Data Model

The command result envelope remains unchanged for successful active commands except that duplicated safety warnings are not required in the top-level `warnings` list.

Relevant shared fields include:

* `mode`
* `events`
* `errors[].code`
* `require_active_ack`
* `sources.require_active_ack`

## Output Contracts

### Preflight warning

The preflight warning is emitted to `stderr` after argument validation succeeds and before any transport send or forward operation begins.

### Confirmation prompt

When `--ack-active` is supplied, the command emits a confirmation prompt to `stderr` and requires the operator to reply `YES` on `stdin` before transmission begins.

### JSON and JSONL

Structured `stdout` output remains machine-readable and shall not rely on duplicated top-level warning strings for active-command safety prompts.

### Table and raw

Human-readable `stdout` remains reserved for the requested output mode; the preflight warning still appears on `stderr`.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `ACTIVE_ACK_REQUIRED` | active acknowledgement is required but `--ack-active` was omitted | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | `--ack-active` was supplied but the confirmation response was not `YES` | 1 |

## Deferred Decisions

* whether future fuzz commands should join the active transmit safety gate once implemented
