# Design Spec: Fuzz-Replay Culprit Identification

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Command surface | `canarchy fuzz identify` |
| Primary area | CLI, fuzzing, safety |
| Related specs | `docs/design/active-transmit-safety.md`, `docs/design/replay-command.md`, `docs/design/response-feedback-fuzz.md` |
| Issues | #464 |

## Goal

Add a safe, bounded, human-in-the-loop workflow for isolating the specific frame
(or minimal frame window) in a fuzz log or capture that produced an observed
effect — the analogue of CaringCaribou's `fuzzer identify` mode. CANarchy has
replay / fuzz / guided-fuzz primitives but no explicit narrowing workflow.

## User-Facing Motivation

After a fuzz campaign or a captured anomaly, the operator knows *that* some frame
in a log caused an effect (a warning light, a reset, a state change) but not
*which* one. Re-deriving that by hand is tedious and error-prone. `fuzz identify`
replays bisected windows of the log and, from the operator's effect/no-effect
observations, narrows the candidate set to a single culprit frame — and stays
automation-friendly by taking observations from flags or a file rather than
hidden interactive prompts.

## Requirements

| ID | Type | Requirement |
|----|------|-------------|
| `REQ-FZID-01` | Ubiquitous | The system shall provide `canarchy fuzz identify <log>` that loads a candump capture or a JSONL fuzz log / replay plan and bisects toward the culprit frame. |
| `REQ-FZID-02` | Ubiquitous | The narrowing engine shall be pure and deterministic: given the frame count and the recorded observations, it shall return the candidate range, the next window to replay, and a resolved culprit once converged. |
| `REQ-FZID-03` | Optional feature | Operators shall be able to mark observed effect / no-effect outcomes non-interactively via `--observe effect|no-effect` flags (repeatable) and/or a JSON `--observations` file. |
| `REQ-FZID-04` | Unwanted behaviour | The workflow shall not issue hidden interactive prompts in non-interactive mode; the only interactive element is the active-transmit `YES` confirmation, which is bypassable via `--ack-active` semantics. |
| `REQ-FZID-05` | Event-driven | When an interface is supplied and the search is unresolved, the system shall replay the next bisected window on the bus behind the active-transmit safety model (preflight warning, `--ack-active`). |
| `REQ-FZID-06` | Optional feature | Where `--dry-run` is supplied, or no interface is given, the system shall report the narrowing plan and next window without transmitting. |
| `REQ-FZID-07` | Ubiquitous | JSON output shall include the replayed/next frame window, the recorded observations, the candidate range and frames, the resolved culprit, a confidence value and rationale, and provenance (source, frame count, planned rounds). |
| `REQ-FZID-08` | Unwanted behaviour | If the log is missing, unreadable, or contains no replayable frames, the system shall return a structured error (`FUZZ_IDENTIFY_LOG_UNAVAILABLE` / `FUZZ_IDENTIFY_INVALID_LOG`) with exit code 1. |
| `REQ-FZID-09` | Unwanted behaviour | If an observation token is not effect/no-effect, or the observations file is not a JSON array, the system shall return a structured error with exit code 1. |
| `REQ-FZID-10` | Optional feature | Where `--max-window` is supplied and the next replay window exceeds it, the system shall refuse with `FUZZ_IDENTIFY_WINDOW_TOO_LARGE` (exit 1) rather than replay an over-large window. |
| `REQ-FZID-11` | Ubiquitous | `fuzz identify` shall be a CLI-only operator workflow and shall not be exposed as an MCP tool. |

## Command Surface

```text
canarchy fuzz identify <log> [--interface can0] [--observations FILE] [--observe effect|no-effect ...]
                       [--rate 100] [--max-window N] [--ack-active] [--dry-run] [--json|--jsonl|--text]
```

`<log>` is a candump capture or a JSONL fuzz log / replay plan (one CAN-frame
object per line, with top-level or `payload`-nested `arbitration_id` + `data`).

## Narrowing Model

The search maintains an inclusive candidate range `[lo, hi]` over the log's
frame indices, starting at the whole log. Each round replays the lower half
`[lo, mid]` (`mid = (lo + hi) // 2`); an `effect` observation keeps the lower
half (`hi = mid`), `no-effect` keeps the upper (`lo = mid + 1`). The search
resolves when `lo == hi`, in `ceil(log2(N))` rounds for a single culprit frame.
Confidence is `1 − (hi − lo) / (N − 1)` — `0.0` over the full log, `1.0` when
resolved. Observations beyond resolution are ignored. The engine assumes a
single causal frame whose presence in a replayed window reproduces the effect;
the candidate window is still reported when that assumption does not hold, so the
operator can inspect the minimal window directly.

## Responsibilities And Boundaries

In scope: log/plan/capture loading, the pure deterministic bisection engine,
non-interactive observation input, one-round-per-invocation replay behind the
active-transmit gate, and structured output with confidence/rationale/provenance.

Out of scope: automatic effect detection (the operator supplies observations);
multi-frame ddmin minimisation beyond a single-culprit bisection; mutation of
the log during replay (frames are replayed verbatim).

## Error Contracts

| Code | Trigger | Exit code |
|------|---------|-----------|
| `FUZZ_IDENTIFY_LOG_UNAVAILABLE` | log missing / unreadable | 1 |
| `FUZZ_IDENTIFY_INVALID_LOG` | log parsed to zero frames | 1 |
| `FUZZ_IDENTIFY_INVALID_OBSERVATION` | observation token not effect/no-effect | 1 |
| `FUZZ_IDENTIFY_INVALID_OBSERVATIONS` | observations file not a JSON array | 1 |
| `FUZZ_IDENTIFY_OBSERVATIONS_UNAVAILABLE` | observations file unreadable | 1 |
| `FUZZ_IDENTIFY_WINDOW_TOO_LARGE` | next window exceeds `--max-window` | 1 |
| `ACTIVE_ACK_REQUIRED` | active replay without `--ack-active` while ack is required | 1 |
| `TRANSPORT_UNAVAILABLE` | replay interface unavailable | 2 |
