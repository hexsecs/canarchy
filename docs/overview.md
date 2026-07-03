# Project Overview

CANarchy is a CLI-first CAN security research toolkit for reproducible, protocol-aware, automation-friendly workflows.

Core principles:

* the CLI is the contract
* structured output is a first-class interface
* J1939 is treated as a primary workflow, not an afterthought
* front ends should stay thin and reuse the same core engine

## Current Capabilities

Implemented and exercised in the current codebase:

* `python-can`-backed live transport workflows plus deterministic scaffold transport for `capture`, `send`, `generate`, and `simulate`
* file-backed `filter`, `stats`, `compare`, `capture-info`, `decode`, `j1939 decode`, and `replay` using candump logs
* `sequence replay` for coordinated transmit of a YAML/JSON sequence of DBC-encoded frames
* live `gateway` bridging between CAN interfaces via `python-can`
* database-backed `decode`, `encode`, `dbc inspect`, `dbc convert`, and `dbc generate-c` across DBC / ARXML / KCD / SYM, including provider-ref resolution and `dbc_source` provenance in structured output
* DBC provider and cache workflows for catalog search, fetch, and refresh through the optional opendbc integration
* J1939 `monitor`, `decode`, `pgn`, `spn`, `tp`, `dm1`, `faults`, `summary`, `inventory`, `compare`, and `map`
* UDS `scan`, `trace`, `services`, `subservices`, `ecu-reset`, `tester-present`, `security-seed`, `dump-dids`, `read-memory`, and `auto`
* DoIP `discovery`, `services`, `ecu-reset`, `tester-present`, `security-seed`, and `dump-dids` for Diagnostic-over-IP workflows
* XCP-on-CAN `scan`, `info`, `dump`, `trace`, `read`, and `commands`
* J1587/J1708 and J2497 (PLC4TRUCKS) passive decode workflows for legacy heavy-vehicle buses
* reverse-engineering helpers: `re signals`, `re counters`, `re entropy`, `re correlate`, `re anomalies`, `re corpus`, `re match-dbc`, `re shortlist-dbc`, and `re suggest`
* active-transmit fuzzing (`fuzz payload`, `replay`, `arbitration-id`, `signal`, `spn`, `guided`, `identify`) behind the active-transmit safety model
* public CAN dataset provider workflows for search, inspect, fetch, download, convert, stream, and replay
* repository-backed skills provider workflows for discovering, fetching, caching, and referencing agent-oriented CANarchy skills
* Python entry-point `plugins` inspection and toggles
* session `save`, `load`, and `show`
* structured `export` for capture files and saved sessions
* shell command reuse through `canarchy shell --command ...`
* a full-screen Textual `tui` dashboard and a read-only `web serve` browser dashboard over the shared command layer
* `config show` for effective transport configuration inspection
* structured `--json`, `--jsonl`, and `--text` output modes

Some protocol-oriented commands still use explicit sample/reference providers rather than true transport-backed execution. See [Architecture](architecture.md) and [Command Spec](command_spec.md) for the current boundary.

## Current Gaps

Not fully implemented yet even where the command surface exists:

* deeper live transport integration beyond the current `python-can` transport path
* follow-up active-transmit safety controls (configurable rate-cap ceiling, TOML target allowlist, explicit `KILL_SWITCH_TRIGGERED` alert)

## Recommended Reading

* [Command Spec](command_spec.md) for the current CLI contract
* [Architecture](architecture.md) for system layout and design rules
* [Docs Workflow](docs_site.md) for local preview and publishing details
* [Agent Guide](agents.md) for repository-specific automation guidance
