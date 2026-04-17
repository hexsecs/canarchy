# README.md (initial)

## CANarchy

CANarchy is a CLI-first CAN security research environment for reproducible, protocol-aware, automation-friendly workflows.

It combines:

* a stable command surface for analysts, scripts, and coding agents
* J1939-first heavy vehicle workflows alongside broader CAN analysis
* structured output for pipelines, replayable research, and machine parsing
* shared core logic across CLI, REPL, and TUI for both agentic use and agentic development

### Why CANarchy?

Most CAN tools force the wrong tradeoff: interactive but hard to automate, scriptable but too raw, or protocol-aware but inconsistent across interfaces.

CANarchy is built differently. The CLI is the contract. Structured output is a first-class feature. J1939 is treated as a primary workflow, not an afterthought. The same core engine should power CLI, REPL, and TUI so analysts, scripts, coding agents, and agent-driven development workflows can all rely on the same behavior.

The project is centered on CAN security research, with strong support for heavy vehicle and J1939 workflows and broader CAN analysis through a security-first lens.

### Key Features

* CLI-first design with deterministic behavior for automation, coding-agent use, and agentic development
* JSON and JSONL output as first-class interfaces, not add-ons
* J1939-first workflows with PGN/SPN-centric analysis for heavy vehicle research
* DBC-backed decode and encode for moving between raw frames and signal semantics
* Replay, mutation, and fuzzing primitives for controlled lab workflows
* Reverse engineering helpers oriented toward explainable evidence capture
* Session-based workflows with shared engine parity across CLI, REPL, and TUI

### Documentation

* [Command spec](docs/COMMAND_SPEC.md)
* [Architecture](docs/architecture.md)

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
