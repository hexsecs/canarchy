# Design Spec: Response-Feedback Guided Fuzzing (`fuzz guided`)

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy fuzz guided` |
| Primary area | Fuzzing, CLI, safety |
| Related specs | `docs/design/active-transmit-safety.md`, `docs/design/uds-transaction-workflows.md` |

## Goal

Drive a coverage-guided fuzzing loop against an external CAN / J1939 / UDS
target. AFL-style instrumentation coverage is unavailable when the target is an
ECU on the far side of a bus, so the feedback signal is derived from *observed
responses*: UDS negative response codes (NRCs), response-timing variance, DM1
fault emergence, and frame-rate / silence transitions. Inputs that elicit new
observed behaviour are kept and their lineage is prioritised for further
mutation, so the campaign spends its budget where the target reacts.

## User-Facing Motivation

Blind fuzzers waste most of their budget re-sending inputs the ECU ignores.
Using the target's own responses as a novelty signal focuses mutation on inputs
that change its behaviour — surfacing new NRCs, latent fault codes, and
timing/silence anomalies far faster, while staying inside the active-transmit
safety model.

## Observation Model

Each fuzzed input produces a `ResponseObservation` (the response frames captured
within a window, the elapsed time, and whether the target went silent). It is
reduced to a `Fingerprint` — a set of category-prefixed behaviour markers:

| Marker | Source | Example |
|--------|--------|---------|
| `nrc:<svc>:<code>` | UDS negative response (`0x7F`) after ISO-TP reassembly | `nrc:27:35` |
| `pos:<svc>` | UDS positive response service id | `pos:50` |
| `dm1:<spn>:<fmi>` | Active DTC in a DM1 broadcast (`canarchy.j1939.dm1_messages`) | `dm1:100:3` |
| `timing:<bucket>` | Response latency bucketed on a fixed ms ladder | `timing:3` |
| `silence` | No response within the window | `silence` |

`--signals` selects which marker categories are active (default all).

## Scoring Function

A `FeedbackTracker` holds the set of markers seen so far. For a new fingerprint,
its *gain* is the weighted count of markers not yet seen:

```
gain(fp) = sum( weight[category(m)] for m in fp.markers if m not in seen )
```

Default weights prioritise semantic findings over timing noise: `nrc` and `dm1`
= 5, `pos` = 2, `silence` = 3, `timing` = 1. An input with `gain > 0` is a new
behaviour: it is retained as a corpus seed and recorded as a finding. The tracker
then folds the fingerprint's markers into `seen`.

## Seed Corpus And Lineage

* A seed is `(data, seed_id, parent_id, generation, score)`. The initial seeds
  seed generation 0 with no parent.
* Each iteration selects a seed (highest score, round-robin among ties for
  energy), mutates it with a `canarchy.fuzzing` mutator (havoc / splice), and
  observes the response. A mutation with `gain > 0` becomes a child seed whose
  `score` is its gain and whose `parent_id` / `generation` record its lineage.
* The corpus is capped (`--max-corpus`); when it overflows, the lowest-scoring
  seeds are pruned, so productive lineages survive and barren ones are dropped.
* `--corpus <dir>` persists the corpus: one raw seed file per seed plus a
  `lineage.json` manifest, and reloads it on the next run so campaigns resume.

## Command Surface

```text
canarchy fuzz guided <interface> --id <arb-id> [--signals nrc,timing,dm1,silence]
    [--corpus <dir>] [--seed-data <hex>] [--max-iterations <n>] [--max-seconds <s>]
    [--max-corpus <n>] [--rate <hz>] [--seed <rng>] [--ack-active] [--dry-run]
    [--json|--jsonl|--text]
```

## Integration Points

* **Mutators:** `canarchy.fuzzing.havoc_payload` / `splice_payload` (the #310 and
  AFL mutators) provide the mutation operators; `fuzz_guided` is a thin loop on
  top, not a new mutation engine.
* **UDS:** `canarchy.uds.reassemble_uds_pdus` reassembles responses for NRC /
  positive fingerprinting.
* **J1939:** `canarchy.j1939.dm1_messages` extracts DM1 active DTCs for fault
  emergence.
* **Transport:** each iteration uses a single `LocalTransport.transaction`
  (send + receive on one bus) rather than `send()` then a separate `capture()`,
  so the receive path is buffering before the probe is transmitted and a fast
  response is not missed and recorded as false `silence`. `uds scan` and
  `xcp scan` use the same primitive.
* **Safety:** `fuzz guided` is an active-transmit command — it honours
  `--ack-active`, `[safety].require_active_ack`, the `YES` confirmation, `--rate`
  pacing, and `--dry-run` (which plans the campaign without opening the
  transport). `--rate` pacing is applied inside the campaign budget with the
  deadline re-checked after each pacing delay, so a delay that crosses
  `--max-seconds` ends the run rather than permitting one more transmission. An
  `--id` above the 11-bit standard range is transmitted as an extended frame
  (inferred, like `send` / `xcp scan`), so a 29-bit id never builds an invalid
  standard frame. The MCP tool mandates `ack_active=true` with `dry_run`
  defaulting to true.

## Failure-Mode Handling

| Condition | Handling |
|-----------|----------|
| Hung / silent ECU | The observation window times out, recorded as a `silence` marker; the loop continues unless the kill-switch fires. |
| Bus / transport error | Surfaced as `FUZZ_GUIDED_TRANSPORT_FAILED` (exit 2); the partial campaign result is preserved. |
| Saturating DM1 output | DM1 markers are de-duplicated by `(spn, fmi)`; a single noisy fault cannot inflate the score unboundedly. |
| Kill-switch | `--max-seconds` and `--max-iterations` bound the campaign; either reaching its limit ends the run with a recorded `stop_reason`. |

## Output Contracts

`--json` returns the campaign envelope: `iterations`, `new_behaviour_count`,
`corpus_size`, `unique_markers`, `stop_reason`, a bounded `findings` list (each
with iteration, parent seed, gained markers), and the resolved campaign config.
`--jsonl` streams per-finding events; `--text` renders a campaign summary.
`--dry-run` returns the plan (`mode: dry_run`) with the seed count and the first
planned mutations, opening no transport.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `FUZZ_GUIDED_INVALID_SIGNALS` | `--signals` names an unknown marker category | 1 |
| `FUZZ_GUIDED_INVALID_ID` | `--id` is not a valid CAN id, or is outside the 29-bit range | 1 |
| `ACTIVE_ACK_REQUIRED` | active run without `--ack-active` while required | 1 |
| `FUZZ_GUIDED_TRANSPORT_FAILED` | the transport raised mid-campaign | 2 |

## Responsibilities And Boundaries

In scope: the response-fingerprint engine, the guided loop with lineage and
persistence, the CLI/MCP surface, and active-transmit safety. Out of scope (v1):
multi-target campaigns, automatic seed minimisation, crash-triage/replay
artifacts beyond the persisted corpus, and feedback signals other than the four
above. These are natural follow-ups once the loop is in use.

## Deferred Decisions

* Seed minimisation / corpus distillation passes.
* A `fuzz guided replay <corpus>` command to re-drive a saved corpus.
* Additional feedback signals (e.g. UDS pending-response `0x78` cadence).
