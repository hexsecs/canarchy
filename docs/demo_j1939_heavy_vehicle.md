# Demo: J1939 Heavy Vehicle Analysis

This demo walks through a realistic J1939 analysis scenario: an engine controller is broadcasting normal data alongside active fault codes. CANarchy finds the fault in three commands.

## Scenario

You have a candump trace from a maintenance session on a heavy vehicle. The engine controller (SA=0x31) is transmitting:

- **PGN 65262** (0xFEEE) — Engine Coolant Temperature, every 100ms
- **PGN 61444** (0xF004) — Electronic Engine Controller 1 (Engine Speed), every 100ms
- A **J1939 Transport Protocol BAM session** carrying a **DM1** (Diagnostic Message 1) with active DTCs

The fixture used in this demo is at `tests/fixtures/j1939_heavy_vehicle.candump`.

```text
(0.000000) can0 18FEEE31#7DFFFFFF
(0.100000) can0 18F00431#FFFF00001900
(0.200000) can0 18FEEE31#7EFFFFFF
(0.300000) can0 18F00431#FFFF00001A00
(0.400000) can0 18ECFF31#200C0002FFCAFE00
(0.450000) can0 18EBFF31#01000000006E0005
(0.500000) can0 18EBFF31#0201BE000702FFFF
(0.550000) can0 18FEEE31#7FFFFFFF
```

---

## Step 1 — Decode all J1939 PGNs

Get an overview of what's on the bus:

```bash
canarchy j1939 decode tests/fixtures/j1939_heavy_vehicle.candump --table
```

```text
command: j1939 decode
file: tests/fixtures/j1939_heavy_vehicle.candump
observations:
- pgn=65262 sa=0x31 da=broadcast prio=6 id=0x18FEEE31 data=7dffffff
- pgn=61444 sa=0x31 da=broadcast prio=6 id=0x18F00431 data=ffff00001900
- pgn=65262 sa=0x31 da=broadcast prio=6 id=0x18FEEE31 data=7effffff
- pgn=61444 sa=0x31 da=broadcast prio=6 id=0x18F00431 data=ffff00001a00
- pgn=60416 sa=0x31 da=0xFF prio=6 id=0x18ECFF31 data=200c0002ffcafe00
- pgn=60160 sa=0x31 da=0xFF prio=6 id=0x18EBFF31 data=01000000006e0005
- pgn=60160 sa=0x31 da=0xFF prio=6 id=0x18EBFF31 data=0201be000702ffff
- pgn=65262 sa=0x31 da=broadcast prio=6 id=0x18FEEE31 data=7fffffff
```

You can see three PGN classes from SA=0x31:

- **65262** (FEEE) — repeated three times, coolant temperature
- **61444** (F004) — repeated twice, engine speed
- **60416** (EC00) and **60160** (EB00) — J1939 TP CM/DT frames carrying a multi-packet message to address 0xFF (broadcast)

---

## Step 2 — Decode Engine Coolant Temperature

SPN 110 (Engine Coolant Temperature) lives in PGN 65262. Decode it directly:

```bash
canarchy j1939 spn 110 --file tests/fixtures/j1939_heavy_vehicle.candump --table
```

```text
command: j1939 spn
spn: 110
file: tests/fixtures/j1939_heavy_vehicle.candump
observations:
- spn=110 name=Engine Coolant Temperature value=85.0 units=degC pgn=65262 sa=0x31 da=broadcast
- spn=110 name=Engine Coolant Temperature value=86.0 units=degC pgn=65262 sa=0x31 da=broadcast
- spn=110 name=Engine Coolant Temperature value=87.0 units=degC pgn=65262 sa=0x31 da=broadcast
```

The coolant temperature is climbing: 85°C → 86°C → 87°C across the 550ms trace. That's a trend worth flagging.

---

## Step 3 — Check for Active Fault Codes

Those TP frames in Step 1 are carrying a DM1 message. Let CANarchy reassemble and decode them:

```bash
canarchy j1939 dm1 tests/fixtures/j1939_heavy_vehicle.candump --table
```

```text
command: j1939 dm1
file: tests/fixtures/j1939_heavy_vehicle.candump
messages:
- sa=0x31 transport=tp dtcs=2 mil=off amber=off codes=spn=110/fmi=5,spn=190/fmi=7
```

Two active DTCs from the engine controller:

| SPN | Name | FMI | Meaning |
|-----|------|-----|---------|
| 110 | Engine Coolant Temperature | 5 | Data valid but above normal operating range — most severe level |
| 190 | Engine Speed | 7 | Mechanical system not responding properly |

The ECU has already flagged both the coolant overheat and engine speed anomaly. All lamps are off (MIL, amber warning) — these are threshold faults, not yet a stop-engine condition.

---

## Machine-Readable Output

All three commands support `--json` for a full structured envelope or `--jsonl` for a streaming event-per-line format. JSONL is suitable for piping into further analysis tools:

```bash
# Stream all J1939 observations as JSONL
canarchy j1939 decode tests/fixtures/j1939_heavy_vehicle.candump --jsonl

# Extract just the coolant temperature values with jq
canarchy j1939 spn 110 --file tests/fixtures/j1939_heavy_vehicle.candump --jsonl \
  | jq '[.payload.spn, .payload.value, .payload.units, .payload.timestamp]'
```

```text
[110, 85.0, "degC", 0.0]
[110, 86.0, "degC", 0.2]
[110, 87.0, "degC", 0.55]
```

See the [Event Schema](event-schema.md) for the full structure of each event type.

---

## With Live Hardware

Replace the fixture path with your live interface and set the python-can backend:

```bash
export CANARCHY_TRANSPORT_BACKEND=python-can
export CANARCHY_PYTHON_CAN_INTERFACE=socketcan   # or kvaser, pcan, etc.

canarchy capture can0 --candump                   # live candump view
canarchy j1939 dm1 today.candump --table          # decode DM1 from saved capture
```

For cross-process demos without physical hardware, see the [Generate and Capture Demo](demo_generate_and_capture.md) using the `udp_multicast` backend.

---

## Summary

| Step | Command | What it shows |
|------|---------|---------------|
| 1 | `j1939 decode` | All PGNs on the bus, including TP sessions |
| 2 | `j1939 spn 110` | Engine Coolant Temp trend (SPN-level extraction) |
| 3 | `j1939 dm1` | Active DTCs reassembled from the TP BAM session |

Three commands, one fixture, complete picture.
