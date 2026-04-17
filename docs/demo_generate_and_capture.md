# Demo: Generate Frames and Watch with Candump

This demo shows how to use `canarchy generate` to produce test CAN traffic and `canarchy capture --candump` to watch it in real time, using the `python-can` virtual backend as a loopback channel.

You need two terminals.

## Terminal 1 — Start the Candump Capture

Start a live candump capture on the virtual channel:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy capture vcan0 --candump
```

The terminal blocks and waits. Each frame that arrives prints as a `candump`-style line.

## Terminal 2 — Generate Frames

### Random frames

Generate five frames with random IDs and payloads:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy generate vcan0 --count 5
```

Terminal 1 prints something like:

```text
(0.000000) vcan0 2A1#C3F19E04
(0.200000) vcan0 05B#00
(0.400000) vcan0 71C#A8B2CC07F1
(0.600000) vcan0 3F0#
(0.800000) vcan0 4D2#119A
```

### Fixed ID and payload

Generate three frames with a known arbitration ID and fixed data:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy generate vcan0 --id 0x7DF --dlc 3 --data DEADBE --count 3
```

Terminal 1 prints:

```text
(0.000000) vcan0 7DF#DEADBE
(0.200000) vcan0 7DF#DEADBE
(0.400000) vcan0 7DF#DEADBE
```

### Incrementing data

Use `--data I` to produce a rolling byte pattern across frames. This is useful for spotting dropped or out-of-order frames:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy generate vcan0 --id 0x100 --dlc 4 --data I --count 4
```

Terminal 1 prints:

```text
(0.000000) vcan0 100#00010203
(0.200000) vcan0 100#04050607
(0.400000) vcan0 100#08090A0B
(0.600000) vcan0 100#0C0D0E0F
```

### Extended (29-bit) IDs

Pass `--extended` to generate frames with 29-bit arbitration IDs:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy generate vcan0 --id 0x18FEEE31 --dlc 8 --data R --extended
```

Terminal 1 prints:

```text
(0.000000) vcan0 18FEEE31#A1B2C3D4E5F60718
```

## Control the Transmission Rate

`--gap` sets the inter-frame delay in milliseconds (default 200 ms). To burst frames quickly:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy generate vcan0 --count 10 --gap 50
```

## Get Structured Output

Omit `--candump` on the capture side and use `--json` on either command to get machine-readable output suitable for scripting:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy generate vcan0 --id 0x123 --dlc 4 --data 11223344 --count 2 --json
```

```json
{
  "ok": true,
  "command": "generate",
  "data": {
    "frame_count": 2,
    "gap_ms": 200.0,
    "interface": "vcan0",
    "mode": "active",
    "transport_backend": "python-can",
    ...
  }
}
```

## Stop the Capture

Press `Ctrl+C` in Terminal 1 to stop the candump session.
