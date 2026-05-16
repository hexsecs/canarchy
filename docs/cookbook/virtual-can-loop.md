# Build a virtual CAN loop for offline testing

## Goal

Run CANarchy end-to-end with no hardware: one terminal sends frames, the
other terminal captures them. Useful for testing scripts, demos, and CI
fixtures.

## Option A — Linux `vcan` (recommended on Linux)

Create a virtual SocketCAN interface (one-time setup, requires root):

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

Confirm:

```bash
ip link show vcan0
```

In one terminal, start a capture:

```bash
canarchy capture vcan0 --candump
```

In another terminal, send a frame:

```bash
canarchy send vcan0 0x123 11223344 --ack-active --json
```

The capture terminal prints the frame in candump form.

## Option B — `udp_multicast` (cross-platform, no kernel modules)

Set the python-can interface to `udp_multicast`. Persist it in
`~/.canarchy/config.toml`:

```toml
[transport]
backend = "python-can"
interface = "udp_multicast"
```

Or export it for the current shell only:

```bash
export CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast
```

On macOS you may need to add a multicast route first:

```bash
sudo route add -net 239.0.0.0/8 -interface lo0
```

In one terminal:

```bash
canarchy capture 239.0.0.1 --candump
```

In another:

```bash
canarchy send 239.0.0.1 0x123 11223344 --ack-active --json
```

## Option C — Scaffold backend (deterministic offline only)

The `scaffold` backend returns pre-recorded fixture frames and does not
deliver anything between processes. Use it for unit-test-like behaviour
where you want a deterministic stream:

```bash
export CANARCHY_TRANSPORT_BACKEND=scaffold
canarchy capture can0 --json
```

## Where to go next

* [Backends and Interfaces](../backends.md)
* [Generate and Capture tutorial](../tutorials/generate_and_capture.md)
