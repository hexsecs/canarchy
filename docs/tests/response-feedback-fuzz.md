# Test Spec: Response-Feedback Guided Fuzzing (`fuzz guided`)

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/response-feedback-fuzz.md` |
| Test files | `tests/test_fuzz_guided.py`, `tests/test_fuzz_archive.py` |

## Requirement Traceability

| Requirement | Description summary | TEST IDs |
|-------------|--------------------|----------|
| Observation model | Markers derived per category, filtered by `--signals` | `TEST-GF-01`, `TEST-GF-02`, `TEST-GF-03` |
| Scoring function | Only previously-unseen markers score | `TEST-GF-04` |
| Seed scoring determinism | Fixed seed → identical campaign | `TEST-GF-06` |
| New-behaviour discovery | Reactive target yields findings | `TEST-GF-05` |
| Lineage pruning | Corpus capped at `--max-corpus` | `TEST-GF-07` |
| Kill-switch mid-campaign | Kill-switch ends the run | `TEST-GF-08` |
| Corpus persistence | Save/load round-trips the corpus | `TEST-GF-09` |
| CLI dry-run / errors | Plan-only and structured errors | `TEST-GF-10`, `TEST-GF-11`, `TEST-GF-12` |
| Active-transmit safety + MCP gate | Active run + MCP `ack_active` gate | `TEST-GF-13`, `TEST-GF-14` |
| Rate pacing bounded by budget | A pacing delay crossing `--max-seconds` ends the run without a further transmission; pacing precedes each transmission | `TEST-GF-15`, `TEST-GF-16` |
| Extended-id inference | A 29-bit `--id` without `--extended` runs as an extended frame; an out-of-range id is a structured error | `TEST-GF-17`, `TEST-GF-18`, `TEST-GF-19` |
| REQ-GFA-01, REQ-GFA-02, REQ-GFA-07 | Pruned findings remain inspectable with payload and response evidence | TEST-GFA-01 |
| REQ-GFA-03 | Explicit manifest and result metadata | TEST-GFA-02 |
| REQ-GFA-04 | Fail closed on storage errors; preserve earlier records | TEST-GFA-03 |
| REQ-GFA-05 | Interruptions retain evidence and report archive path | TEST-GFA-04 |
| REQ-GFA-06 | Dry-run has no archive or transmissions | TEST-GFA-05 |

## Test Cases

### TEST-GF-01 — UDS NRC marker

```gherkin
Given  a response that is a UDS negative response (0x7F 0x27 0x35)
When   it is fingerprinted with the nrc signal enabled
Then   the fingerprint shall contain the marker `nrc:27:35`
```

**Fixture:** none.

---

### TEST-GF-02 — Silence marker

```gherkin
Given  a silent observation
When   it is fingerprinted with the silence signal enabled
Then   the fingerprint shall contain the marker `silence`
```

**Fixture:** none.

---

### TEST-GF-03 — `--signals` filters marker categories

```gherkin
Given  a UDS negative response
When   it is fingerprinted with only the timing signal enabled
Then   the fingerprint shall contain a timing marker and no nrc marker
```

**Fixture:** none.

---

### TEST-GF-04 — Tracker scores only new markers

```gherkin
Given  a fingerprint scored once against a fresh tracker
When   the same fingerprint is scored again
Then   the first score shall be positive and the second shall be zero
```

**Fixture:** none.

---

### TEST-GF-05 — Reactive target yields new behaviours

```gherkin
Given  a mocked responder that returns varying NRCs for high-byte payloads
When   a 300-iteration campaign runs
Then   the result shall record more than one finding and more than one unique marker
```

**Fixture:** in-test reactive responder.

---

### TEST-GF-06 — Determinism under a fixed seed

```gherkin
Given  the same mocked responder and rng seed
When   the campaign runs twice
Then   the iteration count, finding count, unique markers, and per-finding markers shall match
```

**Fixture:** in-test reactive responder.

---

### TEST-GF-07 — Lineage pruning caps the corpus

```gherkin
Given  a productive responder and `--max-corpus 8`
When   a 400-iteration campaign runs
Then   the final corpus shall hold at most 8 seeds
```

**Fixture:** in-test reactive responder.

---

### TEST-GF-08 — Kill-switch stops mid-campaign

```gherkin
Given  a kill-switch that fires after five checks
When   a campaign with a 300-iteration budget runs
Then   the run shall stop with reason kill_switch after at most six iterations
```

**Fixture:** in-test kill-switch.

---

### TEST-GF-09 — Corpus persistence round-trip

```gherkin
Given  a completed campaign's corpus
When   it is saved to a directory and reloaded
Then   a lineage.json manifest shall exist and the reloaded seed count shall match
```

**Fixture:** temporary directory.

---

### TEST-GF-10 — CLI dry-run plans without a transport

```gherkin
Given  `--dry-run`
When   `canarchy fuzz guided --id 0x123 --dry-run --json` is invoked
Then   the envelope shall report mode dry_run with planned mutations and open no transport
```

**Fixture:** none.

---

### TEST-GF-11 — Invalid `--signals` returns a structured error

```gherkin
Given  an unknown feedback signal name
When   `canarchy fuzz guided --id 0x123 --signals nope --json` is invoked
Then   the system shall exit 1 with `FUZZ_GUIDED_INVALID_SIGNALS`
```

**Fixture:** none.

---

### TEST-GF-12 — Invalid `--id` returns a structured error

```gherkin
Given  a non-numeric arbitration id
When   `canarchy fuzz guided --id not-an-id --json` is invoked
Then   the system shall exit 1 with `FUZZ_GUIDED_INVALID_ID`
```

**Fixture:** none.

---

### TEST-GF-13 — Active campaign over the scaffold backend

```gherkin
Given  the scaffold backend and `CANARCHY_MCP_NONINTERACTIVE_ACK=1`
When   `canarchy fuzz guided vcan0 --id 0x123 --ack-active --max-iterations 20 --json` is invoked
Then   the envelope shall report mode active, 20 iterations, and stop_reason max_iterations
```

**Fixture:** scaffold transport backend.

---

### TEST-GF-14 — MCP tool is active-transmit gated

```gherkin
Given  the MCP `fuzz_guided` tool
When   it is called without `ack_active=true`
Then   the system shall refuse with `ACTIVE_TRANSMIT_REQUIRES_ACK` before any transport call
And    its argv builder shall default to `--dry-run`
```

**Fixture:** none.

---

### TEST-GF-15 — Pacing re-checks the budget before transmitting

```gherkin
Given  an injected clock and sleep where the pacing delay advances the clock past max_seconds
When   `run_guided_fuzz` runs with `pace_seconds` larger than the remaining `max_seconds`
Then   the system shall transmit nothing and stop with stop_reason max_seconds
```

**Fixture:** in-process counting responder with injected `clock` / `sleep`.

---

### TEST-GF-16 — Pacing delays each transmission

```gherkin
Given  an injected sleep recorder and `pace_seconds` set
When   `run_guided_fuzz` runs for three transmissions
Then   the system shall apply one pacing delay before each of the three transmissions
```

**Fixture:** in-process reactive responder with an injected `sleep`.

---

### TEST-GF-17 — 29-bit `--id` without `--extended` runs as an extended frame

```gherkin
Given  the scaffold backend and `CANARCHY_MCP_NONINTERACTIVE_ACK=1`
When   `canarchy fuzz guided vcan0 --id 0x18DAF110 --ack-active --max-iterations 2 --json` is invoked
Then   the envelope shall report mode active with `extended` true (no uncaught error)
```

**Fixture:** scaffold transport backend.

---

### TEST-GF-18 — Dry-run infers the extended flag for a 29-bit id

```gherkin
Given  a 29-bit `--id` and `--dry-run`
When   `canarchy fuzz guided --id 0x18DAF110 --dry-run --json` is invoked
Then   the planned campaign shall report `extended` true
```

**Fixture:** none.

---

### TEST-GF-19 — `--id` outside the 29-bit range returns a structured error

```gherkin
Given  an `--id` above the 29-bit CAN id ceiling
When   `canarchy fuzz guided --id 0x20000000 --dry-run --json` is invoked
Then   the system shall exit 1 with error code `FUZZ_GUIDED_INVALID_ID`
```

**Fixture:** none.

## Archive Regression Cases

### TEST-GFA-01 — Findings outlive the corpus

```gherkin
Given two distinct findings, max_corpus one, and mutations exceeding max_payload
When the run prunes a finding and the surviving corpus is saved and reloaded
Then the system shall retain both exact clamped inputs, observations, markers and lineage in the archive
And a new campaign shall have a separate namespace despite seed IDs restarting at s0
```

**Fixture:** `test_pruned_findings_survive_corpus_reload_and_new_campaign`, temporary corpus/archive directories and deterministic responder.

### TEST-GFA-02 — CLI/MCP provenance

```gherkin
Given a fake transport producing two findings
When the active CLI campaign completes
Then the system shall report campaign ID, archive path and finding count
And the manifest shall contain explicit tool/schema, target, feedback and timing configuration
And the MCP argv builder shall accept findings_dir while retaining dry-run by default
```

**Fixture:** `test_cli_manifest_and_output`, `test_mcp_findings_directory_preserves_safety_default`.

### TEST-GFA-03 — Storage failure

```gherkin
Given an injected archive initialization, publication, serialization or final corpus-save failure
When the operation fails
Then the system shall preserve earlier complete JSON records and stop further sends
And the CLI shall return FUZZ_GUIDED_PERSISTENCE_FAILED with the archive location and count
And a failed temporary write shall not publish partial JSON
```

**Fixture:** `test_cli_storage_failure_before_transmit`, `test_failed_publication_keeps_previous_records_and_stops_sends`, `test_serialization_failure_leaves_no_partial_json`, `test_final_corpus_save_failure_preserves_archive`, `test_cli_record_failure_stops_campaign_and_reports_previous_evidence`.

### TEST-GFA-04 — Interrupted campaign

```gherkin
Given a completed finding followed by keyboard interruption or transport failure
When the campaign stops
Then the system shall retain the completed record
And the CLI shall preserve the error category and return the archive location and count
```

**Fixture:** `test_completed_evidence_survives_interruption`, `test_cli_partial_error_reports_archive` with parameterized fake failures.

### TEST-GFA-05 — Dry-run

```gherkin
Given a nonexistent evidence root and dry-run selected
When the CLI plans the campaign
Then the system shall create no archive and call no transport transaction
```

**Fixture:** `test_dry_run_does_not_create_archive_or_transmit`.

## Fixtures And Environment

The loop tests inject an in-process reactive responder (high-byte payloads
elicit varying UDS NRCs; others go silent), so novelty discovery, determinism,
pruning, kill-switch, and persistence are exercised with no live bus. CLI active
tests use the scaffold transport backend.

## Explicit Non-Coverage

* Live-bus campaigns against real ECUs.
* Feedback signals beyond NRC / positive / DM1 / timing / silence.
* Seed minimisation / corpus distillation.

* Abrupt OS power loss is not simulated; atomic publication and injected write failures are tested.
