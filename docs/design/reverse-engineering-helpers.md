# Design Spec: Reverse-Engineering Helpers

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Command surface | `canarchy re signals`, `re counters`, `re entropy`, `re correlate` |
| Primary area | CLI, analysis |

## Goal

Provide evidence-driven reverse-engineering helpers over recorded CAN traffic so operators can identify likely signals, counters, entropy-heavy fields, and correlations without treating heuristics as ground truth.

## User-Facing Motivation

Operators analysing unknown traffic need repeatable helpers that summarise likely structure in captures, highlight rationale, and expose confidence rather than forcing manual byte-by-byte inspection from raw frames alone.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-RE-01` | Ubiquitous | The system shall provide `re signals`, `re counters`, `re entropy`, and `re correlate` commands over capture files. |
| `REQ-RE-02` | Ubiquitous | Each reverse-engineering command shall operate passively on recorded traffic and shall not transmit frames. |
| `REQ-RE-03` | Event-driven | When `re signals <file>` is invoked, the system shall return candidate field boundaries with supporting rationale and confidence metadata. |
| `REQ-RE-04` | Event-driven | When `re counters <file>` is invoked, the system shall return candidate fields that exhibit monotonic incrementing behaviour, including rollover detection and monotonicity evidence. |
| `REQ-RE-05` | Event-driven | When `re entropy <file>` is invoked, the system shall rank arbitration IDs and candidate fields by Shannon entropy derived from observed value distributions. |
| `REQ-RE-06` | Event-driven | When `re correlate <file> --reference <ref>` is invoked, the system shall correlate candidate bit fields against the reference series and return ranked correlation results. |
| `REQ-RE-07` | Ubiquitous | Reverse-engineering output shall include confidence, score, or rationale fields that distinguish heuristic inferences from established facts. |
| `REQ-RE-08` | Ubiquitous | The commands shall support `--json`, `--jsonl`, and `--table` output modes. |
| `REQ-RE-09` | Unwanted behaviour | If `re correlate` is invoked without `--reference`, the system shall return a structured error with code `RE_REFERENCE_REQUIRED` and exit code 1. |
| `REQ-RE-10` | Unwanted behaviour | If the reference file is missing, malformed, or does not match the required timestamped numeric sample schema, the system shall return a structured error with code `RE_REFERENCE_INVALID` and exit code 1. |

## Command Surface

```text
canarchy re signals <file> [--json] [--jsonl] [--table] [--raw]
canarchy re counters <file> [--json] [--jsonl] [--table] [--raw]
canarchy re entropy <file> [--json] [--jsonl] [--table] [--raw]
canarchy re correlate <file> --reference <file> [--json] [--jsonl] [--table] [--raw]
```

### Initial scope assumptions

The first implementation should be file-backed and deterministic. Live capture subscriptions, interactive tuning, and OEM-specific knowledge are explicitly deferred.

## Responsibilities And Boundaries

In scope:

* file-backed heuristic analysis over candump-style captures
* confidence-bearing candidate output
* command-specific summaries over arbitration IDs, bytes, bit ranges, and observed value series

Out of scope:

* declaring inferred fields as authoritative protocol definitions
* OEM-specific reverse-engineering rulesets
* active probing or fuzzing as part of the analysis commands

## Data Model

The initial command family uses explicit result objects under `data` rather than inventing a new global event type.

### Common fields

All reverse-engineering commands shall return:

* `mode: passive`
* `file`
* `analysis`
* `candidate_count`
* `candidates`

Each candidate shall include at least:

* `arbitration_id`
* `score` or `confidence`
* `rationale`

### `re signals`

Signal candidates shall include:

* `start_bit`
* `bit_length`
* `byte_order` when inferable
* `value_shape` summary such as discrete, stepped, or continuous-like

### `re counters`

Counter candidates shall include:

* `start_bit`
* `bit_length`
* `rollover_detected`
* `monotonicity_ratio`

Current implementation note:

* `re counters` is implemented as a deterministic file-backed helper
* the initial heuristic scans nibble- and byte-sized candidate fields at nibble-aligned start bits
* scoring is based on adjacent monotonic increments, explicit rollover detection, and observed value spread

### `re entropy`

Entropy candidates shall include:

* `scope` such as arbitration ID, byte index, or bit range
* `entropy`
* `sample_count`

Current implementation note:

* `re entropy` is implemented as a deterministic file-backed helper
* candidates are ranked per arbitration ID by mean byte entropy descending
* each candidate includes a per-byte breakdown with `byte_position`, `entropy`, and `unique_values`
* IDs with fewer than 10 frames are retained and annotated with `low_sample: true`

### `re correlate`

The initial `re correlate` workflow is file-backed and requires an explicit reference series file.

#### Reference input contract

`--reference` shall point to either:

* a `.json` file containing an object with `name` and `samples`
* a `.jsonl` file containing one sample object per line

Each sample object shall contain:

* `timestamp`: numeric seconds or milliseconds represented consistently within the file
* `value`: numeric value

Optional fields:

* `name`: series name when not supplied by the outer `.json` object
* `units`: operator-facing units metadata

Correlation candidates shall include:

* `reference_name`
* `correlation`
* `lag` when relevant
* `sample_count`

## Output Contracts

### JSON

Commands shall return the standard CANarchy result envelope.

### JSONL

The initial implementation may either emit a single result object line or one candidate object per line. The chosen behavior shall be documented and tested consistently at implementation time.

### Table

Table output shall present compact ranked candidate summaries with confidence/score and rationale visible.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `CAPTURE_SOURCE_UNAVAILABLE` | input capture file is missing | 2 |
| `CAPTURE_SOURCE_INVALID` | input capture file cannot be parsed | 2 |
| `RE_REFERENCE_REQUIRED` | `re correlate` is invoked without a required reference input | 1 |
| `RE_REFERENCE_UNSUPPORTED` | correlation reference input format is unsupported | 1 |
| `RE_REFERENCE_INVALID` | reference file does not match the required timestamped numeric sample schema | 1 |

## Deferred Decisions

* exact candidate schemas and whether they should also be modelled as typed events
* whether `re signals` should emit contiguous-field suggestions, bitfield suggestions, or both in the first version
* threshold and scoring models for counter and entropy ranking
