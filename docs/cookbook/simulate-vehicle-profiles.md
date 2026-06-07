# Run and analyze a simulated vehicle traffic profile

## Goal

Generate a believable mix of classic CAN frames, J1939 PGN traffic, and
occasional DM1 fault bursts — without a live vehicle, a recorded capture, or
any hardware — and then analyze the result with CANarchy's existing decode and
DM1 tooling.

## Step 1 — Plan a run with `--dry-run`

Before transmitting anything, inspect what a profile produces. `--dry-run`
samples the same deterministic frame sequence but skips opening a transport:

```bash
canarchy simulate --profile heavy-truck --rate 50 --duration 2 --seed 1 --dry-run --text
```

```text
command: simulate
interface: unknown
profile: heavy-truck
frames: 100
(0.000000) can0 0CF00400#1C2E2BB8569D806C
(0.020000) can0 18FEF200#0001020304050607
...
```

`--seed` makes the run reproducible: the same profile, rate, duration, and
seed always produce the same arbitration IDs, payload bytes, and timestamps.

## Step 2 — Pipe simulated traffic onto a virtual bus

Bring up a virtual SocketCAN interface (see
[Build a virtual CAN loop](virtual-can-loop.md)), then transmit the profile:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

canarchy simulate vcan0 --profile heavy-truck --rate 50 --duration 10 --seed 1 --ack-active
```

`simulate` is an active-transmit command: it prints a preflight warning, and
with `--ack-active` it asks you to type `YES` before any frame leaves the
interface — the same safety gate used by `generate` and `send`. You can also
target a `udp_multicast` address or rely on `--dry-run` plus shell piping if
you only need a candump-style stream for another tool.

## Step 3 — Capture and decode the simulated traffic

In a second terminal, capture what the simulator produced:

```bash
canarchy capture vcan0 --candump > /tmp/heavy-truck-sim.candump
```

Then run it through the J1939 tooling exactly as you would a real capture —
for example, to see the simulated DM1 fault burst:

```bash
canarchy j1939 dm1 /tmp/heavy-truck-sim.candump --json
```

The `heavy-truck` profile injects an SPN 110 (Engine Coolant Temperature)
fault with FMI 16 and an amber warning lamp; `passenger-car` injects an
SPN 84 (Vehicle Speed) fault with FMI 2 and the MIL lamp. Both decode cleanly
because `simulate` packs DM1 payloads using the same byte layout
`canarchy.j1939.dm1_messages` expects.

## Step 4 — Add your own profile

Profiles are plain JSON resources under
`canarchy/resources/simulate/profiles.json` — no code changes required. Each
profile mixes weighted `classic_frames`, `j1939_messages`, and an optional
`dm1` burst:

```json
{
  "my-archetype": {
    "description": "...",
    "classic_frames": [
      {"name": "...", "arbitration_id": "0x100", "extended": false, "dlc": 8, "weight": 4, "data_pattern": "counter"}
    ],
    "j1939_messages": [
      {"name": "EEC1", "pgn": 61444, "priority": 3, "source_address": 0, "dlc": 8, "weight": 8, "data_pattern": "counter"}
    ],
    "dm1": {
      "weight": 1,
      "source_address": 0,
      "lamp_status": "mil",
      "fault_codes": [{"spn": 110, "fmi": 16, "occurrence_count": 1}]
    }
  }
}
```

`weight` controls how often a template is sampled relative to its peers, and
`data_pattern` may be `counter`, `slow-drift`, or `random`.

## Where to go next

* [Build a virtual CAN loop for offline testing](virtual-can-loop.md)
* [Compare two captures for DM1 fault diffs](compare-dm1-faults.md)
* [J1939 Heavy Vehicle Analysis tutorial](../tutorials/j1939_heavy_vehicle.md)
