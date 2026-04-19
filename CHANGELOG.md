# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
