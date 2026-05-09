# Design Spec: DBC Runtime and Schema Split

## Document Control

| Field | Value |
|-------|-------|
| Status | Complete |
| Command surface | `canarchy decode`, `canarchy encode`, `canarchy dbc inspect` |
| Primary area | CLI, DBC, architecture |
| Related specs | `docs/design/dbc-command-workflows.md`, `docs/design/dbc-inspect-command.md` |

## Goal

Define an internal DBC architecture that preserves CANarchy's stable CLI and event contracts while separating schema-ingestion responsibilities from runtime encode/decode responsibilities.

## User-Facing Motivation

Operators and agents need richer database-aware workflows than the current thin DBC layer provides, but they also need stable outputs. A split architecture lets CANarchy adopt `cantools` where runtime metadata and validation matter, while retaining `canmatrix` for schema ingestion and future conversion-oriented workflows.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-DBCS-01` | Ubiquitous | The system shall preserve the existing `decode` and `encode` command contracts independently of the underlying DBC library implementation. |
| `REQ-DBCS-02` | Ubiquitous | The system shall separate schema-ingestion responsibilities from runtime encode/decode responsibilities behind an internal CANarchy DBC facade. |
| `REQ-DBCS-03` | Event-driven | When the system loads a database for runtime decode, encode, or inspection, it shall expose normalized message and signal metadata without leaking library-specific objects into the command layer. |
| `REQ-DBCS-04` | Event-driven | When future schema-management workflows are implemented, the system shall reserve conversion, normalization, and comparison responsibilities for the schema-ingestion layer. |
| `REQ-DBCS-05` | Unwanted behaviour | If library-specific load, decode, or encode failures occur, the system shall map them to stable CANarchy error codes and exit codes. |
| `REQ-DBCS-06` | State-driven | While both libraries are present in the runtime, the system shall keep one canonical event and JSON output contract for operators and agents. |
| `REQ-DBCS-07` | Optional feature | Where richer metadata-driven workflows are implemented, the system shall use the runtime codec layer to expose signal choices, ranges, units, and validation context. |

## Command Surface

```text
canarchy decode --file <file> --dbc <file> [--json] [--jsonl] [--text]
canarchy decode --stdin --dbc <file> [--json] [--jsonl] [--text]
canarchy encode --dbc <file> <message> <signal=value>... [--json] [--jsonl] [--text]
canarchy dbc inspect <dbc> [--message <name>] [--signals-only] [--json] [--jsonl] [--text]
```

Future schema-management commands are expected to live under a separate `canarchy db ...` namespace.

## Responsibilities And Boundaries

In scope:

* internal separation of schema and runtime responsibilities
* normalized metadata types that abstract over third-party libraries
* migration planning for `decode`, `encode`, and `dbc inspect`

Out of scope:

* exposing user-selectable DBC backends
* preserving raw third-party object models at the command layer
* implementing database authoring workflows

## Architecture Shape

Recommended internal split:

* `canmatrix` as the schema-ingestion layer for load, normalization, conversion, and future database plumbing workflows
* `cantools` as the runtime codec layer for encode, decode, inspection, and metadata-rich validation workflows
* `src/canarchy/dbc.py` as the stable facade consumed by the CLI, REPL, TUI, and MCP server

Suggested internal module boundaries:

* `src/canarchy/dbc.py` — public facade used by commands
* `src/canarchy/dbc_schema.py` — schema-ingestion helpers and source-format normalization
* `src/canarchy/dbc_runtime.py` — runtime encode/decode and inspection helpers
* `src/canarchy/dbc_types.py` — normalized metadata types such as database, message, and signal descriptors

## Data Model

Normalized internal metadata types should include:

* `DatabaseInfo` with path, source format, message count, signal count, and node count
* `MessageInfo` with name, arbitration ID, ID format, frame length, cycle time, senders, and signal count
* `SignalInfo` with name, bit layout, byte order, signedness, scale, offset, min, max, unit, choices, and multiplexer metadata

These normalized types are the contract between the facade and the command layer.

## Output Contracts

The command layer continues to own all human and machine-readable output contracts.

### JSON and JSONL

* `decode` and `encode` shall preserve their existing envelopes and event shapes unless a design spec explicitly expands them
* `dbc inspect` shall emit the metadata structures defined in `docs/design/dbc-inspect-command.md`

### Text

Text formatting remains a command-layer concern and shall not depend on third-party object representations.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DBC_NOT_FOUND` | database file path is missing or unreadable | 3 |
| `DBC_LOAD_FAILED` | database load or parse fails | 3 |
| `DBC_MESSAGE_NOT_FOUND` | named message is absent from the loaded database | 3 |
| `DBC_SIGNAL_INVALID` | a provided signal assignment is invalid for the selected message | 3 |
| `DBC_DECODE_FAILED` | runtime decode fails for a matched frame | 3 |
| `DBC_ENCODE_FAILED` | runtime encode fails for reasons other than invalid signal input | 3 |

## Migration Status

All phases complete as of April 2026:

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Done | Internal metadata types in `dbc_types.py`, facade at `dbc.py`, `DBC_SIGNAL_INVALID` aligned, fixtures expanded |
| Phase 2 | Done | `canarchy dbc inspect` implemented, JSON/JSONL/text outputs, MCP exposed |
| Phase 3 | Done | cantools runtime adapter at `dbc_runtime.py`, decode/encode switched, fixture parity verified |
| Phase 4 | Deferred | canmatrix retained for future schema workflows |
| Phase 5 | Deferred | Evaluate long-term dependency strategy later |

* decide whether `decode` and `encode` should fully switch to the runtime adapter
* remove duplicate adapter paths only after fixture coverage and output-stability checks are satisfactory
* avoid exposing backend selection flags unless there is a demonstrated operator need

## Deferred Decisions

* whether CANarchy should keep both third-party libraries at runtime long term or use one only for migration and schema tooling
* whether `dbc inspect` JSONL metadata events should become part of the global event registry in `docs/event-schema.md`
* whether future schema commands should live under `db` or a broader `schema` namespace
