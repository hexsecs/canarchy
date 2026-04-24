# Project Overview

CANarchy is a CLI-first CAN security research toolkit for reproducible, protocol-aware, automation-friendly workflows.

Core principles:

* the CLI is the contract
* structured output is a first-class interface
* J1939 is treated as a primary workflow, not an afterthought
* front ends should stay thin and reuse the same core engine

## Current Capabilities

Implemented and exercised in the current codebase:

* `python-can`-backed live transport workflows plus deterministic scaffold transport for `capture` and `send`
* file-backed `filter`, `stats`, `decode`, `j1939 decode`, and `replay` using candump logs
* DBC-backed `decode`, `encode`, and `dbc inspect`, including provider-ref resolution and `dbc_source` provenance in structured output
* DBC provider and cache workflows for catalog search, fetch, and refresh through the optional opendbc integration
* J1939 `monitor`, `decode`, `pgn`, `spn`, `tp`, and `dm1`
* UDS `scan`, `trace`, and `services`
* `re signals` for file-backed signal candidate inference
* `re counters` for file-backed likely-counter detection
* `re entropy` for file-backed per-ID and per-byte entropy ranking
* `re match-dbc` and `re shortlist-dbc` for provider-backed DBC candidate ranking against captures
* session `save`, `load`, and `show`
* structured `export` for capture files and saved sessions
* shell command reuse through `canarchy shell --command ...`
* initial text-mode `tui` shell over the shared command layer
* `config show` for effective transport configuration inspection
* structured `--json`, `--jsonl`, `--table`, and `--raw` output modes

Some protocol-oriented commands still use explicit sample/reference providers rather than true transport-backed execution. See [Architecture](architecture.md) and [Command Spec](command_spec.md) for the current boundary.

## Current Gaps

Present in the CLI tree but not yet implemented end to end:

* `re correlate`
* `fuzz replay`, `fuzz mutate`, and `fuzz id`

## Recommended Reading

* [Command Spec](command_spec.md) for the current CLI contract
* [Architecture](architecture.md) for system layout and design rules
* [Docs Workflow](docs_site.md) for local preview and publishing details
* [Agent Guide](agents.md) for repository-specific automation guidance
