# Design Spec: Initial TUI Shell

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy tui` |
| Primary area | Front end |

## Goal

Provide the first usable `canarchy tui` experience as a thin text-mode presentation layer over the existing command system.

## User-Facing Motivation

Operators need a compact interactive view that can surface recent traffic, command context, and alerts without introducing TUI-only protocol or transport behavior.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-TUI-01` | Ubiquitous | The system shall provide a `canarchy tui` command that starts the initial text-mode shell. |
| `REQ-TUI-02` | Event-driven | When `canarchy tui` starts, the system shall render bus status, live traffic, alerts, and command-entry sections. |
| `REQ-TUI-03` | Event-driven | When a command is submitted via TUI command entry, the system shall execute it through the shared CLI parser and result path. |
| `REQ-TUI-04` | Ubiquitous | The TUI shall not introduce transport, protocol, or session logic separate from the shared command layer. |
| `REQ-TUI-05` | Unwanted behaviour | If `shell` or `tui` is submitted via TUI command entry, the system shall return a structured error with code `TUI_COMMAND_UNSUPPORTED` and exit code 1. |

## Command Surface

```text
canarchy tui [--command "<existing canarchy command>"]
```

`--command` runs one command through the TUI command-entry path and exits, which keeps the TUI testable and automation-friendly.

## Responsibilities And Boundaries

In scope:

* text-mode TUI startup from `canarchy tui`
* panes for bus status, live traffic, alerts, and command-entry help
* shared command execution path reused from the CLI

Out of scope:

* full-screen terminal rendering
* background live subscriptions
* richer pane selection, filtering, or focus behavior

## Pane Model

### Bus Status

Shows the current command context plus interface or file source when available.

### Live Traffic

Shows a compact summary of recent frame or protocol activity derived from shared command results.

### Alerts

Shows warnings and structured errors from shared command results.

### Command Entry

Accepts existing CANarchy commands and routes them through the shared parser and result-building path.

## Shared Command Rule

The TUI uses the same command execution path as the CLI for non-interactive commands. Nested interactive front ends such as `shell` or `tui` are rejected from TUI command entry.

## Output Contract

The TUI renders a text-mode shell with the following sections in order:

* shell header
* bus status
* live traffic
* alerts
* command-entry help

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `TUI_COMMAND_UNSUPPORTED` | TUI command entry attempts to launch `shell` or `tui` | 1 |

## Deferred Decisions

* curses or full-screen terminal rendering
* background live capture subscriptions
* dedicated decoded-signal and UDS panes beyond the compact summary list
