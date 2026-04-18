# Getting Started

This guide walks through the fastest way to see CANarchy produce familiar `candump`-style output.

## Install and Sync

Install project dependencies:

```bash
uv sync
```

## Making `canarchy` Available Directly

By default you invoke the CLI as `canarchy`. Two options let you drop the `uv run` prefix.

### Option A — Install as a global tool (recommended)

Installs `canarchy` on your PATH permanently. Works in any directory, any terminal, no activation step:

```bash
uv tool install --editable .
```

The `--editable` flag means source changes take effect immediately without reinstalling. Verify it worked:

```bash
which canarchy
canarchy --version
```

To uninstall later: `uv tool uninstall canarchy`

### Option B — Activate the project virtualenv

Activates `.venv` for the current shell session. `canarchy` is on PATH until you close the terminal or run `deactivate`:

```bash
source .venv/bin/activate
canarchy --version
```

Useful if you want the venv active for other tools in the same session. Pair with [direnv](https://direnv.net/) to activate automatically on `cd` into the project directory.

---

The rest of this guide assumes `canarchy` is available directly. Prefix commands with `uv run` if you have not done either step above.

## Live Candump with Software Loopback

For a local send-and-receive loop across two terminals, use the `python-can` backend with
`udp_multicast`. The `virtual` interface is in-process only and will not deliver frames
between separate terminal sessions.

On macOS you may need to add a multicast route first:

```bash
sudo route add -net 239.0.0.0/8 -interface lo0
```

### Persistent config (recommended)

Create `~/.canarchy/config.toml` so you never need to repeat the backend settings:

```toml
[transport]
backend = "python-can"
interface = "udp_multicast"
```

Then every `canarchy` command in any terminal picks up these settings automatically.

### Per-session config

If you prefer not to write a config file, export the variables at the top of each terminal session:

```bash
export CANARCHY_TRANSPORT_BACKEND=python-can
export CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast
```

### Run the demo

In one terminal, start a live candump capture:

```bash
canarchy capture 239.0.0.1 --candump
```

This command stays open and keeps printing frames until you interrupt it with `Ctrl+C`.

In another terminal, send a frame:

```bash
canarchy send 239.0.0.1 0x123 11223344 --json
```

The capture terminal should print a line like:

```text
(1713369600.000000) 239.0.0.1 123#11223344
```

## Structured Capture Output

If you want machine-readable output instead of a terminal-oriented dump view, use JSON.

```bash
canarchy capture can0 --json
```

Use `--candump` for operator-friendly live traffic watching on a real backend. Use `--json` or `--jsonl` for scripting and automation.

## Read an Existing Candump File

CANarchy can operate on standard timestamped candump log files.

Summarize a capture:

```bash
canarchy stats tests/fixtures/sample.candump --json
```

Filter for a specific arbitration ID:

```bash
canarchy filter tests/fixtures/sample.candump 'id==0x18FEEE31' --json
```

Replay a capture with deterministic timing:

```bash
canarchy replay tests/fixtures/sample.candump --rate 1.0 --json
```

## Supported Candump Forms

Current supported candump text forms include:

* classic frames: `123#11223344`
* remote frames: `123#R`
* CAN FD frames: `123##31122334455667788`
* error frames using a CAN error-flagged identifier such as `20000080#0000000000000000`

For the full current command surface, see the [Command Spec](command_spec.md).
