# Test Spec: XCP Measurement / Calibration Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/xcp-workflows.md` |
| Test file | `tests/test_xcp.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-XCP-01` | Command/error naming + CONNECT parsing | `TEST-XCP-01`, `TEST-XCP-02` |
| `REQ-XCP-02` | Active scan over CONNECT | `TEST-XCP-03`, `TEST-XCP-07`, `TEST-XCP-10` |
| `REQ-XCP-03` | Trace pairs command/response | `TEST-XCP-04`, `TEST-XCP-08` |
| `REQ-XCP-04` | Read surfaces DAQ DTOs | `TEST-XCP-05`, `TEST-XCP-08` |
| `REQ-XCP-05` | Active-transmit safety on scan | `TEST-XCP-11` |
| `REQ-XCP-05a` | `xcp scan --dry-run` plans without transmit | `TEST-XCP-13` |
| `REQ-XCP-06` | Request/response id defaults + overrides | `TEST-XCP-07`, `TEST-XCP-12`, `TEST-XCP-13` |
| `REQ-XCP-07` | Invalid id structured error | `TEST-XCP-09` |
| `REQ-XCP-08` | Scaffold backend sample data | `TEST-XCP-07`, `TEST-XCP-08` |
| `REQ-XCP-09` | MCP tool exposure + active gate | `TEST-XCP-12`, `TEST-XCP-14` |

## Test Cases

### TEST-XCP-01 — Command and error code naming

```gherkin
Given  the XCP command catalog and error table
When   a code is looked up
Then   the system shall return the catalog name, or a hex fallback for unknown codes
```

**Fixture:** none.

---

### TEST-XCP-02 — CONNECT response parsing

```gherkin
Given  a CONNECT positive response payload
When   it is parsed
Then   the system shall report resources, max_cto, max_dto, and protocol/transport versions
```

**Fixture:** none.

---

### TEST-XCP-03 — Scan pairs CONNECT with a positive response

```gherkin
Given  a CONNECT request on the request id and a positive CTO response on the response id
When   the scan parser runs
Then   the system shall emit one CONNECT transaction with parsed connect_info
```

**Fixture:** none.

---

### TEST-XCP-04 — Trace pairs commands with responses (incl. error)

```gherkin
Given  GET_STATUS and GET_SEED command CTOs each followed by a response CTO
When   the trace parser runs
Then   the system shall emit named transactions, surfacing the GET_SEED error code by name
```

**Fixture:** none.

---

### TEST-XCP-05 — Read extracts DAQ DTOs and skips CTO frames

```gherkin
Given  two DTO frames (pid 0x00 / 0x01) and one CTO response frame on the response id
When   the read parser runs
Then   the system shall emit two measurement events and skip the CTO frame
```

**Fixture:** none.

---

### TEST-XCP-06 — Scan ignores unrelated arbitration ids

```gherkin
Given  a CONNECT exchange interleaved with an unrelated CAN id
When   the scan parser runs
Then   the system shall emit only the XCP responder transaction
```

**Fixture:** none.

---

### TEST-XCP-07 — `xcp scan` active envelope (scaffold backend)

```gherkin
Given  the scaffold transport backend
When   `canarchy xcp scan vcan0 --json` is invoked
Then   the envelope shall report mode active, one responder, and a CONNECT transaction
```

**Fixture:** scaffold backend sample provider.

---

### TEST-XCP-08 — `xcp trace` / `xcp read` passive envelopes (scaffold backend)

```gherkin
Given  the scaffold transport backend
When   `canarchy xcp trace vcan0 --json` and `canarchy xcp read vcan0 --json` are invoked
Then   trace shall report three transactions and read shall report two measurements
```

**Fixture:** scaffold backend sample provider.

---

### TEST-XCP-09 — Invalid CAN id returns a structured error

```gherkin
Given  a non-numeric --request-id
When   `canarchy xcp scan vcan0 --request-id not-an-id --json` is invoked
Then   the system shall exit 1 with an error code of `XCP_INVALID_ID`
```

**Fixture:** none.

---

### TEST-XCP-10 — Scan sends CONNECT and parses live responses

```gherkin
Given  a python-can backed transport with send/capture patched
When   `xcp_scan_events` is invoked
Then   the system shall send exactly one CONNECT frame and parse the captured response into a CONNECT transaction
```

**Fixture:** mocked transport `send` / `capture`.

---

### TEST-XCP-11 — Active-transmit safety gates `xcp scan`

```gherkin
Given  `CANARCHY_REQUIRE_ACTIVE_ACK=1` and no `--ack-active`
When   `canarchy xcp scan vcan0 --json` is invoked
Then   the system shall exit 1 with an error code of `ACTIVE_ACK_REQUIRED`
```

**Fixture:** environment variable patched in-test.

---

### TEST-XCP-12 — MCP exposure and argv mapping

```gherkin
Given  the MCP tool registry
Then   `xcp_scan`, `xcp_trace`, `xcp_read`, and `xcp_commands` shall be registered tools
And    `_build_argv` shall map them to the corresponding CLI argv
```

**Fixture:** none.

---

### TEST-XCP-13 — `xcp scan --dry-run` plans the CONNECT without transmitting

```gherkin
Given  a 29-bit request id and `--dry-run`
When   `canarchy xcp scan vcan0 --request-id 0x18DAF110 --dry-run --json` is invoked
Then   the system shall report mode dry_run with a planned CONNECT frame marked extended, opening no transport
```

**Fixture:** none.

---

### TEST-XCP-14 — MCP `xcp_scan` is gated behind active-transmit ack

```gherkin
Given  the MCP `xcp_scan` tool
When   it is called without `ack_active=true`
Then   the system shall refuse with `ACTIVE_TRANSMIT_REQUIRES_ACK` before any transport call
```

**Fixture:** none.

## Fixtures And Environment

Tests use crafted `CanFrame` lists for the parser cases and the scaffold
transport backend (`CANARCHY_TRANSPORT_BACKEND=scaffold`) for the CLI cases, so
no live hardware or network is required. The live-path test patches the
transport `send` / `capture` methods.

## Explicit Non-Coverage

* XCP-on-Ethernet / USB transports.
* A2L-based decoding of DAQ ODT entries into named signals.
* Active DAQ configuration and calibration-write command sequences.
