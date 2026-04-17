# README.md (initial)

## CANarchy

CANarchy is a CLI-first CAN security research toolkit designed for automation, reverse engineering, and protocol analysis.

It combines:

* structured CLI workflows
* an interactive shell (REPL)
* an optional TUI dashboard
* protocol-aware analysis (CAN, J1939, UDS)

### Key Features

* CLI-first design for scripting and agentic workflows
* JSON / JSONL output for machine parsing
* J1939-first workflows (PGN/SPN-centric)
* DBC-backed decode and encode
* Replay, mutation, and fuzzing primitives
* Reverse engineering helpers
* Session-based workflows

### Example Usage

```bash
canarchy capture can0 --jsonl
canarchy decode capture.log --dbc truck.dbc
canarchy j1939 monitor --pgn 65262
canarchy uds scan can0
canarchy replay drive.log --rate 0.5
```

### Philosophy

* CLI is the contract
* Protocol semantics over raw frames
* Structured outputs over formatted text
* Reproducible workflows over ad-hoc interaction

---

# ARCHITECTURE.md (initial)

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
* output formatting (json, jsonl, table, raw)
* exit codes

### 3. Front Ends

* CLI (non-interactive)
* REPL (interactive shell)
* TUI (visual dashboard)

All front ends must use the same command and event system.

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
Transport → Frame → Decode → Protocol → Analysis → Event Stream
```

---

## Plugin Model (future)

Plugins should be able to extend:

* protocols
* commands
* analysis modules
* output sinks

