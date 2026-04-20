# Test Spec: `gateway` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/gateway-command.md` |
| Primary test area | CLI, transport |

## Test Objectives

Validate that `gateway` forwards frames correctly, preserves structured direction metadata, and returns the expected transport and validation errors.

## Coverage Requirements

* unidirectional frame forwarding
* bidirectional frame forwarding
* `--count` terminates after `N` total forwarded frames
* `--src-backend` and `--dst-backend` reach the correct bus open path
* scaffold backend raises `GATEWAY_LIVE_BACKEND_REQUIRED`
* unreachable channel raises `TRANSPORT_UNAVAILABLE`
* `--count 0` returns a structured user error
* JSON output includes the correct direction label
* table output includes the gateway header and candump-style frame lines

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-GATEWAY-01` | `TEST-GATEWAY-01`, `TEST-GATEWAY-02` |
| `REQ-GATEWAY-02` | `TEST-GATEWAY-03` |
| `REQ-GATEWAY-03` | `TEST-GATEWAY-02` |
| `REQ-GATEWAY-04` | `TEST-GATEWAY-04` |
| `REQ-GATEWAY-05` | `TEST-GATEWAY-07` |
| `REQ-GATEWAY-06` | `TEST-GATEWAY-05` |
| `REQ-GATEWAY-07` | `TEST-GATEWAY-08` |
| `REQ-GATEWAY-08` | `TEST-GATEWAY-06` |

## Representative Test Cases

### `TEST-GATEWAY-01` — Unidirectional forwarding

```gherkin
Given  two in-process virtual buses sharing the same channel
And    two frames are available on the source bus
When   the gateway runs in unidirectional mode
Then   both frames shall arrive on the destination bus
And    each forwarded frame shall preserve the original arbitration ID and payload
```

**Fixture:** in-process `python-can` virtual buses (no file required).

---

### `TEST-GATEWAY-02` — Bidirectional forwarding

```gherkin
Given  two in-process virtual buses on distinct channels
When   the operator sends one frame from src to dst and one frame from dst to src
And    the gateway runs in bidirectional mode
Then   both frames shall be forwarded across their respective directions
And    each emitted event shall carry the correct direction label
```

**Fixture:** in-process `python-can` virtual buses (no file required).

---

### `TEST-GATEWAY-03` — Backend selection

```gherkin
Given  source and destination backends are specified explicitly
When   the operator runs `canarchy gateway src dst --src-backend TYPE --dst-backend TYPE`
Then   the correct backend value shall be passed to each respective bus open path
```

**Fixture:** mocked bus open path.

---

### `TEST-GATEWAY-04` — Count limit

```gherkin
Given  more frames are available on the source bus than the requested count
When   the operator runs `canarchy gateway src dst --count 2`
Then   forwarding shall stop after exactly two total forwarded frames
```

**Fixture:** in-process `python-can` virtual bus with more than two frames.

---

### `TEST-GATEWAY-05` — Backend requirement

```gherkin
Given  the scaffold backend is active via `CANARCHY_TRANSPORT_BACKEND=scaffold`
When   the operator runs `canarchy gateway src dst --json`
Then   the command shall exit with code `2`
And    `errors[0].code` shall equal `"GATEWAY_LIVE_BACKEND_REQUIRED"`
```

**Fixture:** scaffold backend environment variable.

---

### `TEST-GATEWAY-06` — Invalid count

```gherkin
Given  a valid gateway source and destination are specified
When   the operator runs `canarchy gateway src dst --count 0 --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_COUNT"`
```

**Fixture:** none required.

---

### `TEST-GATEWAY-07` — JSON output structure

```gherkin
Given  a valid gateway source and destination with one frame available
When   the operator runs `canarchy gateway src dst --count 1 --json`
Then   the result envelope shall contain one frame event
And    the event `source` field shall equal `"gateway.src->dst"`
```

**Fixture:** in-process `python-can` virtual bus with one frame.

---

### `TEST-GATEWAY-08` — Table output

```gherkin
Given  a valid gateway source and destination with one frame available
When   the operator runs `canarchy gateway src dst --count 1 --table`
Then   the output shall contain a `gateway:` header line
And    the output shall contain at least one candump-style frame line
```

**Fixture:** in-process `python-can` virtual bus with one frame.

---

## Fixtures And Environment

No fixture files are required. Tests use in-process `python-can` virtual buses and mocking around the backend open path.

## Explicit Non-Coverage

* physical hardware adapters such as PCAN, SLCAN, and SocketCAN
* cross-process validation beyond the dedicated transport tests
* indefinite streaming without `--count`

## Traceability

This spec maps to the gateway acceptance criteria around forwarding behavior, structured output, and transport/user error handling.
