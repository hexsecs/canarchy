# Test Spec: First-Class J1939 Decoder

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Design doc | `docs/design/j1939-first-class-decoder.md` |
| Test file | `tests/test_cli.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J1939F-01` | Decoder abstraction separates CLI from curated helper logic | `TEST-J1939F-01` |
| `REQ-J1939F-02` | J1939 commands use the library-backed decoder path | `TEST-J1939F-01`, `TEST-J1939F-02`, `TEST-J1939F-03`, `TEST-J1939F-04` |
| `REQ-J1939F-03` | TP messages are reassembled before dependent decode | `TEST-J1939F-03`, `TEST-J1939F-04` |
| `REQ-J1939F-04` | DM1 uses protocol-aware direct and TP decode | `TEST-J1939F-04` |
| `REQ-J1939F-05` | Optional DBC enriches J1939 results | `TEST-J1939F-05`, `TEST-J1939F-06` |
| `REQ-J1939F-06` | SPN lookup uses library metadata and optional DBC | `TEST-J1939F-02`, `TEST-J1939F-06` |
| `REQ-J1939F-07` | Existing command names and output modes stay stable | `TEST-J1939F-02`, `TEST-J1939F-03`, `TEST-J1939F-04`, `TEST-J1939F-05` |
| `REQ-J1939F-08` | Decoder init failure returns a structured backend error | `TEST-J1939F-07` |
| `REQ-J1939F-09` | Missing SPN returns a clean not-found error | `TEST-J1939F-08` |
| `REQ-J1939F-10` | Configured default J1939 DBC is used when no flag is supplied | `TEST-J1939F-09` |

## Test Cases

### TEST-J1939F-01 — CLI commands use the decoder abstraction

```gherkin
Given  the J1939 decoder backend is replaced with a test double
When   the operator runs `canarchy j1939 decode tests/fixtures/j1939_heavy_vehicle.candump --json`
Then   the system shall route the command through the decoder abstraction
And    the CLI layer shall shape the returned records into the standard CANarchy envelope
```

**Fixture:** mocked decoder backend and `tests/fixtures/j1939_heavy_vehicle.candump`.

---

### TEST-J1939F-02 — SPN decode is no longer limited to the curated starter map

```gherkin
Given  a configured J1939 DBC exposes a standard SPN that is not in the legacy curated map
When   the operator runs `canarchy j1939 spn <spn> --file tests/fixtures/sample.candump --json`
Then   the system shall return one or more structured SPN observations
And    the command shall not fail with the legacy unsupported-SPN error
And    the result shall identify the DBC-backed SPN decoder path
```

**Fixture:** `tests/fixtures/sample.candump` and `tests/fixtures/j1939_sample.dbc` with signal SPN attributes.

---

### TEST-J1939F-03 — TP session state drives protocol decode

```gherkin
Given  a fixture contains a multi-packet J1939 transport-protocol transfer
When   the operator runs `canarchy j1939 tp tests/fixtures/j1939_dm1_tp.candump --json`
Then   the system shall return a reassembled transport session summary
And    the returned session shall report the transferred PGN and completion state
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### TEST-J1939F-04 — DM1 decodes direct and TP-carried payloads through the new backend

```gherkin
Given  the fixture `tests/fixtures/j1939_dm1_tp.candump` contains one direct DM1 and one TP-carried DM1
When   the operator runs `canarchy j1939 dm1 tests/fixtures/j1939_dm1_tp.candump --json`
Then   the system shall return both DM1 messages with structured lamp and DTC data
And    the TP-carried DM1 shall depend on a reassembled session rather than the legacy BAM-only parser
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### TEST-J1939F-05 — DBC enriches PGN decode without changing command shape

```gherkin
Given  a J1939 DBC contains signal metadata for a decoded PGN in the capture
When   the operator runs `canarchy j1939 pgn 65262 --file tests/fixtures/j1939_heavy_vehicle.candump --dbc <path> --json`
Then   the system shall preserve the `j1939 pgn` command envelope
And    the decoded records shall include DBC-enriched signal metadata where definitions match
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump` and a representative J1939 DBC fixture.

---

### TEST-J1939F-06 — DBC enriches SPN lookup precedence deterministically

```gherkin
Given  both the J1939 decoder metadata and a supplied DBC can resolve the requested SPN
When   the operator runs `canarchy j1939 spn <spn> --file tests/fixtures/j1939_heavy_vehicle.candump --dbc <path> --json`
Then   the system shall return a deterministic merged result
And    the result shall expose DBC-derived fields according to the documented precedence model
```

**Fixture:** representative J1939 DBC fixture and matching capture.

---

### TEST-J1939F-07 — Decoder initialization failures return backend errors

```gherkin
Given  the configured J1939 decoder backend fails during initialization
When   the operator runs `canarchy j1939 decode tests/fixtures/j1939_heavy_vehicle.candump --json`
Then   the system shall exit with code `3`
And    `errors[0].code` shall equal `"J1939_DECODER_UNAVAILABLE"`
```

**Fixture:** mocked decoder initialization failure.

---

### TEST-J1939F-08 — Missing SPN returns a clean not-found error

```gherkin
Given  neither the library-backed decoder nor an optional DBC can resolve the requested SPN
When   the operator runs `canarchy j1939 spn 999999 --file tests/fixtures/j1939_heavy_vehicle.candump --json`
Then   the system shall exit with code `1`
And    `errors[0].code` shall equal `"J1939_SPN_NOT_FOUND"`
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump` and no matching SPN metadata.

---

### TEST-J1939F-09 — Configured default J1939 DBC applies without a flag

```gherkin
Given  `CANARCHY_J1939_DBC` or `[j1939].dbc` points to a matching J1939 DBC fixture
When   the operator runs `canarchy j1939 spn 110 --file tests/fixtures/sample.candump --json`
Then   the system shall enrich the result with DBC provenance and decoded DBC events
And    the operator shall not need to repeat `--dbc` on that command
```

**Fixture:** `tests/fixtures/sample.candump`, `tests/fixtures/j1939_sample.dbc`, and a file or env-backed J1939 DBC default.

---

### TEST-J1939F-10 — DM1 DTC names can be enriched from J1939 DBC SPN metadata

```gherkin
Given  a DM1 capture reports a DTC whose SPN is not in the starter map
And    a configured or explicit J1939 DBC defines a signal with the matching `SPN` attribute
When   the operator runs `canarchy j1939 dm1 tests/fixtures/j1939_dm1_spn175.candump --json`
Then   the system shall preserve the `j1939 dm1` command envelope
And    the returned DTC shall include the DBC-derived signal name and units
```

**Fixture:** `tests/fixtures/j1939_dm1_spn175.candump` and `tests/fixtures/j1939_sample.dbc`.

## Fixtures And Environment

* existing `tests/fixtures/j1939_heavy_vehicle.candump`
* existing `tests/fixtures/j1939_dm1_tp.candump`
* `tests/fixtures/j1939_sample.dbc` for PGN, SPN, and DM1 enrichment tests
* `tests/fixtures/j1939_dm1_spn175.candump` for non-curated DM1 DTC enrichment tests
* mocked decoder backends for abstraction and error-path coverage

Phase 1 currently covers the abstraction boundary with mocked decoder backends. Phase 2 currently covers decoder-backed routing for `j1939 decode` and `j1939 pgn`. Phase 3 currently routes `j1939 spn`, `j1939 tp`, and `j1939 dm1` through the decoder adapter as well. Phase 4 currently covers direct `--dbc` enrichment for `j1939 decode`, `j1939 pgn`, `j1939 spn`, and `j1939 dm1`, config-backed default J1939 DBC selection, and DBC-backed resolution for non-curated SPNs and DM1 DTC names; broader library-backed transport semantics and richer DBC-enrichment coverage remain planned.

## Explicit Non-Coverage

* OEM-specific diagnostic workflows beyond standard J1939 DM1 behavior
* full network-management behavior outside the CLI command surfaces listed in the design spec
* performance benchmarking details, which should live in a separate benchmark or performance test plan once representative large fixtures are available
