# Test Spec: Standalone ISO-TP Utility Commands

## Document Control

| Field | Value |
|-------|-------|
| Status | Planned |
| Design doc | `docs/design/isotp-utility-commands.md` |
| Test file | `tests/test_isotp.py`, `tests/test_cli.py`, `tests/test_mcp.py` if MCP exposure is implemented |
| Issue | #328 |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|---------------------|----------|
| `REQ-ISOTP-01` | command group exists | `TEST-ISOTP-01` |
| `REQ-ISOTP-02` | file-backed reassembly | `TEST-ISOTP-02` |
| `REQ-ISOTP-03` | source filtering | `TEST-ISOTP-03` |
| `REQ-ISOTP-04` | target metadata and direction | `TEST-ISOTP-04` |
| `REQ-ISOTP-05` | complete messages | `TEST-ISOTP-02`, `TEST-ISOTP-05` |
| `REQ-ISOTP-06` | incomplete malformed/truncated messages | `TEST-ISOTP-06`, `TEST-ISOTP-07` |
| `REQ-ISOTP-07` | flow-control metadata | `TEST-ISOTP-08` |
| `REQ-ISOTP-08` | malformed sequence errors | `TEST-ISOTP-09` |
| `REQ-ISOTP-09` | active send segmentation | `TEST-ISOTP-10` |
| `REQ-ISOTP-10` | dry-run send planning | `TEST-ISOTP-11` |
| `REQ-ISOTP-11` | active-transmit safety | `TEST-ISOTP-12` |
| `REQ-ISOTP-12` | flow-control timeout | `TEST-ISOTP-13` |
| `REQ-ISOTP-13` | JSON/JSONL/text contracts | `TEST-ISOTP-14`, `TEST-ISOTP-15` |
| `REQ-ISOTP-14` | helper reuse | `TEST-ISOTP-16` |

## Test Cases

### TEST-ISOTP-01 — Parser exposes command group

```gherkin
Given  the CLI parser is built
When   the operator requests help for `canarchy isotp --help`
Then   the system shall list `reassemble` and `send` subcommands
And    the implemented command registry shall include `isotp reassemble` and `isotp send`
```

**Fixture:** none.

---

### TEST-ISOTP-02 — Reassemble capture into complete messages

```gherkin
Given  `tests/fixtures/isotp_sample.candump` contains a single-frame message and a multi-frame message
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_sample.candump --json`
Then   the system shall exit with code `0`
And    the response shall contain two `isotp_message` events
And    each complete event shall include payload hex, payload length, frame count, and timestamps
```

**Fixture:** `tests/fixtures/isotp_sample.candump`.

---

### TEST-ISOTP-03 — Source filter limits emitted messages but preserves flow-control metadata

```gherkin
Given  an ISO-TP fixture contains messages on arbitration IDs `0x7E0` and `0x7E8`
And    a multi-frame `0x7E8` message has a reverse-direction flow-control frame on `0x7E0`
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_sample.candump --source 0x7E8 --json`
Then   the system shall emit only messages whose `source_id` is `0x7E8`
And    no `0x7E0` message shall appear in `data.messages`
And    the `0x7E8` message shall still include the related `0x7E0` flow-control frame in `flow_control_count`
```

**Fixture:** `tests/fixtures/isotp_sample.candump`.

---

### TEST-ISOTP-04 — Target metadata classifies direction

```gherkin
Given  an ISO-TP fixture contains request ID `0x7E0` and response ID `0x7E8`
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_sample.candump --source 0x7E8 --target 0x7E0 --json`
Then   the system shall classify the emitted message direction as `response`
And    the event shall include `target_id` equal to `0x7E0`
```

**Fixture:** `tests/fixtures/isotp_sample.candump`.

---

### TEST-ISOTP-05 — Pure helper preserves UDS reassembly behavior

```gherkin
Given  the existing UDS ISO-TP reassembly helper receives a valid first frame and consecutive frames
When   the standalone ISO-TP engine path reassembles those frames
Then   the system shall produce the same application payload bytes as `reassemble_uds_pdus`
And    the UDS transaction tests shall continue to pass
```

**Fixture:** pure `CanFrame` objects matching the UDS unit-test sequences.

---

### TEST-ISOTP-06 — Truncated message emits incomplete event

```gherkin
Given  an ISO-TP fixture contains a first frame whose declared length is not satisfied by the capture
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_truncated.candump --json`
Then   the system shall emit one `isotp_message` event with `complete` equal to `false`
And    the event shall preserve the partial payload bytes observed before capture end
```

**Fixture:** `tests/fixtures/isotp_truncated.candump`.

---

### TEST-ISOTP-07 — Out-of-order consecutive frame emits incomplete event

```gherkin
Given  an ISO-TP fixture contains consecutive frame sequence numbers `1` then `3`
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_malformed.candump --json`
Then   the system shall emit an incomplete `isotp_message` event
And    the event shall include a `sequence_error` describing the expected and observed sequence numbers
```

**Fixture:** `tests/fixtures/isotp_malformed.candump`.

---

### TEST-ISOTP-08 — Flow-control frames become metadata

```gherkin
Given  an ISO-TP fixture includes a flow-control frame between a first frame and consecutive frames
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_sample.candump --json`
Then   the system shall increment `flow_control_count` on the related message
And    the flow-control frame shall not appear as its own `isotp_message` event
```

**Fixture:** `tests/fixtures/isotp_sample.candump`.

---

### TEST-ISOTP-09 — Fatal malformed sequence returns structured error

```gherkin
Given  an ISO-TP fixture contains an invalid PCI nibble that cannot be tied to an open message
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_invalid_pci.candump --json`
Then   the system shall exit with code `3`
And    the response shall contain an error with code `ISOTP_MALFORMED_SEQUENCE`
```

**Fixture:** `tests/fixtures/isotp_invalid_pci.candump`.

---

### TEST-ISOTP-10 — Active send segments payload

```gherkin
Given  the scaffold transport backend records sent frames
When   the operator runs `canarchy isotp send can0 --source 0x7E0 --target 0x7E8 --data 62f190574457313233343536373839 --ack-active --json`
Then   the system shall transmit a first frame followed by consecutive frames
And    the canonical envelope shall report `mode` equal to `active`
```

**Fixture:** scaffold transport backend.

---

### TEST-ISOTP-11 — Dry-run send returns planned frames

```gherkin
Given  no live CAN interface is available
When   the operator runs `canarchy isotp send can0 --source 0x7E0 --target 0x7E8 --data 62f190574457313233343536373839 --dry-run --json`
Then   the system shall exit with code `0`
And    the response shall include planned CAN frames without opening transport
And    the response shall report `mode` equal to `dry_run`
```

**Fixture:** none.

---

### TEST-ISOTP-12 — Active acknowledgement is enforced

```gherkin
Given  active acknowledgement is required by configuration
When   the operator runs `canarchy isotp send can0 --source 0x7E0 --target 0x7E8 --data 22f190 --json` without `--ack-active`
Then   the system shall exit with code `1`
And    the response shall contain an error with code `ACTIVE_ACK_REQUIRED`
```

**Fixture:** temporary CANarchy config with `[safety].require_active_ack = true`.

---

### TEST-ISOTP-13 — Flow-control timeout fails active send

```gherkin
Given  the mocked transport never receives a flow-control frame after an ISO-TP first frame
When   the operator runs `canarchy isotp send can0 --source 0x7E0 --target 0x7E8 --data <multi-frame payload> --ack-active --json`
Then   the system shall exit with code `2`
And    the response shall contain an error with code `ISOTP_FLOW_CONTROL_TIMEOUT`
```

**Fixture:** mocked transport receive path with no flow-control response.

---

### TEST-ISOTP-14 — JSONL emits one event per message

```gherkin
Given  `tests/fixtures/isotp_sample.candump` contains two reassembled ISO-TP messages
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_sample.candump --jsonl`
Then   the system shall emit two JSONL records
And    every record shall have `event_type` equal to `isotp_message`
```

**Fixture:** `tests/fixtures/isotp_sample.candump`.

---

### TEST-ISOTP-15 — Text output summarizes transport state

```gherkin
Given  `tests/fixtures/isotp_sample.candump` contains complete and incomplete ISO-TP messages
When   the operator runs `canarchy isotp reassemble --file tests/fixtures/isotp_sample.candump --text`
Then   the system shall print each source ID, target ID when known, completeness, payload length, and payload hex
And    incomplete messages shall be visibly marked in text output
```

**Fixture:** `tests/fixtures/isotp_sample.candump`.

---

### TEST-ISOTP-16 — CLI handler does not duplicate protocol logic

```gherkin
Given  the standalone ISO-TP command is implemented
When   the test suite inspects the command handler and ISO-TP module boundaries
Then   the system shall route reassembly through the shared ISO-TP helper used by UDS tests
And    the CLI handler shall only perform argument validation, file loading, safety checks, and output formatting
```

**Fixture:** static module inspection or a boundary-focused unit test.

## Fixtures And Environment

Required fixtures:

* `tests/fixtures/isotp_sample.candump` with a single-frame message, a complete multi-frame message, and an observed flow-control frame
* `tests/fixtures/isotp_truncated.candump` with a declared multi-frame length that is not completed
* `tests/fixtures/isotp_malformed.candump` with an out-of-order consecutive frame
* `tests/fixtures/isotp_invalid_pci.candump` with an unrecoverable malformed PCI nibble or invalid length encoding
* existing UDS unit-test `CanFrame` sequences and J1939 TP fixtures for regression coverage that existing protocol-specific paths still pass

## Explicit Non-Coverage

* live physical ECU behavior; tests use scaffold or mocked transports
* ISO-TP extended addressing, mixed addressing, normal-fixed addressing, and CAN FD segmentation until those features are specified
* MCP tool exposure unless the implementation slice adds ISO-TP MCP tools
* UDS service decoding, which remains covered by UDS workflow tests
