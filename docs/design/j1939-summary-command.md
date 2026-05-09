# Design Spec: J1939 Summary Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j1939 summary` |
| Primary area | CLI, protocol |
| Related specs | `docs/design/j1939-expanded-workflows.md`, `docs/design/j1939-bounded-analysis.md` |

## Goal

Provide a reconnaissance-oriented J1939 summary command that helps operators quickly understand what a capture contains before drilling into specific PGNs, SPNs, diagnostics, or transport sessions.

## User-Facing Motivation

Operators often start with the question "what is in this capture and what looks interesting?" A summary command should answer that in one stable, automation-friendly result instead of requiring multiple separate J1939 queries.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1939SUM-01` | Ubiquitous | The system shall provide a `canarchy j1939 summary --file <file>` command for file-backed J1939 capture reconnaissance. |
| `REQ-J1939SUM-02` | Event-driven | When `j1939 summary <file>` is invoked, the system shall report at minimum total frames, interfaces, unique arbitration IDs, first and last timestamps, top PGNs, and top source addresses for the analysed capture window. |
| `REQ-J1939SUM-03` | Event-driven | When `j1939 summary <file>` is invoked, the system shall include a DM1 summary containing whether DM1 traffic is present, how many DM1 messages were observed, and the total active DTC count. |
| `REQ-J1939SUM-04` | Event-driven | When `j1939 summary <file>` is invoked, the system shall include a TP summary containing total TP session count and complete TP session count. |
| `REQ-J1939SUM-05` | Optional feature | Where a completed TP payload decodes cleanly as printable ASCII text, the system shall include that candidate string under a stable structured field in the TP summary. |
| `REQ-J1939SUM-06` | Optional feature | Where `--max-frames` or `--seconds` is specified, the system shall summarise only the bounded capture window. |
| `REQ-J1939SUM-07` | Ubiquitous | The `--json` output for `j1939 summary` shall use stable field names suitable for automation. |

## Command Surface

```text
canarchy j1939 summary --file <capture> [--max-frames <n>] [--seconds <n>] [--json] [--jsonl] [--text] [--raw]
```

## Responsibilities And Boundaries

In scope:

* high-level capture reconnaissance for file-backed J1939 analysis
* top-PGN and top-source-address ranking
* DM1 and TP presence summaries
* candidate printable TP identification strings when a completed payload is obviously printable

Out of scope:

* exhaustive semantic decoding of all TP payloads
* OEM-specific identification heuristics
* multi-capture comparison workflows

## Data Contract

The command returns the standard CANarchy result envelope. `data` for `j1939 summary` includes:

* `mode`
* `file`
* `total_frames`
* `interfaces`
* `unique_arbitration_ids`
* `first_timestamp`
* `last_timestamp`
* `duration_seconds`
* `j1939_frame_count`
* `unique_pgns`
* `top_pgns`
* `top_source_addresses`
* `dm1`
* `tp`

`dm1` includes:

* `present`
* `message_count`
* `active_dtc_count`
* `source_addresses`

`tp` includes:

* `session_count`
* `complete_session_count`
* `session_types`
* `printable_identifiers`

## Output Contracts

`--json` returns a single stable result object. `--text` presents the reconnaissance summary as compact operator-facing lines without dropping the structured field naming in the JSON contract.

## Deferred Decisions

* richer interpretation of TP identification payloads beyond obvious printable ASCII
* exposing top destination addresses or additional ranking dimensions
* promoting the summary metrics into multi-capture comparison workflows
