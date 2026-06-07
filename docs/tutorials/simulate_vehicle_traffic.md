# Tutorial: Simulate a Vehicle's Bus Traffic

This tutorial walks through `canarchy simulate` end to end: planning a run,
transmitting it onto a virtual bus, and analyzing what came out the other
side — all without a live vehicle, hardware, or a recorded capture file.

## What `simulate` gives you

`canarchy simulate` emits a deterministic, seedable mix of classic CAN
frames, J1939 PGN traffic, and occasional DM1 fault bursts, shaped by a named
**vehicle profile**. CANarchy ships two profiles out of the box:

| Profile | Shape |
|---------|-------|
| `heavy-truck` | Class-8 tractor: instrument cluster + body controller heartbeats, EEC1/ET1/CCVS/TC1/EBC1 J1939 traffic, and an SPN 110 (coolant temperature) DM1 burst |
| `passenger-car` | Light-duty vehicle: dense proprietary CAN (RPM, wheel speed, steering, body control, climate) plus a thin J1939 slice and an SPN 84 (vehicle speed) DM1 burst |

Profiles live in `canarchy/resources/simulate/profiles.json` as plain data —
adding a new vehicle archetype never requires touching Python code.

## Step 1 — Plan the run with `--dry-run`

Start by inspecting what a profile produces before transmitting anything.
`--dry-run` samples the exact same deterministic sequence but skips opening a
transport entirely:

```bash
canarchy simulate --profile heavy-truck --rate 50 --duration 2 --seed 1 --dry-run --json
```

The JSON envelope's `data` carries `mode: "dry_run"`, `frame_count`, and the
full list of serialized `events`. Re-run the same command and you will get
byte-for-byte identical arbitration IDs, payloads, and timestamps — `--seed`
makes the stream fully reproducible, which is exactly what you want for CI
fixtures or regression baselines.

Switch to `--text` for a human-readable candump-style preview:

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

## Step 2 — Bring up a virtual bus

`simulate` is an **active-transmit** command — it actually puts frames on a
bus, so it goes through the same safety gate as `generate` and `send`. Set up
a virtual SocketCAN interface first (see
[Build a virtual CAN loop](../cookbook/virtual-can-loop.md) for the full
walkthrough and a `udp_multicast` alternative):

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

## Step 3 — Transmit the profile

In one terminal, start a capture so you can watch the simulated traffic
arrive:

```bash
canarchy capture vcan0 --candump
```

In a second terminal, run the simulator with `--ack-active`. CANarchy prints
a preflight warning and then asks you to type `YES` before any frame is
actually transmitted — this is intentional friction for an active-transmit
workflow:

```bash
canarchy simulate vcan0 --profile heavy-truck --rate 50 --duration 10 --seed 1 --ack-active
```

The capture terminal starts printing the simulated mix of classic CAN, J1939,
and (occasionally) DM1 frames in candump form.

## Step 4 — Capture and analyze the result

Redirect the capture to a file so you can run it back through CANarchy's
analysis tooling:

```bash
canarchy capture vcan0 --candump > /tmp/heavy-truck-sim.candump
```

Then treat it exactly like a real-world trace. Inspect the J1939 traffic mix:

```bash
canarchy j1939 summary /tmp/heavy-truck-sim.candump --json
```

And decode the simulated DM1 fault burst — the `heavy-truck` profile injects
an SPN 110 (Engine Coolant Temperature) fault with FMI 16 and an amber
warning lamp:

```bash
canarchy j1939 dm1 /tmp/heavy-truck-sim.candump --json
```

Because `simulate` packs DM1 payloads using the same byte layout
`canarchy.j1939.dm1_messages` decodes, the fault round-trips cleanly —
useful for validating downstream tooling against a known-good fixture.

## Step 5 — Try the other profile, or write your own

Swap `--profile passenger-car` to see a denser classic-CAN mix with a thinner
J1939 slice and an SPN 84 (Vehicle Speed) DM1 burst. To add a new archetype,
append an entry to `profiles.json` describing weighted `classic_frames`,
`j1939_messages`, and an optional `dm1` block — see
[Run and analyze a simulated vehicle traffic profile](../cookbook/simulate-vehicle-profiles.md)
for the JSON shape and field reference.

## Where to go next

* [Run and analyze a simulated vehicle traffic profile](../cookbook/simulate-vehicle-profiles.md) — cookbook recipe with the profile JSON schema
* [Build a virtual CAN loop for offline testing](../cookbook/virtual-can-loop.md)
* [Generate and Capture](generate_and_capture.md) — the related fixed/random/incrementing frame generator
* [J1939 Heavy Vehicle Analysis](j1939_heavy_vehicle.md) — deeper protocol-aware analysis once you have a capture
