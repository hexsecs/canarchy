# Analyze a capture from a UTHP / TCAT appliance

## Goal

Use CANarchy as the analysis layer for captures taken on a heavy-vehicle
assessment appliance such as the SystemsCyber **UTHP** (Universal Truck
Hacking Platform) or the NMFTA **TCAT** (Truck Cybersecurity Assessment
Tool). Both are BeagleBone-class devices with four CAN channels
(`can0`–`can3`) that expose standard SocketCAN interfaces, so everything
CANarchy does with candump files and SocketCAN applies directly.

This recipe is passive end to end: it captures on the appliance and
analyzes the file offline. No frames are transmitted.

## Prerequisites

* A UTHP or TCAT appliance connected to a truck network (J1939 backbone
  or diagnostic connector) with at least one CAN channel active.
* SSH access to the appliance, or any way to copy files off it.
* CANarchy installed where the analysis runs (the appliance itself can run
  it, but copying captures to a workstation is the more comfortable path).

## Capture on the appliance

The appliances ship `can-utils`, so the simplest capture is candump's
timestamped log format, which CANarchy reads natively:

```bash
# on the appliance — capture 60 seconds of traffic from can0
timeout 60 candump -L can0 > drive.candump
```

CANarchy itself also runs on the appliance if installed there:

```bash
canarchy capture can0 --candump > drive.candump
```

Copy the file to the analysis machine:

```bash
scp tcat:/home/debian/drive.candump .
```

## Triage the capture

Size up the file before deeper analysis and note the suggested
`max_frames` / `seconds` bounds for large captures:

```bash
canarchy capture-info --file drive.candump --json
```

Get the J1939 picture — PGN distribution, source addresses, transport
sessions, and any printable identifiers (VIN, component IDs) broadcast
over TP:

```bash
canarchy j1939 summary --file drive.candump --json
canarchy j1939 inventory --file drive.candump --json
```

Pull the fault story — DM1 DTCs grouped per ECU with SPN names, FMI
descriptions, and lamp status from the bundled SAE catalogs:

```bash
canarchy j1939 faults --file drive.candump --json
```

## Dig deeper with the RE tools

The reverse-engineering commands annotate J1939 frames with PGN labels and
source-address names automatically, and skip J1939 transport-protocol
framing so TP sequence numbers do not masquerade as signals:

```bash
canarchy re entropy --file drive.candump --json
canarchy re counters --file drive.candump --json
canarchy re anomalies --file drive.candump --baseline known_good.candump --json
```

For multi-channel work, capture each appliance channel (`can0`–`can3`) to
its own file and diff them:

```bash
canarchy j1939 compare --file can0.candump --file can1.candump --json
canarchy re corpus --file can0.candump --file can1.candump --json
```

## About UTHP and TCAT

* [UTHP](https://github.com/SystemsCyber/UTHP) is the Universal Truck
  Hacking Platform from the Colorado State University Systems Cyber group:
  a BeagleBone-based appliance image bundling truck-protocol tooling
  (python-can, pretty-j1939, pretty-j1587, PLC4TRUCKSduck, TruckDevil,
  CanCat, cannelloni, and more).
* [TCAT](https://github.com/nmfta-repo/TCAT) is the NMFTA Truck
  Cybersecurity Assessment Tool — the productized, hardened release of the
  same platform, distributed as a flashable image.
* Both projects are MIT licensed. The third-party tools they bundle carry
  their own licenses. CANarchy complements rather than replaces them: the
  appliance provides the bus access and channel breadth; CANarchy provides
  the structured, scriptable analysis layer over the captures.

## See also

* [Compare two captures for DM1 fault diffs](compare-dm1-faults.md)
* [Find counter signals in a capture](find-counter-signals.md)
* [Filter for a single arbitration ID or PGN](filter-pgn.md)
