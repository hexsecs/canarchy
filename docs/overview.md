# Project Overview

CANarchy is a CLI-first CAN security research toolkit for reproducible, protocol-aware, automation-friendly workflows.

Core principles:

* the CLI is the contract
* structured output is a first-class interface
* J1939 is treated as a primary workflow, not an afterthought
* front ends should stay thin and reuse the same core engine

## Current Capabilities

Implemented and exercised in the current codebase:

* scaffolded and opt-in live transport workflows for `capture` and `send`
* file-backed `filter`, `stats`, `decode`, `j1939 decode`, and `replay` using candump logs
* DBC-backed decode and encode
* J1939 `monitor`, `decode`, `pgn`, `spn`, `tp`, and `dm1`
* UDS `scan` and `trace`
* session `save`, `load`, and `show`
* structured `export` for capture files and saved sessions
* shell command reuse through `canarchy shell --command ...`
* initial text-mode `tui` shell over the shared command layer
* structured `--json`, `--jsonl`, `--table`, and `--raw` output modes

## Current Gaps

Present in the CLI tree but still scaffolded or placeholder-only:

* `uds services`
* `re signals`, `re counters`, `re entropy`, and `re correlate`
* `fuzz replay`, `fuzz mutate`, and `fuzz id`

## Recommended Reading

* [Command Spec](command_spec.md) for the current CLI contract
* [Architecture](architecture.md) for system layout and design rules
* [Docs Workflow](docs_site.md) for local preview and publishing details
* [Agent Guide](agents.md) for repository-specific automation guidance
