# Design Spec: Initial TUI Shell

## Document Control

| Field | Value |
|-------|-------|
| Status | Superseded by the full-screen TUI |
| Command surface | `canarchy tui` |
| Primary area | Front end |

> **Update:** `canarchy tui` is now a full-screen Textual application with
> background live capture and interactive, sortable/filterable panes. The
> text-mode shell and the one-shot `tui --command` mode described below have
> been retired. The engine boundary rules (REQ-TUI-03/04/05, including the
> `TUI_COMMAND_UNSUPPORTED` guard) still hold. See `docs/tui_plan.md` for the
> current command/keybinding surface.

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
canarchy tui
```

The TUI is interactive and full-screen; it requires a TTY. For scripted or
automation use, invoke the underlying commands directly (they are the
authoritative contract). The retired `--command` one-shot flag no longer
exists.

## Responsibilities And Boundaries

In scope:

* text-mode TUI startup from `canarchy tui`
* panes for bus status, live traffic, alerts, and command-entry help
* shared command execution path reused from the CLI

Out of scope (for this original text-mode milestone — now delivered by the
full-screen app):

* ~~full-screen terminal rendering~~ — delivered (Textual)
* ~~background live subscriptions~~ — delivered (`CaptureSession`)
* ~~richer pane selection, filtering, or focus behavior~~ — delivered

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

These were deferred for the text-mode milestone and are now implemented by the
full-screen Textual app (`src/canarchy/tui_app.py`, `src/canarchy/tui_capture.py`):

* ~~curses or full-screen terminal rendering~~ — Textual
* ~~background live capture subscriptions~~ — `CaptureSession` streaming
* ~~dedicated decoded-signal and UDS panes beyond the compact summary list~~ —
  dedicated sortable/filterable DataTables per pane

Remaining follow-up: a finite-timeout `capture_stream` loop so live capture
stops instantly on real hardware (today the daemon thread is abandoned on stop).
