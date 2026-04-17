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

## Quickest Candump View

CANarchy can render a `candump`-style live view from its default scaffolded transport.

Run:

```bash
uv run canarchy capture can0 --candump
```

Example output:

```text
(0.000000) can0 18FEEE31#11223344
(0.100000) can0 18F00431#AABBCCDD
```

Use this when you want a quick human-readable view without setting up a live interface.

## Live Candump on a Virtual CAN Bus

For a real local send-and-receive loop, use the `python-can` virtual backend.

In one terminal, start a live candump capture:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy capture vcan0 --candump
```

In another terminal, send a frame onto the same virtual channel:

```bash
CANARCHY_TRANSPORT_BACKEND=python-can \
CANARCHY_PYTHON_CAN_INTERFACE=virtual \
uv run canarchy send vcan0 0x123 11223344 --json
```

The capture terminal should print a line like:

```text
(0.000000) vcan0 123#11223344
```

## Structured Capture Output

If you want machine-readable output instead of a terminal-oriented dump view, use JSON.

```bash
uv run canarchy capture can0 --json
```

Use `--candump` for operator-friendly traffic watching. Use `--json` or `--jsonl` for scripting and automation.

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
