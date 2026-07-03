# TUI Plan

Current status: `canarchy tui` is a **full-screen Textual application** with bus
status, live traffic, **decoded signals**, **J1939 activity** (summary ribbon +
recent table), **UDS transactions**, an append-only **alerts** log (including
replay activity), and a command entry. It streams the bus **live** in the
background, and every pane is an interactive, sortable/filterable table with
operator-controlled backlog. The full-screen + live-streaming milestone
(Suggested Implementation Order items 1, 2, and 6) is now implemented; the
text-mode shell and its one-shot `tui --command` mode have been retired.

Because the app is full-screen it requires an interactive terminal; in a
non-TTY / scripted context it prints guidance and exits non-zero. Use the
individual commands (`capture`, `decode`, `j1939 monitor`, …) for
non-interactive runs — the CLI remains the authoritative contract.

Commands and hotkeys (typed into the command entry):

* `/capture <iface>` — start a **live** background capture on the interface
* `/stop` (or the `x` key) — stop the live capture
* `/filter <pane> [text]` — substring-filter a pane (`traffic`, `decoded`,
  `j1939`, `uds`); no text clears the filter
* `/sort <pane> [column]` — sort a pane by column index or name (toggles
  direction)
* `/clear` (or the `c` key) — reset every pane
* `/help` — list the shared hotkey table in the alerts log
* `/save <name>`, `/load <name>` — session management
* `/dbc <ref>` — inspect a DBC (local path or `opendbc:<name>`)
* `/doctor`, `/config` — environment health / effective configuration
* `/quit`, `/exit` (or the `q` key) — exit the TUI
* Any real CANarchy command typed at the prompt runs through the shared parser
  and folds into the panes.

Keys: `space` pause/resume the live feed, `[` / `]` shrink/grow the backlog,
`ctrl+f` maximize the focused pane, arrow keys navigate rows within a pane,
`tab` moves focus between panes.

This document remains the forward-looking plan for the pane model.

## Goal

Define the initial TUI scope as a presentation layer over the existing CANarchy engine rather than as a separate application with its own business logic.

The TUI should help operators with live analysis, demos, and triage while preserving the project rule that the CLI remains the authoritative contract.

---

## Constraints

The TUI must follow these rules:

* it consumes the same structured events used by the CLI and REPL
* it does not introduce protocol logic that cannot also be reached through commands
* it does not invent a separate session or transport model
* it triggers the same command and engine actions already exposed through the CLI
* it remains deterministic enough that coding agents can reason about state transitions and outputs

This means the TUI is a view over the engine, not a second implementation of the engine.

---

## Initial Operator Workflows

The first TUI milestone should support these workflows:

1. Watch live bus activity and confirm the interface is active.
2. See decoded or protocol-aware views without leaving the live traffic context.
3. Monitor J1939 PGN activity and source-address behavior.
4. Inspect recent UDS transactions during scan or trace workflows.
5. Review alerts, warnings, and replay activity in one place.
6. Execute an existing command quickly from inside the TUI.

---

## Initial Pane Set

### 1. Bus Status

Purpose:

* show active interface or capture source
* show passive versus active mode
* show session context where relevant

Data dependencies:

* session state
* transport status metadata
* current command or workflow context

### 2. Live Traffic Table

Purpose:

* show recent frames in arrival order
* provide a stable raw view for quick triage

Data dependencies:

* `frame` events

Suggested columns:

* timestamp
* interface
* CAN ID
* DLC
* data

### 3. Decoded Signals

Purpose:

* show decoded messages and signal values next to recent frame activity

Data dependencies:

* `decoded_message`
* `signal`

Suggested columns:

* message name
* signal name
* value
* units

### 4. J1939 Activity

Purpose:

* give J1939-first visibility without forcing the operator back to raw IDs

Data dependencies:

* `j1939_pgn`

Suggested columns:

* PGN
* source address
* destination address
* priority
* payload summary

### 5. UDS Transactions

Purpose:

* present request and response activity as transactions rather than isolated frames

Data dependencies:

* `uds_transaction`

Suggested columns:

* service
* service name
* request ID
* response ID
* ECU address
* request bytes
* response bytes

### 6. Alerts And Replay

Purpose:

* keep warnings, active actions, and replay activity visible

Data dependencies:

* `alert`
* `replay_event`

### 7. Command Entry

Purpose:

* provide a lightweight command launcher that routes back through the existing parser

Data dependencies:

* shared command parser and command dispatch

The command entry should execute real commands, not a TUI-only command grammar.

---

## Event Dependencies

The current event model is already sufficient for an initial TUI milestone:

* `frame`
* `decoded_message`
* `signal`
* `j1939_pgn`
* `uds_transaction`
* `replay_event`
* `alert`

The TUI should subscribe to these events through one shared event stream abstraction.

The TUI should not need protocol-specific adapters that bypass the engine.

---

## State Model

The TUI should keep a thin UI state layer only for presentation concerns such as:

* selected pane
* current filters and sort order
* focused row or selected event
* visible time window or backlog size
* command entry draft

It should rely on the existing application state for:

* session context
* active interface
* loaded DBC path
* current capture source
* protocol-aware events

---

## Non-Goals For The First TUI Milestone

Do not add these in the first pass:

* TUI-only protocol workflows
* a separate plugin or extension layer just for the TUI
* custom transport backends that only the TUI can use
* complex multi-window terminal orchestration
* feature parity with mature CAN dashboards before the shared event model is fully exercised

---

## Suggested Implementation Order

1. Expand the event subscription boundary used by CLI, REPL, and TUI for background live updates.
2. Build on the shipped TUI shell with richer bus status, live traffic, and alerts presentation.
3. Add decoded signal and J1939 panes.
4. Add the UDS transaction pane.
5. Extend command entry with better session-aware context display.
6. Add pane-level filtering, focus handling, and backlog/window controls.

---

## Acceptance Mapping

This plan satisfies the issue goals by making these points explicit:

* the TUI scope and constraints are documented
* the initial pane list and event dependencies are clear
* follow-on implementation can proceed without inventing separate domain logic
