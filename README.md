# README.md

## CANarchy

CANarchy is a stream-first CAN analysis and manipulation runtime designed for automation, security research, and agent-driven workflows.

The project is implemented in Python and uses `uv` for environment, dependency, and packaging workflows.

Machine-readable output uses canonical JSON envelopes and JSONL event streams where commands produce typed events. The CLI is the interface. J1939 is a first-class citizen, not an afterthought.

Today the repository delivers:

* a stable CLI surface for analysts, scripts, and coding agents
* J1939-first heavy vehicle workflows: PGN decoding, SPN extraction, TP session reassembly, DM1 fault parsing
* structured output (`--json`, `--jsonl`, `--text`) on every command
* live CAN transport via `python-can` with support for socketcan, virtual bus, and UDP multicast
* UDS scan and trace, DBC decode/encode, capture/filter/replay, and an interactive shell

### Why CANarchy?

Most CAN tools force the wrong tradeoff: interactive but hard to automate, scriptable but too raw, protocol-aware but inconsistent across interfaces. CANarchy is built around the opposite constraint: every output is a stream of typed events you can parse, pipe, or forward to an agent.

The [event schema](docs/event-schema.md) is the stable contract. The CLI wraps it. J1939 heavy vehicle analysis is the initial focus for protocol-aware workflows, with a security-research lens throughout.

### Current State

Fully implemented and tested:

* `capture`, `send`, `filter`, `stats` — transport workflows with live `python-can` and deterministic scaffold backends
* `generate` — cangen-style frame generation (fixed, random, incrementing modes)
* `gateway` — bridge frames between two interfaces (unidirectional and bidirectional)
* `replay` — deterministic replay planning from candump files
* `decode`, `encode` — DBC-backed signal decode and encode
* `j1939 monitor`, `decode`, `pgn`, `spn`, `tp`, `dm1`, `faults`, `summary`, `inventory`, `compare` — J1939 operator workflows across live, file-backed, and decoded views
* `uds scan`, `trace`, `services` — UDS diagnostic workflows and service catalog, including initial transport-backed scan/trace heuristics
* `re signals` — file-backed signal-candidate ranking across 4-bit, 8-bit, and 16-bit fields
* `re counters` — file-backed counter-candidate detection for reverse-engineering workflows
* `re entropy` — file-backed entropy ranking across arbitration IDs and byte positions
* `re correlate` — file-backed correlation of candidate fields against timestamped reference series
* `re match-dbc`, `re shortlist-dbc` — provider-backed DBC candidate ranking against captures
* `skills provider list`, `skills search`, `skills fetch`, `skills cache list`, `skills cache refresh` — repository-backed CANarchy skill discovery, caching, and provenance workflows
* `session save`, `load`, `show` — session management
* `export` — structured artifact export
* `shell` — interactive REPL and `--command` scripting mode
* `tui` — terminal UI front end

Planned but not yet exposed in the CLI:

* active fuzzing workflows for replay mutation, payload mutation, and arbitration-ID probing

Default transport backend is `python-can`; set `CANARCHY_TRANSPORT_BACKEND=scaffold` for deterministic offline behavior.

### Documentation

* [Event Schema](docs/event-schema.md) — canonical event envelope for all structured output
* [Command spec](docs/command_spec.md)
* [CAN Tool Feature Matrix](docs/feature-matrix.md) — high-level comparison to other OSS CAN tools
* [Architecture](docs/architecture.md)
* [Cookbook](docs/cookbook/index.md) — short task-oriented recipes
* [Troubleshooting](docs/troubleshooting.md) — structured error-code catalog
* [Changelog](CHANGELOG.md)
* [Release Workflow](docs/release.md)
* [J1939 Heavy Vehicle Demo](docs/tutorials/j1939_heavy_vehicle.md)

### Community

* [Contributing](CONTRIBUTING.md) — local development, branch flow, PR gates
* [Code of Conduct](CODE_OF_CONDUCT.md)
* [Security Policy](SECURITY.md) — reporting security concerns and active-bus operation guidance

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

6. Optionally install `canarchy` on your PATH so you don't need `uv run` every time:

```bash
uv tool install --editable .
canarchy --help
```

If you want to verify the local environment end to end, run:

```bash
uv run python -m unittest discover -s tests -v
```

Notes:

* `uv sync` creates the local virtual environment and installs the package from the current checkout.
* The checked-in `uv.lock` file should be used for reproducible dependency resolution.
* `uv tool install --editable .` puts `canarchy` on your PATH permanently; edits take effect without reinstalling.
* Live transport support currently uses `python-can`; persist backend settings in `~/.canarchy/config.toml` (see [Getting Started](docs/getting_started.md)).

### Development

```bash
uv sync
uv tool install --editable .
canarchy --help
```

### Versioning Policy

CANarchy uses Semantic Versioning.

Rules:

* `MAJOR` for intentional breaking changes to the CLI contract, structured output contract, or other documented public behavior
* `MINOR` for backward-compatible new commands, new output fields, or new capabilities
* `PATCH` for backward-compatible fixes, documentation corrections, and implementation improvements that do not intentionally break the public contract

Prereleases:

* prereleases should use standard SemVer prerelease identifiers such as `0.2.0a1`, `0.2.0b1`, or `0.2.0rc1`
* prereleases are appropriate when command behavior, output contracts, or packaging flows need release-candidate validation before a stable tag

Release tags:

* Git tags should match the package version exactly, prefixed with `v`, for example `v0.1.0`
* `canarchy --version`, package metadata, and release tags should always agree

Current implementation:

* `src/canarchy/__init__.py` is the authoritative version source
* package metadata is derived from that version during build
* CLI and MCP server version reporting reuse the same version value

### Example Usage

```bash
# Capture and decode
canarchy capture can0 --candump
canarchy capture can0 --jsonl
canarchy decode --file trace.candump --dbc vehicle.dbc --jsonl

# J1939 heavy vehicle analysis
canarchy j1939 decode --file trace.candump --text
canarchy j1939 spn 110 --file trace.candump --text   # Engine Coolant Temp
canarchy j1939 dm1 --file trace.candump --text        # Active fault codes

# Pipe events into downstream tools
canarchy j1939 spn 110 --file trace.candump --jsonl \
  | jq '[.payload.value, .payload.units, .payload.timestamp]'

# Active workflows
canarchy generate can0 --count 10 --gap 50 --id 7DF --jsonl
canarchy gateway can0 239.0.0.1 --count 100
canarchy replay --file trace.candump --rate 2.0 --json
```

Use `--candump` for a human-oriented live view. Use `--jsonl` when feeding output to scripts or agents — every line is a typed event from the [canonical schema](docs/event-schema.md).

Live transport uses `python-can` by default. Set `CANARCHY_PYTHON_CAN_INTERFACE` to choose an interface type, or set `CANARCHY_TRANSPORT_BACKEND=scaffold` for deterministic offline behavior.

Current file support:

* file-backed workflows such as `filter`, `stats`, `decode`, `j1939 decode`, and `replay` read standard timestamped candump log files
* `j1939 pgn` inspects recorded traffic with `--file <capture.candump>`
* the supported log form today is `(timestamp) interface frame#data`
* additional supported candump forms include classic RTR `id#R`, CAN FD `id##<flags><data>`, and error frames using a CAN error-flagged identifier such as `20000080#0000000000000000`
* supported capture-file suffixes today are `.candump` and `.log`; `capture-info --file -`, `stats --file -`, and `filter --file -` can read candump text from stdin
* `filter --stdin`, `decode --stdin`, and `j1939 decode --stdin` read JSONL FrameEvents from stdin
* malformed candump log lines are skipped during capture parsing rather than falling back to sample data; commands that require capture metadata or explicitly validate stdin emptiness return structured errors when no valid frames are available

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
