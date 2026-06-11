# Test Spec: Reverse-Engineering Helpers

## Document Control

| Field | Value |
|-------|-------|
| Status | Current |
| Related design spec | `docs/design/reverse-engineering-helpers.md` |
| Primary test area | CLI, analysis |

## Test Objectives

Define the expected coverage for the reverse-engineering helper family so shipped and future implementation work remains traceable to the command contracts and heuristic-output expectations.

## Coverage Requirements

* command-level success coverage for shipped helpers: `re signals`, `re counters`, `re entropy`, `re correlate`, `re match-dbc`, and `re shortlist-dbc`
* passive file-backed analysis behavior
* structured candidate output with rationale and confidence or score fields
* representative edge cases for sparse captures, low-sample captures, and mixed arbitration IDs
* warning and limit behavior for provider-backed DBC matching workflows
* structured error handling for missing captures, missing or malformed reference files, and insufficient overlap
* human-readable ranked text output for each shipped helper

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-RE-01` | `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04`, `TEST-RE-05` |
| `REQ-RE-02` | `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04`, `TEST-RE-05` |
| `REQ-RE-03` | `TEST-RE-01`, `TEST-RE-06`, `TEST-RE-08`, `TEST-RE-11` |
| `REQ-RE-04` | `TEST-RE-02` |
| `REQ-RE-05` | `TEST-RE-03` |
| `REQ-RE-06` | `TEST-CORR-01`, `TEST-CORR-02`, `TEST-CORR-03` |
| `REQ-RE-07` | `TEST-RE-02`, `TEST-RE-03`, `TEST-RE-04`, `TEST-RE-05` |
| `REQ-RE-08` | `TEST-RE-06`, `TEST-RE-07` |
| `REQ-RE-09` | `TEST-CORR-07` |
| `REQ-RE-10` | `TEST-CORR-04` |
| `REQ-RE-11` | `TEST-RE-04`, `TEST-RE-05`, `TEST-RE-08`, `TEST-RE-09` |
| `REQ-RE-12` | `TEST-RE-05` |
| `REQ-RE-13` | `TEST-RE-12`, `TEST-RE-13` |
| `REQ-RE-14` | `TEST-RE-12`, `TEST-RE-13` |
| `REQ-RE-15` | `TEST-RE-14`, `TEST-RE-15` |
| `REQ-RE-16` | `TEST-RE-13` |
| `REQ-RE-17` | `TEST-RE-16`, `TEST-RE-17` |
| `REQ-RE-18` | `TEST-RE-18`, `TEST-RE-19` |
| `REQ-RE-19` | `TEST-RE-20`, `TEST-RE-21` |
| `REQ-RE-20` | `TEST-RE-22`, `TEST-RE-23` |

## Representative Test Cases

### `TEST-RE-01` — Signal candidate analysis

```gherkin
Given  a capture fixture with stable, high-change, and mid-range candidate fields is available
When   the operator runs `canarchy re signals <fixture> --json`
Then   the result shall include ranked signal candidates with change-rate and observed-range metadata
And    sparse arbitration IDs shall be omitted from the candidate list and recorded in `low_sample_ids`
```

**Fixture:** `tests/fixtures/re_signals_mixed.candump`.

---

### `TEST-RE-02` — Counter candidate analysis

```gherkin
Given  a capture fixture containing monotonically incrementing nibble or byte fields is available
When   the operator runs `canarchy re counters <fixture> --json`
Then   the result shall include candidate fields
And    each candidate shall include monotonicity evidence and rollover detection metadata
```

**Fixture:** capture file with nibble and byte counter fields.

---

### `TEST-RE-03` — Entropy ranking analysis

```gherkin
Given  a capture fixture with mixed-entropy arbitration IDs and fields is available
When   the operator runs `canarchy re entropy <fixture> --json`
Then   the result shall rank arbitration IDs or fields by entropy-related values
And    each entry shall include a sample count
```

**Fixture:** capture file with mixed-entropy fields.

---

### `TEST-RE-04` — DBC match analysis

```gherkin
Given  a capture fixture and a provider-backed DBC catalog are available
When   the operator runs `canarchy re match-dbc <fixture> --json`
Then   the result shall include ranked DBC candidates
And    each candidate shall include `name`, `source_ref`, `score`, `matched_ids`, and `total_capture_ids`
```

**Fixture:** capture file and mocked or cached provider catalog.

---

### `TEST-RE-05` — DBC shortlist analysis

```gherkin
Given  a valid capture fixture and provider catalog are available
When   the operator runs `canarchy re shortlist-dbc <fixture> --make <brand> --json`
Then   the result shall include shortlist candidates filtered by make
And    the response data shall record the selected `make`
```

**Fixture:** capture file and mocked or cached provider catalog.

---

### `TEST-RE-06` — Text output summaries for shipped helpers

```gherkin
Given  a valid capture fixture is available
When   the operator runs a shipped `re` helper with `--text`
Then   the output shall present a compact ranked summary
And    score or confidence data shall be visible in the table
```

**Fixture:** capture file appropriate to the shipped helper.

---

### `TEST-RE-07` — JSONL behavior for shipped helpers

```gherkin
Given  a valid capture fixture is available
When   the operator runs a shipped `re` helper with `--jsonl`
Then   the output shall match the documented JSONL contract selected by the implementation
```

**Fixture:** capture file appropriate to the shipped helper.

---

### `TEST-RE-08` — Missing capture error

```gherkin
Given  the specified capture file does not exist
When   the operator runs any `re` command against the missing file
Then   the command shall exit with code `2`
And    the error shall be a structured capture-source error
```

**Fixture:** none (missing file path).

---

### `TEST-RE-09` — Empty-catalog warning behavior for DBC matching

```gherkin
Given  no provider-catalog candidates are available for DBC matching
When   the operator runs `canarchy re match-dbc <fixture> --json`
Then   the command shall still succeed
And    the result shall contain a warning explaining that no candidates were available
```

**Fixture:** capture file and an empty mocked catalog.

---

### `TEST-RE-10` — Match limit behavior

```gherkin
Given  more candidate DBCs are available than the requested limit
When   the operator runs `canarchy re match-dbc <fixture> --limit <n> --json`
Then   no more than `<n>` candidates shall be returned
```

**Fixture:** capture file and mocked catalog larger than the requested limit.

---

### `TEST-RE-11` — Low-sample or sparse capture behavior

```gherkin
Given  a capture fixture with very few frames or low field variance is available
When   the operator runs any `re` command against the sparse capture
Then   the command shall not exit with an error
And    the result shall return empty or low-confidence candidates
And    no candidates shall be presented as authoritative facts
```

**Fixture:** small or low-variance candump fixture.

---

### `TEST-RE-12` — Baseline-driven anomaly detection

```gherkin
Given  an input capture and a separate baseline capture are available
And    the input has a cyclic id with a gross timing glitch, a new id, and a dropped id
When   the operator runs `canarchy re anomalies <input> --baseline <baseline> --json`
Then   the result mode shall be "baseline"
And    the candidates shall include a `timing` anomaly for the glitched id with |z| ≥ the threshold
And    the candidates shall include an `unknown-id` for the new id and a `dropped-id` for the missing id
```

**Fixture:** `anomaly_input.candump`, `anomaly_baseline.candump`.

---

### `TEST-RE-13` — Self-consistency anomaly detection resists outlier masking

```gherkin
Given  an input capture whose cyclic id contains a single large timing glitch
When   the operator runs `canarchy re anomalies <input> --json` (no baseline)
Then   the result mode shall be "self-consistency"
And    the glitch shall be flagged as a `timing` anomaly (median/MAD statistics prevent self-masking)
And    no `unknown-id` or `dropped-id` anomalies shall be emitted
```

**Fixture:** `anomaly_input.candump`.

---

### `TEST-RE-14` — Event traffic is not falsely flagged (CV guard)

```gherkin
Given  a capture mixing a cyclic id with an event-based id (bursts then long silences)
When   the operator runs `canarchy re anomalies <capture> --json`
Then   the event id shall appear in `event_ids` and not produce any timing anomaly
And    the cyclic id shall appear in `cyclic_ids`
```

**Fixture:** `anomaly_event_mix.candump`.

---

### `TEST-RE-15` — DBC send type overrides timing classification

```gherkin
Given  a capture where an event id happens to look periodic
And    a DBC marks that id with a non-cyclic send type
When   the operator runs `canarchy re anomalies <capture> --dbc <dbc> --json`
Then   `timing_source` shall be "dbc"
And    the event id shall be classified as event and excluded from timing analysis
And    a cyclic id declared in the DBC shall still be timing-checked
```

**Fixture:** `anomaly_dbc_capture.candump`, `anomaly_timing.dbc`.

---

### `TEST-CORR-01` — Correlation candidate analysis (happy path)

```gherkin
Given  a capture fixture containing a linearly-varying byte field is available
And    a matching reference series file (JSON) is available with the same linear values
When   the operator runs `canarchy re correlate <fixture> --reference <ref> --json`
Then   the result shall include at least one candidate for the linear field
And    the candidate shall have pearson_r ≈ 1.0 and spearman_r ≈ 1.0
And    the candidate shall include arbitration_id, start_bit, bit_length, sample_count, and lag_ms
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump`, `tests/fixtures/re_correlate_reference.json`.

---

### `TEST-CORR-02` — JSONL reference format

```gherkin
Given  a capture fixture and a reference series in JSONL format (.jsonl) are available
When   the operator runs `canarchy re correlate <fixture> --reference <ref.jsonl> --json`
Then   the result shall include candidates without error
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump`, `tests/fixtures/re_correlate_reference.jsonl`.

---

### `TEST-CORR-03` — Named reference series

```gherkin
Given  a reference series JSON object with a top-level 'name' field is available
When   the operator runs `canarchy re correlate <fixture> --reference <named-ref> --json`
Then   the result data shall include a 'reference_name' field matching the name in the file
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump`, `tests/fixtures/re_correlate_reference_named.json`.

---

### `TEST-CORR-04` — Text output for re correlate

```gherkin
Given  a valid capture fixture and reference series are available
When   the operator runs `canarchy re correlate <fixture> --reference <ref> --text`
Then   the output shall present ranked candidates
And    each candidate line shall include pearson_r, spearman_r, and lag_ms
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump`, `tests/fixtures/re_correlate_reference.json`.

---

### `TEST-CORR-05` — Missing --reference returns structured error

```gherkin
Given  a valid capture fixture is available
When   the operator runs `canarchy re correlate <fixture> --json` without --reference
Then   the command shall exit with code 1
And    the error shall have code RE_REFERENCE_REQUIRED
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump`.

---

### `TEST-CORR-06` — Missing or malformed reference file returns structured error

```gherkin
Given  the specified reference file does not exist or is not valid JSON
When   the operator runs `canarchy re correlate <fixture> --reference <bad-ref> --json`
Then   the command shall exit with code 1
And    the error shall have code INVALID_REFERENCE_FILE
```

**Fixture:** missing path or `tests/fixtures/re_correlate_reference_malformed.json`.

---

### `TEST-CORR-07` — Reference with fewer than 10 samples returns structured error

```gherkin
Given  a reference file containing fewer than 10 samples is available
When   the operator runs `canarchy re correlate <fixture> --reference <short-ref> --json`
Then   the command shall exit with code 1
And    the error shall have code INVALID_REFERENCE_FILE
```

**Fixture:** `tests/fixtures/re_correlate_reference_short.json`.

---

### `TEST-CORR-08` — Insufficient time overlap returns structured error

```gherkin
Given  a capture fixture and a reference series with non-overlapping timestamps are used
When   `correlate_candidates()` is called directly
Then   a ReferenceSeriesError with code INSUFFICIENT_OVERLAP shall be raised
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump` with a synthetic ReferenceData at non-overlapping timestamps.

---

### `TEST-CORR-09` — Missing capture file returns transport error

```gherkin
Given  the specified capture file does not exist
When   the operator runs `canarchy re correlate <missing> --reference <ref> --json`
Then   the command shall exit with code 2
And    the error shall have code CAPTURE_SOURCE_UNAVAILABLE
```

**Fixture:** none (missing file path), `tests/fixtures/re_correlate_reference.json`.

---

## Fixture Requirements

Fixtures should include:

* captures with stable counters
* captures with mixed-entropy fields
* captures sufficient for DBC-candidate ranking against mocked or cached provider catalogs
* malformed and low-sample fixtures
* a capture with a linearly-varying byte field and a matching reference series for correlation tests
* anomaly fixtures: an input/baseline pair with timing glitches and id-presence differences (`anomaly_input.candump`, `anomaly_baseline.candump`), an event-traffic mix (`anomaly_event_mix.candump`), and a DBC-classification pair (`anomaly_dbc_capture.candump`, `anomaly_timing.dbc`)

Current implementation note:

* `re signals` is covered with a mixed capture containing stable fields, a mid-range candidate, a high-change field, and a low-sample arbitration ID
* `re counters` is covered with fixtures for nibble counters, rollover counters, non-counter noise, and low-sample captures
* `re entropy` is covered with fixtures for constant, alternating, high-entropy, and low-sample arbitration IDs
* `re match-dbc` and `re shortlist-dbc` are covered with mocked provider catalogs for output shape, warnings, and limit handling
* `re correlate` is covered with a linear-field capture, three reference formats (JSON array, named JSON object, JSONL), a short reference, and a malformed reference

## Explicit Non-Coverage

* OEM-specific semantics
* active probing/fuzzing during reverse-engineering analysis
* live backend reverse-engineering workflows in the first version

## Traceability

This spec defines the coverage target for the current shipped reverse-engineering helpers and the deferred helpers that remain to be implemented.

---

### `TEST-RE-16` — J1939 candidates carry PGN / source-address annotation

```gherkin
Given  a capture containing EBC2 (PGN 65215) frames from source address 11
When   `entropy_candidates`, `counter_candidates`, or `corpus_analysis` run over it
Then   the EBC2 candidate shall carry `pgn: 65215`, `pgn_label: "EBC2"`, `source_address: 11`, and `source_address_name: "Brakes - System Controller"`
And    every candidate shall carry `arbitration_id_hex`
```

**Fixture:** `tests/fixtures/re_j1939_tp_mix.candump`.

---

### `TEST-RE-17` — Non-J1939 candidates omit annotation gracefully

```gherkin
Given  a capture of 11-bit arbitration ids
When   `entropy_candidates` runs over it
Then   no candidate shall carry `pgn` or `source_address` fields
```

**Fixture:** `tests/fixtures/re_entropy_mixed.candump`.

---

### `TEST-RE-18` — TP framing is not reported as counters or signals

```gherkin
Given  a capture mixing TP.CM/TP.DT streams (with sequence numbers) and a genuine application counter
When   `counter_candidates` and `signal_analysis` run over it
Then   neither TP id shall appear among the candidates
And    the application counter shall still be found
And    `signal_analysis` shall report both TP ids under `excluded_transport_ids` with their PGN labels
```

**Fixture:** `tests/fixtures/re_j1939_tp_mix.candump`.

---

### `TEST-RE-19` — TP entropy candidates are labeled as transport

```gherkin
Given  the same TP-mix capture
When   `entropy_candidates` runs over it
Then   the TP.DT candidate shall carry `j1939_transport: true`
And    its rationale shall mention transport-protocol framing
```

**Fixture:** `tests/fixtures/re_j1939_tp_mix.candump`.

---

### `TEST-RE-20` — Sparse bursty ids are reported low-rate, not ranked

```gherkin
Given  a no-baseline capture with a sparse bursty diagnostic id (7 gaps, tight median)
When   `anomaly_candidates` runs in self-consistency mode
Then   `min_samples` shall default to 10
And    the sparse id shall not appear among the candidates
And    it shall be listed in `low_rate_ids` with classification source `low-sample`
And    passing `min_samples=3` shall restore scoring for that id
```

**Fixture:** `tests/fixtures/anomaly_sparse_burst.candump`.

---

### `TEST-RE-21` — Reported z-scores are capped

```gherkin
Given  a well-sampled cyclic id with one 100 s dropout (raw z-score ~100000σ)
When   `anomaly_candidates` runs in self-consistency mode
Then   the flagged candidate's `z_score` and `score` shall not exceed 100
And    `z_score_capped` shall be `true` and the rationale shall say "capped"
```

**Fixture:** `tests/fixtures/anomaly_sparse_burst.candump`.

---

### `TEST-RE-22` — RE commands accept both capture-path forms

```gherkin
Given  a valid capture file
When   each `re` command is invoked with `--file <capture>` instead of the positional path
Then   the command shall succeed identically to the positional form
When   both forms are supplied with different paths
Then   a structured `CONFLICTING_FILE_ARGUMENTS` error shall be returned
When   neither form is supplied
Then   a structured `CAPTURE_FILE_REQUIRED` error shall be returned
And    `re corpus` shall accept repeated `--file` flags merged with positional paths
```

**Fixture:** `tests/fixtures/re_entropy_mixed.candump`, `tests/fixtures/re_signals_mixed.candump`.

---

### `TEST-RE-23` — Correlate candidates and per-id analysis rows carry hex ids

```gherkin
Given  a capture and reference series with correlating fields
When   `correlate_candidates` runs
Then   every candidate shall carry `arbitration_id_hex` matching its `arbitration_id`
When   `signal_analysis` runs over a capture
Then   every `analysis_by_id` row shall carry `arbitration_id_hex`
```

**Fixture:** `tests/fixtures/re_correlate_linear.candump`, `tests/fixtures/re_signals_mixed.candump`.
