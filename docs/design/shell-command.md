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

| ID | Requirement |
|----|-------------|
| `REQ-SHELL-01` | The system shall provide a `canarchy shell` command. |
| `REQ-SHELL-02` | `canarchy shell --command "..."` shall execute the provided command through the shared CLI path. |
| `REQ-SHELL-03` | Interactive shell entry shall reuse the existing parser and exit cleanly on `exit`, `quit`, or EOF. |
| `REQ-SHELL-04` | The shell shall not introduce separate protocol or transport behavior. |

## Command Surface

```text
canarchy shell [--command "<existing canarchy command>"] [--json] [--jsonl] [--table] [--raw]
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
