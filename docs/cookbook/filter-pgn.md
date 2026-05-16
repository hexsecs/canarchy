# Filter for a single arbitration ID or PGN

## Goal

Pull every frame matching a specific arbitration ID (or J1939 PGN) out
of a capture, in a form you can pipe into other commands.

## Prerequisites

* CANarchy installed (`canarchy --version` works).
* Any candump capture. The examples use the in-tree fixture
  `tests/fixtures/j1939_heavy_vehicle.candump`.

## Filter on a raw arbitration ID

```bash
canarchy filter 'id==0x18FEEE31' \
  --file tests/fixtures/j1939_heavy_vehicle.candump \
  --jsonl
```

Each output line is a `frame` event from the canonical
[Event Schema](../event-schema.md). Pipe it into `jq` for further
shaping.

## Filter on a J1939 PGN

PGNs map to ranges of arbitration IDs. The cleanest way is to use the
J1939-aware commands instead of writing a regex:

```bash
canarchy j1939 pgn 65262 \
  --file tests/fixtures/j1939_heavy_vehicle.candump \
  --text
```

That prints every observation of PGN 65262 (Engine Coolant Temperature)
with decoded signal context where available.

## Compose with other commands

`filter` supports `&&` and `||`, plus payload substring matching:

```bash
canarchy filter 'id==0x18FEEE31 && data~=7f' \
  --file tests/fixtures/j1939_heavy_vehicle.candump \
  --jsonl \
  | canarchy stats --file - --json
```

## Where to go next

* [Command Spec — filter](../command_spec.md)
* [J1939 Heavy Vehicle Analysis tutorial](../tutorials/j1939_heavy_vehicle.md)
