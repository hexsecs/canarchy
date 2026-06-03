# Backends & Interfaces

CANarchy uses **python-can** as its live transport layer. This page explains how to choose and configure a transport backend, which interface types are available, and how to verify what is in effect.

Important boundary: the transport backend selection applies to transport-facing commands such as `capture`, `send`, `generate`, and `gateway`, and also to protocol commands when they explicitly accept an interface, such as `j1939 monitor <interface>`, `uds scan <interface>`, and `uds trace <interface>`. Sample/reference providers are still used where a command does not yet have a complete live execution path or when the deterministic scaffold backend is selected.

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
| Device or port within that type | `channel` | positional CLI argument or `[transport].default_interface` / `CANARCHY_DEFAULT_INTERFACE` | `can0`, `PCAN_USBBUS1`, `0` |

Example: SocketCAN on Linux, interface `can0`:

```bash
canarchy capture can0   # channel = can0, interface type from config
```

To avoid repeating the same channel on every command, configure a default CAN interface:

```toml
[transport]
default_interface = "can0"
```

Then commands that accept one CAN interface can omit it:

```bash
canarchy capture
canarchy send 0x123 11223344 --json
```

An explicit command-line interface still wins over the configured default.

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

The table below covers common python-can interface types. CANarchy passes the configured `interface` value to `python_can.Bus(channel=<channel>, interface=<interface>)`, so the live hardware capability comes from python-can and the vendor driver/runtime installed on the host.

| Interface name | Hardware / use case | OS | Driver or dependency | Example channel |
|---|---|---|---|---|
| `socketcan` | Linux SocketCAN — real hardware through kernel drivers, `vcan` virtual interfaces, and many USB adapters | Linux | Kernel SocketCAN support plus device driver | `can0`, `vcan0` |
| `virtual` | python-can in-process virtual bus | Any | `python-can` only | `canarchy-test` |
| `udp_multicast` | UDP multicast virtual bus visible across processes and hosts | Any | `python-can` only; multicast routing/firewall must allow traffic | `239.0.0.1` |
| `pcan` | PEAK PCAN-USB and PCAN-PCIe adapters | Windows, Linux, macOS | PEAK PCAN driver/API | `PCAN_USBBUS1` |
| `vector` | Vector VN/VX-series hardware | Windows | Vector XL Driver Library | `0`, `1`, or configured application channel |
| `kvaser` | Kvaser USB/PCIe adapters | Windows, Linux | Kvaser CANlib SDK/runtime | `0`, `1`, or channel name |
| `ixxat` | HMS IXXAT adapters | Windows | IXXAT VCI driver/runtime | adapter-specific channel |
| `slcan` | Serial-line CAN adapters using ASCII CAN over USB/UART | Any | Serial device access; often `python-can` plus OS serial permissions | `/dev/ttyACM0`, `COM3` |
| `cantact` | CANtact / candleLight USB devices | Any | libusb / candleLight support per OS | device-specific channel |
| `gs_usb` | Geschwister Schneider / candleLight USB devices through kernel driver | Linux | Linux `gs_usb` kernel driver | `can0` or USB channel |
| `canalystii` | USB-CAN Analyzer II adapters | Any | python-can CANalyst-II dependencies and vendor library where required | `0` |
| `usb2can` | 8devices USB2CAN | Linux | Kernel driver / SocketCAN-compatible setup | `can0` |
| `neovi` | Intrepid Control Systems neoVI hardware | Windows | Intrepid driver/runtime | device-specific channel |
| `nican` | National Instruments NI-CAN | Windows | NI-CAN runtime | `CAN0` |
| `nixnet` | National Instruments NI-XNET | Windows | NI-XNET runtime | interface alias |
| `remote` | python-can remote server over TCP | Any | Reachable python-can remote server | server endpoint |

!!! note "Full and up-to-date list"
    The canonical reference for all supported interfaces, per-interface configuration options, and required driver packages is the
    [python-can documentation — Interfaces](https://python-can.readthedocs.io/en/stable/interfaces.html).
    CANarchy does not restrict which interfaces are available. If python-can supports an interface and its runtime is installed, configure the python-can interface name with `[transport].interface` or `CANARCHY_PYTHON_CAN_INTERFACE` and pass the channel as the command interface.

!!! warning "Validation scope"
    `canarchy doctor` is intentionally offline. For configured vendor interfaces such as `pcan`, `vector`, `kvaser`, `ixxat`, `neovi`, `nican`, `nixnet`, and `canalystii`, it checks whether the corresponding python-can interface module is importable and gives a driver/runtime hint when it is not. It does not open a device, claim a CAN transceiver is wired correctly, or validate bus traffic. Use the cookbook recipes below for live lab verification.

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

### PCAN-USB / PCAN-PCIe

```toml
[transport]
backend = "python-can"
interface = "pcan"
default_interface = "PCAN_USBBUS1"
```

```bash
canarchy doctor --text
canarchy capture PCAN_USBBUS1 --candump
```

Install the PEAK PCAN driver/API for the host OS first. On Linux, SocketCAN may also expose PEAK devices as `can0`; use `socketcan` instead of `pcan` if you intentionally choose the kernel SocketCAN path.

### Vector VN/VX hardware

```toml
[transport]
backend = "python-can"
interface = "vector"
default_interface = "0"
```

```bash
canarchy doctor --text
canarchy capture 0 --candump
```

Install the Vector XL Driver Library and configure the application/channel mapping with Vector tooling before opening the bus. Vector hardware access is normally Windows-first.

### Kvaser USB / PCIe hardware

```toml
[transport]
backend = "python-can"
interface = "kvaser"
default_interface = "0"
```

```bash
canarchy doctor --text
canarchy capture 0 --candump
```

Install Kvaser CANlib before using the `kvaser` backend. On Linux, some Kvaser devices can also be exposed through SocketCAN; choose `socketcan` when you want to use the kernel `can0` path.

### IXXAT, neoVI, NI-CAN, NI-XNET, and other vendor backends

Configure the python-can interface name and vendor-specific channel exactly as python-can documents it. Examples:

```toml
[transport]
backend = "python-can"
interface = "ixxat"      # or neovi, nican, nixnet, canalystii
default_interface = "0"  # replace with the vendor channel name
```

Then run:

```bash
canarchy doctor --text
canarchy capture --candump
```

`doctor` can catch missing importable python-can interface modules for several vendor backends, but the authoritative hardware setup remains the vendor driver documentation plus python-can's interface page.

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
canarchy doctor --text
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

`config show` reports the effective configuration and source of each value. `doctor` adds offline dependency checks, including a vendor-backend import check when `[transport].interface` is set to a supported hardware backend. A successful `doctor` result means the configured software stack is importable, not that hardware was opened.

For short live verification flows, see:

* [Verify a PCAN interface in 30 seconds](cookbook/verify-pcan-interface.md)
* [Verify a Vector interface in 30 seconds](cookbook/verify-vector-interface.md)
* [Verify a Kvaser interface in 30 seconds](cookbook/verify-kvaser-interface.md)
