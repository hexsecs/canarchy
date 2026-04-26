# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Documentation

* Clarified the agent workflow policy so non-trivial work is expected to happen on dedicated branches and be delivered through pull requests by default rather than direct pushes to `main`.
* Added dedicated current-state design and test specs for `j1939 monitor` and `config show`, and aligned the surrounding J1939 spec language with the current `j1939 tp sessions` command surface.

### Added

* Added `canarchy j1939 compare` for multi-capture comparison of J1939 PGNs, source addresses, DM1 fault changes, and printable TP identification payloads across two or more recorded captures.
* Implemented `canarchy re correlate <file> --reference <ref>` to correlate candidate bit fields against a reference time series. Accepts JSON (array or named object with `name`+`samples`) and JSONL reference formats. Each candidate reports `pearson_r`, `spearman_r`, `sample_count`, and `lag_ms` (optimal time offset in [-500, +500] ms). Candidates are ranked by `|pearson_r|` descending. Structured errors are returned for missing `--reference` (`RE_REFERENCE_REQUIRED`), invalid or short reference files (`INVALID_REFERENCE_FILE`), and insufficient capture/reference time-range overlap (`INSUFFICIENT_OVERLAP`). Also exposed as the `re_correlate` MCP tool. Closes #52.
* Added fast-scan path to `capture-info` for large candump files (> 50 MB). The first and last 64 KB are parsed for timestamps and interface/ID samples; frame count is estimated from file size and average line length. The response payload now includes `scan_mode: "full"` (exact) or `scan_mode: "estimated"` (large-file approximation). Closes #163.
* Added automatic frame cap for `j1939 summary`, `j1939 dm1`, `j1939 faults`, `j1939 inventory`, and `j1939 compare` on captures exceeding 50 MB when no `--max-frames` or `--seconds` limit is specified. Analysis is capped at 500,000 frames and a warning is included in the response. Use `--max-frames` or `--seconds` to override. Closes #163.

### Documentation

* Clarified the agent workflow policy so non-trivial work is expected to happen on dedicated branches and be delivered through pull requests by default rather than direct pushes to `main`.
* Documented the new multi-capture `j1939 compare` workflow across the J1939 design/test specs, command reference, and agent-facing command guidance.

## [0.5.0] - 2026-04-25

### Added

* Added `canarchy j1939 inventory` and the `j1939_inventory` MCP tool for building source-address inventories from recorded J1939 captures, including top PGNs, component-identification strings, vehicle-identification strings, and per-node DM1 presence.

### Changed

* GitHub Pages now publishes the custom repository-root homepage at `/`, while the MkDocs documentation site is built and published under `/docs/` so the existing docs home remains available as the documentation landing page.
* Homepage nav and footer links are now real `<a>` tags instead of plain styled divs. The source lives in `src/homepage/` (`index.html` + `site-brutalist.jsx`) and is copied to the site root by the Pages build script — no more binary blob patching.
* The package version has advanced to `0.4.1.dev0` on `main` so post-`0.4.0` work is identified as development builds until the next release is cut.

### Fixed

* The GitHub Pages root homepage now collapses oversized navigation, hero, CTA, content-grid, and footer layouts for mobile viewports so the base page remains readable and usable on phones.
* The GitHub Pages root homepage now scales marquee text, major section headings, selected card titles, and command/transcript blocks down further for common phone widths including iPhone 16 Pro-sized viewports.
* The GitHub Pages root homepage now uses a compact hamburger menu for mobile navigation while preserving the full inline top nav on larger viewports.
* The GitHub Pages homepage MCP tool catalog and agent transcript now wrap long tool names, argument lists, return types, and transcript lines cleanly on narrow mobile screens instead of overflowing horizontally.
* The GitHub Pages homepage tool matrix now switches to a balanced stacked comparison-card layout on mobile instead of forcing the full desktop table off-screen.

### Documentation

* Documented the `j1939 inventory` workflow across the command reference, J1939 design/test specs, MCP docs, and agent-facing command/tool guidance.
* Documented the split GitHub Pages layout and the combined local/CI build flow for the root homepage plus `/docs/` site.
* Corrected the release workflow documentation to keep artifact build and publish steps on the stable release version before `main` advances to the next `.dev0` development version.

## [0.4.0] - 2026-04-24

### Added

* Added `--offset` parameter to all file-backed commands (`filter`, `stats`, `decode`, `j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp`, `j1939 dm1`, `j1939 summary`) to skip the first N frames before processing. Works alongside `--max-frames` to define a processing window.
* Added `--compact` output format to `filter` command for easy data extraction. Emits one JSON object per line with flat frame data (timestamp, interface, arbitration_id, data) without wrapping metadata.
* Added J1939 performance benchmarks with defined budgets and automated tests (`tests/test_j1939_performance.py`). Benchmark fixture generated via `scripts/generate_benchmark_fixture.py`. All J1939 commands meet budget targets on 10k frame capture.
* Added `capture-info` and the `capture_info` MCP tool for fast capture reconnaissance. They return frame count, first/last timestamps, duration, unique IDs, interfaces, and suggested `max_frames`/`seconds` bounds without loading decoded frame data into memory.
* Added `re signals` as a file-backed reverse-engineering helper that ranks 4-bit, 8-bit, and 16-bit signal candidates, reports `low_sample_ids`, and includes per-ID analysis metadata for follow-on inspection.

### Changed

* Standardized CLI argument ordering: file-backed commands now use `--file` flag for capture file input instead of positional arguments. The `--file` argument is required for file-only commands (`stats`, `capture-info`, `replay`, `j1939 tp`, `j1939 dm1`, `j1939 summary`) to prevent unstructured crashes. Commands with stdin support (`filter`, `decode`, `j1939 decode`) can alternatively use `--stdin`.

### Fixed

* `uds scan` and `uds trace` now reassemble ISO-TP multi-frame UDS responses, ignore flow-control frames, and mark partial transactions with `complete=false` when a segmented response is truncated or arrives out of order.
* `--offset` now counts successfully parsed frames rather than file lines, correctly handling files with blank lines, comments, or malformed entries.
* Unparseable candump lines are now silently skipped instead of causing an error, allowing analysis to proceed with valid frames only.
* Added validation for `--max-frames` and `--seconds` on all file-backed commands (`filter`, `stats`, `decode`) to match J1939 command behavior. Invalid values now return `INVALID_MAX_FRAMES` or `INVALID_ANALYSIS_SECONDS` errors.
* `--stdin` mode now rejects `--max-frames` and `--seconds` flags with `ANALYSIS_WINDOW_REQUIRES_FILE` error, since these bounds cannot be applied to stdin input.
* Added `--max-frames` and `--seconds` parameters to `stats`, `filter`, and `decode` commands for working with large capture files. These mirror the existing parameters on J1939 commands.
* Expanded the `filter` expression engine with six new operators: `dlc><n>` (DLC threshold), `data~=<hex>` (payload substring), `extended` (29-bit frames), `standard` (11-bit frames), `&&` (AND), and `||` (OR). All new operators are composable; `&&` binds tighter than `||`. Unrecognised expressions now return error code `INVALID_FILTER_EXPRESSION` instead of the old `FILTER_EXPRESSION_UNSUPPORTED`.

* MCP server now handles SIGINT (Ctrl+C) and SIGTERM gracefully, without traceback or thread errors during shutdown.
* `j1939 pgn --json` now includes decoded signal values in each event's `decoded_signals` field, matching what the table renderer already showed. Previously the JSON output contained only the raw frame bytes with no signal interpretation.
* `j1939 summary` and `j1939 dm1` now report `active_dtc_count` as the number of DTCs that represent actual fault conditions (SPN > 0, FMI not 0 or 31) instead of the total count of DTC slots in the DM1 payload. This prevents captures where every DM1 message contains only no-fault filler entries (e.g. SPN=255/FMI=0) from being reported as having hundreds of active faults.
* J1939 signal decoding now returns `null`/`None` for the `value` field when the raw signal data matches the J1939 not-available pattern (0xFF for 8-bit, 0xFFFF for 16-bit, 0xFFFFFFFF for 32-bit signals) instead of converting the error sentinel into a physically impossible reading. This fix applies to both the curated SPN decoder and the DBC-backed runtime decoder.

## [0.3.0] - 2026-04-20

### Fixed

* Fixed `--jsonl` output for `j1939 spn`, `j1939 tp`, and `j1939 dm1` commands to emit one line per observation/session/message instead of falling back to full JSON payload. The JSONL emitter now checks for `observations`, `sessions`, and `messages` in addition to `events`.
* Fixed `j1939 dm1 --json` and `--jsonl` to keep deprecated SPN conversion-mode warnings out of plain-text stdout output. DM1 now reports that condition once through structured warnings while preserving the parsed `conversion_method` field per DTC.

### Changed

* Introduced a J1939 decoder abstraction between the CLI and the current curated helper implementation so `j1939 decode`, `j1939 spn`, `j1939 tp`, and `j1939 dm1` can move to a library-backed decoder in follow-on work without changing the command surface.
* Switched J1939 identifier decomposition and DM1 DTC parsing to use `can-j1939` helpers under the existing command surface, and routed file-backed `j1939 pgn` through the new decoder abstraction.
* Moved `j1939 spn`, `j1939 tp`, and `j1939 dm1` execution into the `can-j1939` decoder adapter so all file-backed J1939 decode commands now run through the same backend boundary even though SPN coverage and TP semantics remain intentionally limited.
* Added optional J1939 DBC enrichment for `j1939 decode`, `j1939 pgn`, and `j1939 spn`, including `dbc_source` provenance, extra decoded `dbc_events`, and a reusable default J1939 DBC setting via `CANARCHY_J1939_DBC` or `[j1939].dbc` in `~/.canarchy/config.toml`.
* Expanded `j1939 spn` beyond the curated starter map by resolving non-curated SPNs from J1939 DBC signal `SPN` metadata when a matching DBC is supplied or configured as the default J1939 database.
* Extended the same J1939 DBC coverage idea into `j1939 dm1` so DTC names and units can be enriched from DBC signal `SPN` metadata, with the same `--dbc` and default J1939 DBC config path used by other J1939 decode workflows.
* Deepened the J1939 transport and DM1 path beyond the earlier BAM-only starter behavior so `j1939 tp` and `j1939 dm1` now handle RTS/CTS sessions in addition to BAM, including reassembly and session-level acknowledgement metadata.
* File-backed J1939 decode paths now stream candump input line-by-line instead of reading the whole capture text into memory up front, and the hot `j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp`, and `j1939 dm1` paths now use single-pass iteration where DBC enrichment does not require a retained frame list.
* File-backed `j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp`, and `j1939 dm1` now accept `--max-frames` and `--seconds` bounds so operators can scope large-capture analysis to an initial frame window or time window without scanning the entire file.
* Added `j1939 summary` for capture reconnaissance, including top PGNs and source addresses, DM1 and TP presence metrics, timestamp coverage, and candidate printable TP payload identifiers when completed sessions contain obvious ASCII text.
* Enhanced `j1939 tp` to expose heuristic printable-text decoding and known identification-style payload labels alongside the existing raw reassembled TP payload hex.

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
