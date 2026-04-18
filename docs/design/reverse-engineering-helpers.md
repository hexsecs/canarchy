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

Operators analyzing unknown traffic need repeatable helpers that summarize likely structure in captures, highlight rationale, and expose confidence rather than forcing manual byte-by-byte inspection from raw frames alone.

## Requirements

| ID | Requirement |
|----|-------------|
| `REQ-RE-01` | The system shall provide `re signals`, `re counters`, `re entropy`, and `re correlate` commands over capture files. |
| `REQ-RE-02` | Each reverse-engineering command shall operate passively on recorded traffic and shall not transmit frames. |
| `REQ-RE-03` | `re signals` shall return candidate field boundaries with supporting rationale and confidence metadata. |
| `REQ-RE-04` | `re counters` shall identify byte or bit fields that behave like likely counters and shall expose rollover or monotonicity evidence. |
| `REQ-RE-05` | `re entropy` shall rank arbitration IDs or candidate fields by entropy-related characteristics derived from observed values. |
| `REQ-RE-06` | `re correlate` shall correlate candidate fields against a supplied reference series file and shall report correlation strength. |
| `REQ-RE-07` | Reverse-engineering output shall distinguish heuristics from facts by including confidence, score, or rationale fields. |
| `REQ-RE-08` | The commands shall support structured JSON output suitable for downstream automation and human-readable table summaries. |
| `REQ-RE-09` | `re correlate` shall require an explicit `--reference <file>` input whose samples are timestamped numeric values. |
| `REQ-RE-10` | Invalid inputs or unsupported correlation sources shall return structured user or analysis errors. |

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

The initial command family should use explicit result objects under `data` rather than inventing a new global event type immediately.

### Common fields

All reverse-engineering commands should return:

* `mode: passive`
* `file`
* `analysis`
* `candidate_count`
* `candidates`

Each candidate should include at least:

* `arbitration_id`
* `score` or `confidence`
* `rationale`

### `re signals`

Signal candidates should include:

* `start_bit`
* `bit_length`
* `byte_order` when inferable
* `value_shape` summary such as discrete, stepped, or continuous-like

### `re counters`

Counter candidates should include:

* `start_bit`
* `bit_length`
* `rollover_detected`
* `monotonicity_ratio`

Current implementation note:

* `re counters` is implemented as a deterministic file-backed helper
* the initial heuristic scans nibble- and byte-sized candidate fields at nibble-aligned start bits
* current scoring is based on adjacent monotonic increments, explicit rollover detection, and observed value spread

### `re entropy`

Entropy candidates should include:

* `scope` such as arbitration ID, byte index, or bit range
* `entropy`
* `sample_count`

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

Representative `.json` form:

```json
{
  "name": "vehicle_speed",
  "units": "kph",
  "samples": [
    {"timestamp": 0.0, "value": 0.0},
    {"timestamp": 0.1, "value": 2.0}
  ]
}
```

Representative `.jsonl` form:

```jsonl
{"name":"vehicle_speed","timestamp":0.0,"value":0.0}
{"name":"vehicle_speed","timestamp":0.1,"value":2.0}
```

The implementation should treat the reference series as an ordered numeric time series and align candidate field samples against it using the chosen correlation strategy.

Correlation candidates should include:

* `reference_name`
* `correlation`
* `lag` when relevant
* `sample_count`

## Output Contracts

### JSON

Commands should return the standard CANarchy result envelope.

### JSONL

The initial implementation may either:

* emit a single result object line when using result-only output, or
* emit one candidate object per line if the implementation adopts candidate-event streaming

The chosen behavior should be documented and tested consistently at implementation time.

### Table

Table output should present compact ranked candidate summaries with confidence/score and rationale visible.

### Raw

Raw output should follow the standard command-success/error behavior unless a stronger operator need emerges.

## Error Contracts

Planned structured errors include:

| Code | Trigger | Exit code |
|------|---------|-----------|
| `CAPTURE_SOURCE_UNAVAILABLE` | input capture file is missing | 2 |
| `CAPTURE_SOURCE_INVALID` | input capture file cannot be parsed | 2 |
| `RE_REFERENCE_REQUIRED` | `re correlate` is invoked without a required reference input | 1 |
| `RE_REFERENCE_UNSUPPORTED` | correlation reference input format is unsupported | 1 |
| `RE_REFERENCE_INVALID` | reference file does not match the required timestamped numeric sample schema | 1 |

## Deferred Decisions

* exact candidate schemas and whether they should also be modeled as typed events
* whether `re signals` should emit contiguous-field suggestions, bitfield suggestions, or both in the first version
* threshold and scoring models for counter and entropy ranking
