# Design Spec: `shell` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy shell` |
| Primary area | Front end |

## Goal

Provide a minimal interactive shell and one-shot command-entry front end that reuses the existing CLI parser and command execution path.

## User-Facing Motivation

Operators sometimes want to run several CANarchy commands from a persistent prompt without introducing a second parser or shell-only command language.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SHELL-01` | Ubiquitous | The system shall provide a `canarchy shell` command that starts an interactive prompt reusing the existing CLI parser. |
| `REQ-SHELL-02` | Event-driven | When `canarchy shell --command "<cmd>"` is invoked, the system shall execute the provided command through the shared CLI path and exit. |
| `REQ-SHELL-03` | Event-driven | When the interactive shell receives `exit`, `quit`, or EOF, the system shall terminate cleanly with exit code 0. |
| `REQ-SHELL-04` | Ubiquitous | The shell shall not introduce transport, protocol, or session behavior separate from the shared command layer. |

## Command Surface

```text
canarchy shell [--command "<existing canarchy command>"] [--json] [--jsonl] [--text] [--raw]
```

## Responsibilities And Boundaries

In scope:

* one-shot parser reuse through `--command`
* minimal interactive prompt loop

Out of scope:

* shell-local state beyond repeated command entry
* alternate command grammar

## Output Contracts

The shell delegates output behavior to the shared CLI command path for executed commands.

## Error Contracts

The shell relies on the standard CLI error contract for the delegated command being run.

## Deferred Decisions

* richer shell context management
* history and completion support
