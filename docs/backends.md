# Backends & Interfaces

CANarchy uses **python-can** as its live transport layer. This page explains how to choose and configure a transport backend, which interface types are available, and how to verify what is in effect.

Important boundary: the transport backend selection applies to transport-facing commands such as `capture`, `send`, `generate`, and `gateway`. Some protocol-oriented commands still use explicit sample/reference providers while their true live execution path is being built; those sample providers are separate from the transport backend abstraction.

---

## The Two Backends

| Backend | What it does | When to use it |
|---|---|---|
| `python-can` | Opens a real (or virtual) CAN bus via python-can | **Default** — live capture, transmit, and gateway |
| `scaffold` | Returns deterministic fixture transport frames; never touches hardware | Offline demos, testing, CI |

The default interface type is `socketcan`. On Linux with a configured `can0`, capture works immediately with no config file.

To switch to a different interface type, set it in `~/.canarchy/config.toml`:

```toml
[transport]
backend = "python-can"
interface = "udp_multicast"
```

Or via environment variable (current session only):

```bash
export CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast
```

To use the offline scaffold backend:

```bash
export CANARCHY_TRANSPORT_BACKEND=scaffold
```

To confirm what is actually in effect, run:

```bash
canarchy config show
```

---

## Two-Part Addressing: interface vs. channel

python-can separates **bus type** from **device address**:

| Concept | python-can term | CANarchy config key | Example value |
|---|---|---|---|
| Bus driver / adapter type | `interface` | `interface` in `config.toml` / `CANARCHY_PYTHON_CAN_INTERFACE` | `socketcan`, `kvaser`, `pcan` |
| Device or port within that type | `channel` | positional CLI argument | `can0`, `PCAN_USBBUS1`, `0` |

Example: SocketCAN on Linux, interface `can0`:

```bash
canarchy capture can0   # channel = can0, interface type from config
```

Example: PCAN-USB:

```toml
[transport]
backend = "python-can"
interface = "pcan"
```

```bash
canarchy capture PCAN_USBBUS1
```

---

## Supported Interface Types

The table below covers the most commonly used python-can interface types. CANarchy passes the `interface` value directly to `python_can.Bus()` — any interface that python-can supports will work.

| Interface name | Hardware / use case | OS |
|---|---|---|
| `socketcan` | Linux SocketCAN — real hardware (PEAK, Kvaser, etc. with socketcan driver), `vcan` virtual interfaces, and `slcan` serial adapters | Linux |
| `virtual` | python-can in-process virtual bus — frames only visible within the same process | Any |
| `udp_multicast` | UDP multicast virtual bus — frames visible across processes and hosts on a LAN; no hardware needed | Any |
| `kvaser` | Kvaser USB/PCIe adapters (requires Kvaser drivers) | Windows, Linux |
| `pcan` | PEAK PCAN-USB and PCAN-PCIe adapters (requires PEAK drivers) | Windows, Linux, macOS |
| `ixxat` | HMS IXXAT adapters | Windows |
| `vector` | Vector VN-series hardware (requires Vector XL driver) | Windows |
| `slcan` | Serial-line CAN — adapters that speak ASCII CAN over USB/UART (e.g. CANable, Canable Pro) | Any |
| `cantact` | CANtact / candleLight USB devices | Any |
| `gs_usb` | Geschwister Schneider / candleLight USB devices (kernel driver) | Linux |
| `canalystii` | USB-CAN Analyzer II adapters | Any |
| `usb2can` | 8devices USB2CAN | Linux |
| `neovi` | Intrepid Control Systems neoVI hardware | Windows |
| `nican` | National Instruments NI-CAN | Windows |
| `nixnet` | NI-XNET | Windows |
| `remote` | python-can remote server over TCP | Any |

!!! note "Full and up-to-date list"
    The canonical reference for all supported interfaces, per-interface configuration options, and required driver packages is the
    [python-can documentation — Interfaces](https://python-can.readthedocs.io/en/stable/interfaces.html).
    CANarchy does not restrict which interfaces are available — anything python-can supports can be used.

---

## Common Setups

### SocketCAN on Linux (real hardware or vcan)

```toml
[transport]
backend = "python-can"
interface = "socketcan"
```

Bring up a virtual interface for testing without hardware:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
canarchy capture vcan0
```

### UDP Multicast (cross-process, no hardware)

Useful for testing across terminal sessions on a single machine or across hosts on a LAN. On macOS you may need a multicast route:

```bash
sudo route add -net 239.0.0.0/8 -interface lo0
```

```toml
[transport]
backend = "python-can"
interface = "udp_multicast"
```

```bash
# Terminal 1
canarchy capture 239.0.0.1 --candump

# Terminal 2
canarchy send 239.0.0.1 0x123 DEADBEEF
```

### PCAN-USB on Linux

```toml
[transport]
backend = "python-can"
interface = "pcan"
```

```bash
canarchy capture PCAN_USBBUS1
```

### Virtual (same-process only)

```toml
[transport]
backend = "python-can"
interface = "virtual"
```

The `virtual` interface only delivers frames within the same Python process. Use `udp_multicast` if you need cross-process visibility.

---

## Verifying Your Configuration

```bash
canarchy config show
```

Output shows each value and its source (`[env]`, `[file]`, or `[default]`):

```
Effective transport configuration:
  backend: python-can  [default]
  interface: socketcan  [default]
  capture_limit: 2  [default]
  capture_timeout: 0.05  [default]
config file: /Users/you/.canarchy/config.toml  [not found]
```

Use `--json` for scripted inspection:

```bash
canarchy config show --json | jq .data.backend
```
