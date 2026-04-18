# TUI Plan

Current status: `canarchy tui` now starts an initial text-mode shell with bus status, live traffic, alerts, and command entry routed through the shared command layer.

This document remains the forward-looking plan for taking that initial shell toward the richer pane model described below.

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
