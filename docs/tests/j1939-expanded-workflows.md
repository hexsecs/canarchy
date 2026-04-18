# Test Spec: Expanded J1939 Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
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
| `REQ-J1939-01` | `TEST-J1939-01`, `TEST-J1939-02` |
| `REQ-J1939-02` | `TEST-J1939-03` |
| `REQ-J1939-03` | `TEST-J1939-04`, `TEST-J1939-05` |
| `REQ-J1939-04` | `TEST-J1939-02` |
| `REQ-J1939-05` | `TEST-J1939-03` |
| `REQ-J1939-06` | `TEST-J1939-04`, `TEST-J1939-05` |
| `REQ-J1939-07` | `TEST-J1939-02`, `TEST-J1939-03`, `TEST-J1939-05` |
| `REQ-J1939-08` | `TEST-J1939-01` |

## Representative Test Cases

### `TEST-J1939-01` SPN capture-file requirement

Action: run `canarchy j1939 spn 110 --json`.  
Assert: exit code `1` and `errors[0].code == "CAPTURE_FILE_REQUIRED"`.

### `TEST-J1939-02` SPN observation extraction

Setup: use a capture fixture containing PGN `65262`.  
Action: run `canarchy j1939 spn 110 --file sample.candump --json`.  
Assert: one observation is returned with the expected SPN, PGN, source address, decoded value, and units.

### `TEST-J1939-03` TP BAM session summary

Setup: use a fixture containing TP.CM BAM and TP.DT frames for a DM1 payload.  
Action: run `canarchy j1939 tp j1939_dm1_tp.candump --json`.  
Assert: one complete BAM session is returned with the expected transferred PGN, packet count, and reassembled payload bytes.

### `TEST-J1939-04` DM1 direct and transported parsing

Setup: use a fixture containing one direct DM1 and one TP-reassembled DM1.  
Action: run `canarchy j1939 dm1 j1939_dm1_tp.candump --json`.  
Assert: both messages are returned; the TP message has two DTCs and the direct message preserves its source address and FMI.

### `TEST-J1939-05` DM1 table output

Action: run `canarchy j1939 dm1 j1939_dm1_tp.candump --table`.  
Assert: output includes the command header, message section, transport label, and DTC summaries.

## Fixtures And Environment

* existing `sample.candump`
* `j1939_dm1_tp.candump` for TP and DM1 coverage

## Explicit Non-Coverage

* full RTS/CTS transport control flows
* large multi-packet TP sessions beyond the BAM starter path
* broad SPN database coverage beyond the curated starter decoder set

## Traceability

This spec maps to the J1939 expansion acceptance criteria around protocol-relevant output fields, SPN/TP/DM1 behavior, and representative transport and DM coverage.
