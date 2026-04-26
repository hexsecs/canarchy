# Design Spec: J1939 Bounded File Analysis

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp sessions`, `j1939 dm1` |
| Primary area | CLI, transport, protocol |
| Related specs | `docs/design/j1939-first-class-decoder.md`, `docs/design/j1939-expanded-workflows.md` |

## Goal

Add bounded-analysis controls to file-backed J1939 workflows so operators can inspect large captures predictably without forcing every command to scan the entire file.

## User-Facing Motivation

Large heavy-vehicle captures often contain millions of frames. Analysts need to ask scoped questions such as "show me the first 30 seconds" or "inspect only the first 10,000 frames" before committing to a full-file pass.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-J1939WIN-01` | Optional feature | Where a file-backed J1939 analysis command supports bounded analysis, the system shall accept `--max-frames <n>` to limit work to the first `<n>` frames in the capture. |
| `REQ-J1939WIN-02` | Optional feature | Where a file-backed J1939 analysis command supports bounded analysis, the system shall accept `--seconds <n>` to limit work to frames whose timestamps fall within the first `<n>` seconds of the capture window. |
| `REQ-J1939WIN-03` | Event-driven | When `j1939 decode`, `j1939 pgn`, `j1939 spn`, `j1939 tp sessions`, or `j1939 dm1` is invoked with bounded-analysis flags against a capture file, the system shall apply those bounds during file iteration rather than after a full-file read. |
| `REQ-J1939WIN-04` | Unwanted behaviour | If `--max-frames` is less than `1`, the system shall return a structured user error with code `INVALID_MAX_FRAMES`. |
| `REQ-J1939WIN-05` | Unwanted behaviour | If `--seconds` is negative, the system shall return a structured user error with code `INVALID_ANALYSIS_SECONDS`. |
| `REQ-J1939WIN-06` | Unwanted behaviour | If bounded-analysis flags are used with `j1939 decode --stdin`, the system shall return a structured user error with code `ANALYSIS_WINDOW_REQUIRES_FILE`. |
| `REQ-J1939WIN-07` | Performance | When `j1939 summary`, `j1939 dm1`, `j1939 faults`, `j1939 inventory`, or `j1939 compare` is invoked on a file larger than 50 MB without an explicit `--max-frames` or `--seconds` bound, the system shall automatically cap analysis at 500,000 frames and include a warning in the response instructing the operator to use `--max-frames` or `--seconds` to override. |

## Command Surface

```text
canarchy j1939 decode <capture> [--dbc <path|provider-ref>] [--max-frames <n>] [--seconds <n>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 pgn <pgn> --file <capture> [--dbc <path|provider-ref>] [--max-frames <n>] [--seconds <n>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 spn <spn> --file <capture> [--dbc <path|provider-ref>] [--max-frames <n>] [--seconds <n>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 tp sessions --file <capture> [--max-frames <n>] [--seconds <n>] [--json] [--jsonl] [--table] [--raw]
canarchy j1939 dm1 --file <capture> [--dbc <path|provider-ref>] [--max-frames <n>] [--seconds <n>] [--json] [--jsonl] [--table] [--raw]
```

## Responsibilities And Boundaries

In scope:

* frame-count bounds for file-backed J1939 analysis
* initial time-window bounds measured from the first parsed frame timestamp in the capture
* enforcing bounds while iterating over candump files

Out of scope:

* arbitrary later-window selection such as `--from` / `--to`
* sampling semantics such as every-Nth-frame selection
* bounded-analysis controls for live monitor or stdin workflows

## Data Model

The existing command result envelopes remain unchanged. Bounded-analysis flags affect which capture frames are inspected and therefore which events, observations, sessions, or messages appear in `data`.

## Output Contracts

All existing output modes remain available. `--json` and `--jsonl` continue to emit the same command-specific payload shapes as their unbounded counterparts, but only for the bounded capture slice.

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `INVALID_MAX_FRAMES` | `--max-frames` is less than `1` | 1 |
| `INVALID_ANALYSIS_SECONDS` | `--seconds` is negative | 1 |
| `ANALYSIS_WINDOW_REQUIRES_FILE` | bounded-analysis flags are used with `j1939 decode --stdin` | 1 |

## Deferred Decisions

* whether later-window selection should use `--from` / `--to` capture timestamps or relative offsets
* whether bounded-analysis metadata should be echoed explicitly in command payloads
* whether sampling controls should share this command surface or land as a separate follow-on feature
