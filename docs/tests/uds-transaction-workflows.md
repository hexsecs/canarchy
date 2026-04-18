# Test Spec: UDS Transaction Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/uds-transaction-workflows.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate the structured UDS scan/trace transaction paths, protocol-aware table output, and transport failure handling.

## Coverage Requirements

* scan JSON output with transaction events and active warning
* trace JSON output with transaction events
* protocol-aware table rendering for scan and trace
* transport-unavailable error handling

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-UDS-TX-01` | `TEST-UDS-TX-01`, `TEST-UDS-TX-02` |
| `REQ-UDS-TX-02` | `TEST-UDS-TX-01`, `TEST-UDS-TX-03` |
| `REQ-UDS-TX-03` | `TEST-UDS-TX-02`, `TEST-UDS-TX-04` |
| `REQ-UDS-TX-04` | `TEST-UDS-TX-01` |
| `REQ-UDS-TX-05` | `TEST-UDS-TX-03`, `TEST-UDS-TX-04` |
| `REQ-UDS-TX-06` | `TEST-UDS-TX-05` |

## Representative Test Cases

### `TEST-UDS-TX-01` Scan JSON output

Action: run `canarchy uds scan can0 --json`.  
Assert: output includes active mode, responder count, transaction events, and the active scan warning.

### `TEST-UDS-TX-02` Trace JSON output

Action: run `canarchy uds trace can0 --json`.  
Assert: output includes passive mode, transaction count, and structured transaction events.

### `TEST-UDS-TX-03` Scan table output

Action: run `canarchy uds scan can0 --table`.  
Assert: output includes responder and transaction sections with protocol-aware service metadata.

### `TEST-UDS-TX-04` Trace table output

Action: run `canarchy uds trace can0 --table`.  
Assert: output includes traced transaction summaries with service and identifier information.

### `TEST-UDS-TX-05` Transport error

Action: run `canarchy uds scan offline0 --json`.  
Assert: exit code `2` and `errors[0].code == "TRANSPORT_UNAVAILABLE"`.

## Fixtures And Environment

No dedicated fixtures are required. Coverage uses the deterministic scaffold UDS transaction set.

## Explicit Non-Coverage

* physical ECU interaction
* advanced ISO-TP sequencing behavior beyond the current transaction model

## Traceability

This spec maps to the implemented UDS scan/trace behaviors covered in `test_cli.py`.
