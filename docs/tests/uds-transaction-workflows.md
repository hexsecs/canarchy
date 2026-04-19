# Test Spec: UDS Transaction Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/uds-transaction-workflows.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate the structured UDS scan/trace transaction paths, protocol-aware table output, and transport failure handling.

The current implementation covers both transport-backed single-frame behavior on `python-can` and explicit sample/reference behavior on the scaffold backend.

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

### `TEST-UDS-TX-01` — Scan JSON output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy uds scan can0 --json`
Then   the result shall indicate active mode
And    the result shall include a responder count and structured transaction events
And    the result shall include an active scan warning alert
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-UDS-TX-02` — Trace JSON output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy uds trace can0 --json`
Then   the result shall indicate passive mode
And    the result shall include a transaction count and structured transaction events
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-UDS-TX-03` — Scan table output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy uds scan can0 --table`
Then   the output shall include responder and transaction sections
And    the output shall include protocol-aware service metadata
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-UDS-TX-04` — Trace table output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy uds trace can0 --table`
Then   the output shall include traced transaction summaries
And    the output shall include service and identifier information for each transaction
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-UDS-TX-05` — Transport error

```gherkin
Given  the interface `offline0` is not available
When   the operator runs `canarchy uds scan offline0 --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"TRANSPORT_UNAVAILABLE"`
```

**Fixture:** none (unavailable interface name).

---

## Fixtures And Environment

No dedicated fixture files are required.

Coverage currently uses:

* scaffold-backed sample/reference UDS transaction data for CLI-level coverage
* targeted mocked transport coverage for initial `python-can` single-frame behavior

## Explicit Non-Coverage

* physical ECU interaction
* advanced ISO-TP sequencing behavior beyond the current transaction model

## Traceability

This spec maps to the implemented UDS scan/trace behaviors covered in `test_cli.py`.
