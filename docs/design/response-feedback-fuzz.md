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
* Each iteration selects a seed (randomly with weight `score + 1`), mutates it with a `canarchy.fuzzing` mutator (havoc / splice), and
  observes the response. A mutation with `gain > 0` becomes a child seed whose
  `score` is its gain and whose `parent_id` / `generation` record its lineage.
* The corpus is capped (`--max-corpus`); when it overflows, the lowest-scoring
  seeds are pruned, so productive lineages survive and barren ones are dropped.
* `--corpus <dir>` persists the corpus: one raw seed file per seed plus a
  `lineage.json` manifest, and reloads seed bytes on the next run. Each invocation starts a new feedback
  tracker and campaign namespace; this is seed reuse, not exact process resumption.

## Durable Findings Requirements (#503)

| ID | Type | Requirement |
|----|------|-------------|
| REQ-GFA-01 | Ubiquitous | The active CLI/MCP campaign shall create a unique campaign directory and persist each finding independently of the bounded working corpus before another transmission. |
| REQ-GFA-02 | Ubiquitous | The system shall retain exact clamped payload bytes, response frames/timing/silence, new markers, iteration, parent ID/payload, generation, and campaign-qualified finding identity. |
| REQ-GFA-03 | Ubiquitous | The campaign manifest shall record schema/tool versions, timestamp, initial seeds, effective RNG/mutation/feedback settings, target ID/type/channel, and available transport window settings without copying arbitrary environment variables. |
| REQ-GFA-04 | Unwanted behaviour | If a storage operation fails, the system shall stop further transmissions, report a structured error and archive location, and preserve previously completed records. |
| REQ-GFA-05 | Event-driven | When transport failure or keyboard interruption ends a campaign, the CLI shall report the archive location and completed finding count. |
| REQ-GFA-06 | Optional feature | Where dry-run is selected, the system shall create no archive and transmit no frames. |
| REQ-GFA-08 | Unwanted behaviour | If a campaign rate or duration is non-finite, the CLI shall reject it as a usage error before archive creation, in active and dry-run modes. |
| REQ-GFA-09 | Unwanted behaviour | If a transport transaction raises an OSError, the CLI shall report a transport error; only explicit archive or corpus operations shall produce persistence errors. |
| REQ-GFA-07 | Ubiquitous | The archive shall expose JSON records inspectable offline without executing commands or requiring surviving corpus seeds. |

## Archive Format And Durability

Every active run creates `<root>/<uuid>/campaign.json` and one
`finding-<iteration padded to 8 digits>.json` per interesting input. The root is
`--findings-dir`, otherwise `<corpus>/findings` when `--corpus` is given, otherwise
`~/.canarchy/findings`. Existing corpus manifests and `.bin` files keep their
format; findings never depend on them. Repeated runs use fresh UUID directories
so `s1` in one run cannot overwrite `s1` in another.

The manifest has `schema_version: 1`, `campaign_id`, `created_at`,
`canarchy_version`, explicit `config`, and clamped `initial_seeds` with local
seed IDs. Configuration includes `seed`, `max_payload`, `pace_seconds`, budget,
mutator name, feedback weights/categories, numeric arbitration ID, extended
flag, interface, backend, python-can interface type, capture limit and timeout.
`target_firmware: null` explicitly denotes unavailable ECU identity; physical
ECU state is not reproducible from the manifest alone.

Finding records add `schema_version`, `recorded_at`, `campaign_id`, and
`finding_id` (`<campaign_id>:<seed_id>`) to iteration, seed/parent IDs, generation,
gain and new markers. `data` and `parent_data` are hex strings. `observation`
contains serialized response frames, elapsed seconds, and a silence flag.
Parent snapshots remain available after pruning; initial parents are also in
the manifest and every interesting descendant has its own record.

Records are serialized into a temporary file, flushed and fsynced, then
atomically replaced into their final filename. POSIX additionally fsyncs the
directory; Windows supports the complete-file replacement but not that directory
fsync step. A process killed during a write may leave a hidden temporary file;
offline readers use only `campaign.json` and `finding-*.json`. A write failure
stops the loop rather than proceeding with unrecorded findings. Only previously
completed records are guaranteed: a kill between receiving a response and
publishing its record can lose that in-flight finding. Final corpus-save failure
cannot remove already archived evidence. No automatic retention/pruning of the
findings archive occurs.

The pure loop supports an injected `on_finding` callback and optional campaign
ID. Direct Python callers select their own persistence sink; the CLI/MCP always
wires the archive for active runs. See the command specification for offline
inspection and manual replay planning.

## Command Surface

```text
canarchy fuzz guided <interface> --id <arb-id> [--signals nrc,timing,dm1,silence]
    [--corpus <dir>] [--findings-dir <root>] [--seed-data <hex>] [--max-iterations <n>] [--max-seconds <s>]
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
| Bus / transport error | Surfaced as `FUZZ_GUIDED_TRANSPORT_FAILED` (exit 2); completed finding records remain in the archive, whose location/count is returned in the error data; a partial final corpus is not promised. |
| Saturating DM1 output | DM1 markers are de-duplicated by `(spn, fmi)`; a single noisy fault cannot inflate the score unboundedly. |
| Kill-switch | `--max-seconds` and `--max-iterations` bound the campaign; either reaching its limit ends the run with a recorded `stop_reason`. |

## Output Contracts

`--json` returns the campaign envelope: `iterations`, `new_behaviour_count`,
`corpus_size`, `unique_markers`, `stop_reason`, a `findings` list (each with exact payload, observation, lineage and stable identity), and the resolved campaign config.
`campaign_id`, `archive_path`, and `archived_finding_count` locate durable evidence.
`--jsonl` emits per-finding events after the campaign; persistence itself is incremental. `--text` renders a campaign summary.
`--dry-run` returns the plan (`mode: dry_run`) with the seed count and the first
planned mutations, opening no transport.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `FUZZ_GUIDED_INVALID_SIGNALS` | `--signals` names an unknown marker category | 1 |
| `FUZZ_GUIDED_INVALID_ID` | `--id` is not a valid CAN id, or is outside the 29-bit range | 1 |
| `ACTIVE_ACK_REQUIRED` | active run without `--ack-active` while required | 1 |
| `FUZZ_GUIDED_TRANSPORT_FAILED` | the transport raised mid-campaign | 2 |
| `FUZZ_GUIDED_PERSISTENCE_FAILED` | archive initialization, record publication, or final corpus save failed | 2 |
| `FUZZ_GUIDED_INVALID_TIMING` | non-finite rate or max-seconds | 1 |
| `FUZZ_GUIDED_INTERRUPTED` | keyboard interruption | 1 |

## Responsibilities And Boundaries

In scope: the response-fingerprint engine, the guided loop with lineage and
persistence, the CLI/MCP surface, and active-transmit safety. Out of scope (v1):
multi-target campaigns, automatic seed minimisation, automatic live replay and feedback signals beyond the five categories above. These are natural follow-ups once the loop is in use.

## Deferred Decisions

* Seed minimisation / corpus distillation passes.
* A `fuzz guided replay <corpus>` command to re-drive a saved corpus.
* Additional feedback signals (e.g. UDS pending-response `0x78` cadence).
