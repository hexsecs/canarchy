# Test Spec: `generate` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/generate-command.md` |
| Primary test area | CLI, active transmit |

## Test Objectives

Validate that `generate` produces deterministic frame sequences, emits active-transmit events, and returns structured validation errors for invalid input combinations.

## Coverage Requirements

* fixed frame generation from explicit ID, DLC, and data inputs
* random and incrementing data modes
* count and gap handling in generated timestamps
* preflight active-transmit warning and alert emission
* structured validation errors for invalid ID, DLC, data, count, and gap inputs

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-GENERATE-01` | `TEST-GENERATE-01`, `TEST-GENERATE-02` |
| `REQ-GENERATE-02` | `TEST-GENERATE-01`, `TEST-GENERATE-02`, `TEST-GENERATE-03` |
| `REQ-GENERATE-03` | `TEST-GENERATE-01`, `TEST-GENERATE-03` |
| `REQ-GENERATE-04` | `TEST-GENERATE-01` |
| `REQ-GENERATE-05` | `TEST-GENERATE-04`, `TEST-GENERATE-05`, `TEST-GENERATE-06`, `TEST-GENERATE-07`, `TEST-GENERATE-08` |

## Representative Test Cases

### `TEST-GENERATE-01` — Explicit frame generation

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy generate can0 --id 0x123 --dlc 4 --data 11223344 --count 2 --gap 100 --json`
Then   the result shall contain exactly two frame events
And    each frame shall have arbitration ID `0x123`, a 4-byte payload `11223344`, and timestamps spaced by the gap value
And    the result shall include an active-transmit warning alert event
And    the command shall emit a preflight warning on `stderr`
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-GENERATE-02` — Random generation modes

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `generate` with random identifier or payload settings
Then   the command shall succeed
And    the emitted frames shall still satisfy the expected structural constraints
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-GENERATE-03` — Incrementing payload mode

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `generate` with `--data I`
Then   the payload bytes in successive frames shall increment deterministically
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-GENERATE-04` — Invalid identifier

```gherkin
Given  an invalid frame identifier is supplied
When   the operator runs `canarchy generate can0 --id not_hex --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_FRAME_ID"`
```

**Fixture:** none required.

---

### `TEST-GENERATE-05` — Invalid DLC

```gherkin
Given  an out-of-range DLC value is supplied
When   the operator runs `canarchy generate can0 --dlc 99 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_DLC"`
```

**Fixture:** none required.

---

### `TEST-GENERATE-06` — Invalid payload

```gherkin
Given  a malformed data string is supplied
When   the operator runs `canarchy generate can0 --data ZZZZ --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_FRAME_DATA"`
```

**Fixture:** none required.

---

### `TEST-GENERATE-07` — Invalid count

```gherkin
Given  a count of zero is supplied
When   the operator runs `canarchy generate can0 --count 0 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_COUNT"`
```

**Fixture:** none required.

---

### `TEST-GENERATE-08` — Invalid gap

```gherkin
Given  a negative gap value is supplied
When   the operator runs `canarchy generate can0 --gap -1 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_GAP"`
```

**Fixture:** none required.

---

## Fixtures And Environment

No dedicated fixture files are required. Tests exercise the command through the deterministic scaffold backend and CLI unit coverage.

## Explicit Non-Coverage

* live-backend transmit timing enforcement
* CAN FD generation flags, which remain out of scope

## Traceability

This spec maps to the generate acceptance criteria around deterministic generation, active-transmit signaling, and structured validation errors.
