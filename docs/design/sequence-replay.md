# Design: `canarchy sequence replay` — YAML/JSON multi-message coordinated transmit

## Background

Issue #362. Enables scripted, multi-message CAN transmit scenarios defined in a
YAML or JSON sequence file. Each step specifies a delay before sending and one or
more DBC-encoded frames, supporting coordinated bus simulations and regression tests
against hardware.

## Requirements (EARS)

### Sequence file format

**REQ-SEQ-01** WHEN a sequence file is a JSON or YAML document, the system SHALL
accept either a bare list of steps or a dict with a top-level `steps` key.

**REQ-SEQ-02** WHEN a top-level `dbc` key is present, the system SHALL use it as
the default DBC for all frames in the sequence.

**REQ-SEQ-03** WHEN a step contains a `dbc` key, the system SHALL use it as the
fallback for frames in that step, overriding the top-level DBC.

**REQ-SEQ-04** WHEN a frame contains a `dbc` key, the system SHALL use it for that
frame, overriding step- and file-level fallbacks.

**REQ-SEQ-05** WHEN no DBC is resolvable for a frame, the system SHALL raise
`SEQUENCE_ENCODE_ERROR`.

**REQ-SEQ-06** WHEN a frame `id` is a hex string (e.g. `"0x18FEEE31"`), the system
SHALL parse it as a hexadecimal integer.

**REQ-SEQ-07** WHEN a frame `id` does not match any message in the DBC, the system
SHALL raise `SEQUENCE_ENCODE_ERROR` with a descriptive message.

**REQ-SEQ-08** WHEN a step `delay_ms` key is absent, the system SHALL default to 0.

**REQ-SEQ-09** WHEN a `signals` dict uses `padding=True` semantics, the system SHALL
allow partial signal specification (unspecified signals default to 0).

### Timing and rate

**REQ-SEQ-10** WHEN `--rate` is provided, the system SHALL compute effective delay as
`delay_ms / rate` milliseconds before each step.

**REQ-SEQ-11** WHEN `--rate` is zero, negative, non-finite, or NaN, the system SHALL
reject the argument with error code `INVALID_RATE`.

**REQ-SEQ-12** WHEN `--loop` is set, the system SHALL repeat the full sequence
indefinitely until interrupted with SIGINT (Ctrl-C).

### Transmission modes

**REQ-SEQ-13** WHEN no `--interface` is given, the system SHALL return a plan
with `mode: plan` and no transport is opened.

**REQ-SEQ-14** WHEN `--interface` and `--dry-run` are given, the system SHALL return
`mode: dry_run`, include the interface in the response, and emit an
`ACTIVE_TRANSMIT_DRY_RUN` warning without opening a transport.

**REQ-SEQ-15** WHEN `--interface` is given without `--dry-run`, the system SHALL
transmit all frames in sequence order with inter-step delays and return `mode: active`.

**REQ-SEQ-16** WHEN live transmission is requested, the system SHALL enforce
active-transmit safety (`--ack-active` or operator confirmation).

### Output

**REQ-SEQ-17** WHEN `--json` is used, the system SHALL return one event of type
`sequence_step` per step, each containing `step`, `delay_ms`, `frame_count`, and a
`frames` list with `frame_id`, `frame_id_hex`, `data` (hex), `message_name`,
and `is_extended_id`.

**REQ-SEQ-18** WHEN `--jsonl` is used, the system SHALL emit one JSON line per step
event.

### DBC provider

**REQ-SEQ-19** WHEN a DBC value is a provider reference (e.g. `opendbc:toyota`),
the system SHALL resolve it through the DBC provider registry before loading.

### MCP

**REQ-SEQ-20** The `sequence_replay` MCP tool SHALL accept `file`, `interface`,
`rate`, `loop`, `ack_active`, and `dry_run` parameters.

**REQ-SEQ-21** WHEN `ack_active` is not `true` in an MCP call, the system SHALL
return `ACTIVE_TRANSMIT_REQUIRES_ACK`.

## Architecture

### New module: `canarchy/sequence.py`

- `SequenceError` — exception for load/encode failures
- `FrameSpec(frame_id, signals, dbc, is_extended_id)` — parsed frame
- `SequenceStep(delay_ms, frames, dbc)` — one timing step
- `SequenceFile(steps, dbc)` — top-level sequence
- `load_sequence(path) -> SequenceFile` — parse YAML/JSON
- `encode_frame(frame, fallback_dbc) -> (frame_id, bytes, is_extended, msg_name)`
- `encode_sequence(seq) -> list[step_dict]` — pre-encode all steps

### Changes to `cli.py`

- `SEQUENCE_COMMANDS = {"sequence replay"}` added
- `ACTIVE_TRANSMIT_COMMANDS` extended with `"sequence replay"`
- `IMPLEMENTED_COMMANDS` extended with `SEQUENCE_COMMANDS`
- `sequence` subparser with `replay` sub-subparser added after `replay` parser
- `active_transmit_preflight_warning()` / `active_transmit_confirmation_prompt()` extended
- `validate_args()` extended with rate check for `sequence replay`
- `sequence_payload()` added immediately before `session_payload()`
- `build_result()` dispatch extended with `elif args.command in SEQUENCE_COMMANDS`

### Changes to `mcp_server.py`

- `sequence_replay` tool definition added to `_TOOLS`
- `"sequence_replay"` added to `_ACTIVE_TRANSMIT_TOOLS`
- `case "sequence_replay"` added to `_tool_to_argv()`
