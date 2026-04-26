# Test Spec: Scapy Diagnostic Integration

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/scapy-diagnostic-integration.md` |
| Test file | `tests/test_uds.py`, `tests/test_cli.py`, `tests/test_models.py`, `tests/test_scapy_uds.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-SCAPY-01` | Scapy stays behind a CANarchy-owned adapter boundary | `TEST-SCAPY-01`, `TEST-SCAPY-02` |
| `REQ-SCAPY-02` | Optional Scapy enriches UDS transactions without changing the envelope | `TEST-SCAPY-02`, `TEST-SCAPY-03`, `TEST-SCAPY-04` |
| `REQ-SCAPY-03` | Built-in decoder path remains functional when Scapy is unavailable | `TEST-SCAPY-01`, `TEST-SCAPY-04` |
| `REQ-SCAPY-04` | Negative response code and name are surfaced in structured output | `TEST-SCAPY-03`, `TEST-SCAPY-05` |
| `REQ-SCAPY-05` | Existing command names and event types remain stable | `TEST-SCAPY-03`, `TEST-SCAPY-04`, `TEST-SCAPY-05` |

## Test Cases

### TEST-SCAPY-01 — Missing Scapy falls back cleanly

```gherkin
Given  the optional Scapy dependency is unavailable
When   the UDS Scapy adapter is asked to inspect a payload
Then   the system shall return no Scapy inspection result
And    the built-in UDS path shall remain usable
```

**Fixture:** mocked missing Scapy modules.

---

### TEST-SCAPY-02 — Scapy adapter normalizes packet summaries

```gherkin
Given  a Scapy-compatible UDS packet class is available
When   the adapter inspects a UDS payload
Then   the system shall return a stable summary string
And    packet fields shall be normalized into JSON-safe data
```

**Fixture:** mocked Scapy packet decoder.

---

### TEST-SCAPY-03 — UDS transaction enrichment includes Scapy summaries

```gherkin
Given  the Scapy-backed decoder path is reported as available
When   the UDS trace transaction builder processes a request and response pair
Then   the system shall preserve the existing transaction identity fields
And    the transaction shall include Scapy-backed request and response summaries
```

**Fixture:** mocked Scapy inspection results.

---

### TEST-SCAPY-04 — CLI reports the active protocol decoder path

```gherkin
Given  `uds trace` runs successfully through the built-in decoder path
When   the operator runs `canarchy uds trace can0 --json`
Then   the result shall include `protocol_decoder="built-in"`
And    the command shall preserve the canonical CANarchy result envelope
```

**Fixture:** scaffold backend sample/reference transactions.

---

### TEST-SCAPY-05 — Negative responses include named NRC metadata

```gherkin
Given  a traced UDS response is a negative response frame
When   the transaction builder processes that response
Then   the system shall include `negative_response_code`
And    the system shall include a human-readable `negative_response_name`
```

**Fixture:** pure-function UDS request/negative-response frames.

## Fixtures And Environment

* mocked missing Scapy module state
* mocked Scapy packet decoder
* scaffold-backed UDS sample/reference transactions
* pure-function UDS frame sequences for negative responses

## Explicit Non-Coverage

* Scapy-backed transmission workflows
* deep ECU-specific packet field interpretation beyond stable summary-level output
* fuzzing or mutation workflows that may later reuse the Scapy adapter boundary
