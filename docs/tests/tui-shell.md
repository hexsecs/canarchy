# Test Spec: Initial TUI Shell

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/tui-shell.md` |
| Primary test area | Front end |

## Test Objectives

Validate that the initial TUI shell starts correctly, reuses the shared command path, surfaces structured errors, and rejects nested interactive front ends.

## Coverage Requirements

* TUI startup renders the initial shell
* one-shot TUI command execution reuses the shared command path
* structured command errors appear in the alerts pane
* nested interactive front ends are rejected from TUI command entry

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-TUI-01` | `TEST-TUI-01` |
| `REQ-TUI-02` | `TEST-TUI-01` |
| `REQ-TUI-03` | `TEST-TUI-02`, `TEST-TUI-03` |
| `REQ-TUI-04` | `TEST-TUI-02`, `TEST-TUI-04` |
| `REQ-TUI-05` | `TEST-TUI-04` |

## Representative Test Cases

### `TEST-TUI-01` — TUI startup

```gherkin
Given  EOF is supplied on stdin
When   the operator runs `canarchy tui`
Then   the startup output shall contain the shell header
And    the output shall contain bus status, live traffic, alerts, and command-entry sections
```

**Fixture:** mocked input (EOF).

---

### `TEST-TUI-02` — One-shot command execution

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy tui --command "j1939 monitor --pgn 65262"`
Then   the output shall reflect the shared command result
And    the output shall include command and mode state plus recent traffic content
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-TUI-03` — Shared error surface

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy tui --command "j1939 pgn 300000"`
Then   the output shall contain a structured `INVALID_PGN` error in the alerts pane
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-TUI-04` — Nested front ends rejected

```gherkin
Given  the TUI is running
When   the operator submits the command `shell --command 'capture can0 --text'` from TUI input
Then   the output shall contain `TUI_COMMAND_UNSUPPORTED`
```

**Fixture:** mocked TUI command input.

---

## Fixtures And Environment

No dedicated fixture files are required. Tests use mocked input and shared command execution paths.

## Explicit Non-Coverage

* full-screen terminal UI rendering
* background live capture subscriptions

## Traceability

This spec maps to the initial TUI acceptance criteria around startup, pane wiring, shared command execution, and presentation-layer-only behavior.
