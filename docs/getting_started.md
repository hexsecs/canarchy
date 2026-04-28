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

## Live Capture

CANarchy defaults to the **python-can** backend with **SocketCAN**, so on Linux with a configured CAN interface you can start capturing immediately — no config file needed:

```bash
canarchy capture can0 --candump
```

This command stays open and prints frames in candump format until you interrupt it with `Ctrl+C`.

Use `--json` or `--jsonl` for machine-readable output:

```bash
canarchy capture can0 --jsonl
```

### Verify your active configuration

```bash
canarchy config show
```

This prints each setting along with whether it came from a config file, an environment variable, or the built-in default.

---

## Software Loopback (No Hardware)

For a local send-and-receive loop across two terminals without real hardware, use the
`udp_multicast` interface. The `virtual` interface is in-process only and will not deliver
frames between separate terminal sessions.

On macOS you may need to add a multicast route first:

```bash
sudo route add -net 239.0.0.0/8 -interface lo0
```

Set `udp_multicast` in `~/.canarchy/config.toml`:

```toml
[transport]
backend = "python-can"
interface = "udp_multicast"
```

Or export for the current session only:

```bash
export CANARCHY_PYTHON_CAN_INTERFACE=udp_multicast
```

In one terminal, start a live candump capture:

```bash
canarchy capture 239.0.0.1 --candump
```

In another terminal, send a frame:

```bash
canarchy send 239.0.0.1 0x123 11223344 --json
```

The capture terminal should print a line like:

```text
(1713369600.000000) 239.0.0.1 123#11223344
```

### Offline / scaffold mode

To run CANarchy without any CAN interface (for demos, testing, or CI), force the scaffold backend:

```bash
export CANARCHY_TRANSPORT_BACKEND=scaffold
canarchy capture can0 --json   # returns pre-recorded fixture frames
```

Or set it persistently in `~/.canarchy/config.toml`:

```toml
[transport]
backend = "scaffold"
```

## Read an Existing Candump File

CANarchy can operate on standard timestamped candump log files.

Summarize a capture:

```bash
canarchy stats --file tests/fixtures/sample.candump --json
```

Filter for a specific arbitration ID:

```bash
canarchy filter 'id==0x18FEEE31' --file tests/fixtures/sample.candump --json
```

Replay a capture with deterministic timing:

```bash
canarchy replay --file tests/fixtures/sample.candump --rate 1.0 --json
```

## Discover and Use DBC Files

CANarchy can work with local DBC files or provider-backed refs.

Search the optional opendbc catalog:

```bash
canarchy dbc cache refresh --provider opendbc
canarchy dbc search toyota --provider opendbc --limit 5 --json
```

Decode using a provider ref instead of a local file path:

```bash
canarchy decode --file tests/fixtures/sample.candump --dbc opendbc:toyota_tnga_k_pt_generated --json
```

Structured output for `decode`, `encode`, and `dbc inspect` includes a `data.dbc_source` object so you can see which local or provider-backed DBC resolution was used.

## Supported Candump Forms

Current supported candump text forms include:

* classic frames: `123#11223344`
* remote frames: `123#R`
* CAN FD frames: `123##31122334455667788`
* error frames using a CAN error-flagged identifier such as `20000080#0000000000000000`

For the full current command surface, see the [Command Spec](command_spec.md).

For a complete list of supported python-can interface types and per-adapter setup instructions, see [Backends & Interfaces](backends.md).
