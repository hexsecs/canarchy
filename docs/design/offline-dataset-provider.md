---
description: "The offline dataset provider: deterministic synthetic CAN datasets that let sandboxed agents exercise the dataset workflow end to end with no network access."
---

# Design: Offline Dataset Provider

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Issue | #460 |
| Command surface | `canarchy datasets search\|inspect\|fetch\|provider list` |
| Primary area | Datasets |
| Implementation | `src/canarchy/dataset_offline.py`, `dataset_provider.py` |
| Related specs | [`dataset-provider-workflow.md`](dataset-provider-workflow.md) |

---

## Motivation

Every dataset in the `catalog` provider resolves to a host that a typical sandboxed
agent environment blocks: `zenodo.org` (ROAD), `figshare.com` (CANdid),
`huggingface.co` (commaCarSegments), and `ocslab.hksecurity.net` (the HCRL sets).
A common default allowlist permits git hosts and PyPI and nothing else. An agent
that tries to exercise the documented `datasets` workflow therefore fails — and
fails late, deep inside a replay, with a transport error rather than anything
that identifies the real cause.

That undercuts a capability the project advertises. CANarchy positions itself for
agent-driven workflows, so "install it, point an agent at the dataset commands"
should work without privileged network access.

The obvious fix — mirror a slice of each real dataset from a reachable host — is
mostly not available. Redistribution terms were reviewed per dataset for #460:

| | Datasets | Redistribution |
|---|---|---|
| Forbidden | `syncan` | ETAS/Bosch terms forbid distributing the dataset or modified versions |
| No grant | the nine `hcrl-*` entries | "Research use only" grants no redistribution right |
| Unclear | `road`, `candid` | Terms could not be verified from a primary source |
| Probably permitted | `comma-car-segments` | MIT, notice required |

Mirroring therefore covers at most one to three of fourteen datasets, and cannot
cover the one dataset a reporter already used as a workaround. A slice is still a
copy, so "derived slice" does not escape the licence.

This provider takes the other path: ship no third-party bytes at all, and instead
generate synthetic CAN data from protocol rules. That carries no redistribution
exposure, works with zero egress, and restores the end-to-end workflow an agent
needs to exercise.

---

## Responsibilities And Boundaries

**In scope.** A second registered provider, `offline`, exposing a small set of
synthetic datasets that cover the source formats the conversion layer already
parses, generated deterministically on demand into the dataset cache.

**Out of scope.** Mirroring real datasets (needs per-dataset licence clearance —
tracked separately), catalog reachability metadata so agents can skip unreachable
datasets before starting work (also separate), and any change to how the `catalog`
provider resolves downloads.

**Explicitly not a research corpus.** Synthetic traffic carries real protocol
structure but no real vehicle behaviour. It is suitable for exercising tooling,
demos, tests, and CI. Results computed on it — IDS accuracy, anomaly rates,
signal inference quality — are not research findings and must not be published as
such. The labelling requirements below exist to make that impossible to miss.

---

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-ODS-01` | Ubiquitous | The system shall register an `offline` dataset provider whose datasets resolve without network access. |
| `REQ-ODS-02` | Event-driven | When `datasets fetch offline:<name>` is invoked, the system shall generate the dataset into the provider cache and return a resolution whose `cache_path` is the generated data file. |
| `REQ-ODS-03` | Ubiquitous | The system shall generate byte-identical data for a given dataset name and version on every invocation, on every platform. |
| `REQ-ODS-04` | Ubiquitous | The system shall declare every offline dataset as synthetic in its `license`, its `description`, and a `synthetic: true` metadata flag, and shall surface that flag in machine-readable output. |
| `REQ-ODS-05` | Ubiquitous | The system shall generate offline datasets from protocol rules only, and shall not embed, resample, or otherwise derive them from any third-party capture. |
| `REQ-ODS-06` | State-driven | While a generated dataset is present in the cache, the system shall reuse it and report `is_cached: true` rather than regenerating it. |
| `REQ-ODS-07` | Event-driven | When `datasets search` or `datasets inspect` runs without a provider prefix, the system shall include offline datasets alongside catalog datasets. |
| `REQ-ODS-08` | Unwanted behaviour | If an unknown offline dataset name is requested, the system shall return a structured error with code `DATASET_NOT_FOUND` and exit code 1. |
| `REQ-ODS-09` | Ubiquitous | The system shall write a provenance record for each fetched offline dataset stating that the data is synthetic and naming the generator version. |
| `REQ-ODS-10` | Ubiquitous | The system shall cover each source format the conversion layer parses (`candump`, `hcrl-csv`, `decoded-signal-csv`) with at least one offline dataset. |

---

## Command Surface

No new commands. The provider plugs into the existing surface:

```text
canarchy datasets provider list
canarchy datasets search <query> [--provider offline]
canarchy datasets inspect offline:<name>
canarchy datasets fetch offline:<name>
```

After a fetch, the generated file is an ordinary local file, so the existing
local-file commands consume it with no further network access:

```text
canarchy datasets convert <path> --source-format <fmt> --format candump|jsonl
canarchy datasets stream <path> --source-format <fmt> --format jsonl
canarchy capture-info --file <path>
canarchy stats --file <path>
canarchy j1939 summary --file <path>
canarchy replay --file <path> --rate 0
```

That is the loop #460 reported as broken: `fetch` now produces real bytes, and
every analysis command downstream of it already works offline.

---

## Datasets

| Name | Format | Protocol | Shape |
|------|--------|----------|-------|
| `can-basic` | `candump` | CAN | Periodic frames on a handful of arbitration IDs, with a rolling counter nibble and a checksum byte, so the `re` helpers have something to find |
| `j1939-basic` | `candump` | J1939 | PGN traffic from several source addresses, including a BAM/TP multi-packet sequence and DM1 active faults |
| `can-intrusion` | `hcrl-csv` | CAN | Attack-labelled rows: a normal baseline with labelled injection bursts |
| `signal-decoded` | `decoded-signal-csv` | CAN | Pre-decoded normalised per-ID signal columns |

Frame counts are modest by design (a few thousand each) — enough to exercise
analysis paths, small enough that generation is instant and the cache stays tidy.

---

## Data Model

Descriptors follow `DatasetDescriptor` unchanged. The offline provider fixes
these fields:

| Field | Value |
|-------|-------|
| `provider` | `offline` |
| `license` | `Synthetic data generated by CANarchy - not research data` |
| `source_url` | The CANarchy repository, since the generator is the source |
| `description` | Prefixed `SYNTHETIC:` |
| `metadata.synthetic` | `true` |
| `metadata.generator` | Generator version string |

`dataset_machine_fields()` gains a `synthetic` key, `false` for every descriptor
that does not set the flag, so existing consumers see a stable shape.

---

## Output Contracts

`--json` search and inspect payloads carry `synthetic` alongside the existing
machine fields. `fetch` returns the usual resolution payload; its `cache_path`
points at generated data rather than a provenance stub, and its provenance
record carries `synthetic: true` and the generator version.

Human `--text` output renders the `SYNTHETIC:` description prefix as written, so
the warning is visible in every output mode.

---

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `DATASET_NOT_FOUND` | Unknown offline dataset name | 1 |
| `DATASET_PROVIDER_NOT_FOUND` | Unknown provider prefix | 1 |
| `DATASET_GENERATION_FAILED` | The cache path cannot be written | 2 |

---

## Determinism

Generation seeds a dedicated `random.Random` per dataset from a fixed constant
and the dataset name; it never reads the global `random` state, the clock, or the
environment. Timestamps are computed from a fixed epoch. The same version of
CANarchy therefore always produces the same bytes, which keeps sessions and
provenance hashes (#504) meaningful across machines.

Regenerating with a changed generator is a visible change: the generator version
is recorded in the provenance file, and a dataset's `version` is bumped when its
output changes.

---

## Deferred Decisions

* Mirroring real dataset slices as release assets, for datasets whose terms are
  confirmed in writing. Reachability was verified (GitHub's release-asset CDN is
  reachable from a restricted sandbox), so this is blocked on licence clearance
  rather than on feasibility.
* Catalog reachability metadata (`download_host`) so agents can skip unreachable
  datasets before committing to a workflow.
* Whether `datasets replay` should accept a local path directly, rather than
  requiring `canarchy replay --file` after a fetch.
