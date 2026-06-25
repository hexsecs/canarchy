# Test Spec: Fuzz-Replay Culprit Identification

## Document Control

| Field | Value |
|-------|-------|
| Status | Implemented |
| Design doc | `docs/design/fuzz-identify.md` |
| Test file | `tests/test_fuzz_identify.py` |

## Requirement Traceability

| REQ ID | Description summary | TEST IDs |
|--------|--------------------|----------|
| `REQ-FZID-01` | Load + bisect a fuzz log | `TEST-FZID-01`, `TEST-FZID-05` |
| `REQ-FZID-02` | Deterministic narrowing engine | `TEST-FZID-02`, `TEST-FZID-03` |
| `REQ-FZID-03` | Non-interactive observations (flags + file) | `TEST-FZID-06`, `TEST-FZID-08` |
| `REQ-FZID-05` | Active replay of the next window | `TEST-FZID-09` |
| `REQ-FZID-06` | Dry-run / analysis plans without transmit | `TEST-FZID-05`, `TEST-FZID-06` |
| `REQ-FZID-07` | Structured output (candidate/culprit/confidence/provenance) | `TEST-FZID-05`, `TEST-FZID-07` |
| `REQ-FZID-08` | Invalid / missing log errors | `TEST-FZID-04`, `TEST-FZID-12` |
| `REQ-FZID-09` | Invalid observation errors | `TEST-FZID-01b`, `TEST-FZID-04b` |
| `REQ-FZID-10` | `--max-window` guard | `TEST-FZID-11` |
| `REQ-FZID-05` | Active-transmit ack gate | `TEST-FZID-10` |
| `REQ-FZID-11` | MCP exclusion | `test_every_cli_command_is_exposed_or_documented` |

## Test Cases

Unit tests (`tests/test_fuzz_identify.py`):

* `TEST-FZID-01` — `parse_observation` accepts effect/no-effect/bool tokens; `TEST-FZID-01b` rejects an unknown token.
* `TEST-FZID-02` — `narrow` produces the expected candidate range / next window / confidence for the initial state, single-frame logs, and after an effect / no-effect observation, and ignores observations past resolution.
* `TEST-FZID-03` — an oracle drives `narrow` to every frame index for logs of size 1, 2, 5, 8, 17 and recovers exactly that culprit (binary-search correctness).
* `TEST-FZID-04` — loading a missing file and an empty log raise the structured errors; `TEST-FZID-04b` an observations file that is not a JSON array raises `FUZZ_IDENTIFY_INVALID_OBSERVATIONS`.

CLI tests (`tests/test_fuzz_identify.py::FuzzIdentifyCliTest`):

* `TEST-FZID-05` — `fuzz identify <log> --dry-run --json` reports `mode: dry_run`, frame count, and the next window without transmitting.
* `TEST-FZID-06` — `--observe no-effect --observe effect` narrows the candidate range and echoes the observations.
* `TEST-FZID-07` — a full observation sequence resolves the culprit (`mode: resolved`, confidence 1.0, culprit index).
* `TEST-FZID-08` — observations supplied via `--observations FILE`.
* `TEST-FZID-09` — with `--interface` over the scaffold backend the next window is replayed (`mode: active`, `replayed_window`, frame events emitted) after the preflight warning.
* `TEST-FZID-10` — active replay without `--ack-active` while `require_active_ack` is set returns `ACTIVE_ACK_REQUIRED`.
* `TEST-FZID-11` — `--max-window` smaller than the next window returns `FUZZ_IDENTIFY_WINDOW_TOO_LARGE`.
* `TEST-FZID-12` — a non-existent log returns `FUZZ_IDENTIFY_LOG_UNAVAILABLE`.

## Fixtures And Environment

Tests construct candump and JSONL logs in a temp directory; the active-replay
test uses the scaffold transport backend (`CANARCHY_TRANSPORT_BACKEND=scaffold`)
so no live bus is touched. The narrowing engine is exercised purely in-process.

## Explicit Non-Coverage

* Automatic effect detection (observations are operator-supplied).
* Multi-frame ddmin minimisation beyond single-culprit bisection.
