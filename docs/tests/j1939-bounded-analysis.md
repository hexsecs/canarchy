# Test Spec: J1939 Bounded File Analysis

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/j1939-bounded-analysis.md` |
| Test file | `tests/test_cli.py`, `tests/test_transport.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-J1939WIN-01` | File-backed J1939 commands support `--max-frames` | `TEST-J1939WIN-01`, `TEST-J1939WIN-04` |
| `REQ-J1939WIN-02` | File-backed J1939 commands support `--seconds` | `TEST-J1939WIN-02`, `TEST-J1939WIN-05` |
| `REQ-J1939WIN-03` | Bounds are applied during file iteration | `TEST-J1939WIN-04`, `TEST-J1939WIN-05` |
| `REQ-J1939WIN-04` | Invalid `--max-frames` returns structured error | `TEST-J1939WIN-03` |
| `REQ-J1939WIN-05` | Invalid `--seconds` returns structured error | `TEST-J1939WIN-06` |
| `REQ-J1939WIN-06` | Bounded analysis is rejected with `j1939 decode --stdin` | `TEST-J1939WIN-07` |
| `REQ-J1939WIN-07` | Auto-cap for j1939 summary/dm1/faults/inventory/compare on large files | `TEST-J1939WIN-08`, `TEST-J1939WIN-09`, `TEST-J1939WIN-10`, `TEST-J1939WIN-11`, `TEST-J1939WIN-12`, `TEST-J1939WIN-13` |

## Test Cases

### TEST-J1939WIN-01 — Frame bound limits `j1939 decode`

```gherkin
Given  a capture fixture contains more J1939 frames than the requested frame bound
When   the operator runs `canarchy j1939 decode --file <capture> --max-frames 3 --json`
Then   the system shall return only records derived from the first three capture frames
And    the command shall remain otherwise valid JSON output
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`.

---

### TEST-J1939WIN-02 — Time bound limits `j1939 tp sessions`

```gherkin
Given  a transport-protocol fixture spans multiple timestamps
When   the operator runs `canarchy j1939 tp sessions --file <capture> --seconds 0.08 --json`
Then   the system shall analyse only the initial capture-time window
And    the returned session summary shall reflect an incomplete reassembly if later packets fall outside the window
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### TEST-J1939WIN-03 — Invalid frame bounds fail cleanly

```gherkin
Given  a valid J1939 DM1 capture file
When   the operator runs `canarchy j1939 dm1 --file <capture> --max-frames 0 --json`
Then   the system shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_MAX_FRAMES"`
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### TEST-J1939WIN-04 — Transport iterator enforces frame count bounds

```gherkin
Given  a candump fixture contains more than three frames
When   the transport layer iterates that file with `max_frames=3`
Then   the system shall yield exactly three parsed frames
And    the iterator shall stop without reading the rest of the capture into the returned sequence
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`.

---

### TEST-J1939WIN-05 — Transport iterator enforces time bounds

```gherkin
Given  a candump fixture contains timestamps beyond the requested time window
When   the transport layer iterates that file with `seconds=0.15`
Then   the system shall yield only frames whose timestamps fall within the initial 0.15-second window
And    later frames shall not appear in the yielded sequence
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump`.

---

### TEST-J1939WIN-06 — Invalid seconds fail cleanly

```gherkin
Given  a valid J1939 TP capture file
When   the operator runs `canarchy j1939 tp sessions --file <capture> --seconds -1 --json`
Then   the system shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_ANALYSIS_SECONDS"`
```

**Fixture:** `tests/fixtures/j1939_dm1_tp.candump`.

---

### TEST-J1939WIN-07 — Bounded analysis flags are file-only for `j1939 decode`

```gherkin
Given  `j1939 decode` is reading frame events from stdin
When   the operator runs `canarchy j1939 decode --stdin --seconds 1.0 --json`
Then   the system shall exit with code `1`
And    `errors[0].code` shall equal `"ANALYSIS_WINDOW_REQUIRES_FILE"`
```

**Fixture:** mocked stdin JSONL frame event stream.

### TEST-J1939WIN-08 — j1939 summary auto-caps on large files

```gherkin
Given  a capture file larger than 50 MB (threshold patched to 1 byte in test)
And    no `--max-frames` or `--seconds` flag is provided
When   the operator runs `canarchy j1939 summary --file <large-file> --json`
Then   the response shall include a warning containing "Large file"
And    the warning shall mention 500,000 frames
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump` with threshold patched.

---

### TEST-J1939WIN-09 — j1939 summary does not auto-cap when --max-frames is set

```gherkin
Given  a capture file larger than 50 MB (threshold patched to 1 byte in test)
And    `--max-frames 100` is provided
When   the operator runs `canarchy j1939 summary --file <large-file> --max-frames 100 --json`
Then   the response warnings shall not include any "Large file" auto-cap message
```

**Fixture:** `tests/fixtures/j1939_heavy_vehicle.candump` with threshold patched.

---

### TEST-J1939WIN-10 — j1939 dm1 auto-caps on large files

```gherkin
Given  a capture file larger than 50 MB (threshold patched to 1 byte in test)
And    no `--max-frames` or `--seconds` flag is provided
When   the operator runs `canarchy j1939 dm1 --file <large-file> --json`
Then   the response shall include a warning containing "Large file"
```

**Fixture:** `tests/fixtures/j1939_dm1_spn175.candump` with threshold patched.

---

### TEST-J1939WIN-11 — j1939 faults auto-caps on large files

```gherkin
Given  a capture file larger than 50 MB (threshold patched to 1 byte in test)
And    no `--max-frames` or `--seconds` flag is provided
When   the operator runs `canarchy j1939 faults --file <large-file> --json`
Then   the response shall include a warning containing "Large file"
```

**Fixture:** `tests/fixtures/j1939_dm1_spn175.candump` with threshold patched.

---

### TEST-J1939WIN-12 — j1939 inventory auto-caps on large files

```gherkin
Given  a capture file larger than 50 MB (threshold patched to 1 byte in test)
And    no `--max-frames` or `--seconds` flag is provided
When   the operator runs `canarchy j1939 inventory --file <large-file> --json`
Then   the response shall include a warning containing "Large file"
```

**Fixture:** `tests/fixtures/j1939_inventory.candump` with threshold patched.

---

### TEST-J1939WIN-13 — j1939 compare auto-caps on large files

```gherkin
Given  two capture files larger than 50 MB (threshold patched to 1 byte in test)
And    no `--max-frames` or `--seconds` flag is provided
When   the operator runs `canarchy j1939 compare <file1> <file2> --json`
Then   the response shall include a warning containing "Large file"
```

**Fixture:** `tests/fixtures/j1939_inventory.candump` and `tests/fixtures/j1939_compare_shifted.candump` with threshold patched.

---

## Fixtures And Environment

* `tests/fixtures/j1939_heavy_vehicle.candump`
* `tests/fixtures/j1939_dm1_tp.candump`
* `tests/fixtures/j1939_dm1_spn175.candump`
* `tests/fixtures/j1939_inventory.candump`
* `tests/fixtures/j1939_compare_shifted.candump`
* mocked stdin JSONL frame event input for the file-only validation path

## Explicit Non-Coverage

* later-window selection such as `--from` / `--to`
* sampling or every-Nth-frame semantics
* performance benchmarking on production-sized captures, which remains a separate performance concern
