# Verify a PCAN interface in 30 seconds

## Goal

Confirm that CANarchy can use python-can's `pcan` backend with a PEAK PCAN adapter in a controlled lab setup.

This recipe validates configuration and live device access. It does not prove a target ECU is safe to transmit to.

## Prerequisites

* PEAK PCAN driver/API installed for your OS.
* A PCAN adapter connected to a terminated CAN bus or loopback test setup.
* The channel name known from PEAK tooling or python-can, for example `PCAN_USBBUS1`.

## Configure

Persist the backend and default channel in `~/.canarchy/config.toml`:

```toml
[transport]
backend = "python-can"
interface = "pcan"
default_interface = "PCAN_USBBUS1"
```

Or use environment variables for one shell:

```bash
export CANARCHY_TRANSPORT_BACKEND=python-can
export CANARCHY_PYTHON_CAN_INTERFACE=pcan
export CANARCHY_DEFAULT_INTERFACE=PCAN_USBBUS1
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

`doctor` only checks that the python-can PCAN interface module is importable. It does not open the adapter or validate bus wiring.

A successful `capture` proves CANarchy could open the configured PCAN channel. Seeing frames proves the bus is live and the bitrate/channel are plausible.

## Troubleshooting

* `python_can_interface_dependency` warns: install or repair the PEAK PCAN driver/API in the same environment that runs CANarchy.
* `TRANSPORT_UNAVAILABLE`: check the channel name, adapter connection, permissions, and whether another application owns the PCAN channel.
* No frames: verify bitrate, termination, transceiver power, and whether the attached bus is expected to be silent.
