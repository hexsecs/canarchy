# Verify a Vector interface in 30 seconds

## Goal

Confirm that CANarchy can use python-can's `vector` backend with Vector VN/VX hardware in a controlled lab setup.

This recipe validates configuration and live device access. It does not prove a target ECU is safe to transmit to.

## Prerequisites

* Vector XL Driver Library installed.
* Vector hardware connected to a terminated CAN bus or loopback test setup.
* The Vector application/channel mapping configured with Vector tooling.

## Configure

Persist the backend and default channel in `~/.canarchy/config.toml`:

```toml
[transport]
backend = "python-can"
interface = "vector"
default_interface = "0"
```

Or use environment variables for one shell:

```bash
export CANARCHY_TRANSPORT_BACKEND=python-can
export CANARCHY_PYTHON_CAN_INTERFACE=vector
export CANARCHY_DEFAULT_INTERFACE=0
```

Replace `0` with the channel or application channel that python-can should open in your Vector setup.

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

`doctor` only checks that the python-can Vector interface module is importable. It does not open the adapter, check Vector application mappings, or validate bus wiring.

A successful `capture` proves CANarchy could open the configured Vector channel. Seeing frames proves the bus is live and the bitrate/channel are plausible.

## Troubleshooting

* `python_can_interface_dependency` warns: install or repair the Vector XL Driver Library and confirm the active Python environment can import python-can's Vector backend.
* `TRANSPORT_UNAVAILABLE`: check the application/channel mapping, whether Vector hardware is assigned to another application, and whether another tool owns the channel.
* No frames: verify bitrate, termination, transceiver power, and whether the attached bus is expected to be silent.
