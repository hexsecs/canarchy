# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

* Active transmit commands now emit their safety prompt to `stderr` before transmission begins, and `--ack-active` triggers an explicit confirmation prompt before transmission proceeds.

### Documentation

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
