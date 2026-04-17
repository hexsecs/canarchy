# README.md

## CANarchy

CANarchy is a CLI-first CAN security research toolkit for reproducible, protocol-aware, automation-friendly workflows.

The project is implemented in Python and uses `uv` for environment, dependency, and packaging workflows.

Today the repository combines:

* a stable command surface for analysts, scripts, and coding agents
* J1939-first heavy vehicle workflows alongside broader CAN analysis
* structured output for pipelines, replayable research, and machine parsing
* a shared Python core used by the CLI, session workflows, and shell scaffolding

### Why CANarchy?

Most CAN tools force the wrong tradeoff: interactive but hard to automate, scriptable but too raw, protocol-aware but inconsistent across interfaces, or just poorly documented.

CANarchy is built differently. The CLI is the contract. Structured output is a first-class feature. J1939 is treated as a primary workflow, not an afterthought. The current codebase focuses on making that CLI contract testable while adding a first real live-transport path through `python-can`.

The project is centered on CAN security research, with strong support for heavy vehicle and J1939 workflows and broader CAN analysis through a security-first lens.

### Current State

Implemented and exercised in tests:

* scaffolded transport workflows for `capture`, `send`, `filter`, and `stats`
* optional live `python-can` transport for `capture` and `send`, with the virtual CAN interface as the first supported backend
* deterministic `replay` planning from sample capture data
* DBC-backed `decode` and `encode`
* J1939 `monitor`, `decode`, and `pgn`
* UDS `scan` and `trace`
* session `save`, `load`, and `show`
* structured `--json`, `--jsonl`, `--table`, and `--raw` output modes
* shell command reuse through `canarchy shell --command ...`

Present in the CLI tree but still scaffolded or placeholder-only:

* `export`
* `j1939 spn`, `j1939 tp`, and `j1939 dm1`
* `uds services`
* `re signals`, `re counters`, `re entropy`, and `re correlate`
* `fuzz replay`, `fuzz mutate`, and `fuzz id`
* `tui`

Current implementation note:

* `capture` and `send` default to the deterministic scaffold backend, with an opt-in `python-can` backend for live transport work
* successful command payloads currently include `status: planned` and `implementation: command surface scaffold`

### Documentation

* [Command spec](docs/command_spec.md)
* [Architecture](docs/architecture.md)
* [TUI plan](docs/tui_plan.md)

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
* Live transport support currently uses `python-can`; set `CANARCHY_TRANSPORT_BACKEND=python-can` to enable it.
* The initial real backend focus is the `python-can` `virtual` interface, which is also the default `CANARCHY_PYTHON_CAN_INTERFACE` value.
* The scaffold backend remains the default, so transport workflows can still be exercised locally without a live CAN interface.

### Development

```bash
uv sync
uv run canarchy --help
```

### Example Usage

```bash
canarchy capture can0 --json
canarchy capture can0 --candump
canarchy decode capture.log --dbc tests/fixtures/sample.dbc --json
canarchy encode --dbc tests/fixtures/sample.dbc EngineStatus1 CoolantTemp=55 OilTemp=65 Load=40 LampState=1 --json
canarchy j1939 monitor --pgn 65262
canarchy replay capture.log --rate 0.5 --json
```

These examples work against the current scaffolded transport and fixture-driven protocol data by default. Set `CANARCHY_TRANSPORT_BACKEND=python-can` to exercise the live `capture` and `send` path through `python-can`.

Use `canarchy capture <interface> --candump` when you want a familiar human-oriented live dump view. Use `--json` or `--jsonl` when you need stable machine-readable output.

Current file support:

* file-backed workflows such as `filter`, `stats`, `decode`, `j1939 decode`, and `replay` now read standard timestamped candump log files
* the supported log form today is `(timestamp) interface frame#data`
* malformed candump log lines return structured transport errors instead of falling back to sample data

### Structured Output

Successful commands return a stable JSON envelope:

```json
{
  "ok": true,
  "command": "capture",
  "data": {},
  "warnings": [],
  "errors": []
}
```

Failures return structured errors with actionable hints:

```json
{
  "ok": false,
  "command": "decode",
  "data": {},
  "warnings": [],
  "errors": [
    {
      "code": "DBC_LOAD_FAILED",
      "message": "Failed to parse DBC file.",
      "hint": "Validate the DBC syntax and line endings."
    }
  ]
}
```

### Philosophy

* CLI is the contract
* Protocol semantics over raw frames
* Structured outputs over formatted text
* Reproducible workflows over ad-hoc interaction
