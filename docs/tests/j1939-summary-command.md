# Test Spec: J1939 Summary Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/j1939-summary-command.md` |
| Test file | `tests/test_cli.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J1939SUM-01` | `j1939 summary` command exists | `TEST-J1939SUM-01`, `TEST-J1939SUM-03` |
| `REQ-J1939SUM-02` | Summary includes core reconnaissance fields | `TEST-J1939SUM-01` |
| `REQ-J1939SUM-03` | Summary includes DM1 presence metrics | `TEST-J1939SUM-01` |
| `REQ-J1939SUM-04` | Summary includes TP session metrics | `TEST-J1939SUM-01` |
| `REQ-J1939SUM-05` | Printable TP identifiers surface when obvious | `TEST-J1939SUM-02`, `TEST-J1939SUM-03` |
| `REQ-J1939SUM-06` | Summary respects bounded-analysis controls | existing bounded-analysis coverage plus future dedicated summary-window assertions |
| `REQ-J1939SUM-07` | JSON field names remain stable | `TEST-J1939SUM-01`, `TEST-J1939SUM-02` |

## Test Cases

### TEST-J1939SUM-01 — Summary returns reconnaissance metrics

```gherkin
Given  a representative J1939 capture fixture contains multiple PGNs and at least one TP session
When   the operator runs `canarchy j1939 summary --file <capture> --json`
Then   the system shall return total frames, interfaces, unique arbitration IDs, first and last timestamps, top PGNs, top source addresses, DM1 summary fields, and TP summary fields
And    the JSON field names shall remain stable for automation
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`.

---

### TEST-J1939SUM-02 — Summary extracts printable TP identifiers when useful

```gherkin
Given  a J1939 TP capture fixture contains a completed payload whose bytes form obvious printable ASCII text
When   the operator runs `canarchy j1939 summary --file <capture> --json`
Then   the TP summary shall include that candidate printable identifier string
And    the candidate shall retain the related PGN and addressing metadata
```

**Fixture:** `tests/fixtures/j1939_tp_printable_id.candump`.

---

### TEST-J1939SUM-03 — Text output remains operator-friendly

```gherkin
Given  a J1939 TP capture fixture contains a printable candidate identifier
When   the operator runs `canarchy j1939 summary --file <capture> --text`
Then   the output shall show the summary sections for top PGNs and printable identifiers
And    the printable text shall remain visible in the operator-facing output
```

**Fixture:** `tests/fixtures/j1939_tp_printable_id.candump`.

## Fixtures And Environment

* `tests/fixtures/j1939_heavy_vehicle.candump`
* `tests/fixtures/j1939_tp_printable_id.candump`

## Explicit Non-Coverage

* non-ASCII identification decoding heuristics
* OEM-specific VIN or ECU-identification parsing rules
* multi-capture comparison behavior
