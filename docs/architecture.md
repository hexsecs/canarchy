# Architecture

## Overview

CANarchy is composed of three primary layers:

The implementation language is Python, and the project uses `uv` as the standard workflow for dependency management, environment setup, and package execution.

Current repository status:

* the CLI contract is implemented and covered by unit tests
* the core model includes typed frame, replay, J1939, UDS, and alert events
* transport-backed commands default to a deterministic local scaffold, with an opt-in `python-can` live backend for `capture`, `send`, and `gateway`
* the shell exists today as parser reuse plus a basic interactive loop
* the TUI exists today as an initial text-mode shell over the shared command layer

### 1. Core Engine

Responsible for:

* typed CAN frame and event models
* deterministic local transport scaffolding plus a `python-can` live backend selector
* protocol parsing helpers for J1939
* DBC decode and encode pipelines
* replay planning from relative timestamps
* session persistence helpers
* event generation and serialization

### 2. Command Layer

Responsible for:

* CLI command definitions
* argument parsing and validation
* output formatting (`json`, `jsonl`, `table`, `raw`)
* exit codes

### 3. Front Ends

* CLI (non-interactive)
* shell scaffolding (interactive loop plus one-shot parser reuse)
* TUI (initial text-mode shell with a path toward a richer dashboard)

The CLI is implemented end to end. The shell is implemented as parser reuse plus a simple loop. The TUI now has an initial shell that reuses the shared command path, but richer live subscriptions and pane behavior remain future work.

The current TUI direction and initial pane plan are documented in [TUI plan](tui_plan.md).

This shared architecture is intended to support both agentic use and agentic development: agents should be able to operate the tool through a stable CLI contract and extend the project without introducing UI-only behavior or split logic paths.

---

## Event Model

The current Python implementation already models these structured events:

* frame
* decoded_message
* signal
* j1939_pgn
* uds_transaction
* replay_event
* alert

These dataclasses are serialized deterministically for CLI output now and are intended to be reused by future shell and TUI work.

These events power:

* CLI output
* shell command reuse and interactive shell output
* TUI rendering in the initial text-mode shell

---

## Data Flow

```text
Transport -> Frame -> Decode -> Protocol -> Analysis -> Event Stream
```

---

## Near-Term Gaps

These architectural pieces are not implemented end to end yet:

* broader real transport coverage beyond the initial `python-can` virtual-backed path
* reverse engineering helpers beyond the CLI surface
* fuzzing workflows beyond the CLI surface
* richer TUI live subscriptions and pane behavior beyond the initial shell

## Plugin Model (future)

Plugins should be able to extend:

* protocols
* commands
* analysis modules
* output sinks
