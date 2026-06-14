# Test Spec: DoIP Diagnostic Workflows

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/doip-diagnostic-workflows.md` |
| Test file | `tests/test_doip.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-DOIP-01` | Codec encode/decode round-trips | `TEST-DOIP-01`, `TEST-DOIP-02` |
| `REQ-DOIP-02` | `doip://` URI routes to the DoIP transport | `TEST-DOIP-03`, `TEST-DOIP-04` |
| `REQ-DOIP-03` | `uds scan` enumerates sessions over DoIP | `TEST-DOIP-03` |
| `REQ-DOIP-04` | `uds trace` runs a session + tester-present exchange | `TEST-DOIP-04` |
| `REQ-DOIP-05` | Active-transmit safety gates DoIP scan and trace | `TEST-DOIP-08` |
| `REQ-DOIP-06` | Malformed target returns `DOIP_INVALID_TARGET` | `TEST-DOIP-05` |
| `REQ-DOIP-07` | Unreachable endpoint / timeout error | `TEST-DOIP-06` |
| `REQ-DOIP-08` | Diagnostic NACK / protocol errors | `TEST-DOIP-07`, `TEST-DOIP-02` |
| `REQ-DOIP-09` | UDS negative responses are transactions, not errors | `TEST-DOIP-03` |
| `REQ-DOIP-10` | MCP rejects `doip://` targets | `TEST-DOIP-09` |

## Test Cases

### TEST-DOIP-01 — Codec round-trips routing activation and diagnostic messages

```gherkin
Given  a routing-activation request and a diagnostic message
When   each is encoded and decoded by the DoIP codec
Then   the system shall recover the payload type, source/target addresses, and UDS user data
```

**Fixture:** none (constructed in-test).

---

### TEST-DOIP-02 — Malformed DoIP messages raise structured errors

```gherkin
Given  a DoIP message with a corrupted inverse-version byte, and a truncated message
When   each is decoded
Then   the system shall raise `DOIP_PROTOCOL_ERROR`
```

**Fixture:** none.

---

### TEST-DOIP-03 — `uds scan` enumerates sessions over loopback DoIP

```gherkin
Given  a loopback DoIP responder scripting default, programming, and extended session replies
And    the programming-session reply is a UDS negative response (0x7F 0x10 0x22)
When   `canarchy uds scan doip://127.0.0.1:<port>?logical_address=0x0E80 --json` is invoked
Then   the envelope shall report `transport: doip`, `mode: active`, and three transactions
And    the negative response shall appear as a transaction with `negative_response_code` 0x22
```

**Fixture:** in-process `DoipResponder` bound to loopback (no live network).

---

### TEST-DOIP-04 — `uds trace` runs session control plus tester present

```gherkin
Given  a loopback DoIP responder replying to DiagnosticSessionControl and TesterPresent
When   `canarchy uds trace doip://127.0.0.1:<port>?logical_address=0x0E80 --json` is invoked
Then   the envelope shall report two transactions named DiagnosticSessionControl and TesterPresent
```

**Fixture:** in-process `DoipResponder`.

---

### TEST-DOIP-05 — Malformed target returns a user error

```gherkin
Given  a DoIP target with no logical_address query parameter
When   `canarchy uds scan doip://127.0.0.1:13400 --json` is invoked
Then   the system shall exit 1 with an error code of `DOIP_INVALID_TARGET`
```

**Fixture:** none.

---

### TEST-DOIP-06 — Unreachable endpoint returns a transport error

```gherkin
Given  a TCP port with nothing listening
When   `canarchy uds scan doip://127.0.0.1:<port>?logical_address=0x0E80&timeout=0.3 --json` is invoked
Then   the system shall exit 2 with an error code of `DOIP_CONNECTION_FAILED`
```

**Fixture:** an ephemeral port bound and immediately closed.

---

### TEST-DOIP-07 — Diagnostic negative acknowledgement returns a transport error

```gherkin
Given  a loopback DoIP responder that negatively acknowledges the diagnostic message
When   `canarchy uds scan <doip-uri> --json` is invoked
Then   the system shall exit 2 with an error code of `DOIP_DIAGNOSTIC_NACK`
```

**Fixture:** in-process `DoipResponder` configured with `nack_requests`.

---

### TEST-DOIP-08 — Active-transmit safety gates DoIP scan and trace

```gherkin
Given  `CANARCHY_REQUIRE_ACTIVE_ACK=1` and no `--ack-active` flag
When   `canarchy uds scan <doip-uri>` and `canarchy uds trace <doip-uri>` are invoked
Then   each shall exit 1 with an error code of `ACTIVE_ACK_REQUIRED`
```

**Fixture:** environment variable patched in-test.

---

### TEST-DOIP-09 — MCP rejects DoIP targets on the UDS tools

```gherkin
Given  the MCP `uds_scan` and `uds_trace` tools
When   each is called with a `doip://` interface
Then   the response envelope shall report `ok: false` with code `DOIP_MCP_EXCLUDED`
```

**Fixture:** none.

## Fixtures And Environment

The `DoipResponder` helper is a threaded loopback TCP server that speaks DoIP
(routing activation + diagnostic message exchange) and scripts UDS responses per
request. All network activity is on `127.0.0.1`; no live hardware or external
network is touched. The unreachable-endpoint case binds and closes an ephemeral
port to guarantee a refused connection.

## Explicit Non-Coverage

* UDP DoIP vehicle discovery / announcement messages (out of scope for v1).
* TLS-secured DoIP and authentication handshakes.
* Real-hardware gateway interoperability, which requires a physical DoIP entity.
