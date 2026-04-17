# Architecture

## Overview

CANarchy is composed of three primary layers:

### 1. Core Engine

Responsible for:

* transport backends (SocketCAN, slcan, remote)
* frame ingestion and transmission
* protocol parsing (CAN, J1939, UDS)
* decode pipelines (DBC)
* replay and mutation
* reverse engineering analysis
* event generation

### 2. Command Layer

Responsible for:

* CLI command definitions
* argument parsing and validation
* output formatting (`json`, `jsonl`, `table`, `raw`)
* exit codes

### 3. Front Ends

* CLI (non-interactive)
* REPL (interactive shell)
* TUI (visual dashboard)

All front ends must use the same command and event system.

This shared architecture is intended to support both agentic use and agentic development: agents should be able to operate the tool through a stable CLI contract and extend the project without introducing UI-only behavior or split logic paths.

---

## Event Model

All internal data should be expressed as structured events:

* frame
* decoded_message
* signal
* j1939_pgn
* uds_transaction
* anomaly
* replay_event
* fuzz_event

These events power:

* CLI output
* REPL feedback
* TUI rendering

---

## Data Flow

```text
Transport -> Frame -> Decode -> Protocol -> Analysis -> Event Stream
```

---

## Plugin Model (future)

Plugins should be able to extend:

* protocols
* commands
* analysis modules
* output sinks
