# Test Spec: J1587/J1708 Legacy Heavy-Vehicle Decoding

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/j1587-decode.md` |
| Test file | `tests/test_j1587.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J1587-01` | Parse MID / parameters / checksum-valid | `TEST-J1587-01`, `TEST-J1587-02` |
| `REQ-J1587-02` | PID-range framing rules incl. extended PID | `TEST-J1587-03`..`TEST-J1587-07` |
| `REQ-J1587-03` | Truncated message / parameter errors | `TEST-J1587-08`..`TEST-J1587-11` |
| `REQ-J1587-04` | Bundled PID catalog + overrides | `TEST-J1587-12`, `TEST-J1587-13`, `TEST-J1587-19` |
| `REQ-J1587-05` | PID value resolution + not-available sentinel | `TEST-J1587-14`, `TEST-J1587-15` |
| `REQ-J1587-06` | Unknown PID resolves to all-None | `TEST-J1587-16` |
| `REQ-J1587-07` | `j1587 decode` emits one event per parameter | `TEST-J1587-17`, `TEST-J1587-18`, `TEST-J1587-20`, `TEST-J1587-21` |
| `REQ-J1587-08` | `--offset` / `--max-frames` windowing | `TEST-J1587-22`, `TEST-J1587-23` |
| `REQ-J1587-09` | Structured errors for missing/malformed input | `TEST-J1587-24`..`TEST-J1587-27` |
| `REQ-J1587-10` | `j1587 pids` reference payload | `TEST-J1587-28`, `TEST-J1587-29` |

## Test Cases

### TEST-J1587-01 — Valid checksum is recognized

```gherkin
Given  a raw J1708 message whose byte sum is congruent to 0 mod 256
When   `parse_j1708_message` parses it
Then   the system shall report `checksum_valid: true` and the correct MID
```

**Fixture:** none.

---

### TEST-J1587-02 — Invalid checksum is flagged

```gherkin
Given  the same message with the checksum byte incremented by one
When   `parse_j1708_message` parses it
Then   the system shall report `checksum_valid: false`
```

**Fixture:** none.

---

### TEST-J1587-03 — PID 0-127 takes one data byte

```gherkin
Given  a message containing PID 70 followed by one data byte
When   the message is parsed
Then   the system shall yield a single parameter with pid=70 and one data byte
```

**Fixture:** none.

---

### TEST-J1587-04 — PID 128-191 takes two data bytes

```gherkin
Given  a message containing PID 190 followed by two data bytes
When   the message is parsed
Then   the system shall yield a single parameter with pid=190 and two data bytes
```

**Fixture:** none.

---

### TEST-J1587-05 — PID 192-253 uses an explicit length byte

```gherkin
Given  a message containing PID 200, a length byte of 3, and three data bytes
When   the message is parsed
Then   the system shall yield a single parameter with pid=200 and three data bytes
```

**Fixture:** none.

---

### TEST-J1587-06 — Extended PID marker forms a 16-bit PID

```gherkin
Given  a message containing the extended PID marker 254, an extension byte of 10, a length byte of 2, and two data bytes
When   the message is parsed
Then   the system shall yield a single parameter with pid=266 and two data bytes
```

**Fixture:** none.

---

### TEST-J1587-07 — Multiple parameters in one message

```gherkin
Given  a message containing a PID-70 parameter followed by a PID-190 parameter
When   the message is parsed
Then   the system shall yield both parameters in order
```

**Fixture:** none.

---

### TEST-J1587-08 — Message shorter than two bytes raises

```gherkin
Given  a single-byte "message"
When   `parse_j1708_message` parses it
Then   the system shall raise a ValueError mentioning the MID/checksum requirement
```

**Fixture:** none.

---

### TEST-J1587-09 — Truncated extended PID raises

```gherkin
Given  a message ending in the extended PID marker 254 with no following byte
When   the message is parsed
Then   the system shall raise a ValueError mentioning a truncated extended PID
```

**Fixture:** none.

---

### TEST-J1587-10 — Truncated parameter length raises

```gherkin
Given  a message ending in PID 200 with no following length byte
When   the message is parsed
Then   the system shall raise a ValueError mentioning a truncated parameter length
```

**Fixture:** none.

---

### TEST-J1587-11 — Truncated parameter data raises

```gherkin
Given  a message with PID 200, length byte 3, but only one data byte
When   the message is parsed
Then   the system shall raise a ValueError mentioning truncated parameter data
```

**Fixture:** none.

---

### TEST-J1587-12 — Bundled PID catalog lookup

```gherkin
Given  the bundled J1587 PID catalog
When   PID 190 is looked up
Then   the system shall return name "Engine Speed" and units "rpm"
And    PID 50 (not in the catalog) shall return None
```

**Fixture:** none.

---

### TEST-J1587-13 — Decodable PIDs include the bundled catalog

```gherkin
Given  the bundled J1587 PID catalog
When   `decodable_pids` is queried
Then   the system shall include PIDs 190 and 110
```

**Fixture:** none.

---

### TEST-J1587-14 — Known PID resolves a scaled value

```gherkin
Given  PID 190 (Engine Speed, resolution 0.25, offset 0.0) with raw bytes 0x70 0x17
When   `decode_parameter_value` resolves it
Then   the system shall return name "Engine Speed", value 1500.0, units "rpm"
And    PID 110 (Engine Coolant Temperature, offset -40.0) with raw byte 0x6E shall resolve to value 70.0
```

**Fixture:** none.

---

### TEST-J1587-15 — All-ones sentinel resolves to a null value

```gherkin
Given  PID 190 with raw bytes 0xFF 0xFF
When   `decode_parameter_value` resolves it
Then   the system shall return name "Engine Speed", value None, units "rpm"
```

**Fixture:** none.

---

### TEST-J1587-16 — Unknown PID resolves to all-None

```gherkin
Given  PID 50, which has no catalog entry
When   `decode_parameter_value` resolves it
Then   the system shall return (None, None, None)
```

**Fixture:** none.

---

### TEST-J1587-17 — `decode_events` flattens one event per parameter

```gherkin
Given  a parsed message containing a PID-70 parameter and a PID-190 parameter
When   `decode_events` runs
Then   the system shall return two `J1587ObservationEvent` records carrying the message's MID, timestamp, and checksum-valid flag
```

**Fixture:** none.

---

### TEST-J1587-18 — Checksum failure propagates to events

```gherkin
Given  a parsed message with an invalid checksum
When   `decode_events` runs
Then   the system shall report `checksum_valid: false` on the resulting event
```

**Fixture:** none.

---

### TEST-J1587-19 — PID overrides merge over the bundled catalog

```gherkin
Given  `CANARCHY_J1587_PID_OVERRIDES` points at a JSON file defining PID 260
When   `pid_lookup(260)` is called
Then   the system shall return the override entry
And    bundled entries (e.g. PID 190) shall still resolve unchanged
```

**Fixture:** temporary override JSON file, environment variable patched in-test.

---

### TEST-J1587-20 — `j1587 decode` returns one event per parameter (JSON)

```gherkin
Given  `tests/fixtures/j1708_sample.j1708` (7 messages, 8 parameters, 1 checksum failure)
When   `canarchy j1587 decode --file <fixture> --json` is invoked
Then   the system shall report `message_count: 7`, `parameter_count: 8`, `checksum_failures: 1`
And    the first event shall resolve PID 190 to name "Engine Speed", value 1500.0, units "rpm"
```

**Fixture:** `tests/fixtures/j1708_sample.j1708`.

---

### TEST-J1587-21 — `j1587 decode` text and JSONL output

```gherkin
Given  `tests/fixtures/j1708_sample.j1708`
When   `canarchy j1587 decode --file <fixture> --text` and `--jsonl` are invoked
Then   the text table shall show the file, message/checksum-failure counts, per-parameter lines (including a `checksum=invalid` marker), and the JSONL stream shall contain one `j1587_parameter` line per parameter
```

**Fixture:** `tests/fixtures/j1708_sample.j1708`.

---

### TEST-J1587-22 — `--max-frames` limits the message stream

```gherkin
Given  `tests/fixtures/j1708_sample.j1708`
When   `canarchy j1587 decode --file <fixture> --max-frames 1 --json` is invoked
Then   the system shall report `message_count: 1`
```

**Fixture:** `tests/fixtures/j1708_sample.j1708`.

---

### TEST-J1587-23 — `--offset` skips initial messages

```gherkin
Given  `tests/fixtures/j1708_sample.j1708`
When   `iter_j1708_messages_from_file` is called with offset=2, max_frames=1
Then   the system shall yield the third message (timestamp 0.1)
```

**Fixture:** `tests/fixtures/j1708_sample.j1708`.

---

### TEST-J1587-24 — Missing capture file returns a structured error

```gherkin
Given  a `--file` path that does not exist
When   `canarchy j1587 decode --file <missing> --json` is invoked
Then   the system shall exit 1 with error code `J1587_SOURCE_UNAVAILABLE`
```

**Fixture:** none.

---

### TEST-J1587-25 — Line not matching the capture format is rejected

```gherkin
Given  a capture file containing a line that does not match `(timestamp) j1708 <hex>`
When   the file is parsed
Then   the system shall raise a `TransportError` with code `J1587_SOURCE_INVALID`
```

**Fixture:** temporary capture file.

---

### TEST-J1587-26 — Odd-length hex payload is rejected

```gherkin
Given  a capture line whose hex payload has an odd number of digits
When   the file is parsed
Then   the system shall raise a `TransportError` with code `J1587_SOURCE_INVALID` mentioning the odd digit count
```

**Fixture:** temporary capture file.

---

### TEST-J1587-27 — Truncated message payload is rejected

```gherkin
Given  a capture line whose hex payload decodes to fewer than two bytes
When   the file is parsed
Then   the system shall raise a `TransportError` with code `J1587_SOURCE_INVALID` mentioning the malformed line
And    `canarchy j1587 decode --file <fixture> --json` shall exit 1 with the same error code
```

**Fixture:** temporary capture file.

---

### TEST-J1587-28 — `j1587 pids` returns the bundled catalog (JSON)

```gherkin
Given  the bundled J1587 PID catalog
When   `canarchy j1587 pids --json` is invoked
Then   the system shall report `mode: "reference"` with `pid_count >= 11`
And    PID 190 shall resolve to name "Engine Speed" and units "rpm"
```

**Fixture:** none.

---

### TEST-J1587-29 — `j1587 pids` text output

```gherkin
Given  the bundled J1587 PID catalog
When   `canarchy j1587 pids --text` is invoked
Then   the system shall render a catalog table including a line for PID 190
```

**Fixture:** none.

## Fixtures And Environment

`tests/fixtures/j1708_sample.j1708` provides 7 lines: a two-parameter PID
190 + PID 110 message, repeated single-parameter messages, a PID 91
(Throttle Position) message, a message with a deliberately invalid checksum
(PID 190), a PID 245 (Total Vehicle Distance, 4-byte) message, and a
PID 50 (unknown) message — giving 8 parameters total and 1 checksum failure.
All other tests use crafted in-memory byte sequences or temporary files; no
live hardware or RS-485 transport is required.

## Explicit Non-Coverage

* Live J1708/RS-485 transports and a `j1587 monitor` command.
* A MID-to-ECU-name catalog.
