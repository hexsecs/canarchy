# Getting Started

This guide walks through the fastest way to see CANarchy produce familiar `candump`-style output.

## Install

CANarchy targets Python 3.12 or newer. Pick the install path that matches your use case.

### From PyPI (recommended for users)

```bash
pipx install canarchy            # isolated, on PATH everywhere
# or
pip install --user canarchy      # fallback if pipx is unavailable
```

Confirm the install:

```bash
canarchy --version
canarchy doctor --text
```

`canarchy doctor` runs eight offline health checks (Python, `python-can`, transport backend, caches, config file, MCP server) — every check green means the environment is ready.

### From source (development)

CANarchy uses `uv` for environment, dependency, and packaging workflows.

```bash
uv sync                          # create .venv, install everything
```

Then pick one of:

* **Install as a global tool** (no `uv run` prefix needed afterwards):

  ```bash
  uv tool install --editable .
  ```

  Source edits take effect without reinstalling. Uninstall later with `uv tool uninstall canarchy`.

* **Activate the project virtualenv** for the current shell session:

  ```bash
  source .venv/bin/activate
  ```

  Pair with [direnv](https://direnv.net/) to activate automatically on `cd`.

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

A fully commented sample configuration file is available at [`docs/examples/config.toml`](examples/config.toml). Copy it to `~/.canarchy/config.toml` and uncomment the keys you want to set.

### Check the local environment

`canarchy doctor` runs a battery of fast, offline health checks (Python version, `python-can` import, transport backend, cache writability, opendbc cache, MCP server, config file). Run it before reporting bugs:

```bash
canarchy doctor --text
```

Each check shows `[OK]`, `[WARN]`, or `[FAIL]` and includes a copy-pasteable remediation hint for non-ok results.

### Install shell completion

Tab-completion scripts for `bash`, `zsh`, and `fish` are emitted by the `completion` subcommand. Pick the snippet for your shell:

```bash
# bash
eval "$(canarchy completion bash)"            # one-off in current shell
canarchy completion bash > ~/.bash_completion.d/canarchy   # persistent

# zsh
eval "$(canarchy completion zsh)"             # one-off in current shell
canarchy completion zsh > ~/.zsh/completions/_canarchy && compinit

# fish
canarchy completion fish | source             # one-off in current shell
canarchy completion fish > ~/.config/fish/completions/canarchy.fish
```

The scripts complete the top-level subcommands and the most common flags (`--json`, `--jsonl`, `--text`, `--file`, `--dbc`, `--max-frames`, `--seconds`, `--offset`, `--ack-active`, `--log-level`, `--quiet`).

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
default_interface = "239.0.0.1"
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

If `default_interface` is configured, you can omit the repeated channel:

```bash
canarchy send 0x123 11223344 --json
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

## Analyze CANdid Dataset Files

The [CANdid dataset](https://doi.org/10.25909/29068553) (VehicleSec 2025) provides candump-format CAN logs from 10 passenger vehicles.

Replay the default CANdid catalog stream directly from the remote provider without downloading the full file first:

```bash
canarchy datasets replay catalog:candid --dry-run --json
canarchy datasets replay catalog:candid --rate 1.0
canarchy datasets replay catalog:candid --format jsonl --rate 10 --max-frames 1000
canarchy datasets replay catalog:candid --list-files --json
canarchy datasets replay catalog:candid --file 2_indicator_CAN.log --rate 1000 --max-frames 10
```

Remote replay writes candump or JSONL records to stdout unless `--json` is requested. Use `--list-files --json` to inspect the embedded CANdid replay manifest, then pass `--file <id-or-name>` to select a specific replay file.

You can also pipe remote candump replay directly into stdin-aware analysis commands without creating a temporary file:

```bash
canarchy datasets replay catalog:candid --rate 1000 --max-frames 100 \
  | canarchy stats --file - --json
canarchy datasets replay catalog:candid --rate 1000 --max-frames 100 \
  | canarchy capture-info --file - --json
```

After downloading specific `*_CAN.log` files, use them directly with file-backed analysis commands:

Summarize a CANdid capture:
```bash
canarchy stats --file 2_driving_CAN.log --json
canarchy capture-info --file 2_driving_CAN.log --json
```

Filter for specific arbitration IDs:
```bash
canarchy filter 'id==0x123' --file 2_steering_CAN.log --json
```

Run reverse-engineering helpers:
```bash
canarchy re entropy --file 2_driving_CAN.log
canarchy re counters --file 2_driving_CAN.log
```

The catalog entry includes metadata about annotations, GPS traces, and video artifacts:
```bash
canarchy datasets inspect catalog:candid --json
```

## Discover More Public CAN Dataset Sources

CANarchy also documents curated dataset indexes, such as the PIVOT Auto dataset page, that point to multiple external CAN, CAN-FD, J1939, intrusion-detection, and automotive research datasets.

Search for the PIVOT Auto catalog entry:

```bash
canarchy datasets search pivot
canarchy datasets inspect catalog:pivot-auto-datasets --json
```

The PIVOT entry is an index, not a directly replayable dataset. Follow the linked source pages for downloads, licenses, and file formats, then use the relevant CANarchy analysis workflow for the files you obtain.

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
