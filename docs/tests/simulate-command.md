# Test Spec: `simulate` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Related design spec | `docs/design/simulate-command.md` |
| Primary test area | CLI, active transmit |

## Test Objectives

Validate that `simulate` loads data-driven vehicle profiles, produces a deterministic and seedable mix of classic CAN, J1939, and DM1 frames at the requested rate, supports both dry-run planning and active transmission through the existing safety gate, and returns structured validation errors for invalid input.

## Coverage Requirements

* dry-run planning produces the expected frame count and event shape without opening a transport
* identical `--seed` values reproduce identical frame sequences (arbitration IDs and payload bytes)
* the emitted frame mix matches the selected profile (classic CAN arbitration IDs, known J1939 PGNs, and at least one DM1 burst)
* active mode emits the active-transmit preflight warning, a leading `ACTIVE_TRANSMIT` alert event, and the requested number of frame events
* `--text` output renders the command/interface/profile/frame-count summary plus candump-formatted frame lines
* structured validation errors for an unknown profile, a non-positive `--rate`, and a non-positive `--duration`

## Requirement Traceability

| Requirement ID | Covered by test IDs |
|----------------|---------------------|
| `REQ-SIMULATE-01` | `TEST-SIMULATE-01`, `TEST-SIMULATE-05` |
| `REQ-SIMULATE-02` | `TEST-SIMULATE-03` |
| `REQ-SIMULATE-03` | `TEST-SIMULATE-03` |
| `REQ-SIMULATE-04` | `TEST-SIMULATE-01`, `TEST-SIMULATE-03` |
| `REQ-SIMULATE-05` | `TEST-SIMULATE-02` |
| `REQ-SIMULATE-06` | `TEST-SIMULATE-04` |
| `REQ-SIMULATE-07` | `TEST-SIMULATE-01` |
| `REQ-SIMULATE-08` | `TEST-SIMULATE-04` |
| `REQ-SIMULATE-09` | `TEST-SIMULATE-06` |
| `REQ-SIMULATE-10` | `TEST-SIMULATE-07` |
| `REQ-SIMULATE-11` | `TEST-SIMULATE-08` |
| `REQ-SIMULATE-12` | Deferred — exercised indirectly; no shipped profile is empty |

## Representative Test Cases

### `TEST-SIMULATE-01` — Dry-run planning

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate vcan0 --profile heavy-truck --rate 10 --duration 1 --seed 1 --dry-run --json`
Then   the command shall succeed without opening a transport
And    `data.mode` shall equal `"dry_run"` and `data.dry_run` shall be `true`
And    the result shall contain exactly ten frame events tagged `interface: "vcan0"`
```

**Fixture:** scaffold backend; `LocalTransport.generate_events` patched to assert it is never called.

---

### `TEST-SIMULATE-02` — Deterministic seeding

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate --profile passenger-car --rate 20 --duration 1 --seed 7 --dry-run --json` twice
Then   both runs shall produce the same ordered sequence of (arbitration_id, data) pairs
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-SIMULATE-03` — Frame mix matches the profile

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate vcan0 --profile heavy-truck --rate 50 --duration 5 --seed 3 --dry-run --json`
Then   the command shall emit exactly 250 frame events
And    every classic-CAN frame shall use one of the profile's declared arbitration IDs
And    the extended frames' decomposed PGNs shall include at least one of the profile's J1939 PGNs
And    at least one frame shall carry the profile's DM1 PGN
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-SIMULATE-04` — Active transmission

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate vcan0 --profile passenger-car --rate 10 --duration 1 --seed 5 --json`
Then   the command shall emit the `simulate` preflight warning on `stderr`
And    `data.mode` shall equal `"active"`
And    the first event shall be an `alert` event with `code: "ACTIVE_TRANSMIT"`
And    the result shall contain exactly ten frame events
```

**Fixture:** scaffold backend; `time.sleep` patched to avoid real delays.

---

### `TEST-SIMULATE-05` — Text output

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate vcan0 --profile heavy-truck --rate 5 --duration 1 --seed 0 --text`
Then   stdout shall contain `command: simulate`, `interface: vcan0`, `profile: heavy-truck`, and `frames: 5`
And    stdout shall contain candump-formatted frame lines for the `vcan0` interface
```

**Fixture:** scaffold backend; `time.sleep` patched to avoid real delays.

---

### `TEST-SIMULATE-06` — Unknown profile is rejected at the argument layer

```gherkin
Given  no transport backend override is required
When   the operator runs `canarchy simulate --profile nonexistent --json`
Then   the command shall exit with code `1`
And    `errors[0].code` shall equal `"INVALID_ARGUMENTS"`
And    the error message shall name the invalid choice and list the valid profiles
```

**Fixture:** none required.

---

### `TEST-SIMULATE-07` — Invalid rate

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate vcan0 --profile heavy-truck --rate 0 --dry-run --json`
Then   the command shall exit with the transport error exit code
And    `errors[0].code` shall equal `"SIMULATE_INVALID_RATE"`
```

**Fixture:** scaffold backend (no file required).

---

### `TEST-SIMULATE-08` — Invalid duration

```gherkin
Given  the scaffold transport backend is active
When   the operator runs `canarchy simulate vcan0 --profile heavy-truck --duration -1 --dry-run --json`
Then   the command shall exit with the transport error exit code
And    `errors[0].code` shall equal `"SIMULATE_INVALID_DURATION"`
```

**Fixture:** scaffold backend (no file required).

---

## Fixtures And Environment

No dedicated fixture files are required. Tests exercise the command through the deterministic scaffold backend (`CANARCHY_TRANSPORT_BACKEND=scaffold`) and CLI unit coverage in `tests/test_cli.py`, plus MCP tool coverage in `tests/test_mcp.py` (ack/dry-run gating and `_build_argv` translation).

## Explicit Non-Coverage

* live-backend transmit timing enforcement (mirrors `generate`)
* CAN FD frame emission within profiles
* authoring or validating custom third-party `profiles.json` entries beyond the shipped `heavy-truck` and `passenger-car` profiles
* `SIMULATE_EMPTY_PROFILE`, since no shipped profile is empty and the CLI's `choices`-restricted `--profile` makes `SIMULATE_UNKNOWN_PROFILE` unreachable in practice

## Traceability

This spec maps to the `simulate` acceptance criteria (#333) around profile-driven traffic mixes, deterministic seeding, dry-run planning, active-transmit safety integration, and structured validation errors.
