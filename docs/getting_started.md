# Getting Started

This guide walks through the fastest way to see CANarchy produce familiar `candump`-style output.

## Install and Sync

Install project dependencies:

```bash
uv sync
```

Confirm the CLI is available:

```bash
uv run canarchy --help
```

## Live Candump with Software Loopback

For a local send-and-receive loop across two terminals, use the `python-can` backend with
`udp_multicast`. The `virtual` interface is in-process only and will not deliver frames
between separate terminal sessions.

On macOS you may need to add a multicast route first:

```bash
sudo route add -net 239.0.0.0/8 -interface lo0
```

In one terminal, start a live candump capture:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast \
uv run canarchy capture 239.0.0.1 --candump
```

This command stays open and keeps printing frames until you interrupt it with `Ctrl+C`.

In another terminal, send a frame:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast \
uv run canarchy send 239.0.0.1 0x123 11223344 --json
```

The capture terminal should print a line like:

```text
(1713369600.000000) 239.0.0.1 123#11223344
```

## Structured Capture Output

If you want machine-readable output instead of a terminal-oriented dump view, use JSON.

```bash
uv run canarchy capture can0 --json
```

Use `--candump` for operator-friendly live traffic watching on a real backend. Use `--json` or `--jsonl` for scripting and automation.

## Read an Existing Candump File

CANarchy can operate on standard timestamped candump log files.

Summarize a capture:

```bash
uv run canarchy stats tests/fixtures/sample.candump --json
```

Filter for a specific arbitration ID:

```bash
uv run canarchy filter tests/fixtures/sample.candump 'id==0x18FEEE31' --json
```

Replay a capture with deterministic timing:

```bash
uv run canarchy replay tests/fixtures/sample.candump --rate 1.0 --json
```

## Supported Candump Forms

Current supported candump text forms include:

* classic frames: `123#11223344`
* remote frames: `123#R`
* CAN FD frames: `123##31122334455667788`
* error frames using a CAN error-flagged identifier such as `20000080#0000000000000000`

For the full current command surface, see the [Command Spec](command_spec.md).
