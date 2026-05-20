# Fuzz Tesla DI_torque2 vehicle speed

## Goal

Inspect the Tesla CAN DBC, identify the `DI_vehicleSpeed` field in
`DI_torque2`, and run a bounded active fuzz campaign against the message
that carries it.

This recipe is intended for a controlled lab bus or virtual backend. It
uses the configured CANarchy default interface so the same commands work
with `socketcan`, `virtual`, or `udp_multicast` setups.

## Prerequisites

* CANarchy installed with the opendbc provider cache populated.
* A controlled CAN target or virtual python-can backend.
* Active-transmit authorization for the target environment.

For a cross-platform multicast lab backend, a config like this sends through
python-can `udp_multicast` with `239.0.0.1` as the command channel:

```toml
[transport]
backend = "python-can"
interface = "udp_multicast"
default_interface = "239.0.0.1"
```

In this shape, `[transport].interface` selects the python-can backend type,
and `[transport].default_interface` is the channel CANarchy passes to active
commands when no positional interface is supplied.

## Load the Tesla CAN DBC

Fetch the provider-backed DBC and inspect `DI_torque2`:

```bash
canarchy dbc fetch opendbc:tesla_can --json

canarchy dbc inspect opendbc:tesla_can \
  --message DI_torque2 \
  --json
```

Important fields in `DI_torque2` (`0x118`, DLC 6):

| Signal | Bits | Meaning |
|---|---:|---|
| `DI_torqueEstimate` | 12 | Estimated drive torque |
| `DI_gear` | 3 | Actual gear (`P`, `R`, `N`, `D`, etc.) |
| `DI_brakePedal` | 1 | Brake applied flag |
| `DI_vehicleSpeed` | 12 | Vehicle speed, `raw * 0.05 - 25` MPH |
| `DI_gearRequest` | 3 | Requested gear |
| `DI_torque2Counter` | 4 | Rolling counter |
| `DI_torque2Checksum` | 8 | Message checksum |

`DI_vehicleSpeed` has a physical range of `-25..179.75 MPH`; raw `4095` is
marked `SNA` in the DBC.

## Dry-run first

Plan a 10-second random fuzz run without opening the transport:

```bash
canarchy fuzz payload \
  --id 0x118 \
  --strategy random \
  --dlc 6 \
  --max 1000 \
  --rate 100 \
  --seed 118 \
  --dry-run \
  --json
```

The command omits the positional interface intentionally. CANarchy resolves
the channel from `[transport].default_interface` or
`CANARCHY_DEFAULT_INTERFACE`.

## Run the active fuzz pass

After validating the plan and confirming the target is safe, run the same
payload campaign live:

```bash
canarchy fuzz payload \
  --id 0x118 \
  --strategy random \
  --dlc 6 \
  --max 1000 \
  --rate 100 \
  --seed 118 \
  --ack-active \
  --json
```

CANarchy prints an active-transmit warning and prompts for `YES` before
sending unless the invocation is running through an explicitly authorized
non-interactive integration.

## Add boundary coverage

Follow the random pass with a short boundary pass to hit low/high,
alternating, walking-one, and walking-zero payload patterns:

```bash
canarchy fuzz payload \
  --id 0x118 \
  --strategy boundary \
  --dlc 6 \
  --rate 100 \
  --ack-active \
  --json
```

## Checksum caveat

Tesla messages include counters and checksums, but CANarchy does not yet
implement Tesla checksum repair or expose a Tesla-specific checksum repair
flag for this workflow. Keep the fuzz commands above as raw payload mutation
until the checksum algorithm has been added and validated for the target
message family.

Without checksum repair, this recipe is best for:

* exercising parser, gateway, IDS, and harness behavior
* testing how receivers reject malformed or stale-counter frames
* generating reproducible payload corpora for later replay

For ECU acceptance testing, capture known-good `DI_torque2` traffic first,
infer the checksum/counter behavior, then add a checksum repair step before
active replay.

## What to watch

During or after the fuzz run, monitor for:

* IDS alerts tied to `0x118`
* receiver-side checksum or counter fault logging
* transitions in `DI_state` (`0x368`) such as cruise state, system state, or
  AEB state changes
* downstream disagreement between speed, gear, brake, and torque signals

## Where to go next

* [Build a virtual CAN loop for offline testing](virtual-can-loop.md)
* [Discover and Use Provider-Backed DBC Files tutorial](../tutorials/dbc_provider_workflow.md)
* [Active-Transmit Safety Model](../design/active-transmit-safety.md)
