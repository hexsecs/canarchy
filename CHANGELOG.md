# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

* Fixed `--jsonl` output for `j1939 spn`, `j1939 tp`, and `j1939 dm1` commands to emit one line per observation/session/message instead of falling back to full JSON payload. The JSONL emitter now checks for `observations`, `sessions`, and `messages` in addition to `events`.

### Changed

* Introduced a J1939 decoder abstraction between the CLI and the current curated helper implementation so `j1939 decode`, `j1939 spn`, `j1939 tp`, and `j1939 dm1` can move to a library-backed decoder in follow-on work without changing the command surface.
* Switched J1939 identifier decomposition and DM1 DTC parsing to use `can-j1939` helpers under the existing command surface, and routed file-backed `j1939 pgn` through the new decoder abstraction.
* Moved `j1939 spn`, `j1939 tp`, and `j1939 dm1` execution into the `can-j1939` decoder adapter so all file-backed J1939 decode commands now run through the same backend boundary even though SPN coverage and TP semantics remain intentionally limited.
* Added optional J1939 DBC enrichment for `j1939 decode`, `j1939 pgn`, and `j1939 spn`, including `dbc_source` provenance, extra decoded `dbc_events`, and a reusable default J1939 DBC setting via `CANARCHY_J1939_DBC` or `[j1939].dbc` in `~/.canarchy/config.toml`.
* Expanded `j1939 spn` beyond the curated starter map by resolving non-curated SPNs from J1939 DBC signal `SPN` metadata when a matching DBC is supplied or configured as the default J1939 database.
* Extended the same J1939 DBC coverage idea into `j1939 dm1` so DTC names and units can be enriched from DBC signal `SPN` metadata, with the same `--dbc` and default J1939 DBC config path used by other J1939 decode workflows.

### Documentation

* Added planned design and test specs for moving J1939 onto a first-class library-backed decoder with optional J1939 DBC enrichment, documenting the intended `can-j1939` integration path and CLI/test expectations.
* Added dedicated design and test specs for the provider-backed DBC workflow, covering provider listing, catalog search, fetch, cache management, provider-ref resolution, `dbc_source` provenance, and `auto_refresh` behavior.
* Updated the command reference to document the shipped `generate` command plus current `--stdin` and `--ack-active` command-surface details where the docs had drifted from the implementation.
* Corrected several requirement-to-test traceability tables so the current spec set no longer overstates coverage for transport, UDS, J1939, shell, gateway, and generate workflows.
* Updated the J1939 heavy-vehicle tutorial so its `jq` example matches the current `j1939 spn --jsonl` output shape and no longer queries stale `.payload.*` fields.

## [0.2.0] - 2026-04-19

### Added

* opendbc as an optional DBC provider backed by the `dbc_provider`, `dbc_provider_local`, `dbc_cache`, and `dbc_opendbc` modules; providers are selected via `--provider` flags and configured in `~/.canarchy/config.toml`.
* CLI commands: `dbc provider list`, `dbc search`, `dbc fetch`, `dbc cache list`, `dbc cache prune`, and `dbc cache refresh` for discovering, downloading, and managing DBC files from opendbc.
* `--dbc opendbc:<name>` provider-ref syntax accepted by `decode`, `encode`, and `dbc inspect` for resolving DBC files directly from the opendbc cache.
* `format_dbc_table` and `format_dbc_provider_table` helpers for `--table` output when listing DBC files and providers.
* `comma:<name>` as a convenience alias for `opendbc:<name>` in provider refs (matches Comma.ai community naming).

* `re match-dbc <capture> [--provider opendbc] [--limit 10]` — ranks all locally-cached DBC files against a capture file using a frequency-weighted ID coverage score; returns the top N candidates sorted by score descending.
* `re shortlist-dbc <capture> --make <brand> [--provider opendbc] [--limit 10]` — same as `re match-dbc` but pre-filters candidates by vehicle brand before scoring.
* `score_dbc_candidates()` scoring function in `reverse_engineering.py` — pure function that accepts a `capture_ids` frequency map and a pre-built catalog; no network calls or file I/O at score time.

* `DBC_CACHE_MISS` error now includes a copy-pasteable `canarchy dbc cache refresh --provider opendbc` command and a hint about the `auto_refresh` config option.
* `auto_refresh` opt-in for `[dbc.providers.opendbc]` in `~/.canarchy/config.toml`: when `true`, the first `resolve()` call on a cold cache triggers `refresh()` automatically instead of raising `DBC_CACHE_MISS`. Defaults to `false` for offline safety.

* `decode`, `encode`, and `dbc inspect` now include a `dbc_source` field in `CommandResult.data` reporting the provider, DBC name, pinned version, and resolved local path. Provider refs (`opendbc:<name>`) include a commit SHA version; local file refs include `provider: "local"` and `version: null`.

### Changed

* `dbc inspect` now uses the internal `cantools` runtime adapter while preserving the existing CLI, MCP, and structured output contracts for the current fixtures.
* Added an internal `cantools`-backed DBC runtime adapter that maps database metadata into CANarchy-owned types for fixture-level comparison work.
* The DBC inspection path now uses CANarchy-owned metadata types internally so command-layer outputs no longer depend directly on third-party database objects.
* Active transmit commands now emit their safety prompt to `stderr` before transmission begins, and `--ack-active` triggers an explicit confirmation prompt before transmission proceeds.

### Fixed

* Invalid signal assignments for `encode --dbc ...` now return the documented `DBC_SIGNAL_INVALID` error code instead of a generic encode failure.

### Documentation

* Refreshed the reverse-engineering design and test specs to distinguish the shipped helpers (`re counters`, `re entropy`, `re match-dbc`, `re shortlist-dbc`) from still-deferred `re signals` and `re correlate` work.
* Refreshed tutorials and comparison docs to add a provider-backed DBC workflow tutorial, update tutorial discoverability, and align the feature matrix with the shipped reverse-engineering and DBC-provider capabilities.
* Refreshed `docs/command_spec.md`, `docs/agents.md`, and related operator/spec docs to reflect the current DBC provider workflows, `dbc_source` provenance, reverse-engineering DBC matching commands, and the current curated MCP tool surface.
* Updated `docs/architecture.md` to reflect the current DBC provider/cache/provenance subsystem and the shipped reverse-engineering DBC-matching commands.
* Added planning specs for a future `dbc inspect` command and a phased DBC runtime/schema split using a stable CANarchy facade.
* Reorganized the docs site top navigation into header tabs, added a dedicated Tutorials section, and introduced a Tutorials landing page for the J1939 and generate/capture walkthroughs.
* Migrated all design specs (`docs/design/*.md`) to EARS requirements syntax with an explicit Type column per requirement row.
* Migrated all test specs (`docs/tests/*.md`) to Gherkin Given/When/Then format with fixture annotations.
* Added `docs/spec-template.md` as the canonical template for all future design and test specs.
* Added `docs/tests/composition.md` — new test spec for the stdin piping composition feature.
* Added active-command safety design and test specs covering preflight warnings, confirmation prompts, and `--ack-active` acknowledgement gating.
* Updated `AGENTS.md` to reference `docs/spec-template.md` and document the EARS + Gherkin standard as the required format for new specs.

## [0.1.2] - 2026-04-19

### Added

* Reverse-engineering helpers for file-backed likely counter detection with `re counters`.
* Reverse-engineering helpers for file-backed per-ID and per-byte entropy ranking with `re entropy`.

### Changed

* Transport architecture now separates deterministic scaffold transport behavior from explicit sample/reference protocol providers.
* `j1939 monitor`, `uds scan`, and `uds trace` now have initial transport-backed paths when `python-can` is selected.
* Project version metadata now uses `src/canarchy/__init__.py` as the single authoritative version source.

### Documentation

* Refreshed architecture, backend, command, and feature-comparison docs to match the current implementation.
* Added MkDocs Mermaid support, theme toggles, and missing nav entries.

## [0.1.1] - 2026-04-19

### Fixed

* Corrected license metadata from MIT to GPL-3.0-or-later to match the actual LICENSE file.

## [0.1.0] - 2026-04-19

### Added

* Core CLI workflows for capture, send, filter, stats, generate, gateway, replay, decode, encode, export, session save/load/show, shell, and TUI.
* J1939 workflows for monitor, decode, PGN inspection, SPN inspection, transport protocol inspection, and DM1 inspection.
* UDS workflows for scan, trace, and service catalog inspection.
* MCP server support with `canarchy mcp serve` for exposing implemented commands as MCP tools over stdio.
* Structured output modes across the command surface with JSON, JSONL, table, and raw views.

### Changed

* Default transport backend set to `python-can` with scaffold retained for deterministic offline behavior.
* Documentation and specs reconciled with the current backend and command implementation state.

### Fixed

* MkDocs now renders Mermaid diagrams correctly and keeps them aligned with the active site theme.

### Documentation

* Added feature comparison and architecture diagrams.
* Added release/versioning guidance and expanded design/test specs.
