# Design Spec: Reverse-Engineering Helpers

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Command surface | `canarchy re signals`, `re counters`, `re entropy`, `re correlate`, `re match-dbc`, `re shortlist-dbc` |
| Primary area | CLI, analysis |

## Goal

Provide evidence-driven reverse-engineering helpers over recorded CAN traffic so operators can identify likely signals, counters, entropy-heavy fields, candidate DBC matches, and future correlations without treating heuristics as ground truth.

## User-Facing Motivation

Operators analysing unknown traffic need repeatable helpers that summarise likely structure in captures, highlight rationale, and expose confidence rather than forcing manual byte-by-byte inspection from raw frames alone.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-RE-01` | Ubiquitous | The system shall provide `re signals`, `re counters`, `re entropy`, `re correlate`, `re match-dbc`, and `re shortlist-dbc` commands over capture files. |
| `REQ-RE-02` | Ubiquitous | Each reverse-engineering command shall operate passively on recorded traffic and shall not transmit frames. |
| `REQ-RE-03` | Event-driven | When `re signals <file>` is invoked, the system shall return candidate field boundaries with supporting rationale and confidence metadata. |
| `REQ-RE-04` | Event-driven | When `re counters <file>` is invoked, the system shall return candidate fields that exhibit monotonic incrementing behaviour, including rollover detection and monotonicity evidence. |
| `REQ-RE-05` | Event-driven | When `re entropy <file>` is invoked, the system shall rank arbitration IDs and candidate fields by Shannon entropy derived from observed value distributions. |
| `REQ-RE-06` | Event-driven | When `re correlate <file> --reference <ref>` is invoked, the system shall correlate candidate bit fields against the reference series and return ranked correlation results. |
| `REQ-RE-07` | Ubiquitous | Reverse-engineering output shall include confidence, score, or rationale fields that distinguish heuristic inferences from established facts. |
| `REQ-RE-08` | Ubiquitous | The commands shall support `--json`, `--jsonl`, and `--table` output modes. |
| `REQ-RE-09` | Unwanted behaviour | If `re correlate` is invoked without `--reference`, the system shall return a structured error with code `RE_REFERENCE_REQUIRED` and exit code 1. |
| `REQ-RE-10` | Unwanted behaviour | If the reference file is missing, malformed, or does not match the required timestamped numeric sample schema, the system shall return a structured error with code `RE_REFERENCE_INVALID` and exit code 1. |
| `REQ-RE-11` | Event-driven | When `re match-dbc <capture>` is invoked, the system shall rank candidate DBCs by comparing provider-catalog message IDs against the capture's observed arbitration IDs. |
| `REQ-RE-12` | Event-driven | When `re shortlist-dbc <capture> --make <brand>` is invoked, the system shall pre-filter provider-catalog candidates by make before ranking them against the capture. |

## Command Surface

```text
canarchy re signals <file> [--json] [--jsonl] [--table] [--raw]
canarchy re counters <file> [--json] [--jsonl] [--table] [--raw]
canarchy re entropy <file> [--json] [--jsonl] [--table] [--raw]
canarchy re correlate <file> --reference <file> [--json] [--jsonl] [--table] [--raw]
canarchy re match-dbc <capture> [--provider <name>] [--limit <n>] [--json] [--jsonl] [--table] [--raw]
canarchy re shortlist-dbc <capture> --make <brand> [--provider <name>] [--limit <n>] [--json] [--jsonl] [--table] [--raw]
```

### Initial scope assumptions

The first implementation should be file-backed and deterministic. Live capture subscriptions, interactive tuning, and OEM-specific knowledge are explicitly deferred.

Current implementation note:

* `re signals`, `re counters`, `re entropy`, `re match-dbc`, and `re shortlist-dbc` are implemented as deterministic file-backed helpers
* `re correlate` remains deferred

## Responsibilities And Boundaries

In scope:

* file-backed heuristic analysis over candump-style captures
* confidence-bearing candidate output
* command-specific summaries over arbitration IDs, bytes, bit ranges, and observed value series
* provider-backed DBC candidate ranking against capture arbitration IDs

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

* an identifier appropriate to the candidate family, such as `arbitration_id` or `source_ref`
* `score` or `confidence` when the helper returns ranked candidates
* `rationale` when the helper emits heuristic justification

### `re signals`

Signal candidates shall include:

* `arbitration_id`
* `start_bit`
* `bit_length`
* `score`
* `rationale`
* `sample_count`
* `observed_min`
* `observed_max`
* `change_rate`

Current implementation note:

* `re signals` is implemented as a deterministic file-backed helper
* the initial heuristic evaluates nibble-aligned 4-bit fields, byte-aligned 8-bit fields, and word-aligned 16-bit fields
* IDs with fewer than 5 frames are omitted from the candidate list and recorded in `low_sample_ids`
* result metadata includes `analysis_by_id` summaries with `frame_count`, `payload_bits`, `evaluated_fields`, and per-ID `candidate_count`

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

### `re match-dbc`

DBC match candidates shall include:

* `name`
* `source_ref`
* `score`
* `matched_ids`
* `total_capture_ids`

Current implementation note:

* `re match-dbc` is implemented as a deterministic file-backed helper
* candidate scoring is frequency-weighted by captured arbitration-ID occurrence, not just unique ID overlap
* the default provider is `opendbc`

### `re shortlist-dbc`

Shortlist candidates shall use the same output shape as `re match-dbc` with additional request metadata for the selected make filter.

Current implementation note:

* `re shortlist-dbc` is implemented as a deterministic file-backed helper
* `--make` is required and narrows provider-catalog candidates before scoring

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
* threshold and scoring models for counter and entropy ranking
