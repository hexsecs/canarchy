# Design Spec: `simulate` Command

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy simulate` |
| Primary area | CLI, active transmit |

## Goal

Give operators a standalone bus simulator that emits realistic, deterministic synthetic CAN/J1939 traffic for a named vehicle archetype, so labs and CI pipelines can exercise CANarchy's capture/decode/analysis workflows without a live vehicle or recorded capture.

## User-Facing Motivation

Building and testing CANarchy workflows (or downstream tooling) requires a believable mix of classic CAN frames, J1939 PGN traffic, and occasional DM1 fault bursts. Recorded captures are useful but static and licensing-encumbered; `simulate` produces an unlimited, seedable stream that mirrors the shape of real heavy-vehicle and passenger-car buses.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-SIMULATE-01` | Ubiquitous | The system shall provide a `canarchy simulate [<interface>] --profile <name>` command that emits synthetic CAN traffic shaped by a named vehicle profile. |
| `REQ-SIMULATE-02` | Ubiquitous | The system shall ship at least the `heavy-truck` and `passenger-car` profiles, each mixing classic CAN frames, J1939 PGN traffic, and occasional DM1 fault bursts. |
| `REQ-SIMULATE-03` | Ubiquitous | Profiles shall be data-driven JSON resources so new vehicle archetypes can be added without modifying `canarchy.simulate`. |
| `REQ-SIMULATE-04` | Event-driven | When `simulate` is invoked, the system shall sample frame templates from the selected profile weighted by each template's `weight`, evenly space frame timestamps at `1 / --rate` seconds, and bound the run to `--duration` seconds. |
| `REQ-SIMULATE-05` | Event-driven | When `--seed` is supplied, the system shall produce an identical sequence of frames (arbitration IDs, payload bytes, and timestamps) for repeated invocations with the same profile, rate, duration, and seed. |
| `REQ-SIMULATE-06` | Event-driven | When `simulate` is invoked and validation succeeds, the system shall emit a preflight active-transmit warning to `stderr`, emit a leading active-transmit alert event, and serialise the generated frame events with `source="simulate"` (dry-run) or `source="transport.generate"` (active). |
| `REQ-SIMULATE-07` | Optional feature | Where `--dry-run` is supplied, the system shall plan and serialise the frame events without opening a transport or transmitting. |
| `REQ-SIMULATE-08` | Optional feature | Where `--ack-active` is supplied, the system shall require a confirmation response of `YES` before simulated frames are transmitted. |
| `REQ-SIMULATE-09` | Unwanted behaviour | If `--profile` does not name a known profile, argument parsing shall reject the value with a structured `INVALID_ARGUMENTS` error and exit code 1. |
| `REQ-SIMULATE-10` | Unwanted behaviour | If `--rate` is less than or equal to zero, the system shall return a structured error with code `SIMULATE_INVALID_RATE`. |
| `REQ-SIMULATE-11` | Unwanted behaviour | If `--duration` is less than or equal to zero, the system shall return a structured error with code `SIMULATE_INVALID_DURATION`. |
| `REQ-SIMULATE-12` | Unwanted behaviour | If a profile resource defines no frame templates, the system shall return a structured error with code `SIMULATE_EMPTY_PROFILE`. |

## Command Surface

```text
canarchy simulate [<interface>] --profile {heavy-truck,passenger-car}
                  [--rate <hz>] [--duration <seconds>] [--seed <n>]
                  [--dry-run] [--ack-active]
                  [--json] [--jsonl] [--text]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `interface` | required unless `--dry-run` | CAN interface to transmit on (e.g. `vcan0`, or a `udp_multicast` / candump-piped target configured via the existing transport backends) |
| `--profile` | required | Vehicle traffic profile to emit; one of `PROFILE_NAMES` |
| `--rate` | `50` | Frame emission rate in Hz |
| `--duration` | `10` | Simulation duration in seconds |
| `--seed` | `0` | Random seed; identical seeds reproduce identical frame sequences |
| `--dry-run` | off | Plan simulated frames without opening a transport or transmitting |
| `--ack-active` | off | Request an interactive confirmation prompt before simulated frames are transmitted |

## Responsibilities And Boundaries

In scope:

* loading data-driven profile definitions from `canarchy.resources.simulate.profiles`
* deterministic, seeded sampling of classic CAN, J1939, and DM1 frame templates weighted by profile-declared `weight`
* building well-formed J1939 arbitration IDs (via `compose_arbitration_id`) and DM1 payloads compatible with `canarchy.j1939.dm1_messages` decoding
* reusing the existing active-transmit safety gate, transport backends (including `udp_multicast` and `socketcan`), and candump text rendering — `simulate` introduces no new transmission or output machinery

Out of scope:

* CAN FD frame generation
* live-backend gap enforcement with real sleeps (mirrors `generate`)
* authoring new profiles beyond `heavy-truck` and `passenger-car` (operators may add JSON entries to `profiles.json` without code changes)

## Data Model

`simulate_frames()` returns a list of `CanFrame` instances built from the selected profile's `classic_frames`, `j1939_messages`, and `dm1` template groups:

* **classic** — `arbitration_id` parsed from the template's hex string, `is_extended_id` from `extended`, payload from `data_pattern` (`counter`, `slow-drift`, or `random`)
* **j1939** — `arbitration_id` composed from `pgn` / `priority` / `source_address` via `compose_arbitration_id`, always extended, payload from `data_pattern`
* **dm1** — `arbitration_id` composed from `DM1_PGN`, payload built by `_build_dm1_payload` (2-byte lamp status + 2 reserved bytes + up to one packed DTC, matching the byte layout `canarchy.j1939._parse_dtcs` expects)

Each invocation seeds `random.Random(seed)`; template selection uses `rng.choices(..., weights=...)` so the same seed always yields the same template sequence, and `_pattern_data`'s `random` mode draws from the same `rng` instance to stay reproducible. Frame timestamps are `index * (1.0 / rate)`.

## Event Model

Each generated frame produces a `FrameEvent`. In dry-run mode the `source` is `"simulate"`; in active mode frames flow through `transport.generate_events`, which prefixes a leading `AlertEvent` with `code="ACTIVE_TRANSMIT"` and tags frames with `source="transport.generate"` — identical to the `generate` command's event shape.

## Output Contracts

### Preflight warning

After argument validation succeeds and before any active transmission, `simulate` emits `warning: \`simulate\` will transmit \`<profile>\` profile traffic on interface \`<interface>\`; use intentionally on a controlled bus.` to `stderr`.

### JSON and JSONL

`--json` returns the standard CANarchy envelope with `data` containing `interface`, `profile`, `mode` (`"dry_run"` or `"active"`), `dry_run`, `frame_count`, `rate`, `duration`, `seed`, and the serialised `events`. `--jsonl` emits the event stream one event per line.

### Table

```text
command: simulate
interface: vcan0
profile: heavy-truck
frames: 5
(0.000000) vcan0 0CF00400#1C2E2BB8569D806C
(0.200000) vcan0 18FEF200#0001020304050607
...
```

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_ARGUMENTS` | `--profile` is not one of `PROFILE_NAMES` (rejected by `argparse` `choices`) | 1 |
| `SIMULATE_UNKNOWN_PROFILE` | a profile name reaches `load_profile` that is absent from `profiles.json` (defence in depth; unreachable via the CLI's `choices`-restricted `--profile`) | 2 |
| `SIMULATE_INVALID_RATE` | `--rate` is `<= 0` | 2 |
| `SIMULATE_INVALID_DURATION` | `--duration` is `<= 0` | 2 |
| `SIMULATE_EMPTY_PROFILE` | the selected profile defines no `classic_frames`, `j1939_messages`, or `dm1` templates | 2 |
| `INTERFACE_REQUIRED` | no interface is given, none is configured, and `--dry-run` is absent | 1 |
| `ACTIVE_ACK_REQUIRED` | active acknowledgement is required but `--ack-active` was omitted | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | `--ack-active` was supplied but the confirmation response was not `YES` | 1 |

`SIMULATE_*` codes surface through `canarchy.transport.TransportError`, which `execute_command` maps to the transport exit code (`EXIT_TRANSPORT_ERROR`).

## Deferred Decisions

* additional vehicle archetypes (e.g. motorcycle, off-highway equipment) — can be added as new `profiles.json` entries without code changes
* CAN FD frame emission within profiles
* live-backend gap enforcement with real sleeps
