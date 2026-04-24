# Test Spec: Expanded J1939 Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Related design spec | `docs/design/j1939-expanded-workflows.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate that the expanded J1939 workflows preserve protocol-first behavior and correctly parse supported SPN, TP, DM1, and inventory scenarios.

## Coverage Requirements

* `j1939 spn` capture-file requirement
* `j1939 spn` structured value extraction from a supported SPN
* `j1939 tp` BAM session summary and reassembly
* `j1939 dm1` parsing for both direct and TP-reassembled messages
* `j1939 inventory` source-address inventory assembly from identification and DM1 context
* table output for DM1 remains human-readable

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-J1939-01` | `TEST-J1939-01`, `TEST-J1939-02`, `TEST-J1939-03`, `TEST-J1939-04`, `TEST-J1939-05`, `TEST-J1939-08`, `TEST-J1939-09` |
| `REQ-J1939-02` | `TEST-J1939-02` |
| `REQ-J1939-03` | `TEST-J1939-03` |
| `REQ-J1939-04` | `TEST-J1939-04` |
| `REQ-J1939-05` | `TEST-J1939-02`, `TEST-J1939-03`, `TEST-J1939-04`, `TEST-J1939-05`, `TEST-J1939-06`, `TEST-J1939-07` |
| `REQ-J1939-06` | `TEST-J1939-01` |
| `REQ-J1939-07` | Deferred |
| `REQ-J1939-08` | Deferred |
| `REQ-J1939-09` | `TEST-J1939-06`, `TEST-J1939-07` |
| `REQ-J1939-10` | `TEST-J1939-06`, `TEST-J1939-07` |
| `REQ-J1939-11` | `TEST-J1939-08`, `TEST-J1939-09` |
| `REQ-J1939-12` | `TEST-J1939-08`, `TEST-J1939-09` |
| `REQ-J1939-13` | `TEST-J1939-08`, `TEST-J1939-09` |
| `REQ-J1939-14` | `TEST-J1939-08` |

## Representative Test Cases

### `TEST-J1939-01` — SPN capture-file requirement

```gherkin
Given  no capture file is provided
When   the operator runs `canarchy j1939 spn 110 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"CAPTURE_FILE_REQUIRED"`
```

**Fixture:** none required.

---

### `TEST-J1939-02` — SPN observation extraction

```gherkin
Given  a capture fixture containing PGN `65262` is available
When   the operator runs `canarchy j1939 spn 110 --file sample.candump --json`
Then   exactly one observation shall be returned
And    the observation shall include the expected SPN, PGN, source address, decoded value, and units
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-J1939-03` — TP BAM session summary

```gherkin
Given  the fixture `j1939_dm1_tp.candump` contains TP.CM BAM and TP.DT frames for a DM1 payload
When   the operator runs `canarchy j1939 tp j1939_dm1_tp.candump --json`
Then   exactly one complete BAM session shall be returned
And    the session shall include the expected transferred PGN, packet count, and reassembled payload bytes
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### `TEST-J1939-04` — DM1 direct and transported parsing

```gherkin
Given  the fixture `j1939_dm1_tp.candump` contains one direct DM1 and one TP-reassembled DM1
When   the operator runs `canarchy j1939 dm1 j1939_dm1_tp.candump --json`
Then   both DM1 messages shall be returned
And    the TP-reassembled message shall have two DTCs
And    the direct message shall preserve its source address and FMI
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### `TEST-J1939-05` — DM1 table output

```gherkin
Given  the fixture `j1939_dm1_tp.candump` is available
When   the operator runs `canarchy j1939 dm1 j1939_dm1_tp.candump --table`
Then   the output shall include the command header
And    the output shall include a message section with a transport label
And    the output shall include DTC summaries for each message
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### `TEST-J1939-06` — TP printable identification text

```gherkin
Given  the fixture `j1939_tp_printable_id.candump` contains a completed TP payload with obvious printable ASCII identification text
When   the operator runs `canarchy j1939 tp j1939_tp_printable_id.candump --json`
Then   the returned TP session shall preserve `reassembled_data`
And    the session shall include `decoded_text` plus a heuristic flag
And    the session shall include a stable payload label when the transferred PGN is known to be identification-style data
```

**Fixture:** `tests/fixtures/j1939_tp_printable_id.candump`.

---

### `TEST-J1939-07` — TP table output surfaces printable identification text

```gherkin
Given  the fixture `j1939_tp_printable_id.candump` contains a printable TP identification payload
When   the operator runs `canarchy j1939 tp j1939_tp_printable_id.candump --table`
Then   the operator-facing output shall include the payload label when available
And    the operator-facing output shall include the decoded printable text without hiding the TP session summary context
```

**Fixture:** `tests/fixtures/j1939_tp_printable_id.candump`.

---

### `TEST-J1939-08` — Inventory JSON output associates IDs with source addresses

```gherkin
Given  the fixture `j1939_inventory.candump` contains per-source operational PGNs, component-identification TP payloads, a vehicle-identification TP payload, and DM1 traffic
When   the operator runs `canarchy j1939 inventory --file j1939_inventory.candump --json`
Then   the result shall include one inventory node per observed source address
And    the source-address rows shall include top PGNs plus first and last timestamps
And    the reporting source address shall include the decoded component-identification and vehicle-identification strings when available
And    the reporting source address shall include DM1 presence metadata
```

**Fixture:** `tests/fixtures/j1939_inventory.candump`.

---

### `TEST-J1939-09` — Inventory table output remains operator-friendly

```gherkin
Given  the fixture `j1939_inventory.candump` is available
When   the operator runs `canarchy j1939 inventory --file j1939_inventory.candump --table`
Then   the output shall include the command header
And    the output shall include the decoded vehicle identification text when available
And    the output shall include per-source rows with component-identification and DM1 presence summaries
```

**Fixture:** `tests/fixtures/j1939_inventory.candump`.

---

## Fixtures And Environment

* existing `sample.candump`
* `j1939_dm1_tp.candump` for TP and DM1 coverage
* `j1939_tp_printable_id.candump` for printable TP identification coverage
* `j1939_inventory.candump` for source-address inventory coverage

## Explicit Non-Coverage

* full RTS/CTS transport control flows
* large multi-packet TP sessions beyond the BAM starter path
* broad SPN database coverage beyond the curated starter decoder set

## Traceability

This spec maps to the J1939 expansion acceptance criteria around protocol-relevant output fields, SPN/TP/DM1 behavior, and representative transport and DM coverage.
