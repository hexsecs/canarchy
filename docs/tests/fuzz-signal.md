# Test Spec: `canarchy fuzz signal` — DBC-aware signal mutation

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/fuzz-signal.md` |
| Test file | `tests/test_fuzz.py`, `tests/test_fuzz_cli.py`, `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-FZS-02` | in_bounds stays within declared range | `TEST-FZS-01`, `TEST-FZS-02` |
| `REQ-FZS-03` | out_of_bounds falls outside declared range | `TEST-FZS-03`, `TEST-FZS-08` |
| `REQ-FZS-04` | boundary emits min/max ± 1 lsb | `TEST-FZS-04`, `TEST-FZS-09` |
| `REQ-FZS-05` | enum_gaps emits only undefined choices | `TEST-FZS-05` |
| `REQ-FZS-06` | non-target signals held at baseline | `TEST-FZS-10` |
| `REQ-FZS-07` | determinism for a fixed seed | `TEST-FZS-06`, `TEST-FZS-13` |
| `REQ-FZS-08` | unknown signal errors | `TEST-FZS-07`, `TEST-FZS-15` |
| `REQ-FZS-09` | enum_gaps without choices errors | `TEST-FZS-11`, `TEST-FZS-16` |
| `REQ-FZS-10` | unknown message errors | `TEST-FZS-14` |
| `REQ-FZS-11` | non-positive rate errors | `TEST-FZS-17` |
| `REQ-FZS-13` | dry-run plans without an interface | `TEST-FZS-12` |
| `REQ-FZS-14` | MCP mirror requires ack, defaults dry-run | `TEST-FZS-18`, `TEST-FZS-19` |

## Test Cases

### TEST-FZS-01 — in_bounds stays within declared range

```gherkin
Given  the EngineStatus1 message from sample.dbc
When   signal_payload runs for CoolantTemp in mode in_bounds with count 16
Then   the system shall decode every payload's CoolantTemp into [0, 210]
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-03 — out_of_bounds falls outside declared range

```gherkin
Given  the EngineStatus1 message from sample.dbc
When   signal_payload runs for CoolantTemp in mode out_of_bounds
Then   the system shall decode every payload's CoolantTemp to a value < 0 or > 210
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-04 — boundary emits min/max ± 1 lsb

```gherkin
Given  the EngineStatus1 message from sample.dbc
When   signal_payload runs for CoolantTemp in mode boundary
Then   the decoded value set shall be a superset of {0, 210, 1, 209, -1, 211}
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-05 — enum_gaps emits only undefined choices

```gherkin
Given  the HVAC_Mode message from complex.dbc with choices for 0..5
When   signal_payload runs for HVAC_Mode in mode enum_gaps
Then   the decoded raw value set shall equal {6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
```

**Fixture:** `tests/fixtures/complex.dbc`.

### TEST-FZS-09 — boundary drops unrepresentable steps

```gherkin
Given  LampState spans the full 8-bit range [0, 255]
When   signal_payload runs for LampState in mode boundary
Then   the decoded value set shall equal {0, 255, 1, 254}
And    min-1 / max+1 shall be omitted because they are not representable
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-12 — dry-run plans without an interface

```gherkin
Given  no CAN interface is configured
When   the operator runs `canarchy fuzz signal --dbc sample.dbc --message EngineStatus1 --signal CoolantTemp --mode boundary --dry-run --jsonl`
Then   the system shall exit 0
And    emit one frame event per planned payload with dry_run=true
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-14 — unknown message errors

```gherkin
Given  sample.dbc has no message named NoSuchMessage
When   the operator runs `canarchy fuzz signal --dbc sample.dbc --message NoSuchMessage ... --dry-run --json`
Then   the system shall exit non-zero
And    the response shall contain an error with code "DBC_MESSAGE_NOT_FOUND"
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-18 — MCP fuzz_signal requires ack_active

```gherkin
Given  the MCP server
When   fuzz_signal is called without ack_active
Then   the system shall return an error with code "ACTIVE_TRANSMIT_REQUIRES_ACK"
```

**Fixture:** `tests/fixtures/sample.dbc`.

### TEST-FZS-19 — MCP fuzz_signal defaults to dry-run

```gherkin
Given  the MCP server
When   fuzz_signal is called with ack_active=true and no dry_run
Then   the system shall return data.mode == "dry_run" and data.signal_mode == "boundary"
```

**Fixture:** `tests/fixtures/sample.dbc`.

## Fixtures And Environment

* `tests/fixtures/sample.dbc` — EngineStatus1 / EngineSpeed1 messages (no choices).
* `tests/fixtures/complex.dbc` — HVAC_Mode message with a value table, used for
  `enum_gaps`.

## Explicit Non-Coverage

* Multiplexed-message mutation.
* Negative-scale signals (handled but not exhaustively asserted).
* Live transmission against real hardware (only the LocalTransport / scaffold and
  the active-ack gate are exercised).
