# Test Spec: UDS Transaction Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Partial |
| Related design spec | `docs/design/uds-transaction-workflows.md` |
| Primary test area | CLI, protocol |

## Test Objectives

Validate the structured UDS scan/trace transaction paths, protocol-aware table output, ISO-TP multi-frame response handling, and transport failure handling.

The current implementation covers transport-backed multi-frame response reassembly on `python-can` and explicit sample/reference behavior on the scaffold backend.

## Coverage Requirements

* scan JSON output with transaction events and preflight warning behavior
* trace JSON output with transaction events
* protocol-aware table rendering for scan and trace
* ISO-TP reassembly for first-frame and consecutive-frame responses
* incomplete transaction reporting for truncated or out-of-order responses
* flow-control frame filtering
* transport-unavailable error handling

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-UDS-TX-01` | `TEST-UDS-TX-01`, `TEST-UDS-TX-02` |
| `REQ-UDS-TX-02` | `TEST-UDS-TX-01` |
| `REQ-UDS-TX-03` | `TEST-UDS-TX-01` |
| `REQ-UDS-TX-07` | Deferred |
| `REQ-UDS-TX-08` | Deferred |
| `REQ-UDS-TX-04` | `TEST-UDS-TX-02` |
| `REQ-UDS-TX-05` | `TEST-UDS-TX-03`, `TEST-UDS-TX-04` |
| `REQ-UDS-TX-06` | `TEST-UDS-TX-05` |
| `REQ-UDS-TX-09` | `TEST-UDS-TX-06`, `TEST-UDS-TX-08` |
| `REQ-UDS-TX-10` | `TEST-UDS-TX-07`, `TEST-UDS-TX-08` |
| `REQ-UDS-TX-11` | `TEST-UDS-TX-06` |

## Representative Test Cases

### `TEST-UDS-TX-01` — Scan JSON output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy uds scan can0 --json`
Then   the result shall indicate active mode
And    the result shall include a responder count and structured transaction events
And    the command shall emit a preflight warning on `stderr`
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

### `TEST-UDS-TX-06` — Multi-frame response reassembly

```gherkin
Given  a transport-backed UDS response split across ISO-TP first and consecutive frames
When   the reassembly path processes the captured frames
Then   the system shall emit a single `uds_transaction` event with the full reassembled `response_data`
And    any flow-control frame shall not appear as a transaction in the output
```

**Fixture:** mocked `python-can` capture frames.

---

### `TEST-UDS-TX-07` — Truncated multi-frame response emits incomplete transaction

```gherkin
Given  a segmented UDS response whose consecutive frames do not complete the declared ISO-TP payload length
When   the reassembly path reaches the end of the capture
Then   the system shall emit one `uds_transaction` event with `complete` equal to `false`
And    the event shall preserve the partial `response_data` that was observed
```

**Fixture:** pure-function UDS reassembly frames.

---

### `TEST-UDS-TX-08` — Out-of-order consecutive frame emits incomplete transaction

```gherkin
Given  a segmented UDS response whose next consecutive frame has the wrong sequence number
When   the reassembly path processes the response
Then   the system shall emit one `uds_transaction` event with `complete` equal to `false`
And    the event shall preserve the partial payload captured before the sequence error
```

**Fixture:** pure-function UDS reassembly frames.

---

## Fixtures And Environment

No dedicated fixture files are required.

Coverage currently uses:

* scaffold-backed sample/reference UDS transaction data for CLI-level coverage
* targeted mocked transport coverage for `python-can` multi-frame behavior
* pure-function ISO-TP reassembly frame sequences

## Explicit Non-Coverage

* physical ECU interaction
* segmented UDS request transmission

## Traceability

This spec maps to the implemented UDS scan/trace behaviors covered in `test_cli.py`.
