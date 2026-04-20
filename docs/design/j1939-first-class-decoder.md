# Design Spec: First-Class J1939 Decoder

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Command surface | `canarchy j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp`, `j1939 dm1` |
| Primary area | CLI, protocol, DBC |
| Related specs | `docs/design/j1939-expanded-workflows.md`, `docs/design/dbc-command-workflows.md`, `docs/design/transport-core-commands.md` |

## Goal

Replace the current curated J1939 helper path with a library-backed decoder built around `can-j1939`, while preserving CANarchy's existing CLI contract and structured output modes. The decoder should provide protocol-correct PGN, SPN, TP, and DM1 behavior and optionally enrich signal-level decode with operator-supplied J1939 DBC files.

Phase 1 is implemented: the CLI now consumes a decoder abstraction. Phase 2 is partially implemented: file-backed `j1939 decode` and `j1939 pgn` route through that abstraction, and the underlying identifier and DTC parsing paths use `can-j1939` helpers. Phase 3 is partially implemented: `j1939 spn`, `j1939 tp`, and `j1939 dm1` now execute through a `can-j1939`-backed decoder adapter instead of thin CLI wrappers over the legacy helper functions. The TP/DM1 path now handles both BAM and RTS/CTS transport sessions rather than the earlier BAM-only starter behavior. Phase 4 is partially implemented: `j1939 decode`, `j1939 pgn`, `j1939 spn`, and `j1939 dm1` accept optional DBC enrichment through `--dbc <path|provider-ref>` or a configured default J1939 DBC path. `j1939 spn` can now resolve non-curated SPNs from DBC signal SPN metadata when the requested SPN is not present in the starter map.

## User-Facing Motivation

Operators need J1939 commands that scale beyond a demo-only SPN map. They should be able to inspect standard J1939 traffic, multi-packet transfers, and DM1 diagnostics with protocol-correct semantics, and optionally supply a `j1939.dbc` file to improve names, units, scaling, and signal coverage without changing command workflows.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1939F-01` | Ubiquitous | The system shall provide a J1939 decoder abstraction so CLI commands do not depend directly on the current curated helper implementation. |
| `REQ-J1939F-02` | Event-driven | When `j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp`, or `j1939 dm1` is invoked against a capture or live stream, the system shall use a library-backed J1939 decoder implementation for protocol parsing. |
| `REQ-J1939F-03` | Event-driven | When a J1939 transport-protocol message spans multiple frames, the system shall reassemble the payload before protocol-aware decode and expose the resulting session state through `j1939 tp` and dependent commands such as `j1939 dm1`. |
| `REQ-J1939F-04` | Event-driven | When `j1939 dm1` is invoked, the system shall decode direct and transport-protocol-carried DM1 payloads into structured diagnostic messages without relying on the current BAM-only toy parser. |
| `REQ-J1939F-05` | Optional feature | Where `--dbc <path|provider-ref>` is specified for a J1939 decode workflow, the system shall enrich protocol-aware results with DBC-backed signal metadata and values when the supplied DBC contains a matching J1939 definition. |
| `REQ-J1939F-10` | Optional feature | Where no `--dbc` flag is supplied and a default J1939 DBC is configured through `CANARCHY_J1939_DBC` or `[j1939].dbc`, the system shall use that configured DBC for J1939 DBC enrichment workflows. |
| `REQ-J1939F-06` | Event-driven | When `j1939 spn <spn>` is invoked, the system shall resolve the requested SPN through the library-backed metadata path and optional DBC input rather than limiting decode to the current curated starter map. |
| `REQ-J1939F-07` | Ubiquitous | The system shall preserve the existing command names and standard output modes (`--json`, `--jsonl`, `--table`, `--raw`) while upgrading the decoder implementation. |
| `REQ-J1939F-08` | Unwanted behaviour | If the configured J1939 decoder backend cannot be initialized, the system shall return a structured error with code `J1939_DECODER_UNAVAILABLE` and exit code `3`. |
| `REQ-J1939F-09` | Unwanted behaviour | If `j1939 spn <spn>` is requested and neither the library metadata nor an optional DBC can resolve that SPN, the system shall return a structured error with code `J1939_SPN_NOT_FOUND` and exit code `1`. |

## Command Surface

```text
canarchy j1939 decode <capture> [--dbc <path|provider-ref>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 pgn <pgn> --file <capture> [--dbc <path|provider-ref>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 spn <spn> --file <capture> [--dbc <path|provider-ref>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 tp <capture> [--json] [--jsonl] [--table] [--raw]
canarchy j1939 dm1 <capture> [--dbc <path|provider-ref>] [--json] [--jsonl] [--table] [--raw]

# optional defaults
# ~/.canarchy/config.toml
[j1939]
dbc = "tests/fixtures/j1939_sample.dbc"
```

## Responsibilities And Boundaries

In scope:

* decoder abstraction between CLI and protocol implementation
* `can-j1939` integration for PGN/SPN/TP/DM1 semantics
* optional DBC enrichment for J1939 signal metadata and values
* stable CANarchy output shaping above the decoder layer

Out of scope:

* replacing CANarchy's transport and capture layers with a library-owned CLI
* exposing the full raw `can-j1939` API directly to operators
* OEM-specific diagnostics beyond what standard J1939 metadata and supplied DBCs describe

## Data Model

The upgraded decoder keeps CANarchy command envelopes and output modes, but changes how J1939 facts are produced internally.

### Decoder abstraction

The command layer should consume a decoder interface that returns protocol-shaped records for:

* PGN observations
* SPN observations
* TP session summaries
* DM1 messages

### DBC enrichment fields

Where a J1939 DBC is supplied and matches the decoded PGN, SPN, or DM1-carried SPN references, enriched records may include:

* DBC-derived signal name
* units
* scaling or value metadata
* enum or choice text when available
* `dbc_source` provenance, using the existing DBC-provider model
* `dbc_events` carrying cantools-decoded message and signal events for the selected J1939 frame subset
* DTC-level name and unit enrichment for `j1939 dm1` when a DBC signal `SPN` attribute matches the reported diagnostic SPN

### Precedence model

Protocol identity comes from the J1939 decoder backend. DBC input enriches names and signal metadata when it provides a matching definition, but it does not replace J1939 transport semantics, addressing rules, or session tracking. For `j1939 spn`, DBC signal `SPN` metadata can also supply the SPN definition itself when the starter map does not define that SPN. For `j1939 dm1`, DBC signal `SPN` metadata can fill DTC names and units when the reported SPN is not covered by the starter map. CLI `--dbc` takes precedence over `CANARCHY_J1939_DBC`, which takes precedence over `[j1939].dbc` in the config file.

## Output Contracts

### JSON

J1939 commands shall continue returning the standard CANarchy result envelope. Data payloads should expose the same high-level command sections (`events`, `observations`, `sessions`, `messages`) while allowing richer protocol and DBC-derived fields inside those records.

### JSONL

`j1939 decode` shall continue emitting one event line per decoded J1939 observation. `j1939 spn`, `j1939 tp`, and `j1939 dm1` shall emit one decoded object per line, with optional DBC-enriched fields where applicable.

### Table

Human-readable output shall remain protocol-first, showing PGNs, SPNs, source and destination addressing, TP session progress, and DM1 diagnostic content without forcing operators back to raw frame-only views.

### Raw

Raw mode shall preserve current command-name-on-success behavior unless a command already defines a more specific raw contract.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `J1939_DECODER_UNAVAILABLE` | selected library-backed decoder cannot be initialized | 3 |
| `J1939_SPN_NOT_FOUND` | requested SPN cannot be resolved through the decoder metadata path or optional DBC | 1 |

## Deferred Decisions

* whether `--dbc` should be accepted by all J1939 subcommands in the first rollout or phased into `decode`, `pgn`, `spn`, and `dm1` first
* whether the initial integration should run behind a feature flag before becoming the default decoder
* how much of `canarchy.j1939` remains as thin compatibility wrappers versus being replaced outright
