# Design Spec: Initial TUI Shell

## Goal

Provide the first usable `canarchy tui` experience as a thin text-mode presentation layer over the existing command system.

## Scope

The initial implementation is intentionally minimal:

* a text-mode TUI shell starts from `canarchy tui`
* panes render bus status, live traffic, alerts, and command entry help
* command entry executes existing CANarchy commands through the shared parser and result builder
* no separate transport, protocol, or session logic is introduced

## Command surface

```text
canarchy tui [--command "<existing canarchy command>"]
```

`--command` runs a single command through the TUI command-entry path and exits. This keeps the TUI testable without introducing a separate automation API.

## Pane model

### Bus Status

Shows the current command context and interface or file source when available.

### Live Traffic

Shows a compact summary of recent command-derived traffic or protocol activity.

### Alerts

Shows warnings and structured errors from shared command results.

### Command Entry

Accepts existing CANarchy commands and routes them through the shared parser and result-building path.

## Shared-command rule

The TUI uses the same command execution path as the CLI for non-interactive commands. Nested interactive front ends such as `shell` or `tui` are rejected from TUI command entry with a structured error.

## Deferred

* curses or full-screen terminal rendering
* live background capture subscriptions
* richer pane selection, focus, or filtering state
* decoded-signal and UDS-specific dedicated panes beyond the compact summary list
