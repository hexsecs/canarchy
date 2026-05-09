# Test Spec: `uds services` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/uds-services-command.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate that `uds services` returns a stable protocol-reference catalog and renders it consistently across structured and text output modes.

## Coverage Requirements

* command succeeds without a transport interface
* JSON output contains stable service catalog metadata
* text output presents protocol-aware service summaries

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-UDS-SVC-01` | `TEST-UDS-SVC-01` |
| `REQ-UDS-SVC-02` | `TEST-UDS-SVC-01`, `TEST-UDS-SVC-02` |
| `REQ-UDS-SVC-03` | `TEST-UDS-SVC-01`, `TEST-UDS-SVC-02` |
| `REQ-UDS-SVC-04` | `TEST-UDS-SVC-01` |

## Representative Test Cases

### `TEST-UDS-SVC-01` — JSON catalog output

```gherkin
Given  no transport interface or live bus connection is required
When   the operator runs `canarchy uds services --json`
Then   the command shall succeed
And    the result shall include a `service_count` field
And    the result shall include a `services` list containing known entries such as `DiagnosticSessionControl` and `SecurityAccess`
```

**Fixture:** none required (in-repo UDS service catalog).

---

### `TEST-UDS-SVC-02` — Table catalog output

```gherkin
Given  no transport interface or live bus connection is required
When   the operator runs `canarchy uds services --text`
Then   the output shall include the command header and service count
And    the output shall include catalog rows with service and positive-response identifiers
```

**Fixture:** none required (in-repo UDS service catalog).

## Fixtures And Environment

No fixtures are required. Tests use the deterministic in-repo UDS service catalog.

## Explicit Non-Coverage

* ECU-specific service support detection
* negative-response code catalogs
* OEM-specific service metadata

## Traceability

This spec maps to the `uds services` requirements around deterministic catalog output, protocol metadata, and standard CANarchy output-mode behavior.
