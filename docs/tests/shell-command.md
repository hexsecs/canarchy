# Test Spec: `shell` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/shell-command.md` |
| Primary test area | Front end |

## Test Objectives

Validate the one-shot shared-parser behavior of `shell` and document the current limits of interactive-loop coverage.

## Coverage Requirements

* one-shot shell command execution reuses the shared parser

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-SHELL-01` | `TEST-SHELL-01` |
| `REQ-SHELL-02` | `TEST-SHELL-01` |
| `REQ-SHELL-03` | `TEST-SHELL-01` |
| `REQ-SHELL-04` | `TEST-SHELL-01` |

## Representative Test Cases

### `TEST-SHELL-01` One-shot shell command reuse

Action: run `canarchy shell --command "capture can0 --raw"`.  
Assert: the delegated command executes through the shared CLI path and returns the expected raw output.

## Fixtures And Environment

No dedicated fixtures are required beyond the deterministic scaffold command surface.

## Explicit Non-Coverage

* interactive prompt-loop behavior beyond the one-shot `--command` path
* shell history or completion features, which are not implemented

## Traceability

This spec maps to the currently implemented shell behavior covered in `test_cli.py`.
