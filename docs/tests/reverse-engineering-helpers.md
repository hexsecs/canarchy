# Test Spec: Reverse-Engineering Helpers

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Related design spec | `docs/design/reverse-engineering-helpers.md` |
| Primary test area | CLI, analysis |

## Test Objectives

Define the expected coverage for the reverse-engineering helper family so shipped and future implementation work remains traceable to the command contracts and heuristic-output expectations.

## Coverage Requirements

* command-level success coverage for `re signals`, `re counters`, `re entropy`, and `re correlate`
* passive file-backed analysis behavior
* structured candidate output with rationale and confidence or score fields
* representative edge cases for sparse captures, low-sample captures, and mixed arbitration IDs
* structured error handling for missing captures and unsupported correlation references
* human-readable ranked table output for each command

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-RE-01` | `TEST-RE-01`, `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04` |
| `REQ-RE-02` | `TEST-RE-01`, `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04` |
| `REQ-RE-03` | `TEST-RE-01` |
| `REQ-RE-04` | `TEST-RE-02` |
| `REQ-RE-05` | `TEST-RE-03` |
| `REQ-RE-06` | `TEST-RE-04`, `TEST-RE-08` |
| `REQ-RE-07` | `TEST-RE-01`, `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04` |
| `REQ-RE-08` | `TEST-RE-05`, `TEST-RE-06` |
| `REQ-RE-09` | `TEST-RE-04`, `TEST-RE-08` |
| `REQ-RE-10` | `TEST-RE-07`, `TEST-RE-08`, `TEST-RE-09` |

## Representative Test Cases

### `TEST-RE-01` Signal candidate analysis

Action: run `canarchy re signals <fixture> --json`.  
Assert: output includes passive mode, ranked signal candidates, confidence or score fields, and rationale.

### `TEST-RE-02` Counter candidate analysis

Action: run `canarchy re counters <fixture> --json`.  
Assert: output includes candidate fields with monotonicity or rollover evidence.

### `TEST-RE-03` Entropy ranking analysis

Action: run `canarchy re entropy <fixture> --json`.  
Assert: output ranks arbitration IDs or fields by entropy-related values with sample counts.

### `TEST-RE-04` Correlation analysis

Action: run `canarchy re correlate <fixture> --reference <reference> --json`.  
Assert: output includes ranked correlation candidates with correlation strength and rationale.

The reference fixture should use one of the documented supported formats:

* `.json` object with `name` and `samples`
* `.jsonl` sample stream with timestamp/value pairs

### `TEST-RE-05` Table output summaries

Action: run each `re` command with `--table`.  
Assert: output presents a compact ranked summary with visible score or confidence data.

### `TEST-RE-06` JSONL behavior

Action: run each `re` command with `--jsonl`.  
Assert: output matches the documented JSONL contract selected by the implementation.

### `TEST-RE-07` Missing capture error

Action: run a `re` command against a missing capture file.  
Assert: exit code `2` and a structured capture-source error.

### `TEST-RE-08` Missing or unsupported reference input

Action: run `re correlate` without a required reference input or with an unsupported reference format.  
Assert: exit code `1` and a structured correlation-reference error.

This coverage should also include invalid-schema cases where the reference file exists but does not contain timestamped numeric samples, returning `RE_REFERENCE_INVALID`.

### `TEST-RE-09` Low-sample or sparse capture behavior

Action: run `re` helpers against small or low-variance fixtures.  
Assert: the commands degrade gracefully, return empty or low-confidence results, and do not present guesses as facts.

## Fixture Requirements

Planned fixtures should include:

* captures with stable counters
* captures with mixed-entropy fields
* captures with likely analog-like signals
* captures plus `.json` and `.jsonl` reference-series fixtures for correlation
* malformed and low-sample fixtures

Current implementation note:

* `re counters` is covered with fixtures for nibble counters, rollover counters, non-counter noise, and low-sample captures
* `re entropy` is covered with fixtures for constant-byte, alternating-byte, high-entropy, and low-sample arbitration IDs

## Explicit Non-Coverage

* OEM-specific semantics
* active probing/fuzzing during reverse-engineering analysis
* live backend reverse-engineering workflows in the first version

## Traceability

This spec defines the coverage target for the planned reverse-engineering helper implementation and should be refined as concrete candidate schemas and fixtures are chosen.
