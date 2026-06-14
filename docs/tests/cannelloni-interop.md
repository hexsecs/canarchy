# Test Spec: cannelloni CAN-over-UDP Interop

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/cannelloni-interop.md` |
| Test file | `tests/test_cannelloni.py` |

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-CAN-01` | `TEST-CAN-01`, `TEST-CAN-02` |
| `REQ-CAN-02` | `TEST-CAN-02` |
| `REQ-CAN-03` | `TEST-CAN-04` |
| `REQ-CAN-04` | `TEST-CAN-06` |
| `REQ-CAN-05` | `TEST-CAN-05`, `TEST-CAN-06` |
| `REQ-CAN-06` | `TEST-CAN-07` |
| `REQ-CAN-07` | `TEST-CAN-03` |
| `REQ-CAN-08` | `TEST-CAN-08` |
| `REQ-CAN-04` (MTU) | `TEST-CAN-09` |
| `REQ-CAN-09` | `TEST-CAN-10` |

## Representative Test Cases

### `TEST-CAN-01` — Encoder matches a hand-computed wire reference

```gherkin
Given  a classic standard CAN frame 0x123 # 11 22 33 44
When   it is encoded with seq_no 7
Then   the bytes shall equal the hand-computed header + frame reference
And    decoding the datagram shall recover the header fields and the frame
```

**Fixture:** none (constructed in-test).

---

### `TEST-CAN-02` — Round-trip across all frame types

```gherkin
Given  extended, RTR, error, and CAN FD (BRS+ESI) frames
When   they are encoded into a datagram and decoded back
Then   every frame's id, flags, format, and data shall be preserved
```

**Fixture:** none.

---

### `TEST-CAN-03` — Malformed datagrams raise structured errors

```gherkin
Given  a truncated datagram
When   it is decoded
Then   `CANNELLONI_TRUNCATED` shall be raised
Given  a datagram with an unsupported version byte
When   it is decoded
Then   `CANNELLONI_VERSION_UNSUPPORTED` shall be raised
```

**Fixture:** none.

---

### `TEST-CAN-04` — `cannelloni decode` CLI round-trips a capture

```gherkin
Given  a capture encoded into a cannelloni payload file
When   `canarchy cannelloni decode --file <payload> --json` is invoked
Then   the frame events shall match the original capture's arbitration ids in order
```

**Fixture:** `tests/fixtures/cannelloni_sample.bin` (generated in-test from `sample.candump`).

---

### `TEST-CAN-05` — `cannelloni send --dry-run` plans without a socket

```gherkin
Given  a capture
When   `cannelloni send <target> --file <capture> --dry-run --json` is invoked
Then   the envelope shall report `mode: dry_run` and the planned datagram count
And    the planned datagram hex shall decode back to the capture frames
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-CAN-06` — `cannelloni send` transmits over loopback UDP

```gherkin
Given  a UDP receiver bound to an ephemeral loopback port
And    `CANARCHY_MCP_NONINTERACTIVE_ACK=1` so `--ack-active` passes non-interactively
When   `cannelloni send 127.0.0.1:<port> --file <capture> --ack-active --json` is invoked
Then   the envelope shall report `mode: active`
And    the received datagram shall decode back to the capture's arbitration ids
```

**Fixture:** `tests/fixtures/sample.candump`.

---

### `TEST-CAN-07` — Invalid target returns a structured error

```gherkin
Given  a target with no port
When   `cannelloni send <target> ...` is invoked
Then   the envelope shall report `ok: false` with code `CANNELLONI_INVALID_TARGET`
```

**Fixture:** none.

---

### `TEST-CAN-08` — MCP exposure: decode exposed, send excluded

```gherkin
Given  the MCP tool registry
Then   `cannelloni_decode` shall be a registered tool and `cannelloni_send` shall not
And    `_build_argv("cannelloni_decode", {...})` shall map to the decode CLI argv
```

**Fixture:** none.

---

### `TEST-CAN-09` — Chunks are capped by MTU for CAN FD captures

```gherkin
Given  64 full-size (64-byte) CAN FD frames
When   they are encoded with the default 1500-byte MTU
Then   they shall split into more than one datagram, each within 1500 bytes
And    `max_bytes=None` shall emit a single oversize datagram
```

**Fixture:** none.

---

### `TEST-CAN-10` — Out-of-range DLC is a structured error end to end

```gherkin
Given  a datagram declaring a classic frame with length 9 and 9 data bytes
When   it is decoded (codec and `cannelloni decode --file`)
Then   `CANNELLONI_INVALID_DLC` shall be raised / returned, not a crash
```

**Fixture:** generated in-test.
