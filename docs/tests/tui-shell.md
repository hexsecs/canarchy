# Test Spec: Initial TUI Shell

## Coverage goals

* TUI startup renders the initial shell
* one-shot TUI command execution reuses the shared command path
* structured command errors appear in the alerts pane
* nested interactive front ends are rejected from TUI command entry

## Test cases

### TUI startup

**Action:** run `canarchy tui` with EOF on input.  
**Assert:** startup output contains the shell header plus bus status, live traffic, alerts, and command entry sections.

### One-shot command execution

**Action:** run `canarchy tui --command "j1939 monitor --pgn 65262"`.  
**Assert:** output reflects the shared command result, including command/mode state and recent traffic content.

### Shared error surface

**Action:** run `canarchy tui --command "j1939 pgn 300000"`.  
**Assert:** output contains the structured `INVALID_PGN` error in the alerts pane.

### Nested front ends rejected

**Action:** run `canarchy tui --command "shell --command 'capture can0 --raw'"`.  
**Assert:** output contains `TUI_COMMAND_UNSUPPORTED`.

## What is not tested

* full-screen terminal UI rendering, which is out of scope for this initial milestone
* background live capture subscriptions, which are deferred
