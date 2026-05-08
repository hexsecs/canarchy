# Stream CAN Data from the CANdid Dataset

This tutorial walks through discovering, browsing, and streaming real passenger-vehicle
CAN logs from the [CANdid dataset](https://doi.org/10.25909/29068553) — a CC BY 4.0
research dataset from VehicleSec 2025 containing captures from 10 vehicles across 7
driving maneuvers.

No hardware is required. Streams are fetched directly from Figshare over HTTP.

## Prerequisites

- CANarchy installed (`pip install canarchy`)
- Internet connection (files are streamed from Figshare on demand)

## 1. Inspect the dataset

Get a full summary of what the dataset contains:

```bash
canarchy datasets inspect catalog:candid
```

```
Dataset: catalog:candid [REPLAYABLE]

Basic information
  Provider: catalog
  Name: candid
  Version: vehiclesec25
  Protocol: CAN
  License: CC BY 4.0
  Size: ~13.7 GB
  Description: CANdid: A CAN bus dataset for vehicle security research ...

Format support
  Source formats: candump
  Output formats: jsonl

Source information
  Source URL: https://doi.org/10.25909/29068553
  Replay download URL: https://ndownloader.figshare.com/files/54551156
  Default replay file: 2_brakes_CAN.log
  Replay files:
    1_brakes_CAN.log (candump): 1_brakes_CAN.log
    ...
```

## 2. List all available files

See every file in the manifest with its vehicle, maneuver, and size:

```bash
canarchy datasets replay catalog:candid --list-files --json \
  | jq -r '.data.files[] | "\(.vehicle)\t\(.maneuver)\t\(.id)\t\(.size_bytes)"' \
  | column -t
```

```
1  brakes     1_brakes_CAN.log     8359774
1  indicator  1_indicator_CAN.log  15185132
1  steering   1_steering_CAN.log   15180876
...
10 engine     10_engine_CAN.log    27295876
10 driving    10_driving_CAN.log   145637522
```

67 files total — 10 vehicles, up to 7 maneuvers each (brakes, indicator, steering,
lights, gears, engine, driving).

## 3. Preview a stream without opening it

Use `--dry-run` to resolve which file will be fetched and confirm the limits before
any data is downloaded:

```bash
canarchy datasets replay catalog:candid \
  --file 3_engine_CAN.log \
  --rate 5 \
  --max-frames 100 \
  --dry-run
```

```
Replay plan (dry run): catalog:candid

Source
  Ref: catalog:candid
  Type: dataset_ref
  Download URL: https://ndownloader.figshare.com/files/54551645

Selected replay file
  File: 3_engine_CAN.log
  Format: candump

Limits
  Rate: 5.0 fps
  Max frames: 100
  Max seconds: (none)

Replay plan
  Output format: candump
  Would stream: yes
```

Nothing is downloaded during a dry run.

## 4. Stream the default file

The default file (`2_brakes_CAN.log`) starts streaming immediately at real-time
playback rate. Frames are printed in candump format as they arrive:

```bash
canarchy datasets replay catalog:candid
```

```
(0.000000) can0 316#0000000000000000
(0.004123) can0 1A0#0200000000000000
(0.008211) can0 0C8#000000000000
...
```

Press `Ctrl+C` to stop at any time.

## 5. Choose a specific file

Use `--file` with any id from the manifest:

```bash
# Vehicle 9, engine maneuver
canarchy datasets replay catalog:candid --file 9_engine_CAN.log

# Vehicle 4, full driving session (~186 MB)
canarchy datasets replay catalog:candid --file 4_driving_CAN.log
```

## 6. Control playback rate and limits

```bash
# 10× faster than real time, stop after 500 frames
canarchy datasets replay catalog:candid \
  --file 2_steering_CAN.log \
  --rate 10 \
  --max-frames 500

# Real time, stop after 30 seconds of capture time
canarchy datasets replay catalog:candid \
  --file 7_driving_CAN.log \
  --max-seconds 30
```

`--rate` is a multiplier: `1.0` = real time, `2.0` = 2× speed, `0.5` = half speed.
`--max-frames` and `--max-seconds` refer to the capture timeline, not wall-clock time.

## 7. Stream as JSONL for downstream processing

Switch the output format to JSONL to get one JSON object per frame — useful for piping
into analysis scripts or agents:

```bash
canarchy datasets replay catalog:candid \
  --file 1_brakes_CAN.log \
  --format jsonl \
  --max-frames 10 \
  --jsonl
```

```json
{"timestamp": 0.0, "interface": "can0", "arbitration_id": 790, "data": "0000000000000000", ...}
{"timestamp": 0.004123, "interface": "can0", "arbitration_id": 416, "data": "0200000000000000", ...}
...
```

Use `--jsonl` (streaming output) rather than `--json` (batched) when processing large
files to avoid buffering the entire stream in memory.

## 8. Pipe into other CANarchy commands

Replay output is plain candump text, so you can pipe it into any tool that reads
stdin — or use CANarchy's own analysis commands on a saved capture:

```bash
# Save 60 seconds to a local file, then inspect it
canarchy datasets replay catalog:candid \
  --file 5_driving_CAN.log \
  --max-seconds 60 \
  --raw > /tmp/driving.log

canarchy capture-info /tmp/driving.log
canarchy stats /tmp/driving.log
```

## Dataset notes

| Detail | Value |
|--------|-------|
| License | CC BY 4.0 |
| Vehicles | 10 passenger vehicles (anonymised) |
| Maneuvers | brakes, indicator, steering, lights, gears, engine, driving |
| Format | can-utils candump |
| Source | [https://doi.org/10.25909/29068553](https://doi.org/10.25909/29068553) |
| Paper | [VehicleSec 2025 — Howson et al.](https://www.usenix.org/conference/vehiclesec25/presentation/howson) |

Two files are absent from the upstream dataset: vehicle 2 has no driving log, and
vehicle 6 has no steering or gears logs. Vehicle 10's gears file is named
`10_gearsm_CAN.log` (upstream typo, preserved as-is).
