# Decode SPN 110 (engine coolant temperature)

## Goal

Extract engine coolant temperature samples from a J1939 capture using the
SPN-aware decoder, with no DBC file required.

## Prerequisites

* CANarchy installed.
* Any J1939 capture. The examples use
  `tests/fixtures/j1939_heavy_vehicle.candump`.

## Run

```bash
canarchy j1939 spn 110 \
  --file tests/fixtures/j1939_heavy_vehicle.candump \
  --text
```

Expected output (abridged):

```text
spn: 110
file: tests/fixtures/j1939_heavy_vehicle.candump
observations:
- spn=110 name=Engine Coolant Temperature value=85.0 units=degC pgn=65262 sa=0x31 da=broadcast
- spn=110 name=Engine Coolant Temperature value=86.0 units=degC pgn=65262 sa=0x31 da=broadcast
- spn=110 name=Engine Coolant Temperature value=87.0 units=degC pgn=65262 sa=0x31 da=broadcast
```

## JSONL for downstream tools

```bash
canarchy j1939 spn 110 \
  --file tests/fixtures/j1939_heavy_vehicle.candump \
  --jsonl \
  | jq '[.spn, .value, .units, .timestamp]'
```

## Other useful SPNs

SPN | Description
--- | ---
190 | Engine speed
84  | Wheel-based vehicle speed
96  | Fuel level
100 | Engine oil pressure

Pass any of them to `canarchy j1939 spn <id> --file …`.

## Where to go next

* [J1939 Heavy Vehicle Analysis tutorial](../tutorials/j1939_heavy_vehicle.md)
* [Compare DM1 faults across captures](compare-dm1-faults.md)
