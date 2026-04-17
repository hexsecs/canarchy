# README.md

## CANarchy

CANarchy is a CLI-first CAN security research environment for reproducible, protocol-aware, automation-friendly workflows.

The project is implemented in Python and uses `uv` for environment, dependency, and packaging workflows.

It combines:

* a stable command surface for analysts, scripts, and coding agents
* J1939-first heavy vehicle workflows alongside broader CAN analysis
* structured output for pipelines, replayable research, and machine parsing
* shared core logic across CLI, REPL, and TUI for both agentic use and agentic development

### Why CANarchy?

Most CAN tools force the wrong tradeoff: interactive but hard to automate, scriptable but too raw, protocol-aware but inconsistent across interfaces, or just poorly documented.

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

* [Command spec](docs/command_spec.md)
* [Architecture](docs/architecture.md)

### Installation

CANarchy currently targets Python 3.12 or newer and uses `uv` for environment and packaging workflows.

1. Install Python 3.12 or newer.
2. Install `uv`.
3. Clone the repository.
4. Sync the project environment and dependencies:

```bash
uv sync
```

5. Run the CLI:

```bash
uv run canarchy --help
```

If you want to verify the local environment end to end, run:

```bash
uv run python -m unittest discover -s tests -v
```

Notes:

* `uv sync` creates the local virtual environment and installs the package from the current checkout.
* The checked-in `uv.lock` file should be used for reproducible dependency resolution.
* Transport-oriented commands may require platform-specific CAN interface setup beyond the Python environment.

### Development

```bash
uv sync
uv run canarchy
```

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
