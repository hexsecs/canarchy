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
| `REQ-GATEWAY-04` | `TEST-GATEWAY-04`, `TEST-GATEWAY-06` |
| `REQ-GATEWAY-05` | `TEST-GATEWAY-07` |
| `REQ-GATEWAY-06` | `TEST-GATEWAY-05` |
| `REQ-GATEWAY-07` | `TEST-GATEWAY-08` |

## Representative Test Cases

### `TEST-GATEWAY-01` Unidirectional forwarding

Setup: two in-process virtual buses on the same channel using threads.  
Action: send two frames on the source bus.  
Assert: both frames arrive on the destination bus with the expected arbitration IDs and payloads.

### `TEST-GATEWAY-02` Bidirectional forwarding

Setup: two in-process virtual buses on distinct channels.  
Action: send one frame `src->dst` and one frame `dst->src`.  
Assert: both frames are forwarded and the emitted events carry the correct direction label.

### `TEST-GATEWAY-03` Backend selection

Setup: source and destination backends are provided explicitly.  
Action: run gateway with `--src-backend` and `--dst-backend`.  
Assert: the correct backend values are passed to the source and destination bus open path.

### `TEST-GATEWAY-04` Count limit

Setup: more frames are available than `--count`.  
Action: run gateway with `--count 2`.  
Assert: forwarding stops after exactly two total forwarded frames.

### `TEST-GATEWAY-05` Backend requirement

Setup: default scaffold backend with no `CANARCHY_TRANSPORT_BACKEND` override.  
Action: run `canarchy gateway src dst --json`.  
Assert: exit code `2` and `errors[0].code == "GATEWAY_LIVE_BACKEND_REQUIRED"`.

### `TEST-GATEWAY-06` Invalid count

Setup: request `--count 0`.  
Action: run `canarchy gateway src dst --count 0 --json`.  
Assert: exit code `1` and `errors[0].code == "INVALID_COUNT"`.

### `TEST-GATEWAY-07` JSON output structure

Setup: forward one frame with `--count 1`.  
Action: run with `--json`.  
Assert: payload contains one frame event whose `source` is `gateway.src->dst`.

### `TEST-GATEWAY-08` Table output

Setup: forward one frame with `--count 1`.  
Action: run with `--table`.  
Assert: output contains a `gateway:` header plus at least one candump-style frame line.

## Fixtures And Environment

No fixture files are required. Tests use in-process `python-can` virtual buses and mocking around the backend open path.

## Explicit Non-Coverage

* physical hardware adapters such as PCAN, SLCAN, and SocketCAN
* cross-process validation beyond the dedicated transport tests
* indefinite streaming without `--count`

## Traceability

This spec maps to the gateway acceptance criteria around forwarding behavior, structured output, and transport/user error handling.
