<h1 align="center">CANarchy</h1>

<p align="center">
  <strong>A stream-first CAN bus toolkit for analysts, security researchers, and AI agents.</strong><br>
  Every command emits typed, machine-readable events you can pipe, script, or hand to an agent — with J1939 heavy-vehicle support as a first-class citizen.
</p>

<p align="center">
  <a href="https://pypi.org/project/canarchy/"><img alt="PyPI" src="https://img.shields.io/pypi/v/canarchy"></a>
  <a href="https://pypi.org/project/canarchy/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/canarchy"></a>
  <a href="https://github.com/hexsecs/canarchy/actions/workflows/test.yml"><img alt="Tests" src="https://github.com/hexsecs/canarchy/actions/workflows/test.yml/badge.svg"></a>
  <a href="https://github.com/hexsecs/canarchy/actions/workflows/lint.yml"><img alt="Lint" src="https://github.com/hexsecs/canarchy/actions/workflows/lint.yml/badge.svg"></a>
  <a href="https://github.com/hexsecs/canarchy/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/pypi/l/canarchy"></a>
  <a href="https://hexsecs.github.io/canarchy/"><img alt="Docs" src="https://img.shields.io/badge/docs-hexsecs.github.io-blue"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/hexsecs/canarchy/main/docs/assets/tui.svg" alt="CANarchy's full-screen TUI streaming live CAN traffic, J1939 activity, and DM1 faults" width="920">
</p>

---

## What is CANarchy?

CANarchy is a CLI-first runtime for capturing, decoding, and manipulating CAN and CAN-FD traffic. Most CAN tools force a tradeoff: interactive but hard to automate, scriptable but too raw, or protocol-aware but inconsistent across interfaces. CANarchy is built around the opposite constraint — **every output is a stream of typed events** (`--json`, `--jsonl`, `--text`) you can parse, pipe, or forward to an LLM agent over MCP.

It's for you if you're:

- **A security researcher** reversing an unknown bus, fuzzing ECUs, or diffing captures for anomalies.
- **A heavy-vehicle / J1939 engineer** who wants PGN/SPN decoding, TP reassembly, and DM1 fault parsing without dropping to raw IDs.
- **Building automation or AI agents** that need a stable, machine-readable CAN interface instead of scraping human-formatted text.

## Install

```bash
pipx install canarchy          # isolated, on PATH everywhere
# or:  pip install --user canarchy
```

Requires Python 3.12+. Live transport uses [`python-can`](https://python-can.readthedocs.io/) (socketcan, virtual bus, UDP multicast, and more).

## Try it in 60 seconds — no hardware required

```bash
canarchy --version
canarchy doctor --text          # 8 offline health checks; all green = good install

# Stream typed events from the deterministic scaffold backend —
# no hardware, no fixtures, no network. This is the JSONL contract:
CANARCHY_TRANSPORT_BACKEND=scaffold canarchy capture can0 --jsonl
```

Point it at a real interface once you have one:

```bash
canarchy capture can0 --candump                 # human-friendly live view
canarchy capture can0 --jsonl | jq .            # typed events, one per line
```

Prefer to explore visually? Launch the **full-screen TUI** (pictured above) and watch the bus live:

```bash
canarchy tui        # /capture <iface> to stream; /filter, /sort, /help
```

## Why CANarchy?

The [event schema](https://github.com/hexsecs/canarchy/blob/main/docs/event-schema.md) is the stable contract; the CLI wraps it. That one design choice is what sets CANarchy apart from most open-source CAN tooling:

- **Structured output is the contract, not an afterthought.** Every command — capture, decode, fuzz, reverse-engineer — emits the same canonical JSON envelope. Parse once, reuse everywhere.
- **Pipe-first.** `--jsonl` streams one typed event per line, so `| jq`, `| grep`, or a downstream script Just Works.
- **J1939 is first-class.** PGN decoding, SPN extraction, TP session reassembly, and DM1 fault parsing resolve names from a bundled SAE catalog — not just raw arbitration IDs.
- **Agent-ready.** A built-in [MCP](https://modelcontextprotocol.io/) server exposes the toolkit to Claude and other MCP clients, so an agent can drive CAN analysis directly.

|  | CANarchy | Typical CAN CLI tools |
|---|:---:|:---:|
| Structured output as a core contract | ✅ | ✗ / partial |
| Pipe-friendly typed event stream | ✅ | partial |
| Provider-backed DBC discovery & cache | ✅ | ✗ |
| J1939-first operator workflows | ✅ | partial |
| MCP / agent integration | ✅ | ✗ |

See the full [CAN tool feature matrix](https://github.com/hexsecs/canarchy/blob/main/docs/feature-matrix.md) for an honest, side-by-side comparison with can-utils, SavvyCAN, Caring Caribou, TruckDevil, and others.

## What can you do with it?

```bash
# Decode a capture against a DBC
canarchy decode --file trace.candump --dbc vehicle.dbc --jsonl

# J1939 heavy-vehicle analysis
canarchy j1939 decode --file trace.candump --text
canarchy j1939 spn 110 --file trace.candump --text     # Engine Coolant Temp
canarchy j1939 dm1  --file trace.candump --text          # active fault codes

# Reverse-engineer an unknown bus: rank likely signals, counters, anomalies
canarchy re signals   --file trace.candump --jsonl
canarchy re anomalies --file trace.candump --baseline known_good.candump --jsonl

# Diff two captures per arbitration ID (rate/timing/entropy deltas)
canarchy compare before.candump after.candump --json

# Active workflows (gated by the active-transmit safety model; --dry-run plans safely)
canarchy generate can0 --count 10 --gap 50 --id 7DF --jsonl
canarchy replay --file trace.candump --rate 2.0 --json

# Pipe events straight into downstream tooling
canarchy j1939 spn 110 --file trace.candump --jsonl \
  | jq '[.payload.value, .payload.units, .payload.timestamp]'
```

## Drive it from an AI agent (MCP)

CANarchy ships a [Model Context Protocol](https://modelcontextprotocol.io/) server, so an LLM agent can capture, decode, and analyze CAN traffic through the same structured contract the CLI uses.

```bash
canarchy mcp install --client claude-desktop   # or: --client claude-code
canarchy mcp serve                             # or run the stdio server directly
```

Active-transmit tools require an explicit acknowledgement, so an agent can't put frames on a live bus by accident. See the [active-transmit safety design](https://github.com/hexsecs/canarchy/blob/main/docs/design/active-transmit-safety.md).

## The full-screen TUI

`canarchy tui` opens an interactive, full-screen dashboard that streams the bus live:

- **Live panes:** Live Traffic, Decoded Signals, J1939 (summary ribbon + recent table), UDS transactions, and an append-only Alerts log.
- **Background capture:** `/capture <iface>` starts streaming; `/stop` (or `x`) ends it.
- **Interactive:** `/filter <pane> <text>`, `/sort <pane> <column>`, arrow-key row navigation, `space` to pause the feed, `[`/`]` to resize the backlog, `ctrl+f` to maximize a pane.
- Type any real CANarchy command at the prompt — it runs through the shared parser and folds into the panes.

<details>
<summary><strong>Full command catalog</strong> (click to expand)</summary>

Fully implemented and tested:

**Transport**
- `capture`, `send`, `filter`, `stats` — transport workflows with live `python-can` and deterministic scaffold backends; `stats` reports per-ID frequency/timing, DLC distribution, and a bus-load estimate
- `compare` — diff two or more plain CAN captures per arbitration ID: frame-count/rate deltas, cycle-time drift, payload-entropy deltas against a baseline, each ID flagged (rate-drop, rate-spike, entropy-collapse, timing-drift, new/dropped)
- `capture-info` — fast capture metadata without loading every frame
- `generate` — cangen-style frame generation (fixed, random, incrementing)
- `simulate` — deterministic, profile-driven mix of classic CAN, J1939, and DM1 traffic (no hardware)
- `gateway` — bridge frames between two interfaces (uni- and bidirectional)
- `replay`, `sequence replay` — deterministic replay planning from candump files, and YAML/JSON multi-message coordinated transmit

**Databases (DBC / ARXML / KCD / SYM via cantools)**
- `decode`, `encode` — database-backed signal decode/encode; `encode` resolves SAE PGN/SPN display names for round-trips
- `dbc inspect` (incl. `--layout`, `--search`), `dbc signals` — database and signal inspection
- `dbc convert` — convert databases between DBC / KCD / SYM
- `dbc generate-c` — C source/header/fuzzer generation from a database
- `dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list|prune|refresh` — provider-backed DBC discovery and cache workflows

**J1939**
- `j1939 monitor`, `decode`, `pgn`, `spn`, `tp`, `dm1`, `faults`, `summary`, `inventory`, `compare`, `map` — operator workflows across live, file-backed, and decoded views; faults resolve SPN names and FMI descriptions from the bundled SAE catalog

**UDS**
- `uds scan`, `trace`, `services`, `subservices`, `ecu-reset`, `tester-present`, `security-seed`, `dump-dids`, `read-memory`, `auto` — diagnostic discovery and active workflows

**Reverse engineering**
- `re signals`, `re counters`, `re entropy` — file-backed candidate ranking, annotated with J1939 PGN/source-address context, transport-protocol aware
- `re correlate` — correlate candidate fields against timestamped reference series
- `re anomalies` — inter-frame-timing and unexpected/dropped-ID anomaly detection; against a baseline it also flags per-ID rate drop/spike (suppression/injection) and payload-entropy collapse (plateau/frozen-value attacks)
- `re corpus` — cross-capture coverage, cycle-time drift, and signal-stability analysis
- `re match-dbc`, `re shortlist-dbc` — provider-backed DBC candidate ranking against captures

**Datasets**
- `datasets provider list`, `search`, `inspect`, `fetch`, `download`, `cache list|refresh` — public CAN dataset provider workflows
- `datasets convert`, `stream`, `replay` — dataset conversion and bounded streaming/replay

**Diagnostics over other transports**
- `doip discovery`, `services`, `ecu-reset`, `tester-present`, `security-seed`, `dump-dids` — DoIP UDP discovery and active diagnostic workflows
- `xcp scan`, `info`, `dump` — XCP slave discovery, capability interrogation, and bounded memory dump

**Visualization, front ends, and extensions**
- `plot` — signal time-series plots to PNG/SVG/HTML (`pip install canarchy[plot]`)
- `web serve` — read-only browser dashboard over the JSONL envelope (HTTP + WebSocket)
- `shell` — interactive REPL and `--command` scripting mode
- `tui` — full-screen terminal dashboard with background live capture
- `plugins list|info|enable|disable` — Python entry-point plugin discovery and toggles
- `skills provider list`, `search`, `fetch`, `cache list|refresh` — repository-backed CANarchy skill discovery, caching, and provenance

**Active-transmit fuzzing** (gated by the [active-transmit safety design](https://github.com/hexsecs/canarchy/blob/main/docs/design/active-transmit-safety.md); `--dry-run` is the safe planning path)
- `fuzz payload`, `fuzz replay`, `fuzz arbitration-id`, `fuzz identify` — payload/replay/ID-walk fuzzing and bisecting a fuzz log to the culprit frame
- `fuzz signal`, `fuzz spn` — DBC-signal and J1939-SPN-aware mutation with sentinel coverage
- `fuzz guided` — response-feedback coverage-guided fuzzing with a persisted seed corpus

**Session, export, and utilities**
- `session save`, `load`, `show` — session management
- `export` — structured artifact export
- `doctor` — local environment health checks (Python, `python-can`, vendor backends, caches, MCP, config)
- `mcp serve`, `mcp install` — Model Context Protocol server and client-config helper
- `completion {bash,zsh,fish}` — emit a shell completion script
- `--log-level`, `--quiet` — global stderr logging controls (place before the subcommand)

Default transport backend is `python-can`; set `CANARCHY_TRANSPORT_BACKEND=scaffold` for deterministic offline behavior.

</details>

## The structured contract

Every successful command returns a stable envelope:

```json
{ "ok": true, "command": "capture", "data": {}, "warnings": [], "errors": [] }
```

Failures return structured errors with actionable hints (and a documented [error-code catalog](https://github.com/hexsecs/canarchy/blob/main/docs/troubleshooting.md)):

```json
{
  "ok": false,
  "command": "decode",
  "data": {},
  "warnings": [],
  "errors": [
    { "code": "DBC_LOAD_FAILED", "message": "Failed to parse DBC file.", "hint": "Validate the DBC syntax and line endings." }
  ]
}
```

Use `--candump` for a human-oriented live view; use `--jsonl` when feeding scripts or agents — every line is a typed event from the [canonical schema](https://github.com/hexsecs/canarchy/blob/main/docs/event-schema.md). Set `CANARCHY_PYTHON_CAN_INTERFACE` to choose an interface type, or `CANARCHY_TRANSPORT_BACKEND=scaffold` for deterministic offline behavior.

## Documentation

- [Getting Started](https://github.com/hexsecs/canarchy/blob/main/docs/getting_started.md) · [Cookbook](https://github.com/hexsecs/canarchy/blob/main/docs/cookbook/index.md) — task-oriented recipes
- [Event Schema](https://github.com/hexsecs/canarchy/blob/main/docs/event-schema.md) — the canonical envelope for all structured output
- [Command spec](https://github.com/hexsecs/canarchy/blob/main/docs/command_spec.md) · [Architecture](https://github.com/hexsecs/canarchy/blob/main/docs/architecture.md)
- [CAN Tool Feature Matrix](https://github.com/hexsecs/canarchy/blob/main/docs/feature-matrix.md) — comparison to other OSS CAN tools
- [J1939 Heavy Vehicle Demo](https://github.com/hexsecs/canarchy/blob/main/docs/tutorials/j1939_heavy_vehicle.md) · [Troubleshooting](https://github.com/hexsecs/canarchy/blob/main/docs/troubleshooting.md)
- Full docs site: **[hexsecs.github.io/canarchy](https://hexsecs.github.io/canarchy/)**

## Install from source (development)

CANarchy uses [`uv`](https://docs.astral.sh/uv/) for environment, dependency, and packaging workflows.

```bash
git clone https://github.com/hexsecs/canarchy && cd canarchy
uv sync                          # create the venv and install from the checkout
uv run canarchy --help
uv tool install --editable .     # optional: put `canarchy` on your PATH; edits take effect live
```

Run the test suite end to end:

```bash
uv run python -m unittest discover -s tests -v
```

Shell completions for bash, zsh, and fish come from `canarchy completion <shell>` — see [Getting Started](https://github.com/hexsecs/canarchy/blob/main/docs/getting_started.md#install-shell-completion).

## Community & contributing

CANarchy is GPL-3.0-licensed and welcomes contributions.

- ⭐ **Star the repo** if it's useful — it genuinely helps others find it.
- [Contributing guide](https://github.com/hexsecs/canarchy/blob/main/CONTRIBUTING.md) — local development, branch flow, and PR gates
- [Code of Conduct](https://github.com/hexsecs/canarchy/blob/main/CODE_OF_CONDUCT.md)
- [Security Policy](https://github.com/hexsecs/canarchy/blob/main/SECURITY.md) — reporting concerns and safe active-bus operation

> ⚠️ CANarchy can transmit on live buses. Only operate against vehicles, ECUs, and networks you own or are explicitly authorized to test. Active-transmit commands require explicit acknowledgement by design.

## Philosophy

- The CLI is the contract.
- Protocol semantics over raw frames.
- Structured output over formatted text.
- Reproducible workflows over ad-hoc interaction.

---

<sub>Versioning follows [SemVer](https://semver.org/); see the [changelog](https://github.com/hexsecs/canarchy/blob/main/CHANGELOG.md) and [release workflow](https://github.com/hexsecs/canarchy/blob/main/docs/release.md). `src/canarchy/__init__.py` is the authoritative version source.</sub>
