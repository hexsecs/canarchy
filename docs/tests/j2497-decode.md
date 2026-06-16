# Test Spec: J2497 (PLC4TRUCKS) Trailer Power-Line Decoding

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/j2497-decode.md` |
| Test file | `tests/test_j2497.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J2497-01` | Parse MID / message data / checksum-valid | `TEST-J2497-01`, `TEST-J2497-02`, `TEST-J2497-04` |
| `REQ-J2497-02` | Byte-sum checksum validity | `TEST-J2497-02`, `TEST-J2497-03` |
| `REQ-J2497-03` | Too-short frame raises; data treated opaquely | `TEST-J2497-05`, `TEST-J2497-06` |
| `REQ-J2497-04` | Bundled MID catalog + overrides | `TEST-J2497-09`, `TEST-J2497-10`, `TEST-J2497-13` |
| `REQ-J2497-05` | MID-name resolution incl. unknown MID | `TEST-J2497-07`, `TEST-J2497-08` |
| `REQ-J2497-06` | `j2497 decode` emits one event per frame | `TEST-J2497-14`, `TEST-J2497-15`, `TEST-J2497-16` |
| `REQ-J2497-07` | `--offset` / `--max-frames` windowing | `TEST-J2497-12`, `TEST-J2497-17` |
| `REQ-J2497-08` | Structured errors for missing/malformed input | `TEST-J2497-18`..`TEST-J2497-21` |
| `REQ-J2497-09` | `j2497 mids` reference payload | `TEST-J2497-22`, `TEST-J2497-23` |

## Test Cases

### TEST-J2497-01 — Valid checksum is recognized

```gherkin
Given  a raw J2497 frame whose byte sum is congruent to 0 mod 256
When   `parse_j2497_frame` parses it
Then   the system shall report `checksum_valid: true`, the correct MID, and the message-data bytes
```

**Fixture:** none.

---

### TEST-J2497-02 — Invalid checksum is flagged

```gherkin
Given  the same frame with the checksum byte incremented by one
When   `parse_j2497_frame` parses it
Then   the system shall report `checksum_valid: false`
```

**Fixture:** none.

---

### TEST-J2497-03 — Checksum failure propagates to events

```gherkin
Given  a parsed frame with an invalid checksum
When   `decode_events` runs
Then   the system shall report `checksum_valid: false` on the resulting event
```

**Fixture:** none.

---

### TEST-J2497-04 — Message data is the bytes between MID and checksum

```gherkin
Given  a frame `8A 90 12 34 <checksum>`
When   the frame is parsed
Then   the system shall report mid=0x8A and data=`90 12 34`
```

**Fixture:** none.

---

### TEST-J2497-05 — Frame shorter than two bytes raises

```gherkin
Given  a single-byte "frame"
When   `parse_j2497_frame` parses it
Then   the system shall raise a ValueError mentioning the MID/checksum requirement
```

**Fixture:** none.

---

### TEST-J2497-06 — Data-less frame is accepted

```gherkin
Given  a bare MID + checksum frame (no message data)
When   the frame is parsed
Then   the system shall report empty message data and a valid checksum
```

**Fixture:** none.

---

### TEST-J2497-07 — Known MID resolves an ECU name

```gherkin
Given  a frame from MID 137 (Brakes - Trailer #1 ABS)
When   `decode_events` runs
Then   the resulting event shall carry name "Brakes - Trailer #1 (ABS)"
```

**Fixture:** none.

---

### TEST-J2497-08 — Unknown MID resolves to a null name

```gherkin
Given  a frame from MID 192, which has no catalog entry
When   `decode_events` runs
Then   the resulting event shall carry name None
```

**Fixture:** none.

---

### TEST-J2497-09 — Bundled MID catalog lookup

```gherkin
Given  the bundled J2497 MID catalog
When   MID 137 is looked up
Then   the system shall return name "Brakes - Trailer #1 (ABS)"
And    MID 192 (not in the catalog) shall return None
```

**Fixture:** none.

---

### TEST-J2497-10 — `j2497_mids_payload` is sorted by MID

```gherkin
Given  the bundled J2497 MID catalog
When   `j2497_mids_payload` is called
Then   the entries shall be sorted by MID and include MID 137
```

**Fixture:** none.

---

### TEST-J2497-12 — `--offset` skips initial frames

```gherkin
Given  `tests/fixtures/j2497_sample.j2497`
When   `iter_j2497_frames_from_file` is called with offset=2, max_frames=1
Then   the system shall yield the third frame (timestamp 0.1)
```

**Fixture:** `tests/fixtures/j2497_sample.j2497`.

---

### TEST-J2497-13 — MID overrides merge over the bundled catalog

```gherkin
Given  `CANARCHY_J2497_MID_OVERRIDES` points at a JSON file defining MID 200
When   `mid_lookup(200)` is called
Then   the system shall return the override entry
And    bundled entries (e.g. MID 137) shall still resolve unchanged
```

**Fixture:** temporary override JSON file, environment variable patched in-test.

---

### TEST-J2497-14 — `j2497 decode` returns one event per frame (JSON)

```gherkin
Given  `tests/fixtures/j2497_sample.j2497` (6 frames, 1 checksum failure)
When   `canarchy j2497 decode --file <fixture> --json` is invoked
Then   the system shall report `mode: "passive"`, `frame_count: 6`, `checksum_failures: 1`
And    the first event shall resolve MID 137 to name "Brakes - Trailer #1 (ABS)" with data "2c01"
```

**Fixture:** `tests/fixtures/j2497_sample.j2497`.

---

### TEST-J2497-15 — Invalid checksum surfaces in the decode output

```gherkin
Given  `tests/fixtures/j2497_sample.j2497`
When   `canarchy j2497 decode --file <fixture> --json` is invoked
Then   at least one event shall report `checksum_valid: false`
```

**Fixture:** `tests/fixtures/j2497_sample.j2497`.

---

### TEST-J2497-16 — `j2497 decode` text and JSONL output

```gherkin
Given  `tests/fixtures/j2497_sample.j2497`
When   `canarchy j2497 decode --file <fixture> --text` and `--jsonl` are invoked
Then   the text table shall show the file, frame/checksum-failure counts, and per-frame lines (including a `checksum=invalid` marker), and the JSONL stream shall contain one `j2497_message` line per frame
```

**Fixture:** `tests/fixtures/j2497_sample.j2497`.

---

### TEST-J2497-17 — `--max-frames` limits the frame stream

```gherkin
Given  `tests/fixtures/j2497_sample.j2497`
When   `canarchy j2497 decode --file <fixture> --max-frames 1 --json` is invoked
Then   the system shall report `frame_count: 1`
```

**Fixture:** `tests/fixtures/j2497_sample.j2497`.

---

### TEST-J2497-18 — Missing capture file returns a structured error

```gherkin
Given  a `--file` path that does not exist
When   `canarchy j2497 decode --file <missing> --json` is invoked
Then   the system shall exit 1 with error code `J2497_SOURCE_UNAVAILABLE`
```

**Fixture:** none.

---

### TEST-J2497-19 — Line not matching the capture format is rejected

```gherkin
Given  a capture file containing a line that does not match `(timestamp) j2497 <hex>`
When   the file is parsed
Then   the system shall raise a `TransportError` with code `J2497_SOURCE_INVALID`
```

**Fixture:** temporary capture file.

---

### TEST-J2497-20 — Odd-length hex payload is rejected

```gherkin
Given  a capture line whose hex payload has an odd number of digits
When   the file is parsed
Then   the system shall raise a `TransportError` with code `J2497_SOURCE_INVALID` mentioning the odd digit count
```

**Fixture:** temporary capture file.

---

### TEST-J2497-21 — Too-short frame payload is rejected

```gherkin
Given  a capture line whose hex payload decodes to fewer than two bytes
When   the file is parsed
Then   the system shall raise a `TransportError` with code `J2497_SOURCE_INVALID` mentioning the malformed line
And    `canarchy j2497 decode --file <fixture> --json` shall exit 1 with the same error code
```

**Fixture:** temporary capture file.

---

### TEST-J2497-22 — `j2497 mids` returns the bundled catalog (JSON)

```gherkin
Given  the bundled J2497 MID catalog
When   `canarchy j2497 mids --json` is invoked
Then   the system shall report `mode: "reference"` with `mid_count >= 8`
And    MID 137 shall resolve to name "Brakes - Trailer #1 (ABS)"
```

**Fixture:** none.

---

### TEST-J2497-23 — `j2497 mids` text output

```gherkin
Given  the bundled J2497 MID catalog
When   `canarchy j2497 mids --text` is invoked
Then   the system shall render a catalog table including a line for MID 137
```

**Fixture:** none.

## Fixtures And Environment

`tests/fixtures/j2497_sample.j2497` provides 6 lines: trailer #1, trailer #2,
and tractor ABS lamp-status frames, a multi-byte trailer #1 frame, a frame
with a deliberately invalid checksum, and a frame from an unknown MID — giving
6 frames total and 1 checksum failure. All other tests use crafted in-memory
byte sequences or temporary files; no live hardware or power-line-carrier
transport is required.

## Explicit Non-Coverage

* Live J2497 / power-line-carrier transports and a `j2497 monitor` command.
* PID-level decoding of message-data bytes (covered by `j1587 decode`).
