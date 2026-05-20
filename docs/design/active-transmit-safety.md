# Design Spec: Active-Transmit Safety Model

## Document Control

| Field | Value |
|-------|-------|
| Status | Planned |
| Command surface | `canarchy send`, `generate`, `gateway`, `replay`, `uds scan`, `fuzz payload`, `fuzz replay`, `fuzz arbitration-id` |
| Primary area | CLI, transport, safety |
| Related specs | [`docs/design/active-command-safety.md`](active-command-safety.md), [`docs/design/transport-core-commands.md`](transport-core-commands.md), [`docs/design/generate-command.md`](generate-command.md) |

## Goal

Define the safety controls that every active-transmit command in
CANarchy must honour, including the placeholder `fuzz` command tree
that was removed in #292 pending this design. The model layers
on top of the existing `--ack-active` preflight gate (`active-command-safety.md`)
with five additional controls: rate caps, target allowlists, a
kill-switch, a `--dry-run` planning mode, and run-id provenance on
every emitted event.

## User-Facing Motivation

Active CAN transmission can disturb a live vehicle or test rig. The
existing acknowledgement gate is enough for one-shot `send` and
`generate` calls, but high-rate or long-running workflows
(`fuzz payload`, `gateway`, mutated `replay`) need finer-grained
controls so a misconfigured invocation cannot saturate the bus,
target the wrong arbitration ID space, or continue past an operator
interrupt. Agents calling these workflows over MCP need an explicit
opt-in token so a confused agent cannot accidentally invoke an
active workflow.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-ATS-01` | Ubiquitous | The system shall treat `send`, `generate`, `gateway`, `replay`, `uds scan`, `fuzz payload`, `fuzz replay`, and `fuzz arbitration-id` as active-transmit commands and apply the controls in this spec. |
| `REQ-ATS-02` | Event-driven | When an active-transmit command is invoked, the system shall enforce the existing `active-command-safety.md` acknowledgement gate before applying any control in this spec. |
| `REQ-ATS-03` | Optional feature | Where `--ack-active` is supplied non-interactively (stdin is not a TTY), the system shall accept the flag itself as the acknowledgement and skip the interactive `YES` prompt. |
| `REQ-ATS-04` | Event-driven | When an active-transmit command begins transmission, the system shall stamp every emitted event with a stable `run_id` field derived from a cryptographically random 128-bit identifier. |
| `REQ-ATS-05` | Optional feature | Where `--rate <hz>` is supplied or implied by command defaults, the system shall enforce a per-command rate cap measured in frames per second. |
| `REQ-ATS-06` | Unwanted behaviour | If the rate cap would be exceeded by the requested workload, the system shall return a structured error with code `ACTIVE_TRANSMIT_RATE_EXCEEDED` and exit code `1` before any frame is transmitted. |
| `REQ-ATS-07` | Optional feature | Where `--targets <path>` is supplied (or `[safety].targets_file` is set in `~/.canarchy/config.toml`), the system shall load an allowlist of arbitration IDs and refuse to transmit frames whose ID is not present. |
| `REQ-ATS-08` | Unwanted behaviour | If a target allowlist is in force and the requested transmission targets an ID outside the allowlist, the system shall return a structured error with code `ACTIVE_TRANSMIT_TARGET_BLOCKED` and exit code `1` before any frame is transmitted. |
| `REQ-ATS-09` | State-driven | While an active-transmit command is running, the system shall stop transmission cleanly when SIGINT is received, emitting a final `alert` event with reason `KILL_SWITCH_TRIGGERED`. |
| `REQ-ATS-09a` | State-driven | While an active-transmit command is running **and stdin was a live pipe at command start and has not yet reached EOF**, the system shall also stop cleanly when stdin transitions to EOF. |
| `REQ-ATS-09b` | Unwanted behaviour | If stdin is a TTY, closed, or already at EOF at command start (for example a CI runner that supplies `stdin=/dev/null`, an MCP subprocess, or a cron job), the system shall ignore stdin EOF as a kill condition so non-interactive automation can run to completion. |
| `REQ-ATS-10` | Optional feature | Where `--dry-run` is supplied, the system shall plan the transmission and emit the would-send frames as JSONL events to stdout without opening a transport, and the response shall carry the structured warning code `ACTIVE_TRANSMIT_DRY_RUN`. |
| `REQ-ATS-11` | Optional feature | Where the command is invoked via the MCP server, the system shall require an explicit `ack_active=true` argument in the tool call. |
| `REQ-ATS-12` | Unwanted behaviour | If an MCP active-transmit tool is invoked without `ack_active=true`, the system shall return a structured error with code `ACTIVE_TRANSMIT_REQUIRES_ACK` and exit code `1` without invoking the underlying command. |
| `REQ-ATS-13` | State-driven | While the MCP server is the caller, the system shall default `--dry-run` to true when the agent omits an explicit `dry_run` field, so safe planning is the default for agent-initiated active workflows. |
| `REQ-ATS-14` | Ubiquitous | The system shall keep machine-readable `stdout` output free of duplicated safety prompts; rate-cap, target-block, kill-switch, and dry-run signals shall appear in the canonical envelope's `warnings[]` or `errors[]` arrays, not as raw text. |
| `REQ-ATS-15` | Ubiquitous | The system shall record the active-transmit safety configuration (`require_active_ack`, rate cap default, target allowlist path, MCP dry-run default) in `canarchy config show` output with `[safety]` source attribution. |

## Command Surface

Existing active commands gain four shared flags:

```text
canarchy <active-command> [...] [--ack-active] [--rate <hz>] [--targets <path>] [--dry-run] [--run-id <uuid>]
```

Specific examples:

```text
canarchy send <interface> <frame-id> <hex-data> [--ack-active] [--rate <hz>] [--targets <path>] [--dry-run]
canarchy generate <interface> [--id <hex|R>] [--count <n>] [--rate <hz>]
                              [--ack-active] [--targets <path>] [--dry-run] [--run-id <uuid>]
canarchy gateway <src> <dst> [--bidirectional] [--rate <hz>]
                             [--ack-active] [--targets <path>] [--dry-run] [--run-id <uuid>]
canarchy fuzz payload <iface> --id <hex> --strategy {bitflip,random,boundary}
                              --rate <hz> --max <n> [--ack-active] [--dry-run] [--run-id <uuid>]
canarchy fuzz replay --file <capture> --strategy {timing,payload-bitflip}
                     [--rate <hz>] [--ack-active] [--dry-run] [--run-id <uuid>]
canarchy fuzz arbitration-id <iface> --range <start>:<end> --rate <hz>
                              [--extended] [--ack-active] [--dry-run] [--run-id <uuid>]
```

`--gap` on `generate` remains the canonical inter-frame spacing knob;
`--rate <hz>` is the new safety cap and overrides any implied rate
that would exceed it. Both flags coexist for backwards compatibility.

## Responsibilities And Boundaries

In scope:

* shared safety controls applied uniformly across every active-transmit command
* a single source of truth for the gate (`require_active_ack`, rate cap default, target allowlist) in `~/.canarchy/config.toml`
* MCP-side opt-in token that is independent of the CLI `--ack-active` prompt
* dry-run mode that planning agents can use to inspect a workflow before authorising it
* `run_id` provenance so post-mortem analysis can match an emitted frame to the invocation that produced it

Out of scope:

* passive commands (`capture`, `uds trace`, `filter`, `stats`) — these never transmit and do not need the gate
* offensive tooling beyond what the listed active commands already do (e.g. UDS write-by-DID, ECU reprogramming) — those would need their own spec extending this one
* hardware-level interlocks (relay-cut bus isolation, ignition lockout) — outside the CANarchy process boundary

## Data Model

### Target allowlist file

TOML format, located at the path supplied via `--targets <path>` or
`[safety].targets_file`.

```toml
[allowlist]
description = "Lab bench arbitration IDs"
ids = ["0x100", "0x200-0x2FF", "0x18FEEE31"]
extended = true   # apply to 29-bit IDs
default = "block" # block any ID not listed
```

Ranges use a single hyphen with inclusive bounds. IDs may be supplied
as hex (`0x100`) or decimal (`256`). When `extended = false`, the
allowlist applies only to 11-bit IDs.

### `run_id` field

Every active-transmit-emitted event (`frame`, `alert`, summary
`active_transmit` event) carries:

```json
{ "run_id": "0193bf6e-1e3e-7a8c-b6b1-d0e7d3a8f4f0" }
```

`run_id` is also reported in the final summary envelope under
`data.run_id`.

## Output Contracts

### `--dry-run`

Planning mode. The command emits JSONL events with `event_type:
"frame"` and an additional `payload.frame.dry_run = true` field per
frame that would have been transmitted. The summary envelope carries
`warnings: ["ACTIVE_TRANSMIT_DRY_RUN: <n> frames planned; no transport opened."]`
and `data.dry_run = true`. No transport is opened; rate-cap and
allowlist checks still run.

### Kill switch

The kill switch fires on SIGINT unconditionally and on stdin EOF only
when stdin was a live pipe at command start. When triggered, the
system emits a final `alert` event with
`payload.reason = "KILL_SWITCH_TRIGGERED"` and `payload.frames_sent =
<count>`, then exits with `EXIT_PARTIAL_SUCCESS` (4). The canonical
summary still includes `data.frames_sent` and `data.run_id`.

A pipe is considered "live at command start" when `sys.stdin` is not
a TTY and `select.select([sys.stdin], [], [], 0)` does not already
report EOF at startup. In any other case (TTY input, closed pipe,
`stdin=/dev/null`, MCP subprocess) stdin EOF is silently ignored so
long-running commands (`gateway`, `replay`) can still run to
completion in non-interactive contexts. SIGINT remains the universal
stop signal.

### Rate-cap violations

If the requested workload exceeds the configured rate cap, the
system fails fast with `ACTIVE_TRANSMIT_RATE_EXCEEDED` before opening
the transport. No frames are sent.

### Target-allowlist violations

If a planned frame's ID is outside the allowlist, the system fails
fast with `ACTIVE_TRANSMIT_TARGET_BLOCKED` and reports the blocked
IDs in `errors[0].detail.blocked_ids`.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `ACTIVE_ACK_REQUIRED` | existing — see `active-command-safety.md` | 1 |
| `ACTIVE_CONFIRMATION_DECLINED` | existing — see `active-command-safety.md` | 1 |
| `ACTIVE_TRANSMIT_RATE_EXCEEDED` | requested workload exceeds the configured rate cap | 1 |
| `ACTIVE_TRANSMIT_TARGET_BLOCKED` | requested ID is outside the active target allowlist | 1 |
| `ACTIVE_TRANSMIT_REQUIRES_ACK` | MCP tool invoked without `ack_active=true` | 1 |
| `ACTIVE_TRANSMIT_INVALID_TARGETS` | `--targets <path>` was supplied but the file failed to parse or had no `ids` | 1 |
| `ACTIVE_TRANSMIT_INVALID_RUN_ID` | `--run-id <uuid>` was supplied but did not parse as a UUID | 1 |

Each error carries an actionable `hint` per the convention in
[`docs/event-schema.md`](../event-schema.md#hint-convention).

## Configuration Surface

`~/.canarchy/config.toml`:

```toml
[safety]
require_active_ack = false
targets_file = "~/labs/bench-allowlist.toml"

[safety.rate_cap]
default_hz = 200          # applied when no command-specific cap is configured
maximum_hz = 5000         # hard ceiling that even --rate cannot exceed
fuzz_payload_hz = 100     # per-command override
fuzz_replay_hz = 50
fuzz_arbitration_id_hz = 200
```

Environment overrides:

* `CANARCHY_REQUIRE_ACTIVE_ACK` — boolean
* `CANARCHY_ACTIVE_TARGETS_FILE` — path to the target allowlist
* `CANARCHY_ACTIVE_RATE_CAP_HZ` — overrides `[safety.rate_cap].default_hz`

`canarchy config show` shall report all of the above under
`data.safety` with the same source attribution it already uses for
transport keys.

## MCP Surface

The fuzz tools expose:

```json
{
  "name": "fuzz_payload",
  "inputSchema": {
    "type": "object",
    "required": ["interface", "id", "strategy", "ack_active"],
    "properties": {
      "interface": { "type": "string" },
      "id":        { "type": "string", "description": "hex CAN ID" },
      "strategy":  { "enum": ["bitflip", "random", "boundary"] },
      "rate":      { "type": "number", "description": "frames per second; capped by [safety.rate_cap]" },
      "max":       { "type": "integer" },
      "ack_active":{ "type": "boolean", "const": true },
      "dry_run":   { "type": "boolean", "default": true }
    }
  }
}
```

`ack_active=true` is the only acceptable value; omitting the field or
passing `false` returns `ACTIVE_TRANSMIT_REQUIRES_ACK`. `dry_run`
defaults to `true` so agent-initiated calls plan rather than
transmit; setting `dry_run=false` requires both `ack_active=true` and
the existing CLI safety controls to pass.

## Audit Of Existing Commands Against This Spec

| Command | `--ack-active` | Rate cap | Target allowlist | Kill switch | `--dry-run` | `run_id` | MCP `ack_active=true` |
|---------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `send` | ✓ | n/a (single frame) | gap | n/a | + | + | + |
| `generate` | ✓ | + | + | + | + | + | + |
| `gateway` | ✓ | + | + | + | + | + | + |
| `replay` | ✓ | + | + | + | ✓ | + | ✓ |
| `uds scan` | ✓ | + | + | + | + | + | + |
| `fuzz payload` | + | + | + | + | + | + | + |
| `fuzz replay` | + | + | + | + | + | + | + |
| `fuzz arbitration-id` | + | + | + | + | + | + | + |

Legend: ✓ already implemented; `+` to be added in the
implementation issues that follow; partial means the gate exists but
needs to extend to the new flags.

## Deferred Decisions

* whether `--rate` should be a hard ceiling (current proposal) or a soft target with backoff
* whether to expose target allowlists as a separate `canarchy safety targets` subcommand
* whether to ship a default `safety.targets.lab.toml` example file or leave it as an operator artefact
* SIGTERM handling — current proposal treats SIGINT and stdin EOF; SIGTERM is left to follow-up
* whether to record `run_id` in `canarchy session save` for full-session replay
