# Demo: Generate Frames and Watch with Candump

This demo shows how to use `canarchy generate` to produce test CAN traffic and
`canarchy capture --candump` to watch it arrive in real time.

You need two terminals.

## Set the backend once

Run this in **both** terminals before anything else:

```bash
export CANARCHY_TRANSPORT_BACKEND=python-can
export CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast
```

All subsequent `canarchy` calls in that shell will use these values automatically.

## Backend choice matters

Two backends are available for software-only loopback:

| Backend | Cross-process? | macOS? | Linux? | Requires |
|---------|---------------|--------|--------|---------|
| `virtual` | No — in-process only | Yes | Yes | nothing |
| `udp_multicast` | Yes | Yes\* | Yes | `msgpack`, multicast route |

**`virtual` does not work for this demo.** It uses an in-process shared queue, so frames
sent in one process are invisible to a capture running in a separate terminal. Use
`udp_multicast` for the two-terminal workflow shown here.

> \* macOS requires a multicast route to `239.0.0.0/8`. If you see "No route to host", run:
> ```bash
> sudo route add -net 239.0.0.0/8 -interface lo0
> ```

## Terminal 1 — Start the Candump Capture

```bash
uv run canarchy capture 239.0.0.1 --candump
```

The terminal blocks and waits. Each arriving frame prints as a `candump`-style line.

## Terminal 2 — Generate Frames

### Random frames

```bash
uv run canarchy generate 239.0.0.1 --count 5
```

Terminal 1 prints something like:

```text
(1713369600.000000) 239.0.0.1 2A1#C3F19E04
(1713369600.200000) 239.0.0.1 05B#00
(1713369600.400000) 239.0.0.1 71C#A8B2CC07F1
(1713369600.600000) 239.0.0.1 3F0#
(1713369600.800000) 239.0.0.1 4D2#119A
```

### Fixed ID and payload

```bash
uv run canarchy generate 239.0.0.1 --id 0x7DF --dlc 3 --data DEADBE --count 3
```

Terminal 1 prints:

```text
(1713369600.000000) 239.0.0.1 7DF#DEADBE
(1713369600.200000) 239.0.0.1 7DF#DEADBE
(1713369600.400000) 239.0.0.1 7DF#DEADBE
```

### Incrementing data

`--data I` produces a rolling byte pattern useful for spotting dropped or out-of-order frames:

```bash
uv run canarchy generate 239.0.0.1 --id 0x100 --dlc 4 --data I --count 4
```

Terminal 1 prints:

```text
(1713369600.000000) 239.0.0.1 100#00010203
(1713369600.200000) 239.0.0.1 100#04050607
(1713369600.400000) 239.0.0.1 100#08090A0B
(1713369600.600000) 239.0.0.1 100#0C0D0E0F
```

### Extended (29-bit) IDs

```bash
uv run canarchy generate 239.0.0.1 --id 0x18FEEE31 --dlc 8 --data R --extended
```

### Control the gap

`--gap` sets the inter-frame delay in milliseconds (default 200 ms):

```bash
uv run canarchy generate 239.0.0.1 --count 10 --gap 50
```

## Get Structured Output

Use `--json` instead of `--candump` to get machine-readable output:

```bash
uv run canarchy generate 239.0.0.1 --id 0x123 --dlc 4 --data 11223344 --count 2 --json
```

## Stop the Capture

Press `Ctrl+C` in Terminal 1 to stop the candump session.
