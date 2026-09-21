---
description: "Test strategy and coverage for the offline synthetic dataset provider, including the offline end-to-end analysis path and determinism guarantees."
---

# Test Spec: Offline Dataset Provider

## Document Control

| Field | Value |
|-------|-------|
| Related design spec | [`design/offline-dataset-provider.md`](../design/offline-dataset-provider.md) |
| Issue | #460 |
| Implementation | `src/canarchy/dataset_offline.py` |
| Test file | `tests/test_dataset_offline.py` |

---

## Strategy

The provider exists so that an agent with no network access can run the dataset
workflow end to end. Asserting descriptor metadata alone would not establish
that, so the central tests feed generated data through the real conversion and
analysis paths — the candump parser, the HCRL and decoded-signal CSV parsers,
the J1939 DM1 and transport-protocol decoders, and the reverse-engineering
counter detector. A dataset that cannot be analysed is a dataset that does not
do its job, however well-formed its metadata.

Cache location is redirected to a temporary directory by patching `Path.home`,
because `dataset_cache.cache_root()` resolves under the real home directory and
tests must not write there or depend on what a previous run left behind.

---

## Test Cases

| ID | Requirement | Test |
|----|-------------|------|
| `TEST-ODS-01` | `REQ-ODS-01` | `test_satisfies_the_provider_protocol` |
| `TEST-ODS-02` | `REQ-ODS-02` | `test_fetch_writes_real_data_and_reports_cache_state` |
| `TEST-ODS-03` | `REQ-ODS-03` | `test_generation_is_deterministic` |
| `TEST-ODS-04` | `REQ-ODS-04` | `test_every_dataset_is_labelled_synthetic` |
| `TEST-ODS-05` | `REQ-ODS-05` | Covered by construction and by `test_every_dataset_is_labelled_synthetic`; see "Not tested" below |
| `TEST-ODS-06` | `REQ-ODS-06` | `test_fetch_writes_real_data_and_reports_cache_state`, `test_cache_path_is_versioned` |
| `TEST-ODS-07` | `REQ-ODS-07` | `test_registered_in_the_default_registry_after_the_catalog`, `test_offline_prefix_resolves` |
| `TEST-ODS-08` | `REQ-ODS-08` | `test_inspect_unknown_dataset_reports_not_found`, `test_fetch_unknown_dataset_reports_not_found` |
| `TEST-ODS-09` | `REQ-ODS-09` | `test_fetch_records_synthetic_provenance`, `test_refresh_writes_a_manifest` |
| `TEST-ODS-10` | `REQ-ODS-10` | `test_covers_every_parsed_source_format`, plus the analysis cases below |
| `TEST-ODS-11` | `REQ-ODS-11` | `test_publish_is_atomic_and_cleans_up_on_failure`, `test_a_successful_fetch_after_a_failure_regenerates_cleanly` |
| `TEST-ODS-12` | `REQ-ODS-12` | `test_generation_failure_is_categorised_as_a_backend_error`, `test_generation_failure_exits_with_the_backend_code`, `test_unknown_dataset_still_exits_with_the_usage_code`, `test_dataset_error_defaults_to_the_user_category` |
| `TEST-ODS-13` | `REQ-ODS-13` | `test_offline_fetch_points_at_the_local_path`, `test_offline_fetch_next_steps_name_commands_that_work`, `test_catalog_fetch_still_reports_provenance_only`, `test_fetch_declares_that_data_was_materialised` |
| `TEST-ODS-14` | `REQ-ODS-14` | `test_bam_frames_use_the_global_destination_address`, `test_bam_session_reassembles_as_a_global_broadcast`, `test_destination_address_is_rejected_for_a_pdu2_pgn` |

### TEST-ODS-02 — fetch produces real bytes

```gherkin
Given  the offline provider and an empty dataset cache
When   the operator runs `canarchy datasets fetch offline:can-basic`
Then   the system shall write a non-empty file at the resolution's cache path
And    the resolution shall report `is_cached: false` on first fetch
And    a second fetch shall report `is_cached: true` and reuse the same path
```

**Fixture:** none — data is generated.

### TEST-ODS-03 — determinism

```gherkin
Given  a dataset has been generated once
When   the generated file is deleted and the dataset is fetched again
Then   the system shall produce byte-identical content
```

**Fixture:** none. Run across all four datasets as subtests.

### TEST-ODS-04 — synthetic labelling

```gherkin
Given  the offline provider
When   each descriptor is inspected
Then   the licence string shall identify the data as synthetic
And    the description shall begin with `SYNTHETIC:`
And    `metadata.synthetic` shall be true and `metadata.requires_network` false
And    the access notes shall warn against publishing results computed from it
```

**Fixture:** none.

### TEST-ODS-11 — the J1939 dataset is genuinely analysable

```gherkin
Given  `offline:j1939-basic` has been fetched
When   the frames are passed to the J1939 decoders
Then   the system shall reassemble at least one complete BAM/TP session
And    shall report at least one DM1 message with an active DTC
And    that DTC shall decode as SPN 110 with FMI 3 and an amber warning lamp
```

**Fixture:** none.

### TEST-ODS-12 — the intrusion dataset keeps its labels through conversion

```gherkin
Given  `offline:can-intrusion` has been fetched
When   it is converted with `--source-format hcrl-csv --format jsonl`
Then   the system shall emit a non-zero frame count
And    the converted events shall carry both normal (`R`) and attack (`T`) labels
```

**Fixture:** none.

### TEST-ODS-13 — the counter is discoverable

```gherkin
Given  `offline:can-basic` has been fetched
When   the frames are passed to the counter detector
Then   the system shall report at least one candidate
And    the highest-scoring candidate shall score 1.0
```

**Fixture:** none. This guards the dataset's purpose: it exists so the
reverse-engineering helpers have something real to find.

---

## Not Tested, And Why

* **`REQ-ODS-05` (no third-party derivation) is not directly testable.** No
  assertion can prove data was not derived from a protected capture. It is held
  by construction — the generators build frames from protocol field layouts and
  a seeded PRNG, with no dataset file read at any point — and by review. The
  closest mechanical guard is that the module has no file inputs and no network
  imports.
* **Statistical realism is not asserted.** The data is deliberately simple.
  Asserting that it resembles real vehicle traffic would be asserting the thing
  the provider explicitly disclaims.
* **Cross-platform byte-identity is asserted only on the CI platforms.**
  Determinism follows from seeding a dedicated `random.Random` with a fixed
  string and formatting with fixed precision, neither of which is
  platform-dependent, but the guarantee is only mechanically checked where CI
  runs.

### `TEST-ODS-11`..`14` — review regressions (PR #533)

```gherkin
Scenario: TEST-ODS-11 — publishing a generated dataset is atomic
  Given the rename that publishes a generated dataset fails with ENOSPC
  When  `datasets fetch offline:can-basic` runs
  Then  a DATASET_GENERATION_FAILED error shall be raised
  And   no file shall exist at the dataset's cache path
  And   no temporary sibling shall be left in the cache directory
  And   a subsequent successful fetch shall produce a complete dataset

Scenario: TEST-ODS-12 — a storage failure is a backend error
  Given the cache cannot be written
  When  `datasets fetch offline:can-basic --json` runs
  Then  the exit code shall be 2
  And   errors[0].code shall be "DATASET_GENERATION_FAILED"
  But   an unknown dataset name shall still exit 1

Scenario: TEST-ODS-13 — fetch names next steps that actually work
  When  `datasets fetch offline:can-basic --json` runs
  Then  data.data_is_local shall be true
  And   data.next_steps shall name the cache path
  And   data.next_steps shall not recommend `datasets download` or `datasets replay`
  And   `capture-info --file <cache_path>` and `stats --file <cache_path>` shall exit 0
  But   a catalog fetch shall still report "no data was downloaded"

Scenario: TEST-ODS-14 — the generated BAM is globally addressed
  When  the j1939-basic dataset is generated
  Then  every TP.CM (0xEC) and TP.DT (0xEB) frame shall carry destination 0xFF
  And   the reassembled session shall be a BAM to destination 255
  And   requesting a destination address for a PDU2 PGN shall raise ValueError
```

**Fixture:** none on disk; the cache is redirected to a temporary HOME and the
failure cases patch `canarchy.dataset_offline.os.replace` or swap a dataset's
generator. Implemented in `tests/test_dataset_offline.py` and
`tests/test_dataset_provider.py`. Eight of the nine provider-level cases were
confirmed to fail against the pre-review source; the ninth asserts an error
code that already held.
