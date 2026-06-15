# Test Spec: Response-Feedback Guided Fuzzing (`fuzz guided`)

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/response-feedback-fuzz.md` |
| Test file | `tests/test_fuzz_guided.py` |

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

## Fixtures And Environment

The loop tests inject an in-process reactive responder (high-byte payloads
elicit varying UDS NRCs; others go silent), so novelty discovery, determinism,
pruning, kill-switch, and persistence are exercised with no live bus. CLI active
tests use the scaffold transport backend.

## Explicit Non-Coverage

* Live-bus campaigns against real ECUs.
* Feedback signals beyond NRC / positive / DM1 / timing / silence.
* Seed minimisation / corpus distillation.
