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
* active-transmit alert emission
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

### `TEST-GENERATE-01` Explicit frame generation

Action: run `canarchy generate can0 --id 0x123 --dlc 4 --data 11223344 --count 2 --gap 100 --json`.  
Assert: two frames are returned with the expected identifier, payload, timestamps, and active-transmit alert.

### `TEST-GENERATE-02` Random generation modes

Action: run `generate` with random identifier or payload settings.  
Assert: the command succeeds and emitted frames still satisfy the expected structural constraints.

### `TEST-GENERATE-03` Incrementing payload mode

Action: run `generate` with `--data I`.  
Assert: payload bytes increment deterministically across the emitted frames.

### `TEST-GENERATE-04` Invalid identifier

Action: run `generate` with an invalid `--id` value.  
Assert: exit code `1` and `errors[0].code == "INVALID_FRAME_ID"`.

### `TEST-GENERATE-05` Invalid DLC

Action: run `generate` with an invalid `--dlc` value.  
Assert: exit code `1` and `errors[0].code == "INVALID_DLC"`.

### `TEST-GENERATE-06` Invalid payload

Action: run `generate` with invalid `--data`.  
Assert: exit code `1` and `errors[0].code == "INVALID_FRAME_DATA"`.

### `TEST-GENERATE-07` Invalid count

Action: run `generate` with `--count 0`.  
Assert: exit code `1` and `errors[0].code == "INVALID_COUNT"`.

### `TEST-GENERATE-08` Invalid gap

Action: run `generate` with a negative `--gap`.  
Assert: exit code `1` and `errors[0].code == "INVALID_GAP"`.

## Fixtures And Environment

No dedicated fixture files are required. Tests exercise the command through the deterministic scaffold backend and CLI unit coverage.

## Explicit Non-Coverage

* live-backend transmit timing enforcement
* CAN FD generation flags, which remain out of scope

## Traceability

This spec maps to the generate acceptance criteria around deterministic generation, active-transmit signaling, and structured validation errors.
