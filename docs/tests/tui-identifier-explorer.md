# Test Spec: TUI Identifier Explorer

## Document Control

| Field | Value |
|---|---|
| Status | Implemented |
| Design doc | `docs/design/tui-identifier-explorer.md` |
| Test files | `tests/test_tui_explorer.py`, `tests/test_tui_app.py`, `tests/test_cli.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|---|---|---|
| REQ-TUIX-01 | Typed bus/ID identity | TEST-TUIX-01, TEST-TUIX-03 |
| REQ-TUIX-02 | Summary and log views | TEST-TUIX-01, TEST-TUIX-04 |
| REQ-TUIX-03 | Freeze and return live | TEST-TUIX-03, TEST-TUIX-04 |
| REQ-TUIX-04 | Stable selection and eviction | TEST-TUIX-02, TEST-TUIX-03 |
| REQ-TUIX-05 | Complete non-color detail | TEST-TUIX-01, TEST-TUIX-02 |
| REQ-TUIX-06 | Shared ID/PGN/SA filters | TEST-TUIX-04, TEST-TUIX-05 |
| REQ-TUIX-07 | Visible validation errors | TEST-TUIX-04, TEST-TUIX-05 |
| REQ-TUIX-08 | Typed numeric/time sorting | TEST-TUIX-04 |
| REQ-TUIX-09 | Bounded, responsive analysis | TEST-TUIX-06 |

## Test Cases

### TEST-TUIX-01 — Identifier Identity And Changed Bytes

```gherkin
Given  standard and extended frames share a numeric ID across two buses
When   the explorer folds the frames
Then   the system shall retain separate identifier summaries
And    the detail shall show exact raw hex, bit values, J1939 fields, and a textual changed-byte caret
```

**Fixture:** Synthetic `CanFrame` events in `tests/test_tui_explorer.py`.

### TEST-TUIX-02 — Bounded Evidence And Decoded Meaning

```gherkin
Given  a small backlog contains a frame and a correlated decoded signal
When   another frame evicts the original history
Then   the system shall bound the retained observations and report the evicted key
And    the original detail shall include the decoded signal before eviction
And    malformed frame events shall not shift metadata onto later valid rows
And    DBC decoded-message events shall populate the identifier summary and log with correlated signal evidence
```

**Fixture:** Synthetic frame and signal event dictionaries plus `tests/fixtures/sample.candump` and `tests/fixtures/sample.dbc` through `decode`.

### TEST-TUIX-03 — Stable Selection

```gherkin
Given  the operator has selected an identifier and frozen inspection
When   new frames arrive, the table is sorted and filtered, workspaces switch, and history is evicted
Then   the system shall preserve the identifier and detail snapshot
And    the status shall count incoming frames until return-to-live is invoked
```

**Fixture:** Textual Pilot at 100×35 and synthetic frame events.

### TEST-TUIX-04 — Filter, Sort, And Event Log

```gherkin
Given  frames with J1939 source addresses and timestamps spanning midnight
When   the operator applies SA/PGN/ID filters, sorts, and switches to the event log
Then   the system shall use canonical frame predicates and underlying numeric timestamps
And    invalid typed filters and unknown sort names shall leave the prior view state unchanged
And    selecting a historical log row shall retain that frame's payload while newer frames arrive
And    returning live shall select the newest visible log row instead of the historical row
And    frames hidden by the active typed filter shall not replace the live inspector selection
```

**Fixture:** Textual Pilot at 80×24 and synthetic frame events.

### TEST-TUIX-05 — CLI Source-Address Contract

```gherkin
Given  a candump fixture with two extended frames from source address 0x31
When   the operator runs `filter sa==0x31` or `filter sa == 49`
Then   the system shall return those two frames in the existing JSON envelope
And    standard frames shall not match the J1939 source-address atom
```

**Fixture:** `tests/fixtures/sample.candump`.

### TEST-TUIX-06 — Synthetic Load Bounds

```gherkin
Given  10,000 synthetic frames over 64 identifiers and a 512-observation cap
When   the explorer ingests 100 batches of 100 frames
Then   the system shall retain no more than 512 observations and 64 identifiers
And    model processing shall finish within eight seconds with peak traced memory below 16 MB
And    a 1,000-frame Textual batch shall render summary and log within ten seconds
And    growing the backlog shall increase the explorer capacity as well as the log capacity
```

**Fixture:** In-memory generated frames and Textual Pilot; no adapter, socket, or network.

## Fixtures And Environment

The model benchmark runs under `tracemalloc` and uses deterministic synthetic frames. The UI benchmark runs headlessly under Textual Pilot. Bounds are intentionally generous relative to typical local results to detect major regressions without relying on hardware speed.

## Explicit Non-Coverage

Physical CAN adapters, cross-command DBC joins, and multi-hour rate stability are not exercised in CI.
