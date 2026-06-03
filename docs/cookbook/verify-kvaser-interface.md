# Verify a Kvaser interface in 30 seconds

## Goal

Confirm that CANarchy can use python-can's `kvaser` backend with Kvaser USB or PCIe hardware in a controlled lab setup.

This recipe validates configuration and live device access. It does not prove a target ECU is safe to transmit to.

## Prerequisites

* Kvaser CANlib SDK/runtime installed.
* Kvaser hardware connected to a terminated CAN bus or loopback test setup.
* The channel index or name known from Kvaser tooling or python-can, commonly `0` for the first channel.

## Configure

Persist the backend and default channel in `~/.canarchy/config.toml`:

```toml
[transport]
backend = "python-can"
interface = "kvaser"
default_interface = "0"
```

Or use environment variables for one shell:

```bash
export CANARCHY_TRANSPORT_BACKEND=python-can
export CANARCHY_PYTHON_CAN_INTERFACE=kvaser
export CANARCHY_DEFAULT_INTERFACE=0
```

## Verify

Check the effective configuration and offline dependency status:

```bash
canarchy config show --text
canarchy doctor --text
```

Then open a bounded live capture. Press `Ctrl+C` after you see traffic:

```bash
canarchy capture --candump
```

If the bus is quiet, send only on a controlled loopback or bench bus:

```bash
canarchy send 0x123 11223344 --dry-run --json
canarchy send 0x123 11223344 --ack-active --json
```

## Interpreting Results

`doctor` only checks that the python-can Kvaser interface module is importable. It does not open the adapter, check CANlib channel state, or validate bus wiring.

A successful `capture` proves CANarchy could open the configured Kvaser channel. Seeing frames proves the bus is live and the bitrate/channel are plausible.

## Troubleshooting

* `python_can_interface_dependency` warns: install or repair Kvaser CANlib and confirm the active Python environment can import python-can's Kvaser backend.
* `TRANSPORT_UNAVAILABLE`: check the channel index/name, permissions, whether another application owns the Kvaser channel, and whether you should use `socketcan` instead on Linux.
* No frames: verify bitrate, termination, transceiver power, and whether the attached bus is expected to be silent.
