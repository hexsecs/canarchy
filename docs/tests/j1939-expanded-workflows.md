# Test Spec: Expanded J1939 Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Related design spec | `docs/design/j1939-expanded-workflows.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate that the expanded J1939 workflows preserve protocol-first behavior and correctly parse supported SPN, TP, and DM1 scenarios.

## Coverage Requirements

* `j1939 spn` capture-file requirement
* `j1939 spn` structured value extraction from a supported SPN
* `j1939 tp` BAM session summary and reassembly
* `j1939 dm1` parsing for both direct and TP-reassembled messages
* table output for DM1 remains human-readable

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-J1939-01` | `TEST-J1939-01`, `TEST-J1939-02`, `TEST-J1939-03`, `TEST-J1939-04`, `TEST-J1939-05` |
| `REQ-J1939-02` | `TEST-J1939-02` |
| `REQ-J1939-03` | `TEST-J1939-03` |
| `REQ-J1939-04` | `TEST-J1939-04` |
| `REQ-J1939-05` | `TEST-J1939-02`, `TEST-J1939-03`, `TEST-J1939-04`, `TEST-J1939-05` |
| `REQ-J1939-06` | `TEST-J1939-01` |
| `REQ-J1939-07` | Deferred |
| `REQ-J1939-08` | Deferred |

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

## Fixtures And Environment

* existing `sample.candump`
* `j1939_dm1_tp.candump` for TP and DM1 coverage

## Explicit Non-Coverage

* full RTS/CTS transport control flows
* large multi-packet TP sessions beyond the BAM starter path
* broad SPN database coverage beyond the curated starter decoder set

## Traceability

This spec maps to the J1939 expansion acceptance criteria around protocol-relevant output fields, SPN/TP/DM1 behavior, and representative transport and DM coverage.
