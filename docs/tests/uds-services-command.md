# Test Spec: `uds services` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/uds-services-command.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate that `uds services` returns a stable protocol-reference catalog and renders it consistently across structured and table output modes.

## Coverage Requirements

* command succeeds without a transport interface
* JSON output contains stable service catalog metadata
* table output presents protocol-aware service summaries
* raw output follows standard command-success behavior

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-UDS-SVC-01` | `TEST-UDS-SVC-01` |
| `REQ-UDS-SVC-02` | `TEST-UDS-SVC-01`, `TEST-UDS-SVC-02` |
| `REQ-UDS-SVC-03` | `TEST-UDS-SVC-01`, `TEST-UDS-SVC-02` |
| `REQ-UDS-SVC-04` | `TEST-UDS-SVC-01` |
| `REQ-UDS-SVC-05` | `TEST-UDS-SVC-02`, `TEST-UDS-SVC-03` |

## Representative Test Cases

### `TEST-UDS-SVC-01` JSON catalog output

Action: run `canarchy uds services --json`.  
Assert: the command succeeds and returns `service_count` plus a `services` list containing known entries such as `DiagnosticSessionControl` and `SecurityAccess`.

### `TEST-UDS-SVC-02` Table catalog output

Action: run `canarchy uds services --table`.  
Assert: output includes the command header, service count, and catalog rows with service and positive-response identifiers.

### `TEST-UDS-SVC-03` Raw output behavior

Action: run `canarchy uds services --raw`.  
Assert: raw output emits the command name on success.

## Fixtures And Environment

No fixtures are required. Tests use the deterministic in-repo UDS service catalog.

## Explicit Non-Coverage

* ECU-specific service support detection
* negative-response code catalogs
* OEM-specific service metadata

## Traceability

This spec maps to the `uds services` requirements around deterministic catalog output, protocol metadata, and standard CANarchy output-mode behavior.
