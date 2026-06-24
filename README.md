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

### Try it in 60 seconds

Once a CANarchy release has been published to PyPI:

```bash
pipx install canarchy
canarchy --version
canarchy doctor --text

# Stream two pre-recorded frame events from the deterministic scaffold
# backend — no hardware, no fixture files, no network. Shows the
# canonical JSONL envelope.
CANARCHY_TRANSPORT_BACKEND=scaffold canarchy capture can0 --jsonl
```

`canarchy doctor` runs eight offline health checks; everything green
means the install is good. The scaffold capture demonstrates the
structured-output contract that every command emits. Replace it with
`canarchy capture can0 --candump` once you have a real interface, or
clone the repo to run against the in-tree J1939 fixtures.

For development or for installs from a checkout, see
[Installation](#installation) below.

### Why CANarchy?

Most CAN tools force the wrong tradeoff: interactive but hard to automate, scriptable but too raw, protocol-aware but inconsistent across interfaces. CANarchy is built around the opposite constraint: every output is a stream of typed events you can parse, pipe, or forward to an agent.

The [event schema](docs/event-schema.md) is the stable contract. The CLI wraps it. J1939 heavy vehicle analysis is the initial focus for protocol-aware workflows, with a security-research lens throughout.

### Current State

Fully implemented and tested:

_Transport_

* `capture`, `send`, `filter`, `stats` — transport workflows with live `python-can` and deterministic scaffold backends; `stats` reports per-ID frequency/timing, DLC distribution, and a bus-load estimate
* `compare` — diff two or more plain CAN captures per arbitration ID in one call: frame-count/rate deltas, cycle-time drift, and payload-entropy deltas against a baseline, each ID flagged (rate-drop, rate-spike, entropy-collapse, timing-drift, new/dropped); the generic-CAN analogue of `j1939 compare`
* `capture-info` — fast capture metadata without loading every frame
* `generate` — cangen-style frame generation (fixed, random, incrementing modes)
* `simulate` — deterministic, profile-driven mix of classic CAN, J1939, and DM1 traffic (no hardware needed)
* `gateway` — bridge frames between two interfaces (unidirectional and bidirectional)
* `replay`, `sequence replay` — deterministic replay planning from candump files, and YAML/JSON multi-message coordinated transmit

_Databases (DBC / ARXML / KCD / SYM via cantools)_

* `decode`, `encode` — database-backed signal decode and encode; `encode` resolves SAE PGN/SPN display names for a decode→encode round-trip
* `dbc inspect` (incl. `--layout`, `--search`), `dbc signals` — database and signal inspection
* `dbc convert` — convert databases between DBC / KCD / SYM
* `dbc generate-c` — C source/header/fuzzer generation from a database
* `dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list|prune|refresh` — provider-backed DBC discovery and cache workflows

_J1939_

* `j1939 monitor`, `decode`, `pgn`, `spn`, `tp`, `dm1`, `faults`, `summary`, `inventory`, `compare` — J1939 operator workflows across live, file-backed, and decoded views; faults resolve SPN names and FMI descriptions from the bundled SAE catalog

_UDS_

* `uds scan`, `trace`, `services` — UDS diagnostic workflows and service catalog, including initial transport-backed scan/trace heuristics

_Reverse engineering_

* `re signals`, `re counters`, `re entropy` — file-backed signal/counter/entropy candidate ranking, annotated with J1939 PGN/source-address context and transport-protocol aware
* `re correlate` — correlation of candidate fields against timestamped reference series
* `re anomalies` — inter-frame-timing and unexpected/dropped-ID anomaly detection, with optional baseline; against a baseline it also flags per-ID frame-rate drop/spike (suppression/injection) and payload-entropy collapse (plateau/frozen-value attacks)
* `re corpus` — cross-capture coverage, cycle-time drift, and signal-stability analysis
* `re match-dbc`, `re shortlist-dbc` — provider-backed DBC candidate ranking against captures

_Datasets_

* `datasets provider list`, `search`, `inspect`, `fetch`, `cache list|refresh` — public CAN dataset provider workflows
* `datasets convert`, `stream`, `replay` — dataset conversion and bounded streaming/replay

_Visualization, front ends, and extensions_

* `plot` — signal time-series plots to PNG/SVG/HTML (`pip install canarchy[plot]`)
* `web serve` — read-only browser dashboard over the JSONL envelope (HTTP + WebSocket)
* `shell` — interactive REPL and `--command` scripting mode
* `tui` — terminal UI front end
* `plugins list|info|enable|disable` — Python entry-point plugin discovery and toggles
* `skills provider list`, `search`, `fetch`, `cache list|refresh` — repository-backed CANarchy skill discovery, caching, and provenance workflows

_Active-transmit fuzzing_ (gated by the [active-transmit safety design](docs/design/active-transmit-safety.md); `--dry-run` is the safe planning path)

* `fuzz payload`, `fuzz replay`, `fuzz arbitration-id` — payload/replay/ID-walk fuzzing
* `fuzz signal`, `fuzz spn` — DBC-signal and J1939-SPN-aware mutation with sentinel coverage

_Session, export, and utilities_

* `session save`, `load`, `show` — session management
* `export` — structured artifact export
* `doctor` — local environment health checks (Python, `python-can`, vendor backends, caches, MCP, config)
* `mcp serve`, `mcp install` — Model Context Protocol server and client-config helper
* `completion {bash,zsh,fish}` — emit a shell completion script
* `--log-level` and `--quiet` — global stderr logging controls (place before the subcommand)

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

CANarchy currently targets Python 3.12 or newer.

#### From PyPI (recommended for users)

```bash
pipx install canarchy        # isolated, on PATH everywhere
# or
pip install --user canarchy  # if pipx is not available
```

After install, confirm the environment is healthy:

```bash
canarchy --version
canarchy doctor --text
```

Shell completions for bash, zsh, and fish are produced by `canarchy completion <shell>`; see [Getting Started](docs/getting_started.md#install-shell-completion) for the install snippet for each shell.

#### From source (development)

CANarchy uses `uv` for environment, dependency, and packaging workflows.

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
