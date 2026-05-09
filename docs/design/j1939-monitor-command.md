# Design Spec: J1939 Monitor Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j1939 monitor` |
| Primary area | CLI, protocol, transport |
| Related specs | `docs/design/j1939-first-class-decoder.md`, `docs/design/mcp-server.md`, `docs/design/tui-shell.md` |

## Goal

Define the current implemented behavior of the live `j1939 monitor` workflow so its sample-provider path, transport-backed path, filtering behavior, and output modes are documented as a first-class command contract.

## User-Facing Motivation

Operators need a fast way to inspect live or sample J1939 traffic as PGN-oriented observations without dropping to raw arbitration IDs or needing a capture file first.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1939MON-01` | Ubiquitous | The system shall provide a `canarchy j1939 monitor [<interface>] [--pgn <id>]` command for live or sample J1939 observation. |
| `REQ-J1939MON-02` | State-driven | While `j1939 monitor` is invoked without an interface argument, the system shall use the sample/reference provider and report that implementation in the structured result. |
| `REQ-J1939MON-03` | Event-driven | When `j1939 monitor <interface>` is invoked, the system shall use the transport-backed monitor path and include the selected interface in the structured result. |
| `REQ-J1939MON-04` | Optional feature | Where `--pgn <id>` is specified, the system shall restrict emitted observations to the selected PGN and echo the filter value in the structured result. |
| `REQ-J1939MON-05` | Ubiquitous | The `j1939 monitor` result envelope shall expose passive-mode metadata plus J1939 observation events rather than raw-frame-only output. |
| `REQ-J1939MON-06` | Ubiquitous | `j1939 monitor` shall preserve the standard output modes (`--json`, `--jsonl`, `--text`, `--raw`) with command-specific formatting over the same observation stream. |

## Command Surface

```text
canarchy j1939 monitor [<interface>] [--pgn <id>] [--json] [--jsonl] [--text] [--raw]
```

## Responsibilities And Boundaries

In scope:

* passive J1939 observation output for sample and live monitor paths
* optional PGN filtering
* stable structured result metadata describing interface and implementation mode

Out of scope:

* file-backed capture analysis, which belongs to `j1939 decode`, `j1939 pgn`, `j1939 summary`, and related commands
* decode enrichment through DBC files
* transport-configuration reporting, which belongs to `config show`

## Data Model

The top-level `data` payload includes:

* `mode`
* `interface`
* `pgn_filter`
* `implementation`
* `events`

Each event is a J1939 PGN observation whose payload includes protocol-first fields such as:

* `pgn`
* `source_address`
* `destination_address`
* `priority`
* `frame`

## Output Contracts

### JSON

`--json` emits the standard CANarchy result envelope with `data.events` populated by J1939 observation events.

### JSONL

`--jsonl` emits one serialized J1939 observation event per line, followed by any warning events if warnings are present.

### Table

`--text` renders protocol-first observation lines, including PGN, source address, destination address, priority, and frame data, and shows the active `pgn_filter` when one is applied.

### Raw

`--raw` prints `j1939 monitor` on success.

## Error Contracts

No command-specific error codes are defined for `j1939 monitor`. Generic transport and CLI usage errors apply when the selected live transport path cannot run.

## Deferred Decisions

* whether additional live filters beyond `--pgn` should be exposed
* whether future live monitor views should surface richer derived protocol summaries alongside the event stream
