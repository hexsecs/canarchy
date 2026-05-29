# Test Spec: `canarchy fuzz spn` — J1939 SPN-aware mutation

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/fuzz-spn.md` |
| Test file | `tests/test_fuzz.py`, `tests/test_fuzz_cli.py`, `tests/test_mcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-FZP-02` | in_bounds within operational range | `TEST-FZP-01` |
| `REQ-FZP-03` | not_available sentinel per width | `TEST-FZP-02`, `TEST-FZP-07`, `TEST-FZP-08` |
| `REQ-FZP-04` | error sentinel per width | `TEST-FZP-03`, `TEST-FZP-07`, `TEST-FZP-08` |
| `REQ-FZP-05` | boundary covers operational edges | `TEST-FZP-04`, `TEST-FZP-11` |
| `REQ-FZP-06` | out_of_bounds one lsb past max | `TEST-FZP-05` |
| `REQ-FZP-07` | SPN bytes targeted, rest 0xFF | `TEST-FZP-06` |
| `REQ-FZP-08` | determinism for a fixed seed | `TEST-FZP-09` |
| `REQ-FZP-09` | unknown SPN errors | `TEST-FZP-10`, `TEST-FZP-12` |
| `REQ-FZP-10` | --pgn mismatch errors | `TEST-FZP-13` |
| `REQ-FZP-14` | MCP mirror requires ack, defaults dry-run | `TEST-FZP-14`, `TEST-FZP-15` |

## Test Cases

### TEST-FZP-02 — not_available sentinel

```gherkin
Given  SPN 110 (Engine Coolant Temperature, 1-byte, PGN 65262)
When   spn_payload runs in mode not_available
Then   the SPN byte shall be 0xFF
```

**Fixture:** built-in J1939 metadata.

### TEST-FZP-07 — sentinel/operational-max helpers across widths

```gherkin
Given  the pure-function J1939 helpers
When   evaluated for 1 / 2 / 4-byte widths
Then   not_available shall be 0xFF / 0xFFFF / 0xFFFFFFFF
And    error shall be 0xFE / 0xFEFF / 0xFEFFFFFF
And    operational max shall be 0xFA / 0xFAFF / 0xFAFFFFFF
```

**Fixture:** none.

### TEST-FZP-08 — width 2 / width 4 little-endian placement

```gherkin
Given  SPN 27 (2-byte) and SPN 182 (4-byte) from the built-in metadata
When   spn_payload runs in not_available / error modes
Then   the little-endian decode of the SPN field shall equal the width's sentinel
```

**Fixture:** built-in J1939 metadata.

### TEST-FZP-04 — boundary covers operational edges

```gherkin
Given  SPN 110 with operational raw range [0, 0xFA]
When   spn_payload runs in mode boundary
Then   the SPN bytes shall be the set {0x00, 0xFA, 0x01, 0xF9, 0xFB}
```

**Fixture:** built-in J1939 metadata.

### TEST-FZP-11 — CLI boundary frames carry the J1939 arbitration id

```gherkin
Given  no interface is configured
When   the operator runs `canarchy fuzz spn --spn 110 --mode not_available --dry-run --json`
Then   the frame arbitration id shall be 0x18FEEE00 (PGN 65262 broadcast)
And    the frame shall be an extended-id frame with data starting 0xff
```

**Fixture:** built-in J1939 metadata.

### TEST-FZP-14 — MCP fuzz_spn requires ack_active

```gherkin
Given  the MCP server
When   fuzz_spn is called without ack_active
Then   the system shall return an error with code "ACTIVE_TRANSMIT_REQUIRES_ACK"
```

**Fixture:** none.

## Fixtures And Environment

All cases use CANarchy's bundled J1939 metadata (`canarchy.j1939_metadata`):
SPN 110 (1-byte), SPN 27 (2-byte), SPN 182 (4-byte). No live bus.

## Explicit Non-Coverage

* Multi-packet (BAM/TP) SPNs larger than a single 8-byte PGN payload.
* DBC-sourced SPN metadata (engine uses built-in metadata only).
* Live transmission against real hardware.
