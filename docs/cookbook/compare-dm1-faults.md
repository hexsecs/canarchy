# Compare two captures for DM1 fault diffs

## Goal

Given two J1939 captures from the same vehicle taken at different times,
surface which active fault codes (DM1) changed between them.

## Prerequisites

* CANarchy installed.
* Two J1939 captures. The example uses the in-tree fixtures:
  * `tests/fixtures/j1939_heavy_vehicle.candump`
  * `tests/fixtures/j1939_compare_shifted.candump`

## Show active faults in each capture

```bash
canarchy j1939 dm1 \
  --file tests/fixtures/j1939_heavy_vehicle.candump \
  --text
```

```bash
canarchy j1939 dm1 \
  --file tests/fixtures/j1939_compare_shifted.candump \
  --text
```

Each line lists the source address, transport mode, count of active
DTCs, lamp state, and the decoded `spn`/`fmi` pairs.

## Diff the two captures

```bash
canarchy j1939 compare \
  tests/fixtures/j1939_heavy_vehicle.candump \
  tests/fixtures/j1939_compare_shifted.candump \
  --text
```

The compare output surfaces PGN deltas, source address changes, DM1
fault changes, and printable TP identification differences.

## JSON for further analysis

```bash
canarchy j1939 compare \
  tests/fixtures/j1939_heavy_vehicle.candump \
  tests/fixtures/j1939_compare_shifted.candump \
  --json \
  | jq '.data.dm1_changes'
```

## Where to go next

* [Decode SPN 110](decode-spn-110.md)
* [J1939 Heavy Vehicle Analysis tutorial](../tutorials/j1939_heavy_vehicle.md)
