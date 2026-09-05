# Design Spec: Comparison Identifier Types

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy compare`, MCP `compare` |
| Primary area | Capture analysis, result schema |
| Related specs | [Command specification](../command_spec.md#compare) |

## Goal

Preserve standard/extended CAN identifier identity throughout capture comparisons (#500).

## User-Facing Motivation

Standard `123` and extended `00000123` in candump are distinct identifiers. Merging them hides presence changes and mixes timing, rate, and entropy measurements.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| REQ-COMPARE-ID-01 | Ubiquitous | The comparison engine shall group data frames by `(arbitration_id, is_extended_id)` and compute metrics and flags independently for each pair. |
| REQ-COMPARE-ID-02 | Ubiquitous | The system shall expose `is_extended_id` in every comparison row and count identifier pairs in `id_count` and `summary.unique_ids`. |
| REQ-COMPARE-ID-03 | Ubiquitous | The system shall retain sorted, deduplicated numeric category lists and expose parallel sorted typed identifier lists covering all findings. |
| REQ-COMPARE-ID-04 | Optional feature | Where `--top` limits output, the system shall limit rows only, using descending change score, ascending numeric ID, and standard-before-extended order to break ties. |
| REQ-COMPARE-ID-05 | Unwanted behaviour | If a row represents a standard identifier, the system shall omit J1939 annotations. |
| REQ-COMPARE-ID-06 | Ubiquitous | The CLI and MCP comparison results shall preserve the same identifier identity fields. |

## Command Surface

Existing `compare` arguments and output modes remain as documented in the command specification.

## Responsibilities And Boundaries

The comparison engine owns grouping and output metadata. Parser behavior, other analysis commands, channel grouping, and protocol classification of extended frames are outside this fix. Remote/error frames remain excluded from comparison groups.

## Data Model

Each row adds `is_extended_id: bool`. The existing numeric `arbitration_id` and hexadecimal display fields remain unchanged.

## Output Contracts

For each category (`new`, `dropped`, `rate_drop`, `rate_spike`, `entropy_collapse`, `timing_drift`), the summary includes both `<category>_ids` and `<category>_identifiers`. The latter contains objects such as `{"arbitration_id": 291, "is_extended_id": true}`. Numeric lists cannot distinguish type and remain compatibility views. All summary lists cover uncapped results; typed lists sort by numeric ID then type. Existing JSON/JSONL/text rendering and MCP envelopes carry these additive fields through the shared result path.

## Error Contracts

No new errors. Existing comparison input validation and transport errors remain unchanged.

## Deferred Decisions

Channel-aware comparisons and similar identity changes in other analysis commands require separate issues.
